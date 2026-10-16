"""Unit tests for key-based log redaction (src/log_utils/redaction.py).

The contract that matters: a credential logged via ``extra={...}`` is replaced
before any handler renders it, while ordinary fields — including token-count
metrics — pass through untouched.
"""
from __future__ import annotations

import logging

from src.log_utils.redaction import REDACTED, SensitiveDataFilter, redact_value


def _filtered(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="civicpulse.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="event",
        args=(),
        exc_info=None,
    )
    record.__dict__.update(extra)
    SensitiveDataFilter().filter(record)
    return record


def test_common_credential_keys_are_redacted() -> None:
    record = _filtered(
        password="hunter2",
        access_token="eyJhbGci",
        api_key="sk-live",
        client_secret="shh",
        authorization="Bearer xyz",
        cookie="session=1",
    )
    for key in ("password", "access_token", "api_key", "client_secret", "authorization", "cookie"):
        assert getattr(record, key) == REDACTED


def test_benign_fields_are_untouched() -> None:
    record = _filtered(
        user_id=42,
        http_status_code=200,
        duration_ms=12.5,
        tokens_used=1536,
        token_count=10,
        total_tokens=2048,
        event_type="request_end",
    )
    assert record.user_id == 42
    assert record.http_status_code == 200
    assert record.duration_ms == 12.5
    assert record.tokens_used == 1536
    assert record.token_count == 10
    assert record.total_tokens == 2048
    assert record.event_type == "request_end"


def test_standard_record_fields_are_never_redacted() -> None:
    record = _filtered()
    # `msg`/`name`/`levelname` are structural; redaction must not corrupt them.
    assert record.msg == "event"
    assert record.name == "civicpulse.test"
    assert record.levelname == "INFO"


def test_nested_credentials_are_redacted() -> None:
    value = {
        "user": "ada",
        "context": {"password": "hunter2", "api_key": "sk-live"},
        "headers": [{"authorization": "Bearer xyz"}, {"accept": "application/json"}],
    }
    cleaned = redact_value(value)
    assert cleaned["user"] == "ada"
    assert cleaned["context"]["password"] == REDACTED
    assert cleaned["context"]["api_key"] == REDACTED
    assert cleaned["headers"][0]["authorization"] == REDACTED
    assert cleaned["headers"][1]["accept"] == "application/json"


def test_sensitive_container_key_is_redacted_wholesale() -> None:
    # A key that itself names a credential redacts its whole value -- including
    # a nested dict -- rather than trying to recurse into it.
    record = _filtered(credentials={"password": "hunter2"})
    assert record.credentials == REDACTED


def test_nested_dict_on_record_is_redacted_in_place() -> None:
    record = _filtered(payload={"token": "abc", "keep": "me"})
    assert record.payload == {"token": REDACTED, "keep": "me"}
