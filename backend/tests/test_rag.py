from __future__ import annotations

from src.rag.context import build_rag_context
from src.rag.retrieval import _cosine_similarity


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
