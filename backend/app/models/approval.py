"""approval_tasks (Table 4.15). Decisions are immutable once recorded (BR-9)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, UUIDPrimaryKey, pg_enum
from app.models.enums import ApprovalKind, ApprovalStatus
from app.models.run import Run, StepRun


class ApprovalTask(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "approval_tasks"
    __table_args__ = (Index("ix_approval_tasks_workspace_status", "workspace_id", "status"),)

    step_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("step_runs.id", ondelete="CASCADE"), index=True
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )  # NULL = role-based: every active member of the workspace
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # {"title", "reason", "input", "ai_output", "proposed_action", "editable_fields"}
    payload_json: Mapped[dict[str, Any]]
    status: Mapped[ApprovalStatus] = mapped_column(
        pg_enum(ApprovalStatus, "approval_status"), default=ApprovalStatus.PENDING
    )
    expires_at: Mapped[datetime | None]
    # --- extensions ---
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    automation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automations.id", ondelete="CASCADE")
    )
    kind: Mapped[ApprovalKind] = mapped_column(pg_enum(ApprovalKind, "approval_kind"))
    title: Mapped[str] = mapped_column(String(150))
    decision_payload_json: Mapped[dict[str, Any] | None]  # the edited proposed action, if any
    decision_note: Mapped[str | None] = mapped_column(Text)
    remind_at: Mapped[datetime | None]
    reminded_at: Mapped[datetime | None]
    decided_at: Mapped[datetime | None]

    run: Mapped[Run] = relationship()
    step_run: Mapped[StepRun] = relationship()
