"""Property-based tests for the pure helpers that ride the critical path.

These cover the functions where exhaustive examples are impractical but the
invariants are simple and load-bearing: lexical scoring, rank fusion, the
retrieval metrics, and the request fingerprint that guards idempotent uploads.

Skipped (not failed) when ``hypothesis`` is absent, so the suite still runs in a
lean environment.
"""
from __future__ import annotations

import math

import pytest

pytest.importorskip("hypothesis")

from hypothesis import given, settings, strategies as st  # noqa: E402

from src.domains.issues.idempotency import hash_request  # noqa: E402
from src.ml.evaluation import metrics  # noqa: E402
from src.rag.retrieval import (  # noqa: E402
    _bm25_scores,
    _cosine_similarity,
    _reciprocal_rank_fusion,
    _tokenize,
)

FAST = settings(max_examples=50, deadline=None)

_words = st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=8)
_docs = st.lists(_words, min_size=1, max_size=6)


# ─────────────────────────────────────────────────────────────────────────────
# Tokenizer
# ─────────────────────────────────────────────────────────────────────────────

@given(st.text(max_size=200))
@FAST
def test_tokenize_invariants(text: str) -> None:
    tokens = _tokenize(text)
    assert all(t == t.lower() for t in tokens)
    assert all(len(t) > 1 for t in tokens)
    assert all(t.isalnum() for t in tokens)


# ─────────────────────────────────────────────────────────────────────────────
# BM25
# ─────────────────────────────────────────────────────────────────────────────

@given(docs=st.lists(st.text(max_size=40), min_size=1, max_size=8), query=st.text(max_size=20))
@FAST
def test_bm25_shape_and_non_negative(docs: list[str], query: str) -> None:
    scores = _bm25_scores(docs, query)
    assert len(scores) == len(docs)
    assert all(s >= 0.0 and math.isfinite(s) for s in scores)


@given(st.text(max_size=30))
@FAST
def test_bm25_empty_corpus_is_empty(query: str) -> None:
    assert _bm25_scores([], query) == []


@given(
    target=st.text(alphabet="abcdefghij", min_size=3, max_size=6),
    others=st.lists(st.text(alphabet="klmnopqrst", min_size=3, max_size=6), min_size=1, max_size=4),
)
@FAST
def test_bm25_rewards_term_overlap(target: str, others: list[str]) -> None:
    # A document containing the query term must outscore documents that cannot.
    docs = [target] + others
    scores = _bm25_scores(docs, target)
    assert scores[0] == max(scores)


@given(docs=st.lists(_words, min_size=1, max_size=5))
@FAST
def test_bm25_no_overlap_scores_zero(docs: list[str]) -> None:
    # Query uses letters that cannot appear in the docs' alphabet.
    assert all(s == 0.0 for s in _bm25_scores(docs, "zzz"))


# ─────────────────────────────────────────────────────────────────────────────
# Reciprocal Rank Fusion
# ─────────────────────────────────────────────────────────────────────────────

@given(rankings=st.lists(st.lists(st.integers(min_value=0, max_value=20), max_size=10), max_size=4))
@FAST
def test_rrf_matches_definition(rankings: list[list[int]]) -> None:
    fused = _reciprocal_rank_fusion(rankings)
    expected: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            expected[doc_id] = expected.get(doc_id, 0.0) + 1.0 / (60 + rank + 1)
    assert set(fused) == set(expected)
    assert all(math.isclose(fused[k], expected[k]) for k in fused)


@given(rankings=st.lists(st.lists(st.integers(min_value=0, max_value=20), min_size=1, max_size=8), max_size=4))
@FAST
def test_rrf_scores_positive(rankings: list[list[int]]) -> None:
    assert all(score > 0.0 for score in _reciprocal_rank_fusion(rankings).values())


# ─────────────────────────────────────────────────────────────────────────────
# Retrieval metrics
# ─────────────────────────────────────────────────────────────────────────────

