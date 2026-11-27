"""/workspaces/{id}/automations: AI Automation Builder and lifecycle (UC-07, UC-09)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import DB, WorkspaceMember, WorkspaceOwner
from app.api.v1.process_maps import get_opportunity
from app.api.v1.runs import run_out
from app.connectors.registry import PROVIDER_LABELS, active_connection
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.models import Automation, AutomationVersion, Run, Template
from app.models.enums import RunStatus
from app.schemas.automation import (
    AutomationListItem,
    AutomationOut,
    AutomationStats,
    AutomationVersionOut,
    AutoSendIn,
    ConnectionRequirement,
    DefinitionIn,
    FromTemplateIn,
    RollbackIn,
    TestIn,
    TestOut,
    TraceStep,
    ValidationOut,
    VersionSummary,
)
from app.services.approval_service import clean_customer_approvals
from app.services.automation_builder import AutomationBuilder, providers_used

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["automations"])


def get_automation(db: Session, workspace_id: uuid.UUID, automation_id: uuid.UUID) -> Automation:
    automation = db.scalar(
        select(Automation).where(
            Automation.id == automation_id, Automation.workspace_id == workspace_id
        )
    )
    if automation is None:
        raise NotFoundError("Automation not found.")
    return automation


def stats_for(db: Session, automation_ids: list[uuid.UUID]) -> dict[uuid.UUID, AutomationStats]:
    if not automation_ids:
        return {}
    rows = db.execute(
        select(
            Run.automation_id,
            func.count(Run.id),
            func.count(Run.id).filter(Run.status == RunStatus.SUCCEEDED),
            func.count(Run.id).filter(Run.status == RunStatus.FAILED),
            func.count(Run.id).filter(Run.status == RunStatus.WAITING_APPROVAL),
            func.coalesce(func.sum(Run.minutes_saved), 0),
            func.max(Run.created_at),
        )
        .where(Run.automation_id.in_(automation_ids), Run.is_test.is_(False))
        .group_by(Run.automation_id)
    ).all()
    return {
        r[0]: AutomationStats(
            runs_total=r[1],
            runs_succeeded=r[2],
            runs_failed=r[3],
            runs_waiting=r[4],
            minutes_saved=Decimal(r[5]),
            last_run_at=r[6],
        )
        for r in rows
    }


def automation_out(db: Session, automation: Automation) -> AutomationOut:
    template = db.get(Template, automation.template_id) if automation.template_id else None
    versions = db.scalars(
        select(AutomationVersion)
        .where(AutomationVersion.automation_id == automation.id)
        .order_by(AutomationVersion.version_no.desc())
    ).all()
    current = automation.current_version
    connections = []
    for provider in sorted(providers_used(current.definition_json) if current else set()):
        connection = active_connection(db, automation.workspace_id, provider)
        connections.append(
            ConnectionRequirement(
                provider=provider,
                label=PROVIDER_LABELS.get(provider, provider),
                connected=connection is not None,
                mode=connection.mode.value if connection else None,
            )
        )
    threshold = get_settings().auto_send_min_clean_approvals
    return AutomationOut(
        id=automation.id,
        name=automation.name,
        description=automation.description,
        status=automation.status.value,
        status_reason=automation.status_reason,
        trigger_type=automation.trigger_type,
        template_code=template.code if template else None,
        template_name=template.name if template else None,
        opportunity_id=automation.opportunity_id,
        auto_send=automation.auto_send,
        clean_approvals=clean_customer_approvals(db, automation.id, threshold),
        auto_send_threshold=threshold,
        estimated_minutes_per_run=automation.estimated_minutes_per_run,
        activated_at=automation.activated_at,
        created_at=automation.created_at,
        updated_at=automation.updated_at,
        current_version=AutomationVersionOut.model_validate(current) if current else None,
        versions=[VersionSummary.model_validate(v) for v in versions],
        connections=connections,
        stats=stats_for(db, [automation.id]).get(automation.id, AutomationStats()),
    )


@router.get("/automations", response_model=list[AutomationListItem])
def list_automations(
    ctx: WorkspaceMember, db: DB, include_archived: bool = False
) -> list[AutomationListItem]:
    stmt = (
        select(Automation, Template.name)
        .outerjoin(Template, Template.id == Automation.template_id)
        .where(Automation.workspace_id == ctx.workspace_id)
    )
    if not include_archived:
        stmt = stmt.where(Automation.status != "archived")
    rows = db.execute(stmt.order_by(Automation.created_at.desc())).all()
    stats = stats_for(db, [a.id for a, _ in rows])
    return [
        AutomationListItem(
            id=a.id,
            name=a.name,
            status=a.status.value,
            status_reason=a.status_reason,
            trigger_type=a.trigger_type,
            template_name=t,
            auto_send=a.auto_send,
            version_no=a.current_version.version_no if a.current_version else None,
            stats=stats.get(a.id, AutomationStats()),
        )
        for a, t in rows
    ]


@router.post(
    "/opportunities/{opportunity_id}/automation",
    response_model=AutomationOut,
    status_code=status.HTTP_201_CREATED,
)
def generate_from_opportunity(
    opportunity_id: uuid.UUID, ctx: WorkspaceOwner, db: DB
) -> AutomationOut:
    opportunity = get_opportunity(db, ctx.workspace_id, opportunity_id)
    automation = AutomationBuilder(db, ctx.workspace, ctx.user).generate_from_opportunity(
        opportunity
    )
    return automation_out(db, automation)


@router.post(
    "/automations/from-template", response_model=AutomationOut, status_code=status.HTTP_201_CREATED
)
def generate_from_template(body: FromTemplateIn, ctx: WorkspaceOwner, db: DB) -> AutomationOut:
    automation = AutomationBuilder(db, ctx.workspace, ctx.user).generate_from_template(
        body.template_code
    )
    return automation_out(db, automation)


@router.get("/automations/{automation_id}", response_model=AutomationOut)
def read_automation(automation_id: uuid.UUID, ctx: WorkspaceMember, db: DB) -> AutomationOut:
    return automation_out(db, get_automation(db, ctx.workspace_id, automation_id))


@router.get(
    "/automations/{automation_id}/versions/{version_no}", response_model=AutomationVersionOut
)
def read_version(
    automation_id: uuid.UUID, version_no: int, ctx: WorkspaceMember, db: DB
) -> AutomationVersionOut:
    get_automation(db, ctx.workspace_id, automation_id)
    version = db.scalar(
        select(AutomationVersion).where(
            AutomationVersion.automation_id == automation_id,
            AutomationVersion.version_no == version_no,
        )
    )
    if version is None:
        raise NotFoundError("Version not found.")
    return AutomationVersionOut.model_validate(version)


@router.put("/automations/{automation_id}/definition", response_model=AutomationOut)
def save_definition(
    automation_id: uuid.UUID, body: DefinitionIn, ctx: WorkspaceOwner, db: DB
) -> AutomationOut:
    automation = get_automation(db, ctx.workspace_id, automation_id)
    AutomationBuilder(db, ctx.workspace, ctx.user).save_definition(automation, body.definition)
    return automation_out(db, automation)


@router.post("/automations/{automation_id}/validate", response_model=ValidationOut)
def validate(
    automation_id: uuid.UUID, body: DefinitionIn, ctx: WorkspaceMember, db: DB
) -> ValidationOut:
    get_automation(db, ctx.workspace_id, automation_id)
    issues = AutomationBuilder(db, ctx.workspace, ctx.user).validate(
        body.definition, check_connections=True
    )
    return ValidationOut(valid=not issues, issues=[i.to_dict() for i in issues])


@router.post("/automations/{automation_id}/repair", response_model=AutomationOut)
def repair(automation_id: uuid.UUID, ctx: WorkspaceOwner, db: DB) -> AutomationOut:
    automation = get_automation(db, ctx.workspace_id, automation_id)
    AutomationBuilder(db, ctx.workspace, ctx.user).repair(automation)
    return automation_out(db, automation)


@router.post("/automations/{automation_id}/test", response_model=TestOut)
def test(automation_id: uuid.UUID, body: TestIn, ctx: WorkspaceOwner, db: DB) -> TestOut:
    automation = get_automation(db, ctx.workspace_id, automation_id)
    result = AutomationBuilder(db, ctx.workspace, ctx.user).test(automation, body.sample)
    return TestOut(
        passed=result.passed,
        message=result.message,
        run=run_out(db, result.run),
        steps=[TraceStep(**s) for s in result.trace],
        sandbox_records=result.sandbox_records,
    )


@router.post("/automations/{automation_id}/activate", response_model=AutomationOut)
def activate(automation_id: uuid.UUID, ctx: WorkspaceOwner, db: DB) -> AutomationOut:
    automation = get_automation(db, ctx.workspace_id, automation_id)
    return automation_out(db, AutomationBuilder(db, ctx.workspace, ctx.user).activate(automation))


@router.post("/automations/{automation_id}/pause", response_model=AutomationOut)
def pause(automation_id: uuid.UUID, ctx: WorkspaceOwner, db: DB) -> AutomationOut:
    automation = get_automation(db, ctx.workspace_id, automation_id)
    return automation_out(db, AutomationBuilder(db, ctx.workspace, ctx.user).pause(automation))


@router.post("/automations/{automation_id}/archive", response_model=AutomationOut)
def archive(automation_id: uuid.UUID, ctx: WorkspaceOwner, db: DB) -> AutomationOut:
    automation = get_automation(db, ctx.workspace_id, automation_id)
    return automation_out(db, AutomationBuilder(db, ctx.workspace, ctx.user).archive(automation))


@router.post("/automations/{automation_id}/rollback", response_model=AutomationOut)
def rollback(
    automation_id: uuid.UUID, body: RollbackIn, ctx: WorkspaceOwner, db: DB
) -> AutomationOut:
    automation = get_automation(db, ctx.workspace_id, automation_id)
    AutomationBuilder(db, ctx.workspace, ctx.user).rollback(automation, body.version_no)
    return automation_out(db, automation)


@router.post("/automations/{automation_id}/auto-send", response_model=AutomationOut)
def auto_send(
    automation_id: uuid.UUID, body: AutoSendIn, ctx: WorkspaceOwner, db: DB
) -> AutomationOut:
    automation = get_automation(db, ctx.workspace_id, automation_id)
    return automation_out(
        db, AutomationBuilder(db, ctx.workspace, ctx.user).set_auto_send(automation, body.enabled)
    )
