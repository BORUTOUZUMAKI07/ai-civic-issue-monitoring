from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.embeddings import generate_embedding
from src.domains.issues.models.issue import Issue

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _tokenize(text: str) -> list[str]:
    return [t for t in _WORD_RE.findall(text.lower()) if len(t) > 1]


def _bm25_scores(docs: list[str], query: str, k1: float = 1.5, b: float = 0.75) -> list[float]:
    """Okapi BM25 lexical score of each document against the query.

    IDF is computed over the in-memory corpus — the same set the vector scan
    already loads — so hybrid retrieval needs no inverted index and no extra
    dependency. Pure function: no I/O, which is what makes it testable.
    """
    tokenized = [_tokenize(d) for d in docs]
    n = len(tokenized)
    if n == 0:
        return []

    avgdl = sum(len(toks) for toks in tokenized) / n or 1.0

    df: dict[str, int] = {}
    for toks in tokenized:
        for term in set(toks):
            df[term] = df.get(term, 0) + 1

    query_terms = _tokenize(query)
    scores: list[float] = []
    for toks in tokenized:
        tf: dict[str, int] = {}
        for term in toks:
            tf[term] = tf.get(term, 0) + 1
        dl = len(toks) or 1
        score = 0.0
        for term in query_terms:
            freq = tf.get(term, 0)
            if not freq:
                continue
            doc_freq = df.get(term, 0)
            idf = math.log(1 + (n - doc_freq + 0.5) / (doc_freq + 0.5))
            score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / avgdl))
        scores.append(score)
    return scores


