"""automations (Table 4.11) and automation_versions (Table 4.12)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Numeric, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, Timestamps, UUIDPrimaryKey, pg_enum
from app.models.enums import AutomationStatus


class Automation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "automations"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL")
    )
    # Circular reference automations <-> automation_versions: created after both tables.
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("automation_versions.id", use_alter=True, ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[AutomationStatus] = mapped_column(
        pg_enum(AutomationStatus, "automation_status"), default=AutomationStatus.DRAFT
    )
    # --- extensions ---
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL")
    )
    description: Mapped[str | None] = mapped_column(Text)
    trigger_type: Mapped[str | None] = mapped_column(String(60), index=True)
    estimated_minutes_per_run: Mapped[Decimal] = mapped_column(Numeric(6, 1), default=Decimal(0))
    auto_send: Mapped[bool] = mapped_column(default=False)  # SAF-1
    consecutive_failures: Mapped[int] = mapped_column(SmallInteger, default=0)  # REQ-WE-7
    status_reason: Mapped[str | None] = mapped_column(Text)
    activated_at: Mapped[datetime | None]
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    current_version: Mapped[AutomationVersion | None] = relationship(
        foreign_keys=[current_version_id], post_update=True
    )
    versions: Mapped[list[AutomationVersion]] = relationship(
        back_populates="automation",
        foreign_keys="AutomationVersion.automation_id",
        cascade="all, delete-orphan",
        order_by="AutomationVersion.version_no",
    )


class AutomationVersion(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "automation_versions"
    __table_args__ = (UniqueConstraint("automation_id", "version_no"),)

    automation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automations.id", ondelete="CASCADE"), index=True
    )
    version_no: Mapped[int]
    definition_json: Mapped[dict[str, Any]]
    validated: Mapped[bool] = mapped_column(default=False)
    test_passed: Mapped[bool] = mapped_column(default=False)
    # --- extensions ---
    validation_errors: Mapped[list[Any]] = mapped_column(default=list)
    source: Mapped[str] = mapped_column(
        String(20), default="manual"
    )  # generated|repaired|manual|rollback
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    automation: Mapped[Automation] = relationship(
        back_populates="versions", foreign_keys=[automation_id]
    )
