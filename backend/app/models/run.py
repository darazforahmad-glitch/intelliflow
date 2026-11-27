"""runs (Table 4.13) and step_runs (Table 4.14)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ForeignKey,
    Index,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.automation import Automation, AutomationVersion
from app.models.base import Base, CreatedAt, UUIDPrimaryKey, pg_enum
from app.models.enums import RunStatus, StepRunStatus


class Run(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "runs"
    # Idempotency (REQ-WE-3): one run per provider event per automation. A single inbound
    # event may legitimately trigger several different automations.
    __table_args__ = (
        UniqueConstraint("automation_id", "event_id"),
        Index("ix_runs_workspace_created", "workspace_id", "created_at"),
    )

    automation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automations.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automation_versions.id"))
    event_id: Mapped[str] = mapped_column(String(120))
    status: Mapped[RunStatus] = mapped_column(
        pg_enum(RunStatus, "run_status"), default=RunStatus.QUEUED
    )
    minutes_saved: Mapped[Decimal] = mapped_column(Numeric(6, 1), default=Decimal(0))
    # --- extensions ---
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    is_test: Mapped[bool] = mapped_column(default=False)
    trigger_type: Mapped[str] = mapped_column(String(60))
    resume_point: Mapped[int] = mapped_column(SmallInteger, default=0)
    # Execution context (trigger payload + step outputs) needed to resume: encrypted at rest.
    context_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    summary: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]

    automation: Mapped[Automation] = relationship()
    version: Mapped[AutomationVersion] = relationship()
    step_runs: Mapped[list[StepRun]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="StepRun.seq_no"
    )


class StepRun(UUIDPrimaryKey, Base):
    __tablename__ = "step_runs"
    __table_args__ = (UniqueConstraint("run_id", "step_key"),)

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    step_key: Mapped[str] = mapped_column(String(60))
    status: Mapped[StepRunStatus] = mapped_column(pg_enum(StepRunStatus, "step_run_status"))
    input_json: Mapped[dict[str, Any] | None]  # masked (REQ-WE-6)
    output_json: Mapped[dict[str, Any] | None]  # masked (REQ-WE-6)
    attempt: Mapped[int] = mapped_column(SmallInteger, default=1)
    # --- extensions ---
    seq_no: Mapped[int] = mapped_column(SmallInteger)
    block_type: Mapped[str] = mapped_column(String(40))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]

    run: Mapped[Run] = relationship(back_populates="step_runs")