@given(ranked=st.lists(st.booleans(), max_size=20), k=st.integers(min_value=0, max_value=25))
@FAST
def test_precision_at_k_bounds(ranked: list[bool], k: int) -> None:
    assert 0.0 <= metrics.precision_at_k(ranked, k) <= 1.0


@given(ranked=st.lists(st.booleans(), max_size=20))
@FAST
def test_reciprocal_rank_bounds(ranked: list[bool]) -> None:
    rr = metrics.reciprocal_rank(ranked)
    assert 0.0 <= rr <= 1.0
    if any(ranked):
        assert rr == pytest.approx(1.0 / (ranked.index(True) + 1))
    else:
        assert rr == 0.0


@given(ranked=st.lists(st.booleans(), max_size=20), k=st.integers(min_value=0, max_value=25))
@FAST
def test_ndcg_bounds_and_ideal(ranked: list[bool], k: int) -> None:
    assert 0.0 <= metrics.ndcg_at_k(ranked, k) <= 1.0
    # With at least one relevant hit and k >= 1, putting the hits first is the
    # ideal ranking -> nDCG == 1. The degenerate cases (no hits, or k == 0)
    # have no ideal to normalise against and are covered by the bounds above.
    if k > 0 and any(ranked):
        ideal = [True] * sum(ranked) + [False] * (len(ranked) - sum(ranked))
        assert metrics.ndcg_at_k(ideal, k) == pytest.approx(1.0)


@given(
    y_true=st.lists(st.sampled_from(["pothole", "garbage", "debris"]), max_size=30),
    y_pred=st.lists(st.sampled_from(["pothole", "garbage", "debris"]), max_size=30),
)
@FAST
def test_macro_f1_bounds(y_true: list[str], y_pred: list[str]) -> None:
    # Unequal lengths are tolerated by zip; metric must still be in [0, 1].
    f1 = metrics.macro_f1(y_true, y_pred, ("pothole", "garbage", "debris"))
    assert 0.0 <= f1 <= 1.0


@given(values=st.lists(st.integers(min_value=0, max_value=5), min_size=1, max_size=10))
@FAST
def test_mae_zero_when_perfect(values: list[int]) -> None:
    assert metrics.mean_absolute_error(values, values) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Cosine similarity
# ─────────────────────────────────────────────────────────────────────────────

@given(
    a=st.lists(st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False), min_size=1, max_size=8),
    b=st.lists(st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False), min_size=1, max_size=8),
)
@FAST
def test_cosine_similarity_bounds_and_symmetry(a: list[float], b: list[float]) -> None:
    sim = _cosine_similarity(a, b)
    assert -1.0 - 1e-6 <= sim <= 1.0 + 1e-6
    if len(a) == len(b):
        assert sim == pytest.approx(_cosine_similarity(b, a), abs=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# Idempotency request fingerprint
# ─────────────────────────────────────────────────────────────────────────────

@given(
    user_id=st.integers(min_value=1, max_value=10**9),
    lat=st.floats(min_value=-90, max_value=90, allow_nan=False, allow_infinity=False),
    lon=st.floats(min_value=-180, max_value=180, allow_nan=False, allow_infinity=False),
    description=st.text(max_size=200),
    force=st.booleans(),
    filename=st.text(max_size=30),
    content=st.binary(max_size=200),
)
@FAST
def test_hash_request_is_deterministic(
    user_id: int, lat: float, lon: float, description: str, force: bool, filename: str, content: bytes
) -> None:
    kwargs = dict(
        user_id=user_id,
        latitude=lat,
        longitude=lon,
        description=description,
        force_submit=force,
        filename=filename,
        content=content,
    )
    digest = hash_request(**kwargs)
    assert digest == hash_request(**kwargs)
    assert len(digest) == 64
    # Any change to the image bytes must change the fingerprint.
    assert digest != hash_request(**{**kwargs, "content": content + b"\x00"})
