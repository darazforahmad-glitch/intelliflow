"""workspaces (Table 4.2), memberships (Table 4.3) and invitations."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, UUIDPrimaryKey, pg_enum
from app.models.enums import MembershipRole, MembershipStatus, WorkspaceStatus

if TYPE_CHECKING:
    from app.models.user import User


class Workspace(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(120))
    business_type: Mapped[str | None] = mapped_column(String(60))
    language_pref: Mapped[str] = mapped_column(String(10), default="en")  # en | ur | roman-ur
    timezone: Mapped[str] = mapped_column(String(40), default="Asia/Karachi")
    ai_credit_limit: Mapped[int | None]
    status: Mapped[WorkspaceStatus] = mapped_column(
        pg_enum(WorkspaceStatus, "workspace_status"), default=WorkspaceStatus.ACTIVE
    )
    # --- extensions: BR-5 owner-defined approval amount, suspension, BR-7 deletion ---
    approval_threshold: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("10000"))
    currency: Mapped[str] = mapped_column(String(3), default="PKR")
    suspended_reason: Mapped[str | None] = mapped_column(Text)
    settings_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    deleted_at: Mapped[datetime | None]

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class Membership(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "workspace_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MembershipRole] = mapped_column(pg_enum(MembershipRole, "membership_role"))
    status: Mapped[MembershipStatus] = mapped_column(
        pg_enum(MembershipStatus, "membership_status"), default=MembershipStatus.ACTIVE
    )

    user: Mapped[User] = relationship(back_populates="memberships")
    workspace: Mapped[Workspace] = relationship(back_populates="memberships")


class Invitation(UUIDPrimaryKey, CreatedAt, Base):
    """E-mail invitation for a staff member (REQ-AC-5). Only the token hash is stored."""

    __tablename__ = "invitations"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(255))
    role: Mapped[MembershipRole] = mapped_column(pg_enum(MembershipRole, "membership_role"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]

    workspace: Mapped[Workspace] = relationship()
