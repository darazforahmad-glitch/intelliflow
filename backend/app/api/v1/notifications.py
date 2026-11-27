"""In-app notifications and Web Push subscriptions for the PWA (REQ-AP-2)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.models import Notification, PushSubscription
from app.models.base import utcnow
from app.schemas.common import MessageOut

router = APIRouter(tags=["notifications"])


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=255)
    auth: str = Field(min_length=8, max_length=255)


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000, pattern=r"^https://")
    keys: PushKeys


class EndpointIn(BaseModel):
    endpoint: str


@router.get("/notifications")
def list_notifications(
    user: CurrentUser, db: DB, unread_only: bool = False, limit: int = 30
) -> dict[str, Any]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    items = db.scalars(stmt.order_by(Notification.created_at.desc()).limit(min(limit, 100))).all()
    unread = db.scalars(
        select(Notification.id).where(
            Notification.user_id == user.id, Notification.read_at.is_(None)
        )
    ).all()
    return {
        "unread": len(unread),
        "items": [
            {
                "id": str(n.id),
                "kind": n.kind,
                "title": n.title,
                "body": n.body,
                "url": n.url,
                "workspace_id": str(n.workspace_id) if n.workspace_id else None,
                "read": n.read_at is not None,
                "created_at": n.created_at.isoformat(),
            }
            for n in items
        ],
    }


@router.post("/notifications/{notification_id}/read", response_model=MessageOut)
def mark_read(notification_id: uuid.UUID, user: CurrentUser, db: DB) -> MessageOut:
    db.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
            Notification.read_at.is_(None),
        )
        .values(read_at=utcnow())
    )
    db.commit()
    return MessageOut(message="Marked as read.")


@router.post("/notifications/read-all", response_model=MessageOut)
def mark_all_read(user: CurrentUser, db: DB) -> MessageOut:
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    db.commit()
    return MessageOut(message="All notifications marked as read.")


@router.get("/push/config")
def push_config(_user: CurrentUser) -> dict[str, Any]:
    settings = get_settings()
    return {"enabled": settings.web_push_enabled, "vapid_public_key": settings.vapid_public_key}


@router.post("/push/subscriptions", response_model=MessageOut)
def subscribe(body: PushSubscriptionIn, user: CurrentUser, db: DB, request: Request) -> MessageOut:
    existing = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if existing is None:
        existing = PushSubscription(
            user_id=user.id, endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth
        )
        db.add(existing)
    existing.user_id, existing.p256dh, existing.auth = user.id, body.keys.p256dh, body.keys.auth
    existing.user_agent = (request.headers.get("user-agent") or "")[:255]
    db.commit()
    return MessageOut(message="This device will receive approval alerts.")


@router.delete("/push/subscriptions", response_model=MessageOut)
def unsubscribe(body: EndpointIn, user: CurrentUser, db: DB) -> MessageOut:
    sub = db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint, PushSubscription.user_id == user.id
        )
    )
    if sub:
        db.delete(sub)
        db.commit()
    return MessageOut(message="Push notifications turned off for this device.")
