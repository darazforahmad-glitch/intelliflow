from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class InterviewCreate(BaseModel):
    process_name: str = Field(min_length=2, max_length=120, examples=["Order process"])


class AnswerIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class InterviewMessageOut(ORMModel):
    id: uuid.UUID
    sender: str
    content: str
    language: str | None
    created_at: datetime
    meta_json: dict[str, Any]


class InterviewSessionOut(BaseModel):
    id: uuid.UUID
    process_name: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    question_count: int
    max_questions: int
    ready_for_mapping: bool
    language: str | None
    messages: list[InterviewMessageOut]
    latest_map_id: uuid.UUID | None


class InterviewSummaryOut(BaseModel):
    id: uuid.UUID
    process_name: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    latest_map_id: uuid.UUID | None
    latest_version: int | None
