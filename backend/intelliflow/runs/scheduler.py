"""Fires schedule.daily / schedule.interval automations (Celery Beat calls this every minute)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from intelliflow.automations.models import Automation
from intelliflow.core.enums import AutomationStatus
from intelliflow.runs.event_router import route_trigger

DAILY_GRACE = timedelta(minutes=10)


def fire_due_schedules(now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    fired = 0
    automations = Automation.objects.select_related("current_version", "workspace").filter(
        status=AutomationStatus.ACTIVE, trigger_type__in=["schedule.daily", "schedule.interval"]
    )
    for automation in automations:
        if automation.current_version is None:
            continue
        trigger = automation.current_version.definition_json["trigger"]
        workspace = automation.workspace
        local = now.astimezone(ZoneInfo(workspace.timezone))
        if trigger["type"] == "schedule.daily":
            hour, minute = (int(p) for p in trigger["at"].split(":"))
            due = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if not (due <= local < due + DAILY_GRACE):
                continue
            event_id = f"schedule:{due.date().isoformat()}"
            scheduled_for = due.isoformat()
        else:
            every = int(trigger["every_minutes"]) * 60
            slot = int(now.timestamp()) // every
            event_id = f"schedule:{slot}"
            scheduled_for = datetime.fromtimestamp(slot * every, UTC).isoformat()
        runs = route_trigger(
            workspace_id=automation.workspace_id,
            trigger_type=trigger["type"],
            event_id=event_id,
            trigger={"scheduled_for": scheduled_for},
            automation_ids=[automation.id],
        )
        fired += len(runs)
    return fired
