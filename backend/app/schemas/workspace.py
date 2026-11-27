from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import available_timezones

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel

Language = Literal["en", "ur", "roman-ur"]
_TIMEZONES = available_timezones()


def _check_timezone(value: str | None) -> str | None:
    if value is not None and value not in _TIMEZONES:
        raise ValueError("Unknown timezone, e.g. use Asia/Karachi")
    return value


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    business_type: str | None = Field(default=None, max_length=60)
    language_pref: Language = "en"
    timezone: str = "Asia/Karachi"

    _tz = field_validator("timezone")(_check_timezone)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    business_type: str | None = Field(default=None, max_length=60)
    language_pref: Language | None = None
    timezone: str | None = None
    approval_threshold: Decimal | None = Field(default=None, ge=0, le=100_000_000)

    _tz = field_validator("timezone")(_check_timezone)


class WorkspaceOut(ORMModel):
    id: uuid.UUID
    name: str
    business_type: str | None
    language_pref: str
    timezone: str
    status: str
    approval_threshold: Decimal
    currency: str
    ai_credit_limit: int | None
    created_at: datetime
    role: str | None = None


class MemberOut(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    email: str
    role: str
    status: str
    joined_at: datetime


class InvitationCreate(BaseModel):
    email: EmailStr
    role: Literal["staff"] = "staff"


class InvitationOut(ORMModel):
    id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class InvitationPreview(BaseModel):
    workspace_name: str
    email: str
    role: str
    valid: bool


class KillSwitchOut(BaseModel):
    paused_automations: int
