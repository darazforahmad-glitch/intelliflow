"""In-app notifications, Web Push subscriptions (REQ-AP-2) and the e-mail outbox."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from intelliflow.core.models import CreatedModel


class Notification(CreatedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    kind = models.CharField(max_length=40)  # approval.created, automation.error ...
    title = models.CharField(max_length=150)
    body = models.TextField()
    url = models.CharField(max_length=255, null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications"
        indexes = [
            models.Index(fields=["user", "created_at"], name="ix_notifications_user_created")
        ]


class PushSubscription(CreatedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    endpoint = models.TextField(unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "push_subscriptions"


class EmailMessage(CreatedModel):
    """Outbox of every e-mail the platform sends (verification, invites, approvals)."""

    to_address = models.CharField(max_length=255, db_index=True)
    subject = models.CharField(max_length=255)
    body_text = models.TextField()
    category = models.CharField(max_length=40)
    status = models.CharField(max_length=20, default="queued")  # queued | sent | failed
    error = models.TextField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "email_messages"
