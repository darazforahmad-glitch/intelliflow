"""Operations dashboard figures and reports (REQ-DR-1..5)."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ApprovalTask, Automation, Run, Workspace
from app.models.base import utcnow
from app.models.enums import ApprovalStatus, AutomationStatus, RunStatus
from app.services.ai_service import credits_used


def _period(workspace: Workspace, days: int) -> tuple[datetime, datetime, list[date]]:
    tz = ZoneInfo(workspace.timezone)
    today = utcnow().astimezone(tz).date()
    first = today - timedelta(days=days - 1)
    start = datetime.combine(first, time.min, tz)
    return start, utcnow(), [first + timedelta(days=i) for i in range(days)]


def _hours(minutes: Decimal | float | int) -> float:
    return round(float(minutes) / 60, 1)


def dashboard(db: Session, workspace: Workspace, days: int = 7) -> dict[str, Any]:
    tz = ZoneInfo(workspace.timezone)
    start, end, dates = _period(workspace, days)
    base = select(Run).where(Run.workspace_id == workspace.id, Run.is_test.is_(False))
    counts = dict(
        db.execute(
            select(Run.status, func.count(Run.id))
            .where(
                Run.workspace_id == workspace.id, Run.is_test.is_(False), Run.created_at >= start
            )
            .group_by(Run.status)
        )
        .tuples()
        .all()
    )
    finished = db.execute(
        select(Run.finished_at, Run.minutes_saved).where(
            Run.workspace_id == workspace.id,
            Run.is_test.is_(False),
            Run.status == RunStatus.SUCCEEDED,
            Run.finished_at >= start,
        )
    ).all()
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
        db.scalar(
            select(func.coalesce(func.sum(Run.minutes_saved), 0)).where(
                Run.workspace_id == workspace.id,
                Run.is_test.is_(False),
                Run.status == RunStatus.SUCCEEDED,
                Run.finished_at >= previous_start,
                Run.finished_at < start,
            )
        )
        or 0
    )
    minutes_total = sum(per_day.values(), Decimal(0))
    pending = (
        db.scalar(
            select(func.count(ApprovalTask.id)).where(
                ApprovalTask.workspace_id == workspace.id,
                ApprovalTask.status.in_([ApprovalStatus.PENDING, ApprovalStatus.REMINDED]),
            )
        )
        or 0
    )
    failures = db.scalars(
        base.where(Run.status == RunStatus.FAILED).order_by(Run.created_at.desc()).limit(5)
    ).all()
    automation_names = dict(
        db.execute(
            select(Automation.id, Automation.name).where(Automation.workspace_id == workspace.id)
        )
        .tuples()
        .all()
    )
    total_runs = sum(counts.values())
    active = (
        db.scalar(
            select(func.count(Automation.id)).where(
                Automation.workspace_id == workspace.id,
                Automation.status == AutomationStatus.ACTIVE,
            )
        )
        or 0
    )
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
        "ai_credits": {"used": credits_used(db, workspace.id), "limit": workspace.ai_credit_limit},
    }


def weekly_csv(db: Session, workspace: Workspace, days: int = 7) -> str:
    """REQ-DR-5: export of the runs in the period (CSV)."""
    tz = ZoneInfo(workspace.timezone)
    start, _end, _dates = _period(workspace, days)
    rows = db.execute(
        select(Run, Automation.name)
        .join(Automation, Automation.id == Run.automation_id)
        .where(Run.workspace_id == workspace.id, Run.is_test.is_(False), Run.created_at >= start)
        .order_by(Run.created_at)
    ).all()
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
                run.status.value,
                f"{run.minutes_saved:.1f}",
                run.error or run.summary or "",
            ]
        )
    return buffer.getvalue()
