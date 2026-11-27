"""Connection health: Gmail polling and OAuth token refresh (REQ-IN-6)."""

from __future__ import annotations

from celery import shared_task


@shared_task(name="intelliflow.poll_gmail")
def poll_gmail() -> int:
    from intelliflow.integrations.services import poll_gmail_connections

    return poll_gmail_connections()


@shared_task(name="intelliflow.refresh_expiring_tokens")
def refresh_expiring_tokens() -> int:
    from intelliflow.integrations.services import refresh_expiring_tokens as refresh

    return refresh()
