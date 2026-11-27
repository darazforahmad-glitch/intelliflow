"""Approval reminders and timeouts (REQ-AP-5), run by Celery Beat every minute."""

from __future__ import annotations

from celery import shared_task


@shared_task(name="intelliflow.check_approval_timeouts")
def check_approval_timeouts() -> dict[str, int]:
    from intelliflow.approvals.services import process_timeouts

    reminded, expired = process_timeouts()
    return {"reminded": reminded, "expired": expired}
