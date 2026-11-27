"""Development-only helpers. Mounted only when ENVIRONMENT is development or test."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DB
from app.models import EmailMessage

router = APIRouter(prefix="/dev", tags=["development"])


@router.get("/outbox")
def outbox(
    db: DB, to: str | None = None, limit: int = Query(default=20, ge=1, le=100)
) -> list[dict[str, Any]]:
    """The console e-mail backend's 'inbox', so verification links work without SMTP."""
    stmt = select(EmailMessage)
    if to:
        stmt = stmt.where(EmailMessage.to_address == to.strip().lower())
    messages = db.scalars(stmt.order_by(EmailMessage.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": str(m.id),
            "to": m.to_address,
            "subject": m.subject,
            "body": m.body_text,
            "category": m.category,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]
