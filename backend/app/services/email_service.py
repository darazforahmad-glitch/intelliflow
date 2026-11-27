"""Transactional e-mail via an outbox table. `console` logs (dev); `smtp` delivers over TLS."""

from __future__ import annotations

import logging
import smtplib
import ssl
import uuid
from email.message import EmailMessage as MIMEMessage

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.transaction import on_commit
from app.models import EmailMessage
from app.models.base import utcnow

logger = logging.getLogger(__name__)


def queue_email(db: Session, *, to: str, subject: str, body: str, category: str) -> EmailMessage:
    message = EmailMessage(
        id=uuid.uuid4(), to_address=to, subject=subject, body_text=body, category=category
    )
    db.add(message)
    settings = get_settings()
    if settings.email_backend == "console":
        message.status = "sent"
        message.sent_at = utcnow()
        logger.info(
            "email queued (console backend)", extra={"category": category, "subject": subject}
        )
    else:
        message_id = message.id

        def _dispatch() -> None:
            from app.worker.tasks import send_email

            send_email.delay(str(message_id))

        on_commit(db, _dispatch)
    return message


def deliver(message: EmailMessage) -> None:
    """Deliver one queued message over SMTP with STARTTLS (called by the worker)."""
    settings = get_settings()
    if not settings.smtp_host:
        raise RuntimeError("SMTP_HOST is not configured")
    mime = MIMEMessage()
    mime["From"] = settings.email_from
    mime["To"] = message.to_address
    mime["Subject"] = message.subject
    mime.set_content(message.body_text)
    context = ssl.create_default_context()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls(context=context)
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(mime)
    message.status = "sent"
    message.sent_at = utcnow()
