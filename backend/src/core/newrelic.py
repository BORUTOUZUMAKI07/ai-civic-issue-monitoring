"""New Relic Python APM agent integration.

The agent is only initialized when a real license key is present in the
environment (``NEW_RELIC_LICENSE_KEY``). Without a key this module is a
no-op, so development, CI, and the test suite are completely unaffected
(no telemetry, no collector connection, no performance overhead).

The ``newrelic`` import and the config file exist in the environment, but
``initialize`` is deliberately never called without a key. This keeps the
platform production-safe and free of synthetic/placeholder data.
"""

from __future__ import annotations

import logging
import os

from src.core.config import settings

logger = logging.getLogger("civicpulse")

_ENABLED = False


def newrelic_enabled() -> bool:
    """True when a real New Relic license key is configured."""
    return bool(settings.NEW_RELIC_LICENSE_KEY or os.getenv("NEW_RELIC_LICENSE_KEY"))


def init_newrelic() -> bool:
    """Initialize the New Relic agent. Returns True if the agent started."""
    global _ENABLED
    if _ENABLED:
        return True

    if not newrelic_enabled():
        logger.debug("New Relic disabled: no license key configured")
        return False

    try:
        import newrelic.agent

        config_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "newrelic.ini")
        if not os.path.exists(config_file):
            config_file = os.path.join(os.getcwd(), "newrelic.ini")

        newrelic.agent.initialize(config_file)
        app_name = settings.NEW_RELIC_APP_NAME or "CivicPulse-API"
        newrelic.agent.global_settings().app_name = app_name
        _ENABLED = True
        logger.info("New Relic APM agent initialized (app=%s)", app_name)
        return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("New Relic agent failed to initialize: %s", exc)
        return False


def record_custom_event(event_type: str, params: dict) -> None:
    """Record a custom event with the agent (no-op when disabled)."""
    if not _ENABLED:
        return
    try:
        import newrelic.agent

        newrelic.agent.record_custom_event(event_type, params)
    except Exception:  # pragma: no cover - defensive
        pass


def add_custom_attribute(key: str, value) -> None:
    """Attach a custom attribute to the current transaction (no-op when disabled)."""
    if not _ENABLED:
        return
    try:
        import newrelic.agent

        newrelic.agent.add_custom_attribute(key, value)
    except Exception:  # pragma: no cover - defensive
        pass
