"""Routes trigger events to the active automations that listen for them (REQ-WE-1..3)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors import customer_window
from app.core.transaction import on_commit
from app.engine.workflow_engine import WorkflowEngine
from app.models import Automation, Connection, Run, Workspace
from app.models.enums import AutomationStatus, ConnectionProvider, ConnectionStatus, WorkspaceStatus

logger = logging.getLogger(__name__)


def trigger_filters_match(trigger_spec: dict[str, Any], payload: dict[str, Any]) -> bool:
    filters = trigger_spec.get("filters") or {}
    if (types := filters.get("message_types")) and payload.get("type") not in types:
        return False
    if (needle := filters.get("from_contains")) and needle.lower() not in str(
        payload.get("from", "")
    ).lower():
        return False
    if (needle := filters.get("subject_contains")) and needle.lower() not in str(
        payload.get("subject", "")
    ).lower():
        return False
    return not ((form := filters.get("form_name")) and form != payload.get("form_name"))


def enqueue_run(db: Session, run_id: uuid.UUID) -> None:
    def _dispatch() -> None:
        from app.worker.tasks import execute_run

        execute_run.delay(str(run_id))

    on_commit(db, _dispatch)


def route_trigger(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    trigger_type: str,
    event_id: str,
    trigger: dict[str, Any],
    automation_ids: list[uuid.UUID] | None = None,
) -> list[Run]:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None or workspace.status != WorkspaceStatus.ACTIVE:
        return []
    stmt = select(Automation).where(
        Automation.workspace_id == workspace_id,
        Automation.status == AutomationStatus.ACTIVE,
        Automation.trigger_type == trigger_type,
    )
    if automation_ids is not None:
        stmt = stmt.where(Automation.id.in_(automation_ids))
    engine = WorkflowEngine(db)
    runs: list[Run] = []
    for automation in db.scalars(stmt):
        if automation.current_version is None:
            continue
        if not trigger_filters_match(
            automation.current_version.definition_json.get("trigger", {}), trigger
        ):
            continue
        run = engine.create_run(
            automation, event_id=event_id, trigger_type=trigger_type, trigger=trigger
        )
        if run is not None:
            runs.append(run)
            enqueue_run(db, run.id)
    db.commit()
    return runs


def whatsapp_connections(db: Session, phone_number_id: str) -> list[Connection]:
    candidates = db.scalars(
        select(Connection).where(
            Connection.provider == ConnectionProvider.WHATSAPP,
            Connection.status == ConnectionStatus.CONNECTED,
        )
    ).all()
    return [
        c
        for c in candidates
        if str((c.config_json or {}).get("phone_number_id")) == str(phone_number_id)
    ]


def process_whatsapp_event(db: Session, event: dict[str, Any]) -> list[Run]:
    """Worker side of Algorithm 5.4: one inbound WhatsApp message -> runs."""
    runs: list[Run] = []
    trigger = event["trigger"]
    for connection in whatsapp_connections(db, str(event.get("phone_number_id"))):
        if trigger.get("from"):
            try:
                at = (
                    datetime.fromisoformat(trigger["timestamp"])
                    if trigger.get("timestamp")
                    else datetime.now(UTC)
                )
            except ValueError:
                at = datetime.now(UTC)
            customer_window.mark_inbound(connection.workspace_id, str(trigger["from"]), at)
        runs += route_trigger(
            db,
            workspace_id=connection.workspace_id,
            trigger_type="whatsapp.message_received",
            event_id=str(event["event_id"]),
            trigger=trigger,
        )
    return runs
