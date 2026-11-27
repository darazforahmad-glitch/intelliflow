"""Workflow engine tasks (Celery). Side effects are idempotent: a run is unique per
(automation, provider event), so a redelivered task never runs an automation twice."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from celery import shared_task

from intelliflow.engine.workflow_engine import WorkflowEngine

logger = logging.getLogger(__name__)


def _schedule_retry(run_id: uuid.UUID, delay: float) -> None:
    execute_run.apply_async((str(run_id),), countdown=max(1, int(delay)))


@shared_task(name="intelliflow.execute_run")
def execute_run(run_id: str) -> str:
    run = WorkflowEngine(scheduler=_schedule_retry).execute(uuid.UUID(run_id))
    return str(run.status)


@shared_task(
    name="intelliflow.process_whatsapp_event", bind=True, max_retries=5, default_retry_delay=10
)
def process_whatsapp_event(self: Any, event: dict[str, Any]) -> int:
    from intelliflow.runs.event_router import process_whatsapp_event as route

    try:
        return len(route(event))
    except Exception as exc:  # database blips: retry, the run unique key keeps this idempotent
        logger.exception("whatsapp event processing failed")
        raise self.retry(exc=exc) from exc


@shared_task(name="intelliflow.process_trigger")
def process_trigger(
    workspace_id: str,
    trigger_type: str,
    event_id: str,
    trigger: dict[str, Any],
    automation_ids: list[str] | None = None,
) -> int:
    from intelliflow.runs.event_router import route_trigger

    runs = route_trigger(
        workspace_id=uuid.UUID(workspace_id),
        trigger_type=trigger_type,
        event_id=event_id,
        trigger=trigger,
        automation_ids=[uuid.UUID(a) for a in automation_ids] if automation_ids else None,
    )
    return len(runs)


@shared_task(name="intelliflow.run_scheduled_automations")
def run_scheduled_automations() -> int:
    from intelliflow.runs.scheduler import fire_due_schedules

    return fire_due_schedules()
