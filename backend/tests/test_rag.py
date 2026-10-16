from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core.config import settings
from src.rag.context import build_rag_context
from src.rag.retrieval import (
    RetrievalWeights,
    _cosine_similarity,
    _recency_component,
    _rerank_weighted,
    weighted_score,
)


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        a = [1.0, 2.0, 3.0]
        assert _cosine_similarity(a, a) == pytest_approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest_approx(0.0)

    def test_opposite_vectors(self) -> None:
        assert _cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest_approx(-1.0)

    def test_zero_vector_returns_zero(self) -> None:
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
        assert _cosine_similarity([1.0, 0.0], [0.0, 0.0]) == 0.0

    def test_partial_similarity_between_zero_and_one(self) -> None:
        p = _cosine_similarity([1.0, 0.0], [1.0, 1.0])
        assert 0.0 < p < 1.0
        diff = pytest_approx(1.0 / (2**0.5))
        assert p == diff

    def test_high_dimensional_mixed(self) -> None:
        a = [1.0, 2.0, 3.0, 4.0]
        b = [1.0, 0.0, 3.0, 2.0]
        sim = _cosine_similarity(a, b)
        assert -1.0 <= sim <= 1.0
        assert sim > 0.0


class TestBuildRagContext:
    def test_current_issue_heading_present(self) -> None:
        ctx = build_rag_context({"issue_type": "pothole", "description": "big hole", "severity": 3}, [])
        assert "## Current Issue" in ctx
        assert "pothole" in ctx
        assert "big hole" in ctx
        assert "3" in ctx

    def test_no_similar_issues_message(self) -> None:
        ctx = build_rag_context({"issue_type": "garbage", "description": "pile", "severity": 2}, [])
        assert "No similar historical issues found." in ctx

    def test_with_similar_issues_lists_them(self) -> None:
        similar = [
            {
                "issue_type": "pothole",
                "description": "another pothole",
                "severity": 4,
                "status": "resolved",
                "similarity": 0.9,
            }
        ]
        ctx = build_rag_context(
            {"issue_type": "pothole", "description": "big hole", "severity": 3},
            similar,
        )
        assert "## Similar Historical Issues (1 found)" in ctx
        assert "pothole" in ctx
        assert "resolved" in ctx
        assert "90%" in ctx

    def test_historical_pattern_summary(self) -> None:
        similar = [
            {"issue_type": "pothole", "description": "a", "severity": 4, "status": "resolved", "similarity": 0.9},
            {"issue_type": "pothole", "description": "b", "severity": 3, "status": "in_progress", "similarity": 0.7},
        ]
        ctx = build_rag_context(
            {"issue_type": "pothole", "description": "big hole", "severity": 3},
            similar,
        )
        assert "1/2 similar issues resolved" in ctx
        assert "0.80" in ctx

    def test_description_truncated_to_120_chars(self) -> None:
        long_desc = "x" * 500
        similar = [
            {"issue_type": "pothole", "description": long_desc, "severity": 3, "status": "resolved", "similarity": 0.8}
        ]
        ctx = build_rag_context(
            {"issue_type": "pothole", "description": "big hole", "severity": 3},
            similar,
        )
        assert ("x" * 500) not in ctx
        # 120 chars kept, quoted
        assert f'"{("x"*120)}"' in ctx


def pytest_approx(value: float):
    import pytest

    return pytest.approx(value)


