"""Best-effort redaction of credentials before a log record is rendered.

Why this exists: a token or password logged via ``extra={...}`` otherwise
reaches *every* sink -- the JSON log file, the developer console, and the OTLP
export to New Relic. :class:`SensitiveDataFilter` is a stdlib ``logging.Filter``
attached to each handler, so it scrubs the record **before** any renderer (and
before the OTLP exporter serialises it) sees it, no matter which logger emitted
it.

Deliberately conservative: it redacts by *key name*, never by pattern-matching
free text, so it can never mangle a message or a stack trace. A value under a
key that names a credential is replaced wholesale, recursing into nested
dicts/lists so a secret buried in a payload is caught too.
"""

from __future__ import annotations

import logging
import re
from typing import Any

__all__ = ["REDACTED", "SensitiveDataFilter", "redact_value"]

REDACTED = "***REDACTED***"

# Names that identify a credential, matched on word-ish boundaries so
# ``tokens_used`` (a legitimate counter) is left alone while ``access_token``,
# ``api_key`` and ``password_hash`` are redacted.
_SENSITIVE_KEY_RE = re.compile(
    r"(?:^|[^a-z0-9])"
    r"(?:password|passwd|pwd|secret|token|api[-_]?key|apikey|"
    r"authorization|credentials?|cookie|set[-_]?cookie|"
    r"private[-_]?key|client[-_]?secret|access[-_]?token|refresh[-_]?token|"
    r"session[-_]?id|license[-_]?key|bearer|jwt)"
    r"(?:[^a-z0-9]|$)",
    re.IGNORECASE,
)

# Fields whose names merely contain a sensitive-looking word but carry no
# credential (LLM token accounting). Never redacted, even though e.g.
# ``token_count`` would otherwise match.
_ALLOWED_KEYS = frozenset(
    {
        "token_count",
        "tokens",
        "tokens_used",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "max_tokens",
    }
)

# Every attribute a bare LogRecord already carries. Anything else on the record
# was put there by ``extra=`` and is fair game for redaction.
_STRUCTURAL_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
    "_record",
    "_from_structlog",
}


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _ALLOWED_KEYS:
        return False
    return _SENSITIVE_KEY_RE.search(lowered) is not None


def redact_value(value: Any) -> Any:
    """Recursively scrub credentials from a nested dict/list/tuple value."""
    if isinstance(value, dict):
        return {k: (REDACTED if is_sensitive_key(str(k)) else redact_value(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    return value


class SensitiveDataFilter(logging.Filter):
    """Replace credential values on a ``LogRecord`` before any handler renders it."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in list(record.__dict__.items()):
            if key in _STRUCTURAL_ATTRS:
                continue
            if is_sensitive_key(key):
                record.__dict__[key] = REDACTED
            elif isinstance(value, (dict, list, tuple)):
                record.__dict__[key] = redact_value(value)
        return True
