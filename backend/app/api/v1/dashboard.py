"""Ops Dashboard (UC-12), CSV report (REQ-DR-5) and live updates over Server-Sent Events (REQ-DR-6)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse

from app.api.deps import DB, WorkspaceMember, _user_from_token, get_workspace_context
from app.core.database import new_session
from app.services import event_bus
from app.services.reporting_service import dashboard, weekly_csv

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["dashboard"])


@router.get("/dashboard")
def read_dashboard(
    ctx: WorkspaceMember, db: DB, days: int = Query(default=7, ge=1, le=90)
) -> dict[str, Any]:
    return dashboard(db, ctx.workspace, days)


@router.get("/reports/weekly.csv")
def weekly_report(
    ctx: WorkspaceMember, db: DB, days: int = Query(default=7, ge=1, le=90)
) -> Response:
    body = weekly_csv(db, ctx.workspace, days)
    filename = f"intelliflow-report-{days}d.csv"
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _authorize_stream(workspace_id: uuid.UUID, token: str) -> None:
    db = new_session()
    try:
        user = _user_from_token(db, token)
        get_workspace_context(db, user, workspace_id)
    finally:
        db.close()


@router.get("/events")
async def stream_events(
    workspace_id: uuid.UUID, request: Request, access_token: str = Query(min_length=10)
) -> StreamingResponse:
    """EventSource cannot send headers, so the access token comes as a query parameter
    (query strings are never written to our logs)."""
    await run_in_threadpool(_authorize_stream, workspace_id, access_token)

    async def stream() -> AsyncIterator[str]:
        yield "retry: 5000\n\n"
        async for message in event_bus.subscribe(workspace_id):
            if await request.is_disconnected():
                break
            yield ": keep-alive\n\n" if message == "" else f"data: {message}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
