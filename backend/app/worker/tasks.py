"""Celery tasks. Each task opens its own session; side effects are idempotent."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select

from app.core.database import new_session, session_scope
from app.engine.workflow_engine import WorkflowEngine
from app.models import EmailMessage, Workspace
from app.models.base import utcnow
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _schedule_retry(run_id: uuid.UUID, delay: float) -> None:
    execute_run.apply_async((str(run_id),), countdown=max(1, int(delay)))


@celery_app.task(name="intelliflow.execute_run")
def execute_run(run_id: str) -> str:
    db = new_session()
    try:
        run = WorkflowEngine(db, scheduler=_schedule_retry).execute(uuid.UUID(run_id))
        return run.status.value
    finally:
        db.close()


@celery_app.task(
    name="intelliflow.process_whatsapp_event", bind=True, max_retries=5, default_retry_delay=10
)
def process_whatsapp_event(self: Any, event: dict[str, Any]) -> int:
    from app.services.event_router import process_whatsapp_event as route

    try:
        with session_scope() as db:
            return len(route(db, event))
    except Exception as exc:  # database blips: retry, the run unique key keeps this idempotent
        logger.exception("whatsapp event processing failed")
        raise self.retry(exc=exc) from exc


@celery_app.task(name="intelliflow.process_trigger")
def process_trigger(
    workspace_id: str,
    trigger_type: str,
    event_id: str,
    trigger: dict[str, Any],
    automation_ids: list[str] | None = None,
) -> int:
    from app.services.event_router import route_trigger

    with session_scope() as db:
        runs = route_trigger(
            db,
            workspace_id=uuid.UUID(workspace_id),
            trigger_type=trigger_type,
            event_id=event_id,
            trigger=trigger,
            automation_ids=[uuid.UUID(a) for a in automation_ids] if automation_ids else None,
        )
        return len(runs)


@celery_app.task(name="intelliflow.send_email", bind=True, max_retries=5, default_retry_delay=30)
def send_email(self: Any, message_id: str) -> str:
    from app.services.email_service import deliver

    with session_scope() as db:
        message = db.get(EmailMessage, uuid.UUID(message_id))
        if message is None or message.status == "sent":
            return "skipped"
        try:
            deliver(message)
        except Exception as exc:
            message.error = str(exc)[:500]
            if self.request.retries >= self.max_retries:
                message.status = "failed"
                return "failed"
            raise self.retry(exc=exc) from exc
        return "sent"


@celery_app.task(name="intelliflow.send_push")
def send_push(user_id: str, payload: str) -> int:
    from app.services.notification_service import send_web_push

    with session_scope() as db:
        return send_web_push(db, uuid.UUID(user_id), payload)


@celery_app.task(name="intelliflow.check_approval_timeouts")
def check_approval_timeouts() -> dict[str, int]:
    from app.services.approval_service import process_timeouts

    db = new_session()
    try:
        reminded, expired = process_timeouts(db)
        return {"reminded": reminded, "expired": expired}
    finally:
        db.close()


@celery_app.task(name="intelliflow.run_scheduled_automations")
def run_scheduled_automations() -> int:
    from app.services.scheduler_service import fire_due_schedules

    with session_scope() as db:
        return fire_due_schedules(db)


@celery_app.task(name="intelliflow.poll_gmail")
def poll_gmail() -> int:
    from app.services.connection_service import poll_gmail_connections

    with session_scope() as db:
        return poll_gmail_connections(db)


@celery_app.task(name="intelliflow.refresh_expiring_tokens")
def refresh_expiring_tokens() -> int:
    from app.services.connection_service import refresh_expiring_tokens as refresh

    with session_scope() as db:
        return refresh(db)


@celery_app.task(name="intelliflow.purge_deleted_workspaces")
def purge_deleted_workspaces() -> int:
    """BR-7: a deleted workspace's data is permanently removed within 30 days."""
    with session_scope() as db:
        cutoff = utcnow() - timedelta(days=30)
        ids = db.scalars(
            select(Workspace.id).where(
                Workspace.deleted_at.is_not(None), Workspace.deleted_at < cutoff
            )
        ).all()
        if ids:
            db.execute(delete(Workspace).where(Workspace.id.in_(ids)))
        return len(ids)
