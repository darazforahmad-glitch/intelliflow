"""opportunities (Table 4.8): scored, ranked automation candidates for a map version."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, UUIDPrimaryKey, pg_enum
from app.models.enums import OpportunityStatus
from app.models.process import ProcessMap, ProcessStep
from app.models.template import Template


class Opportunity(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "opportunities"

    map_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("process_maps.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("process_steps.id", ondelete="CASCADE"))
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL")
    )
    rank: Mapped[int | None] = mapped_column(SmallInteger)
    score: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    status: Mapped[OpportunityStatus] = mapped_column(
        pg_enum(OpportunityStatus, "opportunity_status"), default=OpportunityStatus.SUGGESTED
    )
    # --- extensions: explainability (REQ-OA-4, REQ-OA-5) ---
    fit: Mapped[Decimal] = mapped_column(Numeric(3, 2))
    risk: Mapped[Decimal] = mapped_column(Numeric(3, 2))
    minutes_saved_per_week: Mapped[Decimal] = mapped_column(Numeric(8, 1))
    reason: Mapped[str] = mapped_column(Text)

    process_map: Mapped[ProcessMap] = relationship()
    step: Mapped[ProcessStep] = relationship()
    template: Mapped[Template | None] = relationship()