class TestRecencyComponent:
    def test_brand_new_is_one(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert _recency_component(now, now, 30.0) == pytest_approx(1.0)

    def test_one_half_life_is_half(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        created = now - timedelta(days=30)
        assert _recency_component(created, now, 30.0) == pytest_approx(0.5)

    def test_two_half_lives_is_quarter(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        created = now - timedelta(days=60)
        assert _recency_component(created, now, 30.0) == pytest_approx(0.25)

    def test_naive_datetime_is_treated_as_utc(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        created = datetime(2026, 1, 1)  # naive
        assert _recency_component(created, now, 30.0) == pytest_approx(1.0)

    def test_none_is_zero(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert _recency_component(None, now, 30.0) == 0.0


class TestWeightedScore:
    NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def _score(self, similarity, weights, severity=3, status="reported", days_old=0):
        return weighted_score(
            similarity,
            severity=severity,
            status=status,
            created_at=self.NOW - timedelta(days=days_old),
            now=self.NOW,
            weights=weights,
            half_life_days=30.0,
        )

    def test_similarity_only_matches_input(self) -> None:
        w = RetrievalWeights(similarity=1.0, recency=0.0, severity=0.0, resolution=0.0)
        assert self._score(0.42, w) == pytest_approx(0.42)

    def test_recency_only_prefers_newer(self) -> None:
        w = RetrievalWeights(similarity=0.0, recency=1.0, severity=0.0, resolution=0.0)
        new = self._score(0.5, w, days_old=0)
        old = self._score(0.5, w, days_old=30)
        assert new > old
        assert new == pytest_approx(1.0)

    def test_severity_only_prefers_severe(self) -> None:
        w = RetrievalWeights(similarity=0.0, recency=0.0, severity=1.0, resolution=0.0)
        high = self._score(0.5, w, severity=5)
        low = self._score(0.5, w, severity=1)
        assert high > low
        assert low == pytest_approx(0.0)

    def test_resolution_only_prefers_resolved(self) -> None:
        w = RetrievalWeights(similarity=0.0, recency=0.0, severity=0.0, resolution=1.0)
        resolved = self._score(0.5, w, status="resolved")
        open_issue = self._score(0.5, w, status="reported")
        assert resolved == pytest_approx(1.0)
        assert open_issue == pytest_approx(0.0)

    def test_verified_counts_as_resolved(self) -> None:
        w = RetrievalWeights(similarity=0.0, recency=0.0, severity=0.0, resolution=1.0)
        assert self._score(0.5, w, status="verified") == pytest_approx(1.0)

    def test_all_zero_weights_falls_back_to_similarity(self) -> None:
        w = RetrievalWeights(similarity=0.0, recency=0.0, severity=0.0, resolution=0.0)
        assert self._score(0.37, w) == pytest_approx(0.37)

    def test_score_is_bounded(self) -> None:
        w = RetrievalWeights()
        assert 0.0 <= self._score(2.0, w, severity=9, status="resolved", days_old=0) <= 1.0

    def test_weights_are_normalized_by_sum(self) -> None:
        # Doubling every weight must not change the blended result.
        one = self._score(0.6, RetrievalWeights(0.3, 0.2, 0.25, 0.25), days_old=10)
        two = self._score(0.6, RetrievalWeights(0.6, 0.4, 0.5, 0.5), days_old=10)
        assert one == pytest_approx(two)


class TestRerankWeighted:
    NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

    class _FakeIssue:
        def __init__(self, severity: int, status: str, created_at: datetime) -> None:
            self.severity = severity
            self.status = status
            self.created_at = created_at

    def test_recency_weight_reorders_lower_similarity_newer_first(self) -> None:
        old = self._FakeIssue(3, "reported", self.NOW - timedelta(days=365))
        new = self._FakeIssue(3, "reported", self.NOW)
        ranked = [(0.9, old), (0.8, new)]

        result = _rerank_weighted(
            ranked,
            weights=RetrievalWeights(similarity=0.0, recency=1.0, severity=0.0, resolution=0.0),
            half_life_days=30.0,
            now=self.NOW,
        )

        assert result[0][1] is new
        assert result[1][1] is old

    def test_similarity_only_keeps_order(self) -> None:
        a = self._FakeIssue(3, "reported", self.NOW)
        b = self._FakeIssue(3, "reported", self.NOW)
        ranked = [(0.9, a), (0.8, b)]

        result = _rerank_weighted(
            ranked,
            weights=RetrievalWeights(similarity=1.0, recency=0.0, severity=0.0, resolution=0.0),
            half_life_days=30.0,
            now=self.NOW,
        )

        assert [pair[1] for pair in result] == [a, b]


class TestConfigurableContextSize:
    def test_context_uses_configured_limit(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "RAG_MAX_CONTEXT_ISSUES", 2)
        similar = [
            {"issue_type": "pothole", "description": f"desc-{i}", "severity": 3, "status": "reported", "similarity": 0.8}
            for i in range(5)
        ]
        ctx = build_rag_context({"issue_type": "pothole", "description": "q", "severity": 3}, similar)
        assert "## Similar Historical Issues (2 found)" in ctx
        assert "desc-0" in ctx
        assert "desc-1" in ctx
        assert "desc-2" not in ctx
        assert "Historical pattern: 0/2 similar issues resolved" in ctx

    def test_limit_of_zero_is_clamped_to_one(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "RAG_MAX_CONTEXT_ISSUES", 0)
        similar = [
            {"issue_type": "pothole", "description": f"desc-{i}", "severity": 3, "status": "reported", "similarity": 0.8}
            for i in range(3)
        ]
        ctx = build_rag_context({"issue_type": "pothole", "description": "q", "severity": 3}, similar)
        assert "## Similar Historical Issues (1 found)" in ctx
        assert "desc-0" in ctx
        assert "desc-1" not in ctx
