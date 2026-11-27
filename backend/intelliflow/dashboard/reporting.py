"""Operations dashboard figures and reports (REQ-DR-1..5)."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce

from intelliflow.approvals.models import ApprovalTask
from intelliflow.automations.models import Automation
from intelliflow.core.enums import ApprovalStatus, AutomationStatus, RunStatus
from intelliflow.core.models import utcnow
from intelliflow.llm.service import credits_used
from intelliflow.runs.models import Run
from intelliflow.workspaces.models import Workspace


def _period(workspace: Workspace, days: int) -> tuple[datetime, datetime, list[date]]:
    tz = ZoneInfo(workspace.timezone)
    today = utcnow().astimezone(tz).date()
    first = today - timedelta(days=days - 1)
    start = datetime.combine(first, time.min, tz)
    return start, utcnow(), [first + timedelta(days=i) for i in range(days)]


def _hours(minutes: Decimal | float | int) -> float:
    return round(float(minutes) / 60, 1)


def dashboard(workspace: Workspace, days: int = 7) -> dict[str, Any]:
    tz = ZoneInfo(workspace.timezone)
    start, end, dates = _period(workspace, days)
    live_runs = Run.objects.filter(workspace=workspace, is_test=False)
    counts: dict[str, int] = {
        row["status"]: row["n"]
        for row in live_runs.filter(created_at__gte=start)
        .order_by()
        .values("status")
        .annotate(n=Count("id"))
    }
    finished = live_runs.filter(status=RunStatus.SUCCEEDED, finished_at__gte=start).values_list(
        "finished_at", "minutes_saved"
    )
    per_day: dict[date, Decimal] = {d: Decimal(0) for d in dates}
    tasks_handled = 0
    for finished_at, minutes in finished:
        if finished_at is None:
            continue
        local_day = finished_at.astimezone(tz).date()
        if local_day in per_day:
            per_day[local_day] += minutes or 0
        if minutes and minutes > 0:
            tasks_handled += 1
    previous_start = start - timedelta(days=days)
    previous_minutes = (
        live_runs.filter(
            status=RunStatus.SUCCEEDED, finished_at__gte=previous_start, finished_at__lt=start
        ).aggregate(total=Coalesce(Sum("minutes_saved"), Decimal(0)))["total"]
        or 0
    )
    minutes_total = sum(per_day.values(), Decimal(0))
    pending = ApprovalTask.objects.filter(
        workspace=workspace, status__in=[ApprovalStatus.PENDING, ApprovalStatus.REMINDED]
    ).count()
    failures = list(live_runs.filter(status=RunStatus.FAILED).order_by("-created_at")[:5])
    automation_names = dict(
        Automation.objects.filter(workspace=workspace).values_list("id", "name")
    )
    total_runs = sum(counts.values())
    active = Automation.objects.filter(workspace=workspace, status=AutomationStatus.ACTIVE).count()
    return {
        "period": {
            "days": days,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timezone": workspace.timezone,
        },
        "kpis": {
            "hours_saved": _hours(minutes_total),
            "hours_saved_previous_period": _hours(previous_minutes),
            "tasks_handled": tasks_handled,
            "runs": total_runs,
            "runs_succeeded": counts.get(RunStatus.SUCCEEDED, 0),
            "runs_failed": counts.get(RunStatus.FAILED, 0),
            "runs_waiting": counts.get(RunStatus.WAITING_APPROVAL, 0),
            "approvals_pending": pending,
            "active_automations": active,
            "success_rate": (
                round(counts.get(RunStatus.SUCCEEDED, 0) / total_runs * 100, 1)
                if total_runs
                else None
            ),
        },
        "hours_saved_per_day": [
            {
                "date": d.strftime("%d/%m/%Y"),
                "iso_date": d.isoformat(),
                "label": d.strftime("%a"),
                "hours": _hours(per_day[d]),
            }
            for d in dates
        ],
        "recent_failures": [
            {
                "run_id": str(r.id),
                "automation_id": str(r.automation_id),
                "automation_name": automation_names.get(r.automation_id, "Automation"),
                "error": r.error,
                "created_at": r.created_at.isoformat(),
            }
            for r in failures
        ],
        "ai_credits": {"used": credits_used(workspace.id), "limit": workspace.ai_credit_limit},
    }


def weekly_csv(workspace: Workspace, days: int = 7) -> str:
    """REQ-DR-5: export of the runs in the period (CSV)."""
    tz = ZoneInfo(workspace.timezone)
    start, _end, _dates = _period(workspace, days)
    rows = [
        (run, run.automation.name)
        for run in Run.objects.select_related("automation")
        .filter(workspace=workspace, is_test=False, created_at__gte=start)
        .order_by("created_at")
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["Date (DD/MM/YYYY)", "Time", "Automation", "Status", "Minutes saved", "Summary / error"]
    )
    for run, name in rows:
        local = run.created_at.astimezone(tz)
        writer.writerow(
            [
                local.strftime("%d/%m/%Y"),
                local.strftime("%H:%M"),
                name,
                str(run.status),
                f"{run.minutes_saved:.1f}",
                run.error or run.summary or "",
            ]
        )
    return buffer.getvalue()
