from __future__ import annotations

import pytest
from jose import jwt

from src.core.config import settings
from src.core.security import (
    create_access_token,
    create_refresh_token,
    create_ws_ticket,
    decode_token,
)


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


def test_tokens_carry_iat_iss_and_aud() -> None:
    """Every token type names its issuer, audience and mint time.

    The signing key is symmetric, so the signature alone cannot distinguish a
    token minted by this service from one minted by any other system holding
    the same key. ``iss``/``aud`` scope the token; ``iat`` records its age for
    auditing.
    """
    tokens = {
        "access": create_access_token({"sub": "1", "role": "viewer"}),
        "refresh": create_refresh_token({"sub": "1"}),
        "ws": create_ws_ticket(1),
    }
    for name, token in tokens.items():
        decoded = decode_token(token)
        assert decoded["iss"] == settings.JWT_ISSUER, name
        assert decoded["aud"] == settings.JWT_AUDIENCE, name
        assert "iat" in decoded, name


def test_decode_rejects_foreign_audience() -> None:
    """A token signed with the right key but the wrong audience is refused.

    This is the whole point of pinning ``aud``: a sibling service sharing this
    secret must not be able to mint a credential this API will honour.
    """
    forged = jwt.encode(
        {
            "sub": "1",
            "role": "admin",
            "type": "access",
            "iss": settings.JWT_ISSUER,
            "aud": "some-other-service",
            "exp": 9_999_999_999,
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    with pytest.raises(Exception):
        decode_token(forged)


def test_decode_rejects_foreign_issuer() -> None:
    forged = jwt.encode(
        {
            "sub": "1",
            "role": "admin",
            "type": "access",
            "iss": "not-this-service",
            "aud": settings.JWT_AUDIENCE,
            "exp": 9_999_999_999,
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    with pytest.raises(Exception):
        decode_token(forged)
