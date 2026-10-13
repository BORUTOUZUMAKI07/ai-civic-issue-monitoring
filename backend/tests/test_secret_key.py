"""SECRET_KEY hygiene tests.

The validator in ``src/core/config.py`` is what makes a guessable ``SECRET_KEY``
a hard startup error instead of a JWT forgery oracle, so it gets its own
regression suite. Every placeholder value that has ever shipped in an example
file, compose default, CI job, or git history must be rejected — in any
environment, not just production.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config import SECRET_KEY_MIN_LENGTH, Settings, WEAK_SECRET_KEYS

# Every weak value this repo has ever carried or documented lives in
# src.core.config.WEAK_SECRET_KEYS; importing it keeps the test honest against
# the validator instead of maintaining a second copy here.
_WEAK_VALUES = tuple(sorted(WEAK_SECRET_KEYS))


@pytest.mark.parametrize("weak_value", _WEAK_VALUES)
def test_known_placeholder_secret_key_is_rejected(weak_value: str) -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        Settings(SECRET_KEY=weak_value)


def test_empty_secret_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(SECRET_KEY="")


def test_short_secret_key_is_rejected() -> None:
    with pytest.raises(ValidationError, match=f"at least {SECRET_KEY_MIN_LENGTH}"):
        Settings(SECRET_KEY="a" * (SECRET_KEY_MIN_LENGTH - 1))


def test_short_placeholder_past_the_denylist_is_rejected_by_length() -> None:
    # Not on the denylist, but far too short to be a real secret.
    with pytest.raises(ValidationError, match=f"at least {SECRET_KEY_MIN_LENGTH}"):
        Settings(SECRET_KEY="shorter-than-min-length")


def test_long_random_secret_key_is_accepted() -> None:
    key = "a" * 64
    assert Settings(SECRET_KEY=key).SECRET_KEY == key
