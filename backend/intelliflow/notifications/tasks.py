"""Delivery tasks for e-mail (SMTP) and Web Push."""

from __future__ import annotations

from typing import Any

from celery import shared_task

from intelliflow.notifications.models import EmailMessage


@shared_task(name="intelliflow.send_email", bind=True, max_retries=5, default_retry_delay=30)
def send_email(self: Any, message_id: str) -> str:
    from intelliflow.notifications.email import deliver

    message = EmailMessage.objects.filter(pk=message_id).first()
    if message is None or message.status == "sent":
        return "skipped"
    try:
        deliver(message)
    except Exception as exc:
        message.error = str(exc)[:500]
        if self.request.retries >= self.max_retries:
            message.status = "failed"
            message.save(update_fields=["error", "status"])
            return "failed"
        message.save(update_fields=["error"])
        raise self.retry(exc=exc) from exc
    return "sent"


@shared_task(name="intelliflow.send_push")
def send_push(user_id: str, payload: str) -> int:
    from intelliflow.notifications.services import send_web_push

    return send_web_push(user_id, payload)
