"""/workspaces/{id}/runs and /approvals: run history with drill-down (REQ-DR-4) and the
approvals queue (UC-11)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DB, WorkspaceMember
from app.core.errors import NotFoundError
from app.models import ApprovalTask, Automation, AutomationVersion, Run, StepRun, User
from app.models.enums import ApprovalStatus, RunStatus
from app.schemas.run import ApprovalBrief, ApprovalOut, DecisionIn, RunDetailOut, RunOut, StepRunOut
from app.services import approval_service

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["runs and approvals"])


def run_out(db: Session, run: Run) -> RunOut:
    automation = db.get_one(Automation, run.automation_id)
    version = db.get(AutomationVersion, run.version_id)
    duration = (
        (run.finished_at - run.started_at).total_seconds()
        if run.finished_at and run.started_at
        else None
    )
    return RunOut(
        id=run.id,
        automation_id=run.automation_id,
        automation_name=automation.name,
        version_no=version.version_no if version else None,
        status=run.status.value,
        is_test=run.is_test,
        trigger_type=run.trigger_type,
        minutes_saved=run.minutes_saved,
        summary=run.summary,
        error=run.error,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_seconds=duration,
    )


@router.get("/runs", response_model=list[RunOut])
def list_runs(
    ctx: WorkspaceMember,
    db: DB,
    *,
    status: RunStatus | None = None,
    automation_id: uuid.UUID | None = None,
    include_tests: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[RunOut]:
    stmt = select(Run).where(Run.workspace_id == ctx.workspace_id)
    if status is not None:
        stmt = stmt.where(Run.status == status)
    if automation_id is not None:
        stmt = stmt.where(Run.automation_id == automation_id)
    if not include_tests:
        stmt = stmt.where(Run.is_test.is_(False))
    runs = db.scalars(stmt.order_by(Run.created_at.desc()).limit(limit).offset(offset)).all()
    return [run_out(db, r) for r in runs]


@router.get("/runs/{run_id}", response_model=RunDetailOut)
def read_run(run_id: uuid.UUID, ctx: WorkspaceMember, db: DB) -> RunDetailOut:
    run = db.scalar(select(Run).where(Run.id == run_id, Run.workspace_id == ctx.workspace_id))
    if run is None:
        raise NotFoundError("Run not found.")
    steps = db.scalars(
        select(StepRun).where(StepRun.run_id == run.id).order_by(StepRun.seq_no)
    ).all()
    approvals = db.scalars(
        select(ApprovalTask).where(ApprovalTask.run_id == run.id).order_by(ApprovalTask.created_at)
    ).all()
    return RunDetailOut(
        **run_out(db, run).model_dump(),
        steps=[StepRunOut.model_validate(s) for s in steps],
        approvals=[
            ApprovalBrief(
                id=a.id,
                kind=a.kind.value,
                title=a.title,
                status=a.status.value,
                created_at=a.created_at,
                decided_at=a.decided_at,
            )
            for a in approvals
        ],
    )


def approval_out(db: Session, task: ApprovalTask) -> ApprovalOut:
    automation = db.get_one(Automation, task.automation_id)
    decided_by = db.get(User, task.decided_by) if task.decided_by else None
    return ApprovalOut(
        id=task.id,
        status=task.status.value,
        kind=task.kind.value,
        title=task.title,
        automation_id=task.automation_id,
        automation_name=automation.name,
        run_id=task.run_id,
        step_title=(task.payload_json or {}).get("step_title"),
        payload=task.payload_json,
        decision_payload=task.decision_payload_json,
        decided_by_name=decided_by.full_name if decided_by else None,
        decided_at=task.decided_at,
        decision_note=task.decision_note,
        created_at=task.created_at,
        remind_at=task.remind_at,
        expires_at=task.expires_at,
    )


def _get_task(db: Session, workspace_id: uuid.UUID, task_id: uuid.UUID) -> ApprovalTask:
    task = db.scalar(
        select(ApprovalTask).where(
            ApprovalTask.id == task_id, ApprovalTask.workspace_id == workspace_id
        )
    )
    if task is None:
        raise NotFoundError("Approval not found.")
    return task


@router.get("/approvals", response_model=list[ApprovalOut])
def list_approvals(
    ctx: WorkspaceMember,
    db: DB,
    state: Literal["open", "decided", "all"] = "open",
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ApprovalOut]:
    stmt = select(ApprovalTask).where(ApprovalTask.workspace_id == ctx.workspace_id)
    open_states = [ApprovalStatus.PENDING, ApprovalStatus.REMINDED]
    if state == "open":
        stmt = stmt.where(ApprovalTask.status.in_(open_states)).order_by(ApprovalTask.created_at)
    elif state == "decided":
        stmt = stmt.where(ApprovalTask.status.not_in(open_states)).order_by(
            ApprovalTask.decided_at.desc()
        )
    else:
        stmt = stmt.order_by(ApprovalTask.created_at.desc())
    return [approval_out(db, t) for t in db.scalars(stmt.limit(limit))]


@router.get("/approvals/{task_id}", response_model=ApprovalOut)
def read_approval(task_id: uuid.UUID, ctx: WorkspaceMember, db: DB) -> ApprovalOut:
    return approval_out(db, _get_task(db, ctx.workspace_id, task_id))


@router.post("/approvals/{task_id}/decision", response_model=ApprovalOut)
def decide(task_id: uuid.UUID, body: DecisionIn, ctx: WorkspaceMember, db: DB) -> ApprovalOut:
    """decideApproval(taskId, decision, editedPayload): staff and owners may decide (BR-2)."""
    task = _get_task(db, ctx.workspace_id, task_id)
    approval_service.decide(
        db,
        task,
        ctx.user,
        body.decision,
        edited_params=body.edited_params,
        edited_fields=body.edited_fields,
        note=body.note,
    )
    db.expire_all()
    return approval_out(db, _get_task(db, ctx.workspace_id, task_id))
