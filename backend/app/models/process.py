"""process_maps (Table 4.6) and process_steps (Table 4.7). Maps are versioned, never overwritten."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Numeric, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, UUIDPrimaryKey, pg_enum
from app.models.enums import StepType


class ProcessMap(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "process_maps"
    __table_args__ = (UniqueConstraint("session_id", "version"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    graph_json: Mapped[dict[str, Any]]
    version: Mapped[int]
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    change_note: Mapped[str | None] = mapped_column(String(255))

    steps: Mapped[list[ProcessStep]] = relationship(
        back_populates="process_map", cascade="all, delete-orphan", order_by="ProcessStep.seq_no"
    )


class ProcessStep(UUIDPrimaryKey, Base):
    __tablename__ = "process_steps"
    __table_args__ = (UniqueConstraint("map_id", "seq_no"), UniqueConstraint("map_id", "step_key"))

    map_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("process_maps.id", ondelete="CASCADE"), index=True
    )
    seq_no: Mapped[int] = mapped_column(SmallInteger)
    title: Mapped[str] = mapped_column(String(150))
    step_type: Mapped[StepType] = mapped_column(pg_enum(StepType, "step_type"))
    minutes_per_run: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    runs_per_week: Mapped[int | None]
    is_manual: Mapped[bool] = mapped_column(default=False)
    # --- extensions used by Algorithm 5.2 and the editable flowchart ---
    step_key: Mapped[str] = mapped_column(String(30))
    actor: Mapped[str | None] = mapped_column(String(80))
    action: Mapped[str | None] = mapped_column(Text)
    app: Mapped[str | None] = mapped_column(String(40))
    predecessor_key: Mapped[str | None] = mapped_column(String(30))
    involves_customer_messaging: Mapped[bool] = mapped_column(default=False)
    involves_money: Mapped[bool] = mapped_column(default=False)
    support_status: Mapped[str | None] = mapped_column(String(20))  # supported | not_yet_supported

    process_map: Mapped[ProcessMap] = relationship(back_populates="steps")

    @property
    def weekly_minutes(self) -> Decimal:
        """REQ-OA-1: minutes per run x runs per week."""
        return (self.minutes_per_run or Decimal(0)) * (self.runs_per_week or 0)
