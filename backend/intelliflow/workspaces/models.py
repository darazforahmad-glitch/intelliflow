"""Workspaces (Table 4.2), memberships (Table 4.3) and staff invitations (REQ-AC-5)."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

from intelliflow.core.enums import MembershipRole, MembershipStatus, WorkspaceStatus
from intelliflow.core.models import CreatedModel, choices_check


class Workspace(CreatedModel):
    name = models.CharField(max_length=120)
    business_type = models.CharField(max_length=60, null=True, blank=True)
    language_pref = models.CharField(max_length=10, default="en")  # en | ur | roman-ur
    timezone = models.CharField(max_length=40, default="Asia/Karachi")
    ai_credit_limit = models.IntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=WorkspaceStatus.choices, default=WorkspaceStatus.ACTIVE
    )
    # --- extensions: BR-5 owner-defined approval amount, suspension, BR-7 deletion ---
    approval_threshold = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("10000")
    )
    currency = models.CharField(max_length=3, default="PKR")
    suspended_reason = models.TextField(null=True, blank=True)
    settings_json = models.JSONField(default=dict, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "workspaces"
        constraints = [
            choices_check("workspaces", "status", WorkspaceStatus),
        ]

    def __str__(self) -> str:
        return self.name


class Membership(CreatedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=MembershipRole.choices)
    status = models.CharField(
        max_length=10, choices=MembershipStatus.choices, default=MembershipStatus.ACTIVE
    )

    class Meta:
        db_table = "memberships"
        constraints = [
            choices_check("memberships", "role", MembershipRole),
            choices_check("memberships", "status", MembershipStatus),
            models.UniqueConstraint(
                fields=["user", "workspace"], name="uq_memberships_user_id_workspace_id"
            ),
        ]


class Invitation(CreatedModel):
    """E-mail invitation for a staff member (REQ-AC-5). Only the token hash is stored."""

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="invitations")
    email = models.CharField(max_length=255)
    role = models.CharField(max_length=10, choices=MembershipRole.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="invited_by",
        related_name="+",
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "invitations"
        constraints = [
            choices_check("invitations", "role", MembershipRole),
        ]
