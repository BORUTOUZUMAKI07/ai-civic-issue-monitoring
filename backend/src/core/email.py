"""Outbound email via SMTP.

Gated on config: if ``SMTP_HOST`` is not set this module is a no-op (logs a debug
line). This keeps development, CI, and the test suite free of any real mail
delivery and of any network dependency.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

import tenacity

from src.core.config import settings

logger = logging.getLogger("civicpulse")


def smtp_configured() -> bool:
    """True when an SMTP host is configured so we can actually send mail."""
    return bool(settings.SMTP_HOST)


# Transient transport failures are worth a retry with backoff; everything else
# (bad credentials, refused recipients, malformed addresses) is not — retrying
# cannot fix it and can trip an SMTP account's lockout policy. `OSError` covers
# `ConnectionRefusedError`/`socket.gaierror`/`TimeoutError`; the SMTP subclasses
# cover a server that dropped the connection mid-session.
_RETRYABLE_SMTP: tuple[type[Exception], ...] = (
    OSError,
    TimeoutError,
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPConnectError,
)


def _send_once(subject: str, to: str, text: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER or "no-reply@civicpulse.local"
    msg["To"] = to
    msg.set_content(text)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        if settings.SMTP_USER and settings.SMTP_PASS:
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
        server.send_message(msg)


@tenacity.retry(
    retry=tenacity.retry_if_exception_type(_RETRYABLE_SMTP),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
    stop=tenacity.stop_after_attempt(3),
    reraise=True,
    before_sleep=tenacity.before_sleep_log(logger, logging.WARNING),
)
def _send_with_retry(subject: str, to: str, text: str) -> None:
    _send_once(subject, to, text)


def send_email(subject: str, to: str, text: str) -> bool:
    """Send a plain-text email. Returns True if the message was accepted by the SMTP server.

    Raises no exception: transient transport failures are retried with
    exponential backoff, the outcome is logged, and the caller decides what to
    surface.
    """
    if not smtp_configured():
        logger.debug("SMTP not configured; skipping email to %s", to)
        return False
    if not to:
        logger.debug("No recipient; skipping email")
        return False

    try:
        _send_with_retry(subject, to, text)
        logger.info("Email sent to %s (subject=%s)", to, subject)
        return True
    except Exception as exc:  # pragma: no cover - network path
        logger.warning("Failed to send email to %s: %s", to, exc)
        return False
