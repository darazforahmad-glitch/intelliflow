"""Notifies people through in-app notifications, Web Push (VAPID) and e-mail (REQ-AP-2)."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.transaction import on_commit
from app.models import Membership, Notification, PushSubscription, User
from app.models.enums import MembershipRole, MembershipStatus
from app.services.email_service import queue_email

logger = logging.getLogger(__name__)


def workspace_members(
    db: Session, workspace_id: uuid.UUID, *, roles: Iterable[MembershipRole] | None = None
) -> list[User]:
    stmt = (
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.workspace_id == workspace_id, Membership.status == MembershipStatus.ACTIVE
        )
    )
    if roles is not None:
        stmt = stmt.where(Membership.role.in_(list(roles)))
    return list(db.scalars(stmt).unique())


def notify(
    db: Session,
    users: Iterable[User],
    *,
    workspace_id: uuid.UUID | None,
    kind: str,
    title: str,
    body: str,
    url: str | None = None,
    email: bool = True,
    push: bool = True,
) -> list[Notification]:
    settings = get_settings()
    created: list[Notification] = []
    for user in users:
        notification = Notification(
            user_id=user.id, workspace_id=workspace_id, kind=kind, title=title, body=body, url=url
        )
        db.add(notification)
        created.append(notification)
        if email:
            link = f"{settings.frontend_url}{url}" if url else settings.frontend_url
            queue_email(
                db,
                to=user.email,
                subject=f"IntelliFlow: {title}",
                body=f"{body}\n\nOpen: {link}\n",
                category=kind,
            )
        if push and settings.web_push_enabled:
            user_id = user.id
            payload = json.dumps({"title": title, "body": body, "url": url or "/", "kind": kind})

            def _dispatch(uid: uuid.UUID = user_id, data: str = payload) -> None:
                from app.worker.tasks import send_push

                send_push.delay(str(uid), data)

            on_commit(db, _dispatch)
    return created


def send_web_push(db: Session, user_id: uuid.UUID, payload: str) -> int:
    """Deliver a push payload to every subscription of a user; prune dead endpoints."""
    from pywebpush import WebPushException, webpush

    settings = get_settings()
    sent = 0
    for sub in db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)):
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
                ttl=3600,
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in {404, 410}:
                db.delete(sub)
            else:
                logger.warning("web push failed", extra={"status": status})
    return sent
