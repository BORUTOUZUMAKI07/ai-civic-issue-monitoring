"""Shared outbound LLM client with timeout and retry.

One :class:`openai.AsyncOpenAI` client per process (created lazily on first
use) instead of a fresh client per request: the SDK pools connections, applies
its own bounded retry budget per ``max_retries``, and enforces the per-request
timeout configured here. On top of the SDK's retries, a tenacity wrapper adds
exponential backoff for the transient failure classes (connection errors,
timeouts, rate limits, 5xx), so one upstream blip does not turn every
concurrent request into an immediate fallback at the same millisecond.

``chat_completion_retryable`` reraises the last error once its budget is
exhausted; every caller in this codebase has a deterministic non-LLM fallback
(the keyword classifier, the embedding keyword fallback), so fail-open is the
caller's decision, not a silent default here.
"""

from __future__ import annotations

import logging
from typing import Any

import tenacity
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, InternalServerError, RateLimitError

from src.core.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    """Return the process-wide :class:`AsyncOpenAI` client, creating it on first use."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            # The classifier guards on OPENAI_API_KEY before ever calling this,
            # so a real key is normally present. The placeholder keeps client
            # construction itself from raising when a key is genuinely missing.
            api_key=settings.OPENAI_API_KEY or "unset",
            base_url=settings.OPENAI_BASE_URL,
            timeout=settings.OPENAI_TIMEOUT_SECONDS,
            max_retries=settings.OPENAI_MAX_RETRIES,
        )
    return _client


# The openai package ships no type information (see the mypy overrides in
# backend/pyproject.toml), so the exception classes are `Any`; the annotation
# is what tenacity needs to match against.
_RETRYABLE: tuple[type[Exception], ...] = (
    APIConnectionError,  # type: ignore[arg-type]
    APITimeoutError,  # type: ignore[arg-type]
    RateLimitError,  # type: ignore[arg-type]
    InternalServerError,  # type: ignore[arg-type]
)


@tenacity.retry(
    retry=tenacity.retry_if_exception_type(_RETRYABLE),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=10),
    stop=tenacity.stop_after_attempt(3),
    reraise=True,
    before_sleep=tenacity.before_sleep_log(logger, logging.WARNING),
)
async def chat_completion_retryable(**kwargs: Any) -> Any:
    """Call ``chat.completions.create`` with timeout, SDK retries, and backoff.

    Raises the last error after exhausting the retry budget; callers fall back
    to their deterministic keyword path.
    """
    return await get_openai_client().chat.completions.create(**kwargs)
