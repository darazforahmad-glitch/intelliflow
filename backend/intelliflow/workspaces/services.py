"""Workspaces, team management (invite/remove staff) and the kill switch (REQ-AC-3..5, SAF-2)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction

from intelliflow.accounts.models import User
from intelliflow.accounts.services import normalize_email
from intelliflow.audit import services as audit_service
from intelliflow.automations.models import Automation
from intelliflow.core.enums import AutomationStatus, MembershipRole, MembershipStatus
from intelliflow.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from intelliflow.core.models import utcnow
from intelliflow.core.security import generate_url_token, hash_url_token
from intelliflow.notifications import event_bus
from intelliflow.notifications.email import queue_email
from intelliflow.workspaces.models import Invitation, Membership, Workspace


@transaction.atomic
def create_workspace(user: User, data: dict[str, Any]) -> tuple[Workspace, Membership]:
    workspace = Workspace.objects.create(
        name=data["name"].strip(),
        business_type=(data.get("business_type") or "").strip() or None,
        language_pref=data.get("language_pref", "en"),
        timezone=data.get("timezone", "Asia/Karachi"),
        ai_credit_limit=settings.DEFAULT_AI_CREDIT_LIMIT,
        approval_threshold=Decimal(settings.DEFAULT_APPROVAL_THRESHOLD),
    )
    membership = Membership.objects.create(
        user=user, workspace=workspace, role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE
    )
    audit_service.record(
        "workspace.created",
        workspace_id=workspace.id,
        actor_id=user.id,
        entity_type="workspace",
        entity_id=workspace.id,
    )
    return workspace, membership


def list_for_user(user: User) -> list[tuple[Workspace, Membership]]:
    memberships = (
        Membership.objects.select_related("workspace")
        .filter(user=user, status=MembershipStatus.ACTIVE, workspace__deleted_at__isnull=True)
        .order_by("workspace__created_at")
    )
    return [(m.workspace, m) for m in memberships]


@transaction.atomic
def update_workspace(workspace: Workspace, actor: User, changes: dict[str, Any]) -> Workspace:
    changes = {field: value for field, value in changes.items() if value is not None}
    for field, value in changes.items():
        setattr(workspace, field, value)
    workspace.save()
    audit_service.record(
        "workspace.updated",
        workspace_id=workspace.id,
        actor_id=actor.id,
        entity_type="workspace",
        entity_id=workspace.id,
        data={"fields": sorted(changes)},
    )
    return workspace


def list_members(workspace_id: uuid.UUID) -> list[tuple[Membership, User]]:
    memberships = (
        Membership.objects.select_related("user")
        .filter(workspace_id=workspace_id)
        .exclude(status=MembershipStatus.REMOVED)
        .order_by("created_at")
    )
    return [(m, m.user) for m in memberships]


@transaction.atomic
def invite_staff(workspace: Workspace, actor: User, email: str, role: str) -> Invitation:
    role = MembershipRole(role)
    email = normalize_email(email)
    existing_user = User.objects.filter(email=email).first()
    if existing_user:
        membership = Membership.objects.filter(workspace=workspace, user=existing_user).first()
        if membership and membership.status == MembershipStatus.ACTIVE:
            raise ConflictError(
                "This person is already a member of the workspace.", code="already_member"
            )
        if membership is None:
            Membership.objects.create(
                user=existing_user,
                workspace=workspace,
                role=role,
                status=MembershipStatus.INVITED,
            )
        else:
            membership.status = MembershipStatus.INVITED
            membership.role = role
            membership.save(update_fields=["status", "role"])
    # Revoke older open invitations for the same address.
    Invitation.objects.filter(
        workspace=workspace, email=email, accepted_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=utcnow())
    token, token_hash = generate_url_token()
    invitation = Invitation.objects.create(
        workspace=workspace,
        email=email,
        role=role,
        token_hash=token_hash,
        invited_by=actor,
        expires_at=utcnow() + timedelta(days=settings.INVITATION_TTL_DAYS),
    )
    queue_email(
        to=email,
        subject=f"{actor.full_name} invited you to {workspace.name} on IntelliFlow",
        body=f"{actor.full_name} has invited you to join '{workspace.name}' on IntelliFlow as "
        f"{role.value}.\n\nAccept the invitation: {settings.FRONTEND_URL}/invite?token={token}\n\n"
        f"The invitation expires in {settings.INVITATION_TTL_DAYS} days.",
        category="invitation",
    )
    audit_service.record(
        "member.invited",
        workspace_id=workspace.id,
        actor_id=actor.id,
        entity_type="invitation",
        data={"role": role.value},
    )
    return invitation


def _open_invitation(token: str) -> Invitation:
    invitation = (
        Invitation.objects.select_related("workspace")
        .filter(token_hash=hash_url_token(token))
        .first()
    )
    if (
        invitation is None
        or invitation.revoked_at
        or invitation.accepted_at
        or invitation.expires_at < utcnow()
    ):
        raise ValidationFailedError(
            "This invitation is invalid or has expired.",
            code="invalid_invitation",
            hint="Ask the workspace owner to send a new invitation.",
        )
    return invitation


def preview_invitation(token: str) -> tuple[Invitation, bool]:
    try:
        return _open_invitation(token), True
    except ValidationFailedError:
        invitation = (
            Invitation.objects.select_related("workspace")
            .filter(token_hash=hash_url_token(token))
            .first()
        )
        if invitation is None:
            raise NotFoundError("Invitation not found.") from None
        return invitation, False


@transaction.atomic
def accept_invitation(user: User, token: str) -> Membership:
    invitation = _open_invitation(token)
    if normalize_email(user.email) != invitation.email:
        raise PermissionDeniedError(
            "This invitation was sent to a different e-mail address.",
            code="invitation_email_mismatch",
            hint=f"Sign in with {invitation.email} to accept it.",
        )
    membership = Membership.objects.filter(
        workspace_id=invitation.workspace_id, user=user
    ).first() or Membership(user=user, workspace_id=invitation.workspace_id)
    membership.status = MembershipStatus.ACTIVE
    membership.role = invitation.role
    membership.save()
    invitation.accepted_at = utcnow()
    invitation.save(update_fields=["accepted_at"])
    audit_service.record(
        "member.joined",
        workspace_id=invitation.workspace_id,
        actor_id=user.id,
        entity_type="membership",
    )
    return membership


def list_invitations(workspace_id: uuid.UUID) -> list[Invitation]:
    return list(Invitation.objects.filter(workspace_id=workspace_id).order_by("-created_at"))


@transaction.atomic
def revoke_invitation(workspace_id: uuid.UUID, invitation_id: uuid.UUID, actor: User) -> None:
    invitation = Invitation.objects.filter(id=invitation_id, workspace_id=workspace_id).first()
    if invitation is None:
        raise NotFoundError("Invitation not found.")
    invitation.revoked_at = invitation.revoked_at or utcnow()
    invitation.save(update_fields=["revoked_at"])
    audit_service.record(
        "member.invitation_revoked",
        workspace_id=workspace_id,
        actor_id=actor.id,
        entity_type="invitation",
        entity_id=invitation_id,
    )


@transaction.atomic
def remove_member(workspace_id: uuid.UUID, membership_id: uuid.UUID, actor: User) -> None:
    membership = Membership.objects.filter(id=membership_id, workspace_id=workspace_id).first()
    if membership is None or membership.status == MembershipStatus.REMOVED:
        raise NotFoundError("Member not found.")
    if membership.role == MembershipRole.OWNER:
        raise PermissionDeniedError(
            "The workspace owner cannot be removed.", code="cannot_remove_owner"
        )
    membership.status = MembershipStatus.REMOVED
    membership.save(update_fields=["status"])
    audit_service.record(
        "member.removed",
        workspace_id=workspace_id,
        actor_id=actor.id,
        entity_type="membership",
        entity_id=membership_id,
    )


def kill_switch(workspace: Workspace, actor: User) -> int:
    """SAF-2: pause every running automation of the workspace immediately."""
    with transaction.atomic():
        paused = Automation.objects.filter(
            workspace=workspace, status=AutomationStatus.ACTIVE
        ).update(
            status=AutomationStatus.PAUSED,
            status_reason="Paused by the workspace kill switch.",
            updated_at=utcnow(),
        )
        audit_service.record(
            "workspace.kill_switch",
            workspace_id=workspace.id,
            actor_id=actor.id,
            entity_type="workspace",
            entity_id=workspace.id,
            data={"paused": paused},
        )
    event_bus.publish(workspace.id, "automation.updated", {"kill_switch": True})
    return paused
