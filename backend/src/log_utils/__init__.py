"""
Structured logging built on structlog.

Two halves with clearly separate jobs:

* **stdlib ``logging`` owns transport.** Every call site keeps using plain
  ``logging.getLogger(...)`` and ``logger.info("... %s", x, extra={...})``, and
  the console + file handlers installed by :func:`setup_logging` deliver them.
  Nothing outside this module had to change.
* **structlog owns rendering and context.** It turns a record into JSON
  (production, and always in the log file) or a readable console line
  (development), and merges in whatever is bound to the *contextvars* context.

This replaced ``python-json-logger``, which could only flatten the fields of
the one record it was handed. The upgrade that actually matters is
:mod:`structlog.contextvars`: :class:`src.middleware.logging.LoggingMiddleware`
binds ``correlation_id`` once per request, so every log line emitted anywhere
during that request carries it automatically -- including the ~30 modules that
call ``logging.getLogger(__name__)`` directly and never passed
``extra={"correlation_id": ...}`` themselves.

Handlers are installed on the **root** logger rather than on ``civicpulse``
alone. Call sites are split between ``get_logger()`` (which namespaces under
``civicpulse.``) and bare ``logging.getLogger(__name__)`` (which namespaces
under ``src.``); attaching only to ``civicpulse`` silently dropped the latter
to Python's last-resort handler, so most of the codebase's INFO logs never
reached the JSON file at all.

Every handler also carries the shared
:class:`src.log_utils.redaction.SensitiveDataFilter`, so a credential logged via
``extra={...}`` is scrubbed before the JSON file, the console and the OTLP
export render it.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import structlog

from src.core.config import settings
from src.log_utils.redaction import SensitiveDataFilter

__all__ = ["setup_logging", "get_logger", "log_request_start", "log_request_end"]

# Marks the handlers this module owns, so setup_logging() can replace them
# idempotently without ripping out handlers pytest or uvicorn installed on the
# root logger (those would otherwise be cleared on every app lifespan).
_HANDLER_MARKER = "_civicpulse_handler"

# One shared instance attached to every handler (console, file, OTLP). Attached
# per handler rather than per logger so it runs for records from any logger that
# propagates to the root, and before each handler formats/exports the record.
_SENSITIVE_FILTER = SensitiveDataFilter()

# Once the root logger is wired up these libraries become chatty. WARNING
# keeps genuine failures visible without burying application logs.
_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "urllib3",
    "asyncio",
    "sqlalchemy.engine",
    "multipart",
    "PIL",
)


# Every attribute a LogRecord always carries. Anything else sitting on the
# record was put there by `extra=` and is a field the caller wants rendered.
_STANDARD_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
    "_record",
    "_from_structlog",
}


def _merge_record_extras(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Recover ``extra={...}`` fields from a stdlib ``LogRecord``.

    ``ProcessorFormatter`` forwards only the message, level and timestamp by
    default, whereas the ``python-json-logger`` setup this replaced included
    them -- so without this, ``http_status_code`` and ``duration_ms`` on the
    request logs would silently vanish. ``setdefault`` means a value already
    bound to the contextvars context (correlation_id, user_id) still wins.
    """
    record = event_dict.get("_record")
    if record is None:
        return event_dict
    for key, value in record.__dict__.items():
        if key in _STANDARD_RECORD_ATTRS:
            continue
        event_dict.setdefault(key, value)
    return event_dict


