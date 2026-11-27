"""Routes trigger events to the active automations that listen for them (REQ-WE-1..3)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from django.db import transaction

from intelliflow.integrations.connectors import customer_window
from intelliflow.engine.workflow_engine import WorkflowEngine
from intelliflow.automations.models import Automation
from intelliflow.integrations.models import Connection
from intelliflow.runs.models import Run
from intelliflow.workspaces.models import Workspace
from intelliflow.core.enums import (
    AutomationStatus,
    ConnectionProvider,
    ConnectionStatus,
    WorkspaceStatus,
)

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


def enqueue_run(run_id: uuid.UUID) -> None:
    """Queue the run for a worker once the transaction that created it has committed."""

    def _dispatch() -> None:
        from intelliflow.runs.tasks import execute_run

        execute_run.delay(str(run_id))

    transaction.on_commit(_dispatch)


@transaction.atomic
def route_trigger(
    *,
    workspace_id: uuid.UUID,
    trigger_type: str,
    event_id: str,
    trigger: dict[str, Any],
    automation_ids: list[uuid.UUID] | None = None,
) -> list[Run]:
    workspace = Workspace.objects.filter(pk=workspace_id).first()
    if workspace is None or workspace.status != WorkspaceStatus.ACTIVE:
        return []
    automations = Automation.objects.select_related("current_version", "workspace").filter(
        workspace_id=workspace_id, status=AutomationStatus.ACTIVE, trigger_type=trigger_type
    )
    if automation_ids is not None:
        automations = automations.filter(id__in=automation_ids)
    engine = WorkflowEngine()
    runs: list[Run] = []
    for automation in automations:
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
            enqueue_run(run.id)
    return runs


def whatsapp_connections(phone_number_id: str) -> list[Connection]:
    candidates = Connection.objects.filter(
        provider=ConnectionProvider.WHATSAPP, status=ConnectionStatus.CONNECTED
    )
    return [
        c
        for c in candidates
        if str((c.config_json or {}).get("phone_number_id")) == str(phone_number_id)
    ]


def process_whatsapp_event(event: dict[str, Any]) -> list[Run]:
    """Worker side of Algorithm 5.4: one inbound WhatsApp message -> runs."""
    runs: list[Run] = []
    trigger = event["trigger"]
    for connection in whatsapp_connections(str(event.get("phone_number_id"))):
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
            workspace_id=connection.workspace_id,
            trigger_type="whatsapp.message_received",
            event_id=str(event["event_id"]),
            trigger=trigger,
        )
    return runs
