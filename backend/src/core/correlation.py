"""Shared correlation-ID normalization.

Correlation IDs join browser, BFF, backend and OTLP telemetry into one trace.
The only value we ever accept from a caller is a canonical UUID; anything else
is replaced with a freshly generated UUID so arbitrary text never reaches
structured logs. Keeping this rule in one place lets the HTTP middleware and the
browser-error intake apply identical validation.
"""

from __future__ import annotations

import uuid


def normalize_correlation_id(supplied: str | None) -> str:
    """Return a canonical UUID for ``supplied``, or a new UUID if it is invalid.

    ``uuid.UUID(...).str`` canonicalises case and braces, so both upper-case and
    braced UUIDs are accepted while their logged form stays stable.
    """
    value = (supplied or "").strip()
    if value:
        try:
            return str(uuid.UUID(value))
        except (ValueError, AttributeError, TypeError):
            pass
    return str(uuid.uuid4())
