"""
Structured logging setup with JSON format and correlation ID support.
"""

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pythonjsonlogger import jsonlogger

from src.core.config import settings


class CorrelationIdFilter(logging.Filter):
    def __init__(self, correlation_id: Optional[str] = None):
        super().__init__()
        self.correlation_id = correlation_id

    def filter(self, record):
        if not hasattr(record, "correlation_id"):
            record.correlation_id = self.correlation_id or "no-correlation-id"
        return True


class JSONFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["timestamp"] = datetime.now(timezone.utc).isoformat()
        log_record["service"] = settings.PROJECT_NAME
        log_record["environment"] = settings.ENVIRONMENT
        log_record["version"] = settings.VERSION
        if hasattr(record, "correlation_id"):
            log_record["correlation_id"] = record.correlation_id
        for attr in ("trace_id", "span_id", "user_id", "issue_id"):
            if hasattr(record, attr):
                log_record[attr] = getattr(record, attr)


def setup_logging(correlation_id: Optional[str] = None):
    logger = logging.getLogger("civicpulse")
    is_prod = settings.ENVIRONMENT == "production"
    log_level = logging.INFO if is_prod else logging.DEBUG
    logger.setLevel(log_level)
    logger.handlers.clear()

    formatter = JSONFormatter(fmt="%(timestamp)s %(level)s %(name)s %(message)s", timestamp=True)
    correlation_filter: logging.Filter = CorrelationIdFilter(correlation_id)

    prod_filter = None
    if is_prod:

        class ProdFilter(logging.Filter):
            def filter(self, record):
                return record.levelno >= logging.INFO

        prod_filter = ProdFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(correlation_filter)
    if prod_filter:
        console_handler.addFilter(prod_filter)
    logger.addHandler(console_handler)

    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "civicpulse.log"
    file_handler = logging.FileHandler(filename=log_file, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(correlation_filter)
    if prod_filter:
        file_handler.addFilter(prod_filter)
    logger.addHandler(file_handler)

    logger.addFilter(correlation_filter)
    return logger


def get_logger(name: str = "civicpulse") -> logging.Logger:
    if name != "civicpulse" and not name.startswith("civicpulse."):
        name = f"civicpulse.{name}"
    return logging.getLogger(name)


def log_request_start(logger: logging.Logger, method: str, path: str, correlation_id: str):
    logger.info(
        f"Request started: {method} {path}",
        extra={"correlation_id": correlation_id, "event": "request_start", "http_method": method, "http_path": path},
    )


def log_request_end(
    logger: logging.Logger, method: str, path: str, status_code: int, duration_ms: float, correlation_id: str
):
    logger.info(
        f"Request completed: {method} {path} -> {status_code} ({duration_ms:.2f}ms)",
        extra={
            "correlation_id": correlation_id,
            "event": "request_end",
            "http_method": method,
            "http_path": path,
            "http_status_code": status_code,
            "duration_ms": duration_ms,
        },
    )


__all__ = ["setup_logging", "get_logger", "log_request_start", "log_request_end"]
