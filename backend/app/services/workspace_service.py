"""Workspaces, team management (invite/remove staff) and the kill switch (REQ-AC-3..5, SAF-2)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.core.security import generate_url_token, hash_url_token
from app.models import Automation, Invitation, Membership, User, Workspace
from app.models.base import utcnow
from app.models.enums import AutomationStatus, MembershipRole, MembershipStatus
from app.schemas.workspace import WorkspaceCreate, WorkspaceUpdate
from app.services import audit_service, event_bus
from app.services.auth_service import normalize_email
from app.services.email_service import queue_email


def create_workspace(
    db: Session, user: User, data: WorkspaceCreate
) -> tuple[Workspace, Membership]:
    settings = get_settings()
    workspace = Workspace(
        name=data.name.strip(),
        business_type=(data.business_type or "").strip() or None,
        language_pref=data.language_pref,
        timezone=data.timezone,
        ai_credit_limit=settings.default_ai_credit_limit,
        approval_threshold=Decimal(settings.default_approval_threshold),
    )
    db.add(workspace)
    db.flush()
    membership = Membership(
        user_id=user.id,
        workspace_id=workspace.id,
        role=MembershipRole.OWNER,
        status=MembershipStatus.ACTIVE,
    )
    db.add(membership)
    audit_service.record(
        db,
        "workspace.created",
        workspace_id=workspace.id,
        actor_id=user.id,
        entity_type="workspace",
        entity_id=workspace.id,
    )
    db.commit()
    return workspace, membership


def list_for_user(db: Session, user: User) -> list[tuple[Workspace, Membership]]:
    rows = db.execute(
        select(Workspace, Membership)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(
            Membership.user_id == user.id,
            Membership.status == MembershipStatus.ACTIVE,
            Workspace.deleted_at.is_(None),
        )
        .order_by(Workspace.created_at)
    ).all()
    return [(w, m) for w, m in rows]


def update_workspace(
    db: Session, workspace: Workspace, actor: User, data: WorkspaceUpdate
) -> Workspace:
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(workspace, field, value)
    audit_service.record(
        db,
        "workspace.updated",
        workspace_id=workspace.id,
        actor_id=actor.id,
        entity_type="workspace",
        entity_id=workspace.id,
        data={"fields": sorted(changes)},
    )
    db.commit()
    return workspace


def list_members(db: Session, workspace_id: uuid.UUID) -> list[tuple[Membership, User]]:
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.workspace_id == workspace_id, Membership.status != MembershipStatus.REMOVED
        )
        .order_by(Membership.created_at)
    ).all()
    return [(m, u) for m, u in rows]


def invite_staff(
    db: Session, workspace: Workspace, actor: User, email: str, role: MembershipRole
) -> Invitation:
    settings = get_settings()
    email = normalize_email(email)
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user:
        membership = db.scalar(
            select(Membership).where(
                Membership.workspace_id == workspace.id, Membership.user_id == existing_user.id
            )
        )
        if membership and membership.status == MembershipStatus.ACTIVE:
            raise ConflictError(
                "This person is already a member of the workspace.", code="already_member"
            )
        if membership is None:
            db.add(
                Membership(
                    user_id=existing_user.id,
                    workspace_id=workspace.id,
                    role=role,
                    status=MembershipStatus.INVITED,
                )
            )
        else:
            membership.status = MembershipStatus.INVITED
            membership.role = role
    # Revoke older open invitations for the same address.
    for old in db.scalars(
        select(Invitation).where(
            Invitation.workspace_id == workspace.id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
    ):
        old.revoked_at = utcnow()
    token, token_hash = generate_url_token()
    invitation = Invitation(
        workspace_id=workspace.id,
        email=email,
        role=role,
        token_hash=token_hash,
        invited_by=actor.id,
        expires_at=utcnow() + timedelta(days=settings.invitation_ttl_days),
    )
    db.add(invitation)
    queue_email(
        db,
        to=email,
        subject=f"{actor.full_name} invited you to {workspace.name} on IntelliFlow",
        body=f"{actor.full_name} has invited you to join '{workspace.name}' on IntelliFlow as "
        f"{role.value}.\n\nAccept the invitation: {settings.frontend_url}/invite?token={token}\n\n"
        f"The invitation expires in {settings.invitation_ttl_days} days.",
        category="invitation",
    )
    audit_service.record(
        db,
        "member.invited",
        workspace_id=workspace.id,
        actor_id=actor.id,
        entity_type="invitation",
        data={"role": role.value},
    )
    db.commit()
    return invitation


def _open_invitation(db: Session, token: str) -> Invitation:
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == hash_url_token(token)))
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


def preview_invitation(db: Session, token: str) -> tuple[Invitation, bool]:
    try:
        return _open_invitation(db, token), True
    except ValidationFailedError:
        invitation = db.scalar(
            select(Invitation).where(Invitation.token_hash == hash_url_token(token))
        )
        if invitation is None:
            raise NotFoundError("Invitation not found.") from None
        return invitation, False


def accept_invitation(db: Session, user: User, token: str) -> Membership:
    invitation = _open_invitation(db, token)
    if normalize_email(user.email) != invitation.email:
        raise PermissionDeniedError(
            "This invitation was sent to a different e-mail address.",
            code="invitation_email_mismatch",
            hint=f"Sign in with {invitation.email} to accept it.",
        )
    membership = db.scalar(
        select(Membership).where(
            Membership.workspace_id == invitation.workspace_id, Membership.user_id == user.id
        )
    )
    if membership is None:
        membership = Membership(
            user_id=user.id, workspace_id=invitation.workspace_id, role=invitation.role
        )
        db.add(membership)
    membership.status = MembershipStatus.ACTIVE
    membership.role = invitation.role
    invitation.accepted_at = utcnow()
    audit_service.record(
        db,
        "member.joined",
        workspace_id=invitation.workspace_id,
        actor_id=user.id,
        entity_type="membership",
    )
    db.commit()
    return membership


def list_invitations(db: Session, workspace_id: uuid.UUID) -> list[Invitation]:
    return list(
        db.scalars(
            select(Invitation)
            .where(Invitation.workspace_id == workspace_id)
            .order_by(Invitation.created_at.desc())
        )
    )


def revoke_invitation(
    db: Session, workspace_id: uuid.UUID, invitation_id: uuid.UUID, actor: User
) -> None:
    invitation = db.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id, Invitation.workspace_id == workspace_id
        )
    )
    if invitation is None:
        raise NotFoundError("Invitation not found.")
    invitation.revoked_at = invitation.revoked_at or utcnow()
    audit_service.record(
        db,
        "member.invitation_revoked",
        workspace_id=workspace_id,
        actor_id=actor.id,
        entity_type="invitation",
        entity_id=invitation_id,
    )
    db.commit()


def remove_member(
    db: Session, workspace_id: uuid.UUID, membership_id: uuid.UUID, actor: User
) -> None:
    membership = db.scalar(
        select(Membership).where(
            Membership.id == membership_id, Membership.workspace_id == workspace_id
        )
    )
    if membership is None or membership.status == MembershipStatus.REMOVED:
        raise NotFoundError("Member not found.")
    if membership.role == MembershipRole.OWNER:
        raise PermissionDeniedError(
            "The workspace owner cannot be removed.", code="cannot_remove_owner"
        )
    membership.status = MembershipStatus.REMOVED
    audit_service.record(
        db,
        "member.removed",
        workspace_id=workspace_id,
        actor_id=actor.id,
        entity_type="membership",
        entity_id=membership_id,
    )
    db.commit()


def kill_switch(db: Session, workspace: Workspace, actor: User) -> int:
    """SAF-2: pause every running automation of the workspace immediately."""
    automations = db.scalars(
        select(Automation).where(
            Automation.workspace_id == workspace.id, Automation.status == AutomationStatus.ACTIVE
        )
    ).all()
    for automation in automations:
        automation.status = AutomationStatus.PAUSED
        automation.status_reason = "Paused by the workspace kill switch."
    audit_service.record(
        db,
        "workspace.kill_switch",
        workspace_id=workspace.id,
        actor_id=actor.id,
        entity_type="workspace",
        entity_id=workspace.id,
        data={"paused": len(automations)},
    )
    db.commit()
    event_bus.publish(workspace.id, "automation.updated", {"kill_switch": True})
    return len(automations)