def _enrich(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Stamp the constant service metadata onto every rendered event.

    Runs for structlog-native records and, via ``foreign_pre_chain``, for plain
    stdlib records -- which is every record this application produces.
    """
    event_dict.setdefault("service", settings.PROJECT_NAME)
    event_dict.setdefault("environment", settings.ENVIRONMENT)
    event_dict.setdefault("version", settings.VERSION)
    return event_dict


def _pre_chain() -> list[Any]:
    """Processors applied to every record before it reaches a renderer."""
    return [
        # `extra={...}` off the LogRecord; must run before anything reads them.
        _merge_record_extras,
        # Whatever the request scope bound (correlation_id, user_id, ...).
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        _enrich,
        structlog.processors.StackInfoRenderer(),
        # Flattens `exc_info` into a formatted traceback under `exception`.
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
    ]


def _formatter(renderer: Any, pre_chain: list[Any]) -> logging.Formatter:
    return structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=pre_chain,
    )


def setup_logging(correlation_id: str | None = None) -> logging.Logger:
    """Configure structlog and install the console + file handlers.

    Idempotent: calling it twice (reloader, repeated TestClient lifespans)
    swaps our handlers rather than duplicating them, and leaves handlers other
    tools installed untouched.
    """
    is_prod = settings.ENVIRONMENT == "production"
    log_level = logging.INFO if is_prod else logging.DEBUG

    pre_chain = _pre_chain()
    structlog.configure(
        processors=pre_chain + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Production and the on-disk log are always machine-readable; only the
    # developer console is allowed to be pretty.
    json_renderer = structlog.processors.JSONRenderer()
    console_renderer = json_renderer if is_prod else structlog.dev.ConsoleRenderer()

    root = logging.getLogger()
    root.setLevel(log_level)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Drop only handlers from a previous call; anything pytest or uvicorn put
    # on the root logger stays where it is.
    for existing in list(root.handlers):
        if getattr(existing, _HANDLER_MARKER, False):
            root.removeHandler(existing)
            existing.close()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(_formatter(console_renderer, pre_chain))
    console_handler.addFilter(_SENSITIVE_FILTER)
    setattr(console_handler, _HANDLER_MARKER, True)
    root.addHandler(console_handler)

    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(filename=log_dir / "civicpulse.log", encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(_formatter(json_renderer, pre_chain))
    file_handler.addFilter(_SENSITIVE_FILTER)
    setattr(file_handler, _HANDLER_MARKER, True)
    root.addHandler(file_handler)

    # Layer-1 -> Layer-2: when NEW_RELIC_ENABLED, forward every rendered line
    # to the OpenTelemetry collector over OTLP/HTTP (it owns the New Relic
    # key). Fail-open -- an unconfigured or broken export must never break
    # logging.
    if settings.NEW_RELIC_ENABLED:
        try:
            from src.core.observability import setup_otlp_log_handler

            otlp_handler = setup_otlp_log_handler(log_level)
            # Redact before the exporter serialises the record, so a credential
            # in `extra={...}` never leaves the process either.
            if otlp_handler is not None and _SENSITIVE_FILTER not in otlp_handler.filters:
                otlp_handler.addFilter(_SENSITIVE_FILTER)
        except Exception as exc:  # noqa: BLE001 - fail-open seam
            logging.getLogger("civicpulse").warning("OTLP log handler setup failed: %s", exc)

    # Kept for callers that still pass one; correlation also flows through
    # contextvars, which is what reaches the modules that never pass it.
    if correlation_id:
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

    return logging.getLogger("civicpulse")


def get_logger(name: str = "civicpulse") -> logging.Logger:
    if name != "civicpulse" and not name.startswith("civicpulse."):
        name = f"civicpulse.{name}"
    return logging.getLogger(name)


def log_request_start(logger: logging.Logger, method: str, path: str, correlation_id: str) -> None:
    logger.info(
        "Request started: %s %s",
        method,
        path,
        extra={
            "correlation_id": correlation_id,
            # structlog reserves `event` for the log message itself, so the
            # machine-readable tag lives under `event_type`.
            "event_type": "request_start",
            "http_method": method,
            "http_path": path,
        },
    )


def log_request_end(
    logger: logging.Logger, method: str, path: str, status_code: int, duration_ms: float, correlation_id: str
) -> None:
    logger.info(
        "Request completed: %s %s -> %s (%.2fms)",
        method,
        path,
        status_code,
        duration_ms,
        extra={
            "correlation_id": correlation_id,
            "event_type": "request_end",
            "http_method": method,
            "http_path": path,
            "http_status_code": status_code,
            "duration_ms": duration_ms,
        },
    )
