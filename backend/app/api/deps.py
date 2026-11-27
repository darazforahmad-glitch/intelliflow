"""FastAPI dependencies: DB session, authentication and workspace-scoped RBAC (SEC-4, BR-1, BR-2)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import new_session
from app.core.errors import AuthenticationError, NotFoundError, PermissionDeniedError
from app.core.security import decode_token
from app.models import Membership, User, Workspace
from app.models.enums import MembershipRole, MembershipStatus, WorkspaceStatus

_bearer = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    db = new_session()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


DB = Annotated[Session, Depends(get_db)]


def _user_from_token(db: Session, token: str | None) -> User:
    if not token:
        raise AuthenticationError("Please sign in to continue.")
    claims = decode_token(token, "access")
    user = db.get(User, claims.user_id)
    if user is None or user.token_version != claims.token_version:
        raise AuthenticationError(
            "Your session has ended. Please sign in again.", code="session_revoked"
        )
    return user


def get_current_user(
    db: DB, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> User:
    return _user_from_token(db, credentials.credentials if credentials else None)


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_platform_admin(user: CurrentUser) -> User:
    if not user.is_platform_admin:
        raise PermissionDeniedError("This area is for IntelliFlow platform administrators only.")
    return user


PlatformAdmin = Annotated[User, Depends(get_platform_admin)]


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


def get_workspace_context(
    db: DB, user: CurrentUser, workspace_id: Annotated[uuid.UUID, Path()]
) -> WorkspaceContext:
    row = db.execute(
        select(Workspace, Membership)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(
            Workspace.id == workspace_id,
            Membership.user_id == user.id,
            Membership.status == MembershipStatus.ACTIVE,
            Workspace.deleted_at.is_(None),
        )
    ).first()
    if row is None:  # 404 rather than 403: do not reveal other workspaces exist
        raise NotFoundError("Workspace not found.")
    workspace, membership = row
    if workspace.status == WorkspaceStatus.SUSPENDED:
        raise PermissionDeniedError(
            "This workspace has been suspended. Please contact IntelliFlow support.",
            code="workspace_suspended",
        )
    return WorkspaceContext(workspace=workspace, membership=membership, user=user)


WorkspaceMember = Annotated[WorkspaceContext, Depends(get_workspace_context)]


def require_owner(ctx: WorkspaceMember) -> WorkspaceContext:
    if not ctx.is_owner:  # BR-1 / BR-2
        raise PermissionDeniedError(
            "Only the workspace owner can do this.",
            code="owner_only",
            hint="Ask the owner of this workspace to make the change.",
        )
    return ctx


WorkspaceOwner = Annotated[WorkspaceContext, Depends(require_owner)]


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
