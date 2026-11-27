"""/workspaces/{id}/process-maps and opportunities (REQ-FM-6/7, REQ-OA-1..6, UC-05)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import DB, WorkspaceMember, WorkspaceOwner
from app.core.errors import NotFoundError
from app.models import Automation, Opportunity, ProcessMap, ProcessStep, Template
from app.models.enums import OpportunityStatus, StepType
from app.schemas.process import (
    MapVersionIn,
    MapVersionRef,
    OpportunityOut,
    ProcessMapOut,
    ProcessMapSummary,
    StepOut,
    TemplateRef,
)
from app.services import audit_service
from app.services.ai_service import AIService
from app.services.opportunity_analyzer import TOP_N, OpportunityAnalyzer, per_day
from app.services.process_mapper import ProcessMapper

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["flow mapper"])


def get_map(db: Session, workspace_id: uuid.UUID, map_id: uuid.UUID) -> ProcessMap:
    process_map = db.scalar(
        select(ProcessMap).where(ProcessMap.id == map_id, ProcessMap.workspace_id == workspace_id)
    )
    if process_map is None:
        raise NotFoundError("Process map not found.")
    return process_map


def get_opportunity(db: Session, workspace_id: uuid.UUID, opportunity_id: uuid.UUID) -> Opportunity:
    opportunity = db.scalar(
        select(Opportunity)
        .join(ProcessMap, ProcessMap.id == Opportunity.map_id)
        .where(Opportunity.id == opportunity_id, ProcessMap.workspace_id == workspace_id)
    )
    if opportunity is None:
        raise NotFoundError("Opportunity not found.")
    return opportunity


def _step_out(step: ProcessStep) -> StepOut:
    return StepOut(
        id=step.id,
        key=step.step_key,
        seq_no=step.seq_no,
        title=step.title,
        actor=step.actor,
        action=step.action,
        step_type=step.step_type.value,
        app=step.app,
        minutes_per_run=step.minutes_per_run,
        runs_per_week=step.runs_per_week,
        weekly_minutes=step.weekly_minutes,
        is_manual=step.is_manual,
        predecessor_key=step.predecessor_key,
        involves_customer_messaging=step.involves_customer_messaging,
        involves_money=step.involves_money,
        support_status=step.support_status,
    )


def opportunity_out(
    opportunity: Opportunity,
    step: ProcessStep,
    template: Template | None,
    automation_id: uuid.UUID | None,
) -> OpportunityOut:
    return OpportunityOut(
        id=opportunity.id,
        rank=opportunity.rank,
        score=opportunity.score,
        status=opportunity.status.value,
        fit=opportunity.fit,
        risk=opportunity.risk,
        minutes_saved_per_week=opportunity.minutes_saved_per_week,
        minutes_saved_per_day=per_day(opportunity.minutes_saved_per_week),
        reason=opportunity.reason,
        step_id=step.id,
        step_key=step.step_key,
        step_title=step.title,
        template=(
            TemplateRef(
                id=template.id,
                code=template.code,
                name=template.name,
                category=template.category,
                required_connections=list(template.required_connections or []),
            )
            if template
            else None
        ),
        automation_id=automation_id,
    )


def serialize_map(db: Session, process_map: ProcessMap) -> ProcessMapOut:
    steps = {s.id: s for s in process_map.steps}
    rows = db.execute(
        select(Opportunity, Template)
        .outerjoin(Template, Template.id == Opportunity.template_id)
        .where(Opportunity.map_id == process_map.id)
    ).all()
    automation_ids = (
        dict(
            db.execute(
                select(Automation.opportunity_id, Automation.id).where(
                    Automation.opportunity_id.in_([o.id for o, _ in rows])
                )
            )
            .tuples()
            .all()
        )
        if rows
        else {}
    )
    items = sorted(
        (opportunity_out(o, steps[o.step_id], t, automation_ids.get(o.id)) for o, t in rows),
        key=lambda o: (o.rank is None, o.rank or 0),
    )
    versions = db.scalars(
        select(ProcessMap)
        .where(ProcessMap.session_id == process_map.session_id)
        .order_by(ProcessMap.version)
    ).all()
    manual = [s for s in process_map.steps if s.step_type in {StepType.MANUAL, StepType.HUMAN_ONLY}]
    return ProcessMapOut(
        id=process_map.id,
        session_id=process_map.session_id,
        name=process_map.name,
        version=process_map.version,
        is_latest=process_map.version == max(v.version for v in versions),
        created_at=process_map.created_at,
        change_note=process_map.change_note,
        graph_json=process_map.graph_json,
        steps=[_step_out(s) for s in process_map.steps],
        total_weekly_minutes=sum((s.weekly_minutes for s in process_map.steps), Decimal(0)),
        manual_weekly_minutes=sum((s.weekly_minutes for s in manual), Decimal(0)),
        opportunities=[
            o
            for o in items
            if o.status != OpportunityStatus.DISMISSED.value and (o.rank or 99) <= TOP_N
        ],
        other_opportunities=[
            o
            for o in items
            if o.status != OpportunityStatus.DISMISSED.value and (o.rank or 99) > TOP_N
        ],
        dismissed_opportunities=[o for o in items if o.status == OpportunityStatus.DISMISSED.value],
        unsupported_steps=[
            s.step_key for s in process_map.steps if s.support_status == "not_yet_supported"
        ],
        versions=[
            MapVersionRef(
                id=v.id, version=v.version, created_at=v.created_at, change_note=v.change_note
            )
            for v in versions
        ],
    )


@router.get("/process-maps", response_model=list[ProcessMapSummary])
def list_maps(ctx: WorkspaceMember, db: DB) -> list[ProcessMapSummary]:
    latest = (
        select(ProcessMap.session_id, func.max(ProcessMap.version).label("v"))
        .where(ProcessMap.workspace_id == ctx.workspace_id)
        .group_by(ProcessMap.session_id)
        .subquery()
    )
    maps = db.scalars(
        select(ProcessMap)
        .join(
            latest,
            (latest.c.session_id == ProcessMap.session_id) & (latest.c.v == ProcessMap.version),
        )
        .order_by(ProcessMap.created_at.desc())
    ).all()
    summaries = []
    for m in maps:
        top = db.execute(
            select(ProcessStep.title)
            .join(Opportunity, Opportunity.step_id == ProcessStep.id)
            .where(Opportunity.map_id == m.id, Opportunity.rank == 1)
        ).scalar()
        manual = sum(
            (
                s.weekly_minutes
                for s in m.steps
                if s.step_type in {StepType.MANUAL, StepType.HUMAN_ONLY}
            ),
            Decimal(0),
        )
        summaries.append(
            ProcessMapSummary(
                id=m.id,
                session_id=m.session_id,
                name=m.name,
                version=m.version,
                created_at=m.created_at,
                step_count=len(m.steps),
                manual_weekly_minutes=manual,
                top_opportunity=top,
            )
        )
    return summaries


@router.get("/process-maps/{map_id}", response_model=ProcessMapOut)
def read_map(map_id: uuid.UUID, ctx: WorkspaceMember, db: DB) -> ProcessMapOut:
    return serialize_map(db, get_map(db, ctx.workspace_id, map_id))


@router.post(
    "/process-maps/{map_id}/versions",
    response_model=ProcessMapOut,
    status_code=status.HTTP_201_CREATED,
)
def save_version(
    map_id: uuid.UUID, body: MapVersionIn, ctx: WorkspaceOwner, db: DB
) -> ProcessMapOut:
    base = get_map(db, ctx.workspace_id, map_id)
    mapper = ProcessMapper(db, AIService(db, ctx.workspace))
    new_map = mapper.save_edited_version(
        base,
        [s.model_dump() for s in body.steps],
        ctx.user,
        name=body.name,
        note=body.note,
        positions={k: v.model_dump() for k, v in (body.positions or {}).items()},
    )
    OpportunityAnalyzer(db).analyze(new_map, ctx.workspace.approval_threshold)
    audit_service.record(
        db,
        "process_map.version_saved",
        workspace_id=ctx.workspace_id,
        actor_id=ctx.user.id,
        entity_type="process_map",
        entity_id=new_map.id,
        data={"version": new_map.version},
    )
    db.commit()
    db.refresh(new_map)
    return serialize_map(db, new_map)


@router.post("/opportunities/{opportunity_id}/dismiss", response_model=ProcessMapOut)
def dismiss(opportunity_id: uuid.UUID, ctx: WorkspaceOwner, db: DB) -> ProcessMapOut:
    opportunity = get_opportunity(db, ctx.workspace_id, opportunity_id)
    OpportunityAnalyzer(db).dismiss(opportunity)
    db.commit()
    return serialize_map(db, opportunity.process_map)


@router.post("/opportunities/{opportunity_id}/restore", response_model=ProcessMapOut)
def restore(opportunity_id: uuid.UUID, ctx: WorkspaceOwner, db: DB) -> ProcessMapOut:
    opportunity = get_opportunity(db, ctx.workspace_id, opportunity_id)
    OpportunityAnalyzer(db).restore(opportunity)
    db.commit()
    return serialize_map(db, opportunity.process_map)
