"""templates (Table 4.9): reusable, versioned automation skeletons shared by all workspaces."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey


class Template(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "templates"
    # A code can have many versions; at most one is published (is_active) at a time.
    __table_args__ = (
        UniqueConstraint("code", "version"),
        Index(
            "uq_templates_active_code",
            "code",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    code: Mapped[str] = mapped_column(String(60), index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(60))
    description: Mapped[str | None] = mapped_column(Text)
    definition_json: Mapped[dict[str, Any]]
    version: Mapped[int] = mapped_column(default=1)
    is_active: Mapped[bool] = mapped_column(default=True)
    # --- extensions: matching rules for Algorithm 5.2 and connection prerequisites ---
    match_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    required_connections: Mapped[list[Any]] = mapped_column(default=list)
    retired_at: Mapped[datetime | None]
