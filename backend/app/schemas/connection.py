from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Provider = Literal["whatsapp", "gmail", "google_sheets", "webform"]


class ConnectionOut(BaseModel):
    id: uuid.UUID
    provider: str
    label: str
    mode: str
    status: str
    display_name: str | None
    external_account_id: str | None
    config: dict[str, Any]
    last_error: str | None
    created_at: datetime
    webhook_url: str | None = None
    has_credentials: bool


class SandboxIn(BaseModel):
    provider: Provider


class WhatsAppConnectIn(BaseModel):
    phone_number_id: str = Field(min_length=5, max_length=40, pattern=r"^\d+$")
    waba_id: str = Field(min_length=5, max_length=40, pattern=r"^\d+$")
    access_token: str = Field(min_length=20, max_length=1000)
    display_phone_number: str | None = Field(default=None, max_length=30)


class WebformIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class ConnectionConfigIn(BaseModel):
    config: dict[str, Any]


class SimulateIn(BaseModel):
    text: str | None = Field(default=None, max_length=4000)
    sender: str | None = Field(default=None, max_length=20)
    name: str | None = Field(default=None, max_length=80)
    subject: str | None = Field(default=None, max_length=250)
    body: str | None = Field(default=None, max_length=8000)
    fields: dict[str, Any] | None = None