def _reciprocal_rank_fusion(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    """Reciprocal Rank Fusion of several ranked id lists → id → fused score.

    RRF combines rank positions rather than raw scores, so it fuses cosine
    similarity (0..1) and BM25 (unbounded) without having to normalise either —
    which is exactly the mismatch that makes naive score-summing hybrid search
    unreliable.
    """
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return fused


def _issue_result(issue: Issue, similarity: float) -> dict:
    return {
        "issue_id": issue.id,
        "issue_type": issue.issue_type.value if hasattr(issue.issue_type, "value") else issue.issue_type,
        "description": issue.description,
        "severity": issue.severity,
        "status": issue.status.value if hasattr(issue.status, "value") else issue.status,
        "latitude": issue.latitude,
        "longitude": issue.longitude,
        "ward_id": issue.ward_id,
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
        "similarity": round(similarity, 4),
    }


# A historical issue counts as "resolved" for the resolution component of the
# weighted re-ranker when it reached one of these terminal states. `verified`
# means an admin confirmed the fix, so it is at least as strong a signal as a
# plain `resolved`.
RESOLVED_STATUSES = frozenset({"resolved", "verified"})


@dataclass(frozen=True)
class RetrievalWeights:
    """Relative importance of each signal in the weighted re-ranker.

    Values are normalized by their sum at scoring time, so they need not add to
    exactly 1.0. Set one to 0 to drop that signal entirely.
    """

    similarity: float = 0.3
    recency: float = 0.2
    severity: float = 0.25
    resolution: float = 0.25


def _status_value(status: object) -> str:
    return status.value if hasattr(status, "value") else str(status)


def _recency_component(created_at: Optional[datetime], now: datetime, half_life_days: float) -> float:
    """Exponential decay in (0, 1]: 1.0 for a brand-new issue, 0.5 at one half-life."""
    if created_at is None:
        return 0.0
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
    if half_life_days <= 0:
        return 1.0
    return float(0.5 ** (age_days / half_life_days))


def weighted_score(
    similarity: float,
    *,
    severity: Optional[int],
    status: object,
    created_at: Optional[datetime],
    now: datetime,
    weights: RetrievalWeights,
    half_life_days: float = 30.0,
) -> float:
    """Blend the four retrieval signals into a single score in [0, 1].

    Pure function (no I/O, no globals): the caller passes ``now`` and the weights
    so the harness and the tests can pin them.
    """
    components = (
        (weights.similarity, max(0.0, min(1.0, similarity))),
        (weights.recency, _recency_component(created_at, now, half_life_days)),
        (weights.severity, max(0.0, min(1.0, ((severity or 1) - 1) / 4.0))),
        (weights.resolution, 1.0 if _status_value(status) in RESOLVED_STATUSES else 0.0),
    )
    total_weight = sum(weight for weight, _ in components)
    if total_weight <= 0:
        # Every weight is zero — fall back to similarity rather than dividing by 0.
        return max(0.0, min(1.0, similarity))
    return sum(weight * value for weight, value in components) / total_weight


def _weights_from_settings() -> RetrievalWeights:
    return RetrievalWeights(
        similarity=settings.RAG_SIMILARITY_WEIGHT,
        recency=settings.RAG_RECENCY_WEIGHT,
        severity=settings.RAG_SEVERITY_WEIGHT,
        resolution=settings.RAG_RESOLUTION_WEIGHT,
    )


def _rerank_weighted(
    ranked: list[tuple[float, Issue]],
    *,
    weights: RetrievalWeights,
    half_life_days: float,
    now: Optional[datetime] = None,
) -> list[tuple[float, Issue]]:
    """Reorder ``(similarity, Issue)`` pairs by :func:`weighted_score`."""
    reference = now or datetime.now(timezone.utc)
    return sorted(
        ranked,
        key=lambda pair: weighted_score(
            pair[0],
            severity=pair[1].severity,
            status=pair[1].status,
            created_at=pair[1].created_at,
            now=reference,
            weights=weights,
            half_life_days=half_life_days,
        ),
        reverse=True,
    )


async def _load_candidates(db: AsyncSession, exclude_issue_id: Optional[int]) -> list[Issue]:
    if settings.RETRIEVAL_HYBRID:
        # Lexical fusion needs every description, embedding or not.
        stmt = select(Issue)
    else:
        stmt = select(Issue).where(Issue.embedding.isnot(None))
    if exclude_issue_id:
        stmt = stmt.where(Issue.id != exclude_issue_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _rank_by_vector(issues: list[Issue], query_embedding: list[float]) -> list[tuple[float, Issue]]:
    ranked: list[tuple[float, Issue]] = []
    for issue in issues:
        if not issue.embedding:
            continue
        try:
            issue_vec = json.loads(issue.embedding)
            if not isinstance(issue_vec, list) or len(issue_vec) != len(query_embedding):
                continue
            ranked.append((_cosine_similarity(query_embedding, issue_vec), issue))
        except (json.JSONDecodeError, TypeError):
            continue
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked


async def find_similar_issues(
    db: AsyncSession,
    query_text: str,
    top_k: Optional[int] = None,
    threshold: Optional[float] = None,
    exclude_issue_id: Optional[int] = None,
) -> list[dict]:
    top_k = top_k or settings.RAG_TOP_K
    threshold = threshold or settings.RAG_SIMILARITY_THRESHOLD

    try:
        query_embedding = await generate_embedding(query_text)
    except Exception as e:
        logger.warning("Embedding generation failed, falling back to keyword search: %s", e)
        return await _keyword_fallback(db, query_text, top_k, exclude_issue_id)

    if query_embedding is None:
        return await _keyword_fallback(db, query_text, top_k, exclude_issue_id)

    issues = await _load_candidates(db, exclude_issue_id)
    vector_ranked = _rank_by_vector(issues, query_embedding)

    # Hybrid (opt-in via RETRIEVAL_HYBRID): fuse the dense ranking with a
    # lexical BM25 ranking over the same corpus. Default remains pure vector so
    # this changes no behaviour until it is measured better — see
    # scripts/evaluate_ml.py --retrieval.
    if settings.RETRIEVAL_HYBRID and issues:
        bm25 = _bm25_scores([issue.description or "" for issue in issues], query_text)
        lexical_ranked = sorted(
            ((score, issues[idx]) for idx, score in enumerate(bm25) if score > 0),
            key=lambda x: x[0],
            reverse=True,
        )
        fused = _reciprocal_rank_fusion(
            [
                [issue.id for _, issue in vector_ranked],
                [issue.id for _, issue in lexical_ranked],
            ]
        )
        sim_by_id = {issue.id: sim for sim, issue in vector_ranked}
        ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        issue_by_id = {issue.id: issue for issue in issues}
        return [_issue_result(issue_by_id[iid], sim_by_id.get(iid, 0.0)) for iid, _ in ordered if iid in issue_by_id]

    # Weighted re-ranking (opt-in) reorders the candidates that already pass the
    # similarity threshold below; the threshold itself stays on raw cosine so the
    # eligible set is identical and only the ordering changes. Mutually exclusive
    # with the hybrid path above, which returns early.
    if settings.RAG_WEIGHTED_RERANK:
        vector_ranked = _rerank_weighted(
            vector_ranked,
            weights=_weights_from_settings(),
            half_life_days=settings.RAG_RECENCY_HALF_LIFE_DAYS,
        )

    return [_issue_result(issue, sim) for sim, issue in vector_ranked if sim >= threshold][:top_k]


async def _keyword_fallback(
    db: AsyncSession,
    query_text: str,
    top_k: int,
    exclude_issue_id: Optional[int],
) -> list[dict]:
    stmt = select(Issue).where(Issue.description.isnot(None))
    if exclude_issue_id:
        stmt = stmt.where(Issue.id != exclude_issue_id)

    result = await db.execute(stmt.limit(100))
    issues = result.scalars().all()

    query_lower = query_text.lower()
    scored = []
    for issue in issues:
        desc = (issue.description or "").lower()
        words = set(query_lower.split())
        desc_words = set(desc.split())
        overlap = len(words & desc_words)
        if overlap > 0:
            scored.append((overlap, issue))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [_issue_result(issue, min(0.95, 0.5 + score * 0.1)) for score, issue in scored[:top_k]]
