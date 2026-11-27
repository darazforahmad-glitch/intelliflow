from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

StepTypeLiteral = Literal["start", "manual", "automated", "human_only", "end"]
AppLiteral = Literal[
    "whatsapp",
    "excel",
    "google_sheets",
    "gmail",
    "paper",
    "phone",
    "webform",
    "website",
    "bank",
    "courier",
    "pos",
    "other",
    "none",
]


class StepOut(BaseModel):
    id: uuid.UUID
    key: str
    seq_no: int
    title: str
    actor: str | None
    action: str | None
    step_type: str
    app: str | None
    minutes_per_run: Decimal | None
    runs_per_week: int | None
    weekly_minutes: Decimal
    is_manual: bool
    predecessor_key: str | None
    involves_customer_messaging: bool
    involves_money: bool
    support_status: str | None


class TemplateRef(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    category: str | None
    required_connections: list[str]


class OpportunityOut(BaseModel):
    id: uuid.UUID
    rank: int | None
    score: Decimal
    status: str
    fit: Decimal
    risk: Decimal
    minutes_saved_per_week: Decimal
    minutes_saved_per_day: Decimal
    reason: str
    step_id: uuid.UUID
    step_key: str
    step_title: str
    template: TemplateRef | None
    automation_id: uuid.UUID | None = None


class MapVersionRef(BaseModel):
    id: uuid.UUID
    version: int
    created_at: datetime
    change_note: str | None


class ProcessMapOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    name: str
    version: int
    is_latest: bool
    created_at: datetime
    change_note: str | None
    graph_json: dict[str, Any]
    steps: list[StepOut]
    total_weekly_minutes: Decimal
    manual_weekly_minutes: Decimal
    opportunities: list[OpportunityOut]
    other_opportunities: list[OpportunityOut]
    dismissed_opportunities: list[OpportunityOut]
    unsupported_steps: list[str]
    versions: list[MapVersionRef]


class ProcessMapSummary(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    name: str
    version: int
    created_at: datetime
    step_count: int
    manual_weekly_minutes: Decimal
    top_opportunity: str | None


class Position(BaseModel):
    x: float
    y: float


class StepIn(BaseModel):
    key: str | None = Field(default=None, max_length=30)
    title: str = Field(min_length=2, max_length=150)
    actor: str = Field(default="Owner", min_length=1, max_length=80)
    action: str | None = Field(default=None, max_length=1000)
    step_type: StepTypeLiteral
    app: AppLiteral = "other"
    minutes_per_run: Decimal = Field(default=Decimal(0), ge=0, le=600)
    runs_per_week: int = Field(default=0, ge=0, le=10000)
    involves_customer_messaging: bool = False
    involves_money: bool = False


class MapVersionIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    note: str | None = Field(default=None, max_length=255)
    steps: list[StepIn] = Field(min_length=3, max_length=40)
    positions: dict[str, Position] | None = None
