"""/api/v1/workspaces: workspace CRUD, team, invitations, kill switch (REQ-AC-3..5, SAF-2)."""

from __future__ import annotations

from typing import Any

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from intelliflow.accounts.serializers import TokenSerializer
from intelliflow.core.api.permissions import IsWorkspaceMember, WorkspaceContext, message
from intelliflow.workspaces import services
from intelliflow.workspaces.serializers import (
    InvitationCreateSerializer,
    InvitationSerializer,
    WorkspaceCreateSerializer,
    WorkspaceSerializer,
    WorkspaceUpdateSerializer,
    member_out,
)

UUID_REGEX = "[0-9a-fA-F-]{36}"


def _workspace(workspace: Any, role: Any) -> dict[str, Any]:
    return WorkspaceSerializer(workspace, context={"role": role}).data


class WorkspaceViewSet(viewsets.ViewSet):
    lookup_url_kwarg = "workspace_id"
    lookup_value_regex = UUID_REGEX
    # BR-1/BR-2: only the owner changes the workspace, manages the team or pulls the kill switch.
    owner_actions = {
        "partial_update",
        "kill_switch",
        "remove_member",
        "invitations",
        "revoke_invitation",
    }
    ctx: WorkspaceContext

    def get_permissions(self):  # type: ignore[no-untyped-def]
        if self.action in {"list", "create"}:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsWorkspaceMember()]

    def list(self, request: Request) -> Response:
        return Response([_workspace(w, m.role) for w, m in services.list_for_user(request.user)])

    def create(self, request: Request) -> Response:
        body = WorkspaceCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        workspace, membership = services.create_workspace(request.user, body.validated_data)
        return Response(_workspace(workspace, membership.role), status=status.HTTP_201_CREATED)

    def retrieve(self, request: Request, workspace_id: str) -> Response:
        return Response(_workspace(self.ctx.workspace, self.ctx.membership.role))

    def partial_update(self, request: Request, workspace_id: str) -> Response:
        body = WorkspaceUpdateSerializer(data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        workspace = services.update_workspace(
            self.ctx.workspace, self.ctx.user, body.validated_data
        )
        return Response(_workspace(workspace, self.ctx.membership.role))

    @action(detail=True, methods=["post"], url_path="kill-switch")
    def kill_switch(self, request: Request, workspace_id: str) -> Response:
        paused = services.kill_switch(self.ctx.workspace, self.ctx.user)
        return Response({"paused_automations": paused})

    @action(detail=True, methods=["get"])
    def members(self, request: Request, workspace_id: str) -> Response:
        return Response([member_out(m, u) for m, u in services.list_members(self.ctx.workspace_id)])

    @action(detail=True, methods=["delete"], url_path=f"members/(?P<membership_id>{UUID_REGEX})")
    def remove_member(self, request: Request, workspace_id: str, membership_id: str) -> Response:
        services.remove_member(self.ctx.workspace_id, membership_id, self.ctx.user)
        return Response(message("The member has been removed from the workspace."))

    @action(detail=True, methods=["get", "post"])
    def invitations(self, request: Request, workspace_id: str) -> Response:
        if request.method == "GET":
            invitations = services.list_invitations(self.ctx.workspace_id)
            return Response(InvitationSerializer(invitations, many=True).data)
        body = InvitationCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        invitation = services.invite_staff(
            self.ctx.workspace,
            self.ctx.user,
            body.validated_data["email"],
            body.validated_data["role"],
        )
        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True, methods=["delete"], url_path=f"invitations/(?P<invitation_id>{UUID_REGEX})"
    )
    def revoke_invitation(
        self, request: Request, workspace_id: str, invitation_id: str
    ) -> Response:
        services.revoke_invitation(self.ctx.workspace_id, invitation_id, self.ctx.user)
        return Response(message("The invitation has been revoked."))


class InvitationViewSet(viewsets.ViewSet):
    """Public invitation preview and acceptance (the invitee may not be a member yet)."""

    lookup_field = "token"
    lookup_value_regex = "[^/]+"

    def get_permissions(self):  # type: ignore[no-untyped-def]
        return [AllowAny()] if self.action == "retrieve" else [IsAuthenticated()]

    def retrieve(self, request: Request, token: str) -> Response:
        invitation, valid = services.preview_invitation(token)
        return Response(
            {
                "workspace_name": invitation.workspace.name,
                "email": invitation.email,
                "role": invitation.role,
                "valid": valid,
            }
        )

    @action(detail=False, methods=["post"])
    def accept(self, request: Request) -> Response:
        body = TokenSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.accept_invitation(request.user, body.validated_data["token"])
        return Response(message("You have joined the workspace."))
