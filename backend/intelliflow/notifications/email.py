"""Transactional e-mail through an outbox table and Django's e-mail framework.

Every message is stored in `email_messages`. With the console backend (development)
it is only logged and kept in the outbox, which the dev "inbox" endpoint reads; with
SMTP a Celery task delivers it after the transaction commits.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMessage as DjangoEmail
from django.db import transaction

from intelliflow.core.models import utcnow
from intelliflow.notifications.models import EmailMessage

logger = logging.getLogger(__name__)


def sends_real_email() -> bool:
    return "smtp" in settings.EMAIL_BACKEND


def queue_email(*, to: str, subject: str, body: str, category: str) -> EmailMessage:
    message = EmailMessage(to_address=to, subject=subject, body_text=body, category=category)
    if not sends_real_email():
        message.status = "sent"
        message.sent_at = utcnow()
        message.save()
        logger.info(
            "email queued (console backend)", extra={"category": category, "subject": subject}
        )
        return message
    message.save()
    message_id = str(message.id)

    def _dispatch() -> None:
        from intelliflow.notifications.tasks import send_email

        send_email.delay(message_id)

    transaction.on_commit(_dispatch)
    return message


def deliver(message: EmailMessage) -> None:
    """Deliver one queued message with the configured backend (called by the worker)."""
    DjangoEmail(
        subject=message.subject,
        body=message.body_text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[message.to_address],
    ).send(fail_silently=False)
    message.status = "sent"
    message.sent_at = utcnow()
    message.save(update_fields=["status", "sent_at"])
