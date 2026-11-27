"""Platform administration (REQ-PA-1..5), shared by the REST API and the Django admin site.

Aggregates only: platform admins never see a workspace's message content (BR-8).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce

from intelliflow.accounts.models import User
from intelliflow.audit import services as audit_service
from intelliflow.audit.models import AuditLog, LLMUsage
from intelliflow.automations.models import Automation, Template
from intelliflow.automations.validator import WorkflowValidator
from intelliflow.core.enums import AutomationStatus, MembershipRole, RunStatus, WorkspaceStatus
from intelliflow.core.errors import ConflictError, NotFoundError, ValidationFailedError
from intelliflow.core.models import utcnow
from intelliflow.llm.service import credits_used, month_start
from intelliflow.runs.models import Run
from intelliflow.workspaces.models import Workspace


def template_out(t: Template) -> dict[str, Any]:
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


# ------------------------------------------------------------------ REQ-PA-2: metrics
def metrics() -> dict[str, Any]:
    now = utcnow()
    since = now - timedelta(days=13)
    per_day: dict[str, dict[str, int]] = {}
    for created_at, run_status in Run.objects.filter(
        created_at__gte=since, is_test=False
    ).values_list("created_at", "status"):
        bucket = per_day.setdefault(created_at.date().isoformat(), {"runs": 0, "failed": 0})
        bucket["runs"] += 1
        bucket["failed"] += int(run_status == RunStatus.FAILED)
    week = now - timedelta(days=7)
    finished_runs = Run.objects.filter(
        created_at__gte=week,
        is_test=False,
        status__in=[RunStatus.SUCCEEDED, RunStatus.FAILED],
    )
    finished = finished_runs.count()
    failed = finished_runs.filter(status=RunStatus.FAILED).count()
    usage = LLMUsage.objects.filter(created_at__gte=month_start()).aggregate(
        input_tokens=Coalesce(Sum("input_tokens"), 0),
        output_tokens=Coalesce(Sum("output_tokens"), 0),
        cost=Coalesce(Sum("cost_usd"), Decimal(0)),
        calls=Count("id"),
    )
    days = [(since + timedelta(days=i)).date().isoformat() for i in range(14)]
    return {
        "workspaces": {
            "active": Workspace.objects.filter(
                status=WorkspaceStatus.ACTIVE, deleted_at__isnull=True
            ).count(),
            "suspended": Workspace.objects.filter(status=WorkspaceStatus.SUSPENDED).count(),
        },
        "users": User.objects.count(),
        "active_automations": Automation.objects.filter(status=AutomationStatus.ACTIVE).count(),
        "runs_per_day": [{"date": d, **per_day.get(d, {"runs": 0, "failed": 0})} for d in days],
        "failure_rate_7d": round(failed / finished * 100, 1) if finished else None,
        "llm_month": {
            "input_tokens": int(usage["input_tokens"]),
            "output_tokens": int(usage["output_tokens"]),
            "cost_usd": float(Decimal(usage["cost"]).quantize(Decimal("0.0001"))),
            "calls": int(usage["calls"]),
        },
    }


def workspace_rows() -> list[dict[str, Any]]:
    week = utcnow() - timedelta(days=7)
    workspaces = (
        Workspace.objects.filter(deleted_at__isnull=True)
        .annotate(runs_7d=Count("runs", filter=Q(runs__created_at__gte=week, runs__is_test=False)))
        .order_by("-created_at")
    )
    out = []
    for workspace in workspaces:
        owner = (
            User.objects.filter(
                memberships__workspace=workspace, memberships__role=MembershipRole.OWNER
            )
            .values_list("email", flat=True)
            .first()
        )
        out.append(
            {
                "id": str(workspace.id),
                "name": workspace.name,
                "business_type": workspace.business_type,
                "status": workspace.status,
                "suspended_reason": workspace.suspended_reason,
                "owner_email": owner,
                "created_at": workspace.created_at.isoformat(),
                "runs_7d": workspace.runs_7d,
                "ai_credits_used": credits_used(workspace.id),
                "ai_credit_limit": workspace.ai_credit_limit,
            }
        )
    return out


# ------------------------------------------------------------------ REQ-PA-3/4: limits, suspension
def get_workspace(workspace_id: uuid.UUID | str) -> Workspace:
    workspace = Workspace.objects.filter(pk=workspace_id).first()
    if workspace is None or workspace.deleted_at is not None:
        raise NotFoundError("Workspace not found.")
    return workspace


@transaction.atomic
def suspend(workspace: Workspace, admin: User, reason: str) -> int:
    """Suspends a workspace: pauses its automations and blocks its users' sign-in."""
    workspace.status = WorkspaceStatus.SUSPENDED
    workspace.suspended_reason = reason
    workspace.save(update_fields=["status", "suspended_reason"])
    paused = Automation.objects.filter(workspace=workspace, status=AutomationStatus.ACTIVE).update(
        status=AutomationStatus.PAUSED,
        status_reason="Paused because the workspace was suspended.",
        updated_at=utcnow(),
    )
    audit_service.record(
        "admin.workspace_suspended",
        workspace_id=workspace.id,
        actor_id=admin.id,
        entity_type="workspace",
        entity_id=workspace.id,
        data={"reason": reason, "paused": paused},
    )
    return paused


