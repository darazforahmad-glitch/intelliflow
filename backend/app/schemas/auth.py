from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, pattern=r"^\+?[0-9][0-9\s-]{6,19}$")
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class EmailRequest(BaseModel):
    email: EmailStr


class TokenRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)


class UpdateMeRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = Field(default=None, pattern=r"^\+?[0-9][0-9\s-]{6,19}$")


class UserOut(ORMModel):
    id: uuid.UUID
    full_name: str
    email: str
    phone: str | None
    email_verified: bool
    is_platform_admin: bool
    created_at: datetime


class MembershipOut(BaseModel):
    membership_id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_name: str
    role: str
    status: str
    workspace_status: str


class MeOut(UserOut):
    memberships: list[MembershipOut]


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type label
    expires_in: int
    user: UserOut
