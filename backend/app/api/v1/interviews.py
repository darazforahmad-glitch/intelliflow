"""/workspaces/{id}/interviews: the Flow Mapper chat (UC-03)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import DB, WorkspaceMember, WorkspaceOwner
from app.api.v1.process_maps import serialize_map
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.models import InterviewSession, ProcessMap
from app.schemas.interview import (
    AnswerIn,
    InterviewCreate,
    InterviewMessageOut,
    InterviewSessionOut,
    InterviewSummaryOut,
)
from app.schemas.process import ProcessMapOut
from app.services.ai_service import AIService
from app.services.interview_agent import InterviewAgent
from app.services.opportunity_analyzer import OpportunityAnalyzer
from app.services.process_mapper import ProcessMapper

router = APIRouter(prefix="/workspaces/{workspace_id}/interviews", tags=["flow mapper"])


def _get_session(db: Session, workspace_id: uuid.UUID, session_id: uuid.UUID) -> InterviewSession:
    session = db.scalar(
        select(InterviewSession).where(
            InterviewSession.id == session_id, InterviewSession.workspace_id == workspace_id
        )
    )
    if session is None:
        raise NotFoundError("Interview not found.")
    return session


def _latest_map(db: Session, session_id: uuid.UUID) -> ProcessMap | None:
    return db.scalar(
        select(ProcessMap)
        .where(ProcessMap.session_id == session_id)
        .order_by(ProcessMap.version.desc())
        .limit(1)
    )


def _out(db: Session, session: InterviewSession) -> InterviewSessionOut:
    latest = _latest_map(db, session.id)
    return InterviewSessionOut(
        id=session.id,
        process_name=session.process_name,
        status=session.status.value,
        started_at=session.started_at,
        completed_at=session.completed_at,
        question_count=session.question_count,
        max_questions=get_settings().interview_max_questions,
        ready_for_mapping=session.ready_for_mapping,
        language=session.language,
        messages=[InterviewMessageOut.model_validate(m) for m in session.messages],
        latest_map_id=latest.id if latest else None,
    )


@router.get("", response_model=list[InterviewSummaryOut])
def list_interviews(ctx: WorkspaceMember, db: DB) -> list[InterviewSummaryOut]:
    latest = (
        select(ProcessMap.session_id, func.max(ProcessMap.version).label("v"))
        .group_by(ProcessMap.session_id)
        .subquery()
    )
    rows = db.execute(
        select(InterviewSession, ProcessMap)
        .outerjoin(latest, latest.c.session_id == InterviewSession.id)
        .outerjoin(
            ProcessMap,
            (ProcessMap.session_id == InterviewSession.id) & (ProcessMap.version == latest.c.v),
        )
        .where(InterviewSession.workspace_id == ctx.workspace_id)
        .order_by(InterviewSession.started_at.desc())
    ).all()
    return [
        InterviewSummaryOut(
            id=s.id,
            process_name=s.process_name,
            status=s.status.value,
            started_at=s.started_at,
            completed_at=s.completed_at,
            latest_map_id=m.id if m else None,
            latest_version=m.version if m else None,
        )
        for s, m in rows
    ]


@router.post("", response_model=InterviewSessionOut, status_code=status.HTTP_201_CREATED)
def start_interview(body: InterviewCreate, ctx: WorkspaceOwner, db: DB) -> InterviewSessionOut:
    agent = InterviewAgent(db, ctx.workspace, AIService(db, ctx.workspace))
    return _out(db, agent.start(ctx.user, body.process_name))


@router.get("/{session_id}", response_model=InterviewSessionOut)
def get_interview(session_id: uuid.UUID, ctx: WorkspaceMember, db: DB) -> InterviewSessionOut:
    return _out(db, _get_session(db, ctx.workspace_id, session_id))


@router.post("/{session_id}/messages", response_model=InterviewSessionOut)
def answer(
    session_id: uuid.UUID, body: AnswerIn, ctx: WorkspaceOwner, db: DB
) -> InterviewSessionOut:
    session = _get_session(db, ctx.workspace_id, session_id)
    agent = InterviewAgent(db, ctx.workspace, AIService(db, ctx.workspace))
    return _out(db, agent.answer(session, body.content))


@router.post(
    "/{session_id}/complete", response_model=ProcessMapOut, status_code=status.HTTP_201_CREATED
)
def complete(session_id: uuid.UUID, ctx: WorkspaceOwner, db: DB) -> ProcessMapOut:
    """buildProcessMap(sessionId): map + validated steps + ranked opportunities (Table 4.16)."""
    session = _get_session(db, ctx.workspace_id, session_id)
    process_map = ProcessMapper(db, AIService(db, ctx.workspace)).build(session, ctx.user)
    OpportunityAnalyzer(db).analyze(process_map, ctx.workspace.approval_threshold)
    db.commit()
    db.refresh(process_map)
    return serialize_map(db, process_map)


@router.post("/{session_id}/abandon", response_model=InterviewSessionOut)
def abandon(session_id: uuid.UUID, ctx: WorkspaceOwner, db: DB) -> InterviewSessionOut:
    session = _get_session(db, ctx.workspace_id, session_id)
    InterviewAgent(db, ctx.workspace, AIService(db, ctx.workspace)).abandon(session)
    return _out(db, session)
