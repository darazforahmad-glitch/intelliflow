from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.run import RunOut


class AutomationVersionOut(ORMModel):
    id: uuid.UUID
    version_no: int
    definition_json: dict[str, Any]
    validated: bool
    test_passed: bool
    validation_errors: list[Any]
    source: str
    created_at: datetime


class VersionSummary(ORMModel):
    id: uuid.UUID
    version_no: int
    validated: bool
    test_passed: bool
    source: str
    created_at: datetime


class ConnectionRequirement(BaseModel):
    provider: str
    label: str
    connected: bool
    mode: str | None


class AutomationStats(BaseModel):
    runs_total: int = 0
    runs_succeeded: int = 0
    runs_failed: int = 0
    runs_waiting: int = 0
    minutes_saved: Decimal = Decimal(0)
    last_run_at: datetime | None = None


class AutomationOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: str
    status_reason: str | None
    trigger_type: str | None
    template_code: str | None
    template_name: str | None
    opportunity_id: uuid.UUID | None
    auto_send: bool
    clean_approvals: int
    auto_send_threshold: int
    estimated_minutes_per_run: Decimal
    activated_at: datetime | None
    created_at: datetime
    updated_at: datetime
    current_version: AutomationVersionOut | None
    versions: list[VersionSummary]
    connections: list[ConnectionRequirement]
    stats: AutomationStats


class AutomationListItem(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    status_reason: str | None
    trigger_type: str | None
    template_name: str | None
    auto_send: bool
    version_no: int | None
    stats: AutomationStats


class DefinitionIn(BaseModel):
    definition: dict[str, Any]


class FromTemplateIn(BaseModel):
    template_code: str = Field(min_length=2, max_length=60)


class TestIn(BaseModel):
    sample: dict[str, Any] = Field(default_factory=dict)


class TraceStep(BaseModel):
    key: str
    type: str
    title: str
    status: str
    input: dict[str, Any]
    output: dict[str, Any]
    attempts: int


class TestOut(BaseModel):
    passed: bool
    message: str
    run: RunOut
    steps: list[TraceStep]
    sandbox_records: list[dict[str, Any]]


class RollbackIn(BaseModel):
    version_no: int = Field(ge=1)


class AutoSendIn(BaseModel):
    enabled: bool


class ValidationOut(BaseModel):
    valid: bool
    issues: list[dict[str, Any]]
