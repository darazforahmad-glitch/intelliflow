"""/api/v1/workspaces: workspace CRUD, team, invitations, kill switch (REQ-AC-3..5, SAF-2)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import DB, CurrentUser, WorkspaceMember, WorkspaceOwner
from app.models.enums import MembershipRole
from app.schemas.auth import TokenRequest
from app.schemas.common import MessageOut
from app.schemas.workspace import (
    InvitationCreate,
    InvitationOut,
    InvitationPreview,
    KillSwitchOut,
    MemberOut,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspaceUpdate,
)
from app.services import workspace_service

router = APIRouter(tags=["workspaces"])


def _out(workspace, role: str | None) -> WorkspaceOut:  # type: ignore[no-untyped-def]
    return WorkspaceOut.model_validate(workspace).model_copy(update={"role": role})


@router.get("/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(user: CurrentUser, db: DB) -> list[WorkspaceOut]:
    return [_out(w, m.role.value) for w, m in workspace_service.list_for_user(db, user)]


@router.post("/workspaces", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(body: WorkspaceCreate, user: CurrentUser, db: DB) -> WorkspaceOut:
    workspace, membership = workspace_service.create_workspace(db, user, body)
    return _out(workspace, membership.role.value)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(ctx: WorkspaceMember) -> WorkspaceOut:
    return _out(ctx.workspace, ctx.membership.role.value)


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(body: WorkspaceUpdate, ctx: WorkspaceOwner, db: DB) -> WorkspaceOut:
    workspace = workspace_service.update_workspace(db, ctx.workspace, ctx.user, body)
    return _out(workspace, ctx.membership.role.value)


@router.post("/workspaces/{workspace_id}/kill-switch", response_model=KillSwitchOut)
def kill_switch(ctx: WorkspaceOwner, db: DB) -> KillSwitchOut:
    return KillSwitchOut(
        paused_automations=workspace_service.kill_switch(db, ctx.workspace, ctx.user)
    )


@router.get("/workspaces/{workspace_id}/members", response_model=list[MemberOut])
def list_members(ctx: WorkspaceMember, db: DB) -> list[MemberOut]:
    return [
        MemberOut(
            membership_id=m.id,
            user_id=u.id,
            full_name=u.full_name,
            email=u.email,
            role=m.role.value,
            status=m.status.value,
            joined_at=m.created_at,
        )
        for m, u in workspace_service.list_members(db, ctx.workspace_id)
    ]


@router.delete("/workspaces/{workspace_id}/members/{membership_id}", response_model=MessageOut)
def remove_member(membership_id: uuid.UUID, ctx: WorkspaceOwner, db: DB) -> MessageOut:
    workspace_service.remove_member(db, ctx.workspace_id, membership_id, ctx.user)
    return MessageOut(message="The member has been removed from the workspace.")


@router.get("/workspaces/{workspace_id}/invitations", response_model=list[InvitationOut])
def list_invitations(ctx: WorkspaceOwner, db: DB) -> list[InvitationOut]:
    return [
        InvitationOut.model_validate(i)
        for i in workspace_service.list_invitations(db, ctx.workspace_id)
    ]


@router.post(
    "/workspaces/{workspace_id}/invitations",
    response_model=InvitationOut,
    status_code=status.HTTP_201_CREATED,
)
def invite(body: InvitationCreate, ctx: WorkspaceOwner, db: DB) -> InvitationOut:
    invitation = workspace_service.invite_staff(
        db, ctx.workspace, ctx.user, body.email, MembershipRole(body.role)
    )
    return InvitationOut.model_validate(invitation)


@router.delete("/workspaces/{workspace_id}/invitations/{invitation_id}", response_model=MessageOut)
def revoke_invitation(invitation_id: uuid.UUID, ctx: WorkspaceOwner, db: DB) -> MessageOut:
    workspace_service.revoke_invitation(db, ctx.workspace_id, invitation_id, ctx.user)
    return MessageOut(message="The invitation has been revoked.")


@router.get("/invitations/{token}", response_model=InvitationPreview)
def preview_invitation(token: str, db: DB) -> InvitationPreview:
    invitation, valid = workspace_service.preview_invitation(db, token)
    return InvitationPreview(
        workspace_name=invitation.workspace.name,
        email=invitation.email,
        role=invitation.role.value,
        valid=valid,
    )


@router.post("/invitations/accept", response_model=MessageOut)
def accept_invitation(body: TokenRequest, user: CurrentUser, db: DB) -> MessageOut:
    workspace_service.accept_invitation(db, user, body.token)
    return MessageOut(message="You have joined the workspace.")
