"""Tests for RAG-assisted classification (the ``rag_context`` wiring).

Covers the three behaviours that matter:
* flag off → a preclassified category is trusted, the LLM is never called;
* flag on + low gate confidence + context → the LLM is consulted *with* the
  context and its answer wins;
* flag on + confident gate → the LLM is still skipped;
* the LLM prompt actually contains the retrieved history.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.agents.classifier import _openai_classify, classify_issue
from src.core.config import settings


@pytest.fixture(autouse=True)
def _restore_settings() -> Any:
    original = (settings.RAG_CLASSIFY_ENABLED, settings.RAG_CLASSIFY_MIN_CONFIDENCE)
    yield
    settings.RAG_CLASSIFY_ENABLED, settings.RAG_CLASSIFY_MIN_CONFIDENCE = original


async def test_preclassified_trusted_when_rag_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RAG_CLASSIFY_ENABLED", False)
    llm = AsyncMock(return_value=("garbage", 3, 0.9))
    monkeypatch.setattr("src.agents.classifier._openai_classify", llm)

    result = await classify_issue(
        {
            "description": "big pothole",
            "category": "pothole",
            "category_confidence": 0.3,
            "rag_context": "## Similar Historical Issues (1 found)",
        }
    )

    assert result["result"]["classification_source"] == "preclassified"
    assert result["category"] == "pothole"
    assert result["result"]["rag_context_used"] is False
    llm.assert_not_awaited()


async def test_low_confidence_consults_llm_with_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RAG_CLASSIFY_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_CLASSIFY_MIN_CONFIDENCE", 0.6)
    llm = AsyncMock(return_value=("garbage", 3, 0.9))
    monkeypatch.setattr("src.agents.classifier._openai_classify", llm)

    result = await classify_issue(
        {
            "description": "overflowing bin",
            "category": "pothole",
            "category_confidence": 0.3,
            "rag_context": "HISTORY",
        }
    )

    assert result["result"]["classification_source"] == "openai+rag"
    assert result["category"] == "garbage"
    assert result["result"]["rag_context_used"] is True
    llm.assert_awaited_once()
    # The context is forwarded as the second positional argument.
    assert llm.await_args.args[1] == "HISTORY"


async def test_confident_gate_skips_llm_even_with_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RAG_CLASSIFY_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_CLASSIFY_MIN_CONFIDENCE", 0.6)
    llm = AsyncMock(return_value=("garbage", 3, 0.9))
    monkeypatch.setattr("src.agents.classifier._openai_classify", llm)

    result = await classify_issue(
        {
            "description": "clear pothole",
            "category": "pothole",
            "category_confidence": 0.95,
            "rag_context": "HISTORY",
        }
    )

    assert result["result"]["classification_source"] == "preclassified"
    llm.assert_not_awaited()


async def test_llm_failure_falls_back_to_preclassified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RAG_CLASSIFY_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_CLASSIFY_MIN_CONFIDENCE", 0.6)
    monkeypatch.setattr("src.agents.classifier._openai_classify", AsyncMock(return_value=None))

    result = await classify_issue(
        {
            "description": "overflowing bin",
            "category": "pothole",
            "category_confidence": 0.3,
            "rag_context": "HISTORY",
        }
    )

    assert result["result"]["classification_source"] == "preclassified"
    assert result["category"] == "pothole"


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Message(content)


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [_Choice(content)]


async def test_prompt_includes_retrieved_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    captured: dict[str, Any] = {}

    async def fake_chat(**kwargs: Any) -> _Response:
        captured.update(kwargs)
        return _Response('{"category": "garbage", "severity": 3, "confidence": 0.8, "reasoning": "x"}')

    monkeypatch.setattr("src.agents.classifier.chat_completion_retryable", fake_chat)

    out = await _openai_classify("overflowing bin", "## Similar Historical Issues (1 found)\n1. [garbage] ...")

    assert out == ("garbage", 3, 0.8)
    prompt = captured["messages"][0]["content"]
    assert "Similar Historical Issues" in prompt
    assert "overflowing bin" in prompt


async def test_prompt_has_no_history_block_when_no_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    captured: dict[str, Any] = {}

    async def fake_chat(**kwargs: Any) -> _Response:
        captured.update(kwargs)
        return _Response('{"category": "pothole", "severity": 4, "confidence": 0.8, "reasoning": "x"}')

    monkeypatch.setattr("src.agents.classifier.chat_completion_retryable", fake_chat)

    await _openai_classify("deep pothole", "")

    prompt = captured["messages"][0]["content"]
    assert "historical issues" not in prompt.lower()
