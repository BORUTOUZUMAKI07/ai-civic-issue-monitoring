from __future__ import annotations

import pytest

from src.core.security import create_access_token, decode_token


def test_create_and_decode_token() -> None:
    payload = {"sub": "1", "role": "field_worker"}
    token = create_access_token(payload)
    decoded = decode_token(token)
    assert decoded["sub"] == "1"
    assert decoded["role"] == "field_worker"
    assert "exp" in decoded


def test_decode_invalid_token() -> None:
    with pytest.raises(Exception):
        decode_token("invalid.token.here")


def test_token_has_expiry() -> None:
    token = create_access_token({"sub": "1"})
    decoded = decode_token(token)
    assert "exp" in decoded
