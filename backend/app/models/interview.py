"""interview_sessions (Table 4.4) and interview_messages (Table 4.5)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKey, pg_enum, utcnow
from app.models.enums import InterviewStatus, MessageSender


class InterviewSession(UUIDPrimaryKey, Base):
    __tablename__ = "interview_sessions"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    started_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    process_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[InterviewStatus] = mapped_column(
        pg_enum(InterviewStatus, "interview_status"), default=InterviewStatus.IN_PROGRESS
    )
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    completed_at: Mapped[datetime | None]
    # --- extensions: REQ-FM-2 question budget and the detected language ---
    question_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    language: Mapped[str | None] = mapped_column(String(10))
    ready_for_mapping: Mapped[bool] = mapped_column(default=False)

    messages: Mapped[list[InterviewMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="InterviewMessage.created_at",
    )


class InterviewMessage(UUIDPrimaryKey, Base):
    __tablename__ = "interview_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True
    )
    sender: Mapped[MessageSender] = mapped_column(pg_enum(MessageSender, "message_sender"))
    content: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(10))
    meta_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    session: Mapped[InterviewSession] = relationship(back_populates="messages")