@transaction.atomic
def reactivate(workspace: Workspace, admin: User) -> None:
    workspace.status = WorkspaceStatus.ACTIVE
    workspace.suspended_reason = None
    workspace.save(update_fields=["status", "suspended_reason"])
    audit_service.record(
        "admin.workspace_reactivated",
        workspace_id=workspace.id,
        actor_id=admin.id,
        entity_type="workspace",
        entity_id=workspace.id,
    )


@transaction.atomic
def set_limits(workspace: Workspace, admin: User, ai_credit_limit: int | None) -> None:
    workspace.ai_credit_limit = ai_credit_limit
    workspace.save(update_fields=["ai_credit_limit"])
    audit_service.record(
        "admin.limits_changed",
        workspace_id=workspace.id,
        actor_id=admin.id,
        entity_type="workspace",
        entity_id=workspace.id,
        data={"ai_credit_limit": ai_credit_limit},
    )


# ------------------------------------------------------------------ REQ-PA-1: templates
def validate_definition(definition: dict[str, Any]) -> None:
    issues = WorkflowValidator().validate(definition)
    if issues:
        raise ValidationFailedError(
            "The template definition is not valid.", details=[i.to_dict() for i in issues]
        )


@transaction.atomic
def create_template(admin: User, data: dict[str, Any]) -> Template:
    if Template.objects.filter(code=data["code"]).exists():
        raise ConflictError("A template with this code exists; publish a new version instead.")
    validate_definition(data["definition"])
    template = Template.objects.create(
        code=data["code"],
        name=data["name"],
        category=data.get("category"),
        description=data.get("description"),
        definition_json=data["definition"],
        match_json=data.get("match") or {},
        required_connections=data.get("required_connections") or [],
        version=1,
        is_active=False,
    )
    audit_service.record(
        "admin.template_created",
        actor_id=admin.id,
        entity_type="template",
        data={"code": template.code},
    )
    return template


@transaction.atomic
def new_template_version(admin: User, code: str, data: dict[str, Any]) -> Template:
    latest = Template.objects.filter(code=code).order_by("-version").first()
    if latest is None:
        raise NotFoundError("Template not found.")
    validate_definition(data["definition"])
    template = Template.objects.create(
        code=code,
        name=data["name"],
        category=data.get("category"),
        description=data.get("description"),
        definition_json=data["definition"],
        match_json=data.get("match") or latest.match_json,
        required_connections=data.get("required_connections") or latest.required_connections,
        version=latest.version + 1,
        is_active=False,
    )
    audit_service.record(
        "admin.template_versioned",
        actor_id=admin.id,
        entity_type="template",
        data={"code": code, "version": template.version},
    )
    return template


def get_template(template_id: uuid.UUID | str) -> Template:
    template = Template.objects.filter(pk=template_id).first()
    if template is None:
        raise NotFoundError("Template not found.")
    return template


@transaction.atomic
def publish_template(template: Template, admin: User) -> Template:
    """Publishes one version; any other published version of the same code is retired."""
    Template.objects.filter(code=template.code, is_active=True).exclude(pk=template.pk).update(
        is_active=False
    )
    template.is_active = True
    template.retired_at = None
    template.save(update_fields=["is_active", "retired_at", "updated_at"])
    audit_service.record(
        "admin.template_published",
        actor_id=admin.id,
        entity_type="template",
        entity_id=template.id,
        data={"code": template.code, "version": template.version},
    )
    return template


@transaction.atomic
def retire_template(template: Template, admin: User) -> Template:
    template.is_active = False
    template.retired_at = utcnow()
    template.save(update_fields=["is_active", "retired_at", "updated_at"])
    audit_service.record(
        "admin.template_retired", actor_id=admin.id, entity_type="template", entity_id=template.id
    )
    return template


# ------------------------------------------------------------------ REQ-PA-5: audit log
def audit_rows(workspace_id: uuid.UUID | None, limit: int) -> list[dict[str, Any]]:
    entries = AuditLog.objects.select_related("actor").order_by("-created_at")
    if workspace_id:
        entries = entries.filter(workspace_id=workspace_id)
    return [
        {
            "id": str(a.id),
            "action": a.action,
            "workspace_id": str(a.workspace_id) if a.workspace_id else None,
            "actor_email": a.actor.email if a.actor_id else None,
            "entity_type": a.entity_type,
            "entity_id": a.entity_id,
            "data": a.data_json,
            "ip_address": a.ip_address,
            "created_at": a.created_at.isoformat(),
        }
        for a in entries[:limit]
    ]
