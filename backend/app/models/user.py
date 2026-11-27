"""users (Table 4.1) and one-time user tokens (e-mail verification, password reset)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, UUIDPrimaryKey, pg_enum
from app.models.enums import TokenPurpose

if TYPE_CHECKING:
    from app.models.workspace import Membership


class User(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)  # stored lower-case
    phone: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))  # Argon2id (SEC-1)
    email_verified: Mapped[bool] = mapped_column(default=False)
    # --- extensions to Table 4.1 needed by REQ-AC-2/REQ-AC-4 and session revocation ---
    is_platform_admin: Mapped[bool] = mapped_column(default=False)
    failed_login_attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    locked_until: Mapped[datetime | None]
    token_version: Mapped[int] = mapped_column(default=0)
    last_login_at: Mapped[datetime | None]

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # never include PII beyond the id
        return f"<User {self.id}>"


class UserToken(UUIDPrimaryKey, CreatedAt, Base):
    """Single-use token; only its SHA-256 hash is stored."""

    __tablename__ = "user_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[TokenPurpose] = mapped_column(pg_enum(TokenPurpose, "token_purpose"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
