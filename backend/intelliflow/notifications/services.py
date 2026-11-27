"""Notifies people through in-app notifications, Web Push (VAPID) and e-mail (REQ-AP-2)."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterable

from django.conf import settings
from django.db import transaction

from intelliflow.accounts.models import User
from intelliflow.core.enums import MembershipRole, MembershipStatus
from intelliflow.notifications.email import queue_email
from intelliflow.notifications.models import Notification, PushSubscription

logger = logging.getLogger(__name__)


def workspace_members(
    workspace_id: uuid.UUID, *, roles: Iterable[MembershipRole] | None = None
) -> list[User]:
    members = User.objects.filter(
        memberships__workspace_id=workspace_id, memberships__status=MembershipStatus.ACTIVE
    )
    if roles is not None:
        members = members.filter(memberships__role__in=list(roles))
    return list(members.distinct())


def notify(
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
    created: list[Notification] = []
    for user in users:
        created.append(
            Notification.objects.create(
                user=user, workspace_id=workspace_id, kind=kind, title=title, body=body, url=url
            )
        )
        if email:
            link = f"{settings.FRONTEND_URL}{url}" if url else settings.FRONTEND_URL
            queue_email(
                to=user.email,
                subject=f"IntelliFlow: {title}",
                body=f"{body}\n\nOpen: {link}\n",
                category=kind,
            )
        if push and settings.WEB_PUSH_ENABLED:
            payload = json.dumps({"title": title, "body": body, "url": url or "/", "kind": kind})

            def _dispatch(uid: str = str(user.id), data: str = payload) -> None:
                from intelliflow.notifications.tasks import send_push

                send_push.delay(uid, data)

            transaction.on_commit(_dispatch)
    return created


def send_web_push(user_id: uuid.UUID | str, payload: str) -> int:
    """Deliver a push payload to every subscription of a user; prune dead endpoints."""
    from pywebpush import WebPushException, webpush

    sent = 0
    for sub in PushSubscription.objects.filter(user_id=user_id):
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
                ttl=3600,
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in {404, 410}:
                sub.delete()
            else:
                logger.warning("web push failed", extra={"status": status})
    return sent
