"""DRF permissions: workspace-scoped RBAC (SEC-4, BR-1, BR-2) and platform admins.

Every URL under /workspaces/<workspace_id>/ is checked against the caller's active
membership. Other workspaces answer 404 rather than 403, so their existence is never
revealed. The resolved context is stored on the view as `view.ctx`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from intelliflow.accounts.models import User
from intelliflow.core.enums import MembershipRole, MembershipStatus, WorkspaceStatus
from intelliflow.core.errors import NotFoundError, PermissionDeniedError
from intelliflow.workspaces.models import Membership, Workspace


@dataclass(slots=True)
class WorkspaceContext:
    workspace: Workspace
    membership: Membership
    user: User

    @property
    def is_owner(self) -> bool:
        return self.membership.role == MembershipRole.OWNER

    @property
    def workspace_id(self) -> uuid.UUID:
        return self.workspace.id


def workspace_context(user: User, workspace_id: uuid.UUID | str) -> WorkspaceContext:
    membership = (
        Membership.objects.select_related("workspace")
        .filter(
            workspace_id=workspace_id,
            user=user,
            status=MembershipStatus.ACTIVE,
            workspace__deleted_at__isnull=True,
        )
        .first()
    )
    if membership is None:  # 404 rather than 403: do not reveal other workspaces exist
        raise NotFoundError("Workspace not found.")
    if membership.workspace.status == WorkspaceStatus.SUSPENDED:
        raise PermissionDeniedError(
            "This workspace has been suspended. Please contact IntelliFlow support.",
            code="workspace_suspended",
        )
    return WorkspaceContext(workspace=membership.workspace, membership=membership, user=user)


def require_owner(ctx: WorkspaceContext) -> WorkspaceContext:
    if not ctx.is_owner:  # BR-1 / BR-2
        raise PermissionDeniedError(
            "Only the workspace owner can do this.",
            code="owner_only",
            hint="Ask the owner of this workspace to make the change.",
        )
    return ctx


class IsWorkspaceMember(BasePermission):
    """Any active member (owner or staff). Views may list `owner_actions` (action names or
    HTTP methods) that are restricted to the owner."""

    def has_permission(self, request: Request, view: Any) -> bool:
        if not request.user:
            return False
        ctx = workspace_context(request.user, view.kwargs["workspace_id"])
        owner_actions: set[str] = getattr(view, "owner_actions", set())
        action = getattr(view, "action", None)
        if action in owner_actions or request.method in owner_actions:
            require_owner(ctx)
        view.ctx = ctx
        return True


class IsWorkspaceOwner(IsWorkspaceMember):
    def has_permission(self, request: Request, view: Any) -> bool:
        super().has_permission(request, view)
        require_owner(view.ctx)
        return True


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request: Request, view: Any) -> bool:
        if not request.user:
            return False
        if not request.user.is_platform_admin:
            raise PermissionDeniedError(
                "This area is for IntelliFlow platform administrators only."
            )
        return True


def message(text: str) -> dict[str, str]:
    """The `MessageOut` body used by actions that have nothing else to return."""
    return {"message": text}
