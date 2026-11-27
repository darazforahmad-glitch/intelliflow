"""Platform administration (REQ-PA-1..5). Aggregates only: admins never see a workspace's
message content (BR-8)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import DB, PlatformAdmin
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models import AuditLog, Automation, LLMUsage, Membership, Run, Template, User, Workspace
from app.models.base import utcnow
from app.models.enums import AutomationStatus, MembershipRole, RunStatus, WorkspaceStatus
from app.schemas.common import MessageOut
from app.services import audit_service
from app.services.ai_service import credits_used, month_start
from app.services.workflow_validator import WorkflowValidator

router = APIRouter(prefix="/admin", tags=["platform admin"])


class SuspendIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class LimitsIn(BaseModel):
    ai_credit_limit: int | None = Field(default=None, ge=0, le=1_000_000)


class TemplateIn(BaseModel):
    code: str = Field(min_length=3, max_length=60, pattern=r"^[a-z][a-z0-9_]+$")
    name: str = Field(min_length=3, max_length=120)
    category: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=1000)
    definition: dict[str, Any]
    match: dict[str, Any] = Field(default_factory=dict)
    required_connections: list[str] = Field(default_factory=list)


def _template_out(t: Template) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "code": t.code,
        "name": t.name,
        "category": t.category,
        "version": t.version,
        "is_active": t.is_active,
        "retired_at": t.retired_at.isoformat() if t.retired_at else None,
        "required_connections": t.required_connections,
        "match": t.match_json,
        "description": t.description,
        "definition": t.definition_json,
        "updated_at": t.updated_at.isoformat(),
    }


@router.get("/metrics")
def metrics(_admin: PlatformAdmin, db: DB) -> dict[str, Any]:
    now = utcnow()
    since = now - timedelta(days=13)
    per_day: dict[str, dict[str, int]] = {}
    for created_at, run_status in db.execute(
        select(Run.created_at, Run.status).where(Run.created_at >= since, Run.is_test.is_(False))
    ):
        day = created_at.date().isoformat()
        bucket = per_day.setdefault(day, {"runs": 0, "failed": 0})
        bucket["runs"] += 1
        bucket["failed"] += int(run_status == RunStatus.FAILED)
    week = now - timedelta(days=7)
    done = dict(
        db.execute(
            select(Run.status, func.count(Run.id))
            .where(
                Run.created_at >= week,
                Run.is_test.is_(False),
                Run.status.in_([RunStatus.SUCCEEDED, RunStatus.FAILED]),
            )
            .group_by(Run.status)
        )
        .tuples()
        .all()
    )
    finished = sum(done.values())
    usage = db.execute(
        select(
            func.coalesce(func.sum(LLMUsage.input_tokens), 0),
            func.coalesce(func.sum(LLMUsage.output_tokens), 0),
            func.coalesce(func.sum(LLMUsage.cost_usd), 0),
            func.count(LLMUsage.id),
        ).where(LLMUsage.created_at >= month_start())
    ).one()
    days = [(since + timedelta(days=i)).date().isoformat() for i in range(14)]
    return {
        "workspaces": {
            "active": db.scalar(
                select(func.count(Workspace.id)).where(
                    Workspace.status == WorkspaceStatus.ACTIVE, Workspace.deleted_at.is_(None)
                )
            )
            or 0,
            "suspended": db.scalar(
                select(func.count(Workspace.id)).where(
                    Workspace.status == WorkspaceStatus.SUSPENDED
                )
            )
            or 0,
        },
        "users": db.scalar(select(func.count(User.id))) or 0,
        "active_automations": db.scalar(
            select(func.count(Automation.id)).where(Automation.status == AutomationStatus.ACTIVE)
        )
        or 0,
        "runs_per_day": [{"date": d, **per_day.get(d, {"runs": 0, "failed": 0})} for d in days],
        "failure_rate_7d": (
            round(done.get(RunStatus.FAILED, 0) / finished * 100, 1) if finished else None
        ),
        "llm_month": {
            "input_tokens": int(usage[0]),
            "output_tokens": int(usage[1]),
            "cost_usd": float(Decimal(usage[2]).quantize(Decimal("0.0001"))),
            "calls": int(usage[3]),
        },
    }


@router.get("/workspaces")
def list_workspaces(_admin: PlatformAdmin, db: DB) -> list[dict[str, Any]]:
    week = utcnow() - timedelta(days=7)
    runs = dict(
        db.execute(
            select(Run.workspace_id, func.count(Run.id))
            .where(Run.created_at >= week, Run.is_test.is_(False))
            .group_by(Run.workspace_id)
        )
        .tuples()
        .all()
    )
    out = []
    for workspace in db.scalars(
        select(Workspace)
        .where(Workspace.deleted_at.is_(None))
        .order_by(Workspace.created_at.desc())
    ):
        owner = db.scalar(
            select(User.email)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.workspace_id == workspace.id, Membership.role == MembershipRole.OWNER)
            .limit(1)
        )
        out.append(
            {
                "id": str(workspace.id),
                "name": workspace.name,
                "business_type": workspace.business_type,
                "status": workspace.status.value,
                "suspended_reason": workspace.suspended_reason,
                "owner_email": owner,
                "created_at": workspace.created_at.isoformat(),
                "runs_7d": runs.get(workspace.id, 0),
                "ai_credits_used": credits_used(db, workspace.id),
                "ai_credit_limit": workspace.ai_credit_limit,
            }
        )
    return out


def _workspace(db: Any, workspace_id: uuid.UUID) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise NotFoundError("Workspace not found.")
    return workspace


@router.post("/workspaces/{workspace_id}/suspend", response_model=MessageOut)
def suspend(workspace_id: uuid.UUID, body: SuspendIn, admin: PlatformAdmin, db: DB) -> MessageOut:
    workspace = _workspace(db, workspace_id)
    workspace.status = WorkspaceStatus.SUSPENDED
    workspace.suspended_reason = body.reason
    paused = 0
    for automation in db.scalars(
        select(Automation).where(
            Automation.workspace_id == workspace.id, Automation.status == AutomationStatus.ACTIVE
        )
    ):
        automation.status = AutomationStatus.PAUSED
        automation.status_reason = "Paused because the workspace was suspended."
        paused += 1
    audit_service.record(
        db,
        "admin.workspace_suspended",
        workspace_id=workspace.id,
        actor_id=admin.id,
        entity_type="workspace",
        entity_id=workspace.id,
        data={"reason": body.reason, "paused": paused},
    )
    db.commit()
    return MessageOut(message=f"Workspace suspended; {paused} automation(s) paused.")


@router.post("/workspaces/{workspace_id}/reactivate", response_model=MessageOut)
def reactivate(workspace_id: uuid.UUID, admin: PlatformAdmin, db: DB) -> MessageOut:
    workspace = _workspace(db, workspace_id)
    workspace.status = WorkspaceStatus.ACTIVE
    workspace.suspended_reason = None
    audit_service.record(
        db,
        "admin.workspace_reactivated",
        workspace_id=workspace.id,
        actor_id=admin.id,
        entity_type="workspace",
        entity_id=workspace.id,
    )
    db.commit()
    return MessageOut(message="Workspace reactivated. The owner can switch automations back on.")


@router.patch("/workspaces/{workspace_id}/limits", response_model=MessageOut)
def set_limits(workspace_id: uuid.UUID, body: LimitsIn, admin: PlatformAdmin, db: DB) -> MessageOut:
    workspace = _workspace(db, workspace_id)
    workspace.ai_credit_limit = body.ai_credit_limit
    audit_service.record(
        db,
        "admin.limits_changed",
        workspace_id=workspace.id,
        actor_id=admin.id,
        entity_type="workspace",
        entity_id=workspace.id,
        data={"ai_credit_limit": body.ai_credit_limit},
    )
    db.commit()
    return MessageOut(message="Limits updated.")


@router.get("/templates")
def list_templates(_admin: PlatformAdmin, db: DB) -> list[dict[str, Any]]:
    return [
        _template_out(t)
        for t in db.scalars(select(Template).order_by(Template.code, Template.version.desc()))
    ]


def _validated_definition(definition: dict[str, Any]) -> None:
    issues = WorkflowValidator().validate(definition)
    if issues:
        raise ValidationFailedError(
            "The template definition is not valid.", details=[i.to_dict() for i in issues]
        )


@router.post("/templates", status_code=status.HTTP_201_CREATED)
def create_template(body: TemplateIn, admin: PlatformAdmin, db: DB) -> dict[str, Any]:
    if db.scalar(select(Template.id).where(Template.code == body.code)):
        raise ConflictError("A template with this code exists; publish a new version instead.")
    _validated_definition(body.definition)
    template = Template(
        code=body.code,
        name=body.name,
        category=body.category,
        description=body.description,
        definition_json=body.definition,
        match_json=body.match,
        required_connections=body.required_connections,
        version=1,
        is_active=False,
    )
    db.add(template)
    audit_service.record(
        db,
        "admin.template_created",
        actor_id=admin.id,
        entity_type="template",
        data={"code": body.code},
    )
    db.commit()
    return _template_out(template)


@router.post("/templates/{code}/versions", status_code=status.HTTP_201_CREATED)
def new_template_version(
    code: str, body: TemplateIn, admin: PlatformAdmin, db: DB
) -> dict[str, Any]:
    latest = db.scalar(
        select(Template).where(Template.code == code).order_by(Template.version.desc()).limit(1)
    )
    if latest is None:
        raise NotFoundError("Template not found.")
    _validated_definition(body.definition)
    template = Template(
        code=code,
        name=body.name,
        category=body.category,
        description=body.description,
        definition_json=body.definition,
        match_json=body.match or latest.match_json,
        required_connections=body.required_connections or latest.required_connections,
        version=latest.version + 1,
        is_active=False,
    )
    db.add(template)
    audit_service.record(
        db,
        "admin.template_versioned",
        actor_id=admin.id,
        entity_type="template",
        data={"code": code, "version": template.version},
    )
    db.commit()
    return _template_out(template)


@router.post("/templates/{template_id}/publish")
def publish_template(template_id: uuid.UUID, admin: PlatformAdmin, db: DB) -> dict[str, Any]:
    template = db.get(Template, template_id)
    if template is None:
        raise NotFoundError("Template not found.")
    for other in db.scalars(
        select(Template).where(
            Template.code == template.code, Template.id != template.id, Template.is_active.is_(True)
        )
    ):
        other.is_active = False
    db.flush()
    template.is_active = True
    template.retired_at = None
    audit_service.record(
        db,
        "admin.template_published",
        actor_id=admin.id,
        entity_type="template",
        entity_id=template.id,
        data={"code": template.code, "version": template.version},
    )
    db.commit()
    return _template_out(template)


@router.post("/templates/{template_id}/retire")
def retire_template(template_id: uuid.UUID, admin: PlatformAdmin, db: DB) -> dict[str, Any]:
    template = db.get(Template, template_id)
    if template is None:
        raise NotFoundError("Template not found.")
    template.is_active = False
    template.retired_at = utcnow()
    audit_service.record(
        db,
        "admin.template_retired",
        actor_id=admin.id,
        entity_type="template",
        entity_id=template.id,
    )
    db.commit()
    return _template_out(template)


@router.get("/audit-logs")
def audit_logs(
    _admin: PlatformAdmin,
    db: DB,
    workspace_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    stmt = select(AuditLog, User.email).outerjoin(User, User.id == AuditLog.actor_id)
    if workspace_id:
        stmt = stmt.where(AuditLog.workspace_id == workspace_id)
    rows = db.execute(stmt.order_by(AuditLog.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": str(a.id),
            "action": a.action,
            "workspace_id": str(a.workspace_id) if a.workspace_id else None,
            "actor_email": email,
            "entity_type": a.entity_type,
            "entity_id": a.entity_id,
            "data": a.data_json,
            "ip_address": a.ip_address,
            "created_at": a.created_at.isoformat(),
        }
        for a, email in rows
    ]
