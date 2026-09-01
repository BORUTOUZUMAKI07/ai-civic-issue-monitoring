from __future__ import annotations

import json
import logging
import math
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.embeddings import generate_embedding
from src.models.issue import Issue

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


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

    stmt = select(Issue).where(Issue.embedding.isnot(None))
    if exclude_issue_id:
        stmt = stmt.where(Issue.id != exclude_issue_id)
    result = await db.execute(stmt)
    issues = result.scalars().all()

    scored = []
    for issue in issues:
        try:
            if not issue.embedding:
                continue
            issue_vec = json.loads(issue.embedding)
            if not isinstance(issue_vec, list) or len(issue_vec) != len(query_embedding):
                continue
            sim = _cosine_similarity(query_embedding, issue_vec)
            if sim >= threshold:
                scored.append((sim, issue))
        except (json.JSONDecodeError, TypeError):
            continue

    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "issue_id": issue.id,
            "issue_type": issue.issue_type.value if hasattr(issue.issue_type, "value") else issue.issue_type,
            "description": issue.description,
            "severity": issue.severity,
            "status": issue.status.value if hasattr(issue.status, "value") else issue.status,
            "latitude": issue.latitude,
            "longitude": issue.longitude,
            "ward_id": issue.ward_id,
            "created_at": issue.created_at.isoformat() if issue.created_at else None,
            "similarity": round(sim, 4),
        }
        for sim, issue in scored[:top_k]
    ]


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

    return [
        {
            "issue_id": issue.id,
            "issue_type": issue.issue_type.value if hasattr(issue.issue_type, "value") else issue.issue_type,
            "description": issue.description,
            "severity": issue.severity,
            "status": issue.status.value if hasattr(issue.status, "value") else issue.status,
            "latitude": issue.latitude,
            "longitude": issue.longitude,
            "ward_id": issue.ward_id,
            "created_at": issue.created_at.isoformat() if issue.created_at else None,
            "similarity": min(0.95, 0.5 + score * 0.1),
        }
        for score, issue in scored[:top_k]
    ]
