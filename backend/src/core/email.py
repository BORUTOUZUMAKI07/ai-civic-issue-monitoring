"""Outbound email via SMTP.

Gated on config: if ``SMTP_HOST`` is not set this module is a no-op (logs a debug
line). This keeps development, CI, and the test suite free of any real mail
delivery and of any network dependency.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from src.core.config import settings

logger = logging.getLogger("civicpulse")


def smtp_configured() -> bool:
    """True when an SMTP host is configured so we can actually send mail."""
    return bool(settings.SMTP_HOST)


def send_email(subject: str, to: str, text: str) -> bool:
    """Send a plain-text email. Returns True if the message was accepted by the SMTP server.

    Raises no exception: failures are logged and the caller can decide what to surface.
    """
    if not smtp_configured():
        logger.debug("SMTP not configured; skipping email to %s", to)
        return False
    if not to:
        logger.debug("No recipient; skipping email")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER or "no-reply@civicpulse.local"
    msg["To"] = to
    msg.set_content(text)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            if settings.SMTP_USER and settings.SMTP_PASS:
                server.login(settings.SMTP_USER, settings.SMTP_PASS)
            server.send_message(msg)
        logger.info("Email sent to %s (subject=%s)", to, subject)
        return True
    except Exception as exc:  # pragma: no cover - network path
        logger.warning("Failed to send email to %s: %s", to, exc)
        return False
