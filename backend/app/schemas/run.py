from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class StepRunOut(ORMModel):
    id: uuid.UUID
    step_key: str
    seq_no: int
    block_type: str
    status: str
    input_json: dict[str, Any] | None
    output_json: dict[str, Any] | None
    error: str | None
    attempt: int
    started_at: datetime | None
    finished_at: datetime | None


class RunOut(BaseModel):
    id: uuid.UUID
    automation_id: uuid.UUID
    automation_name: str
    version_no: int | None
    status: str
    is_test: bool
    trigger_type: str
    minutes_saved: Decimal
    summary: str | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_seconds: float | None


class ApprovalBrief(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    status: str
    created_at: datetime
    decided_at: datetime | None


class RunDetailOut(RunOut):
    steps: list[StepRunOut]
    approvals: list[ApprovalBrief]


class ApprovalOut(BaseModel):
    id: uuid.UUID
    status: str
    kind: str
    title: str
    automation_id: uuid.UUID
    automation_name: str
    run_id: uuid.UUID
    step_title: str | None
    payload: dict[str, Any]
    decision_payload: dict[str, Any] | None
    decided_by_name: str | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime
    remind_at: datetime | None
    expires_at: datetime | None


class DecisionIn(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    edited_params: dict[str, Any] | None = None
    edited_fields: dict[str, Any] | None = None
    note: str | None = Field(default=None, max_length=500)
