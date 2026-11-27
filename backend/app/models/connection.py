"""connections (Table 4.10). Tokens are AES-256-GCM encrypted at rest (SEC-2, REQ-IN-5)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum
from app.models.enums import ConnectionMode, ConnectionProvider, ConnectionStatus


class Connection(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "connections"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[ConnectionProvider] = mapped_column(
        pg_enum(ConnectionProvider, "connection_provider")
    )
    external_account_id: Mapped[str | None] = mapped_column(String(120), index=True)
    token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    status: Mapped[ConnectionStatus] = mapped_column(
        pg_enum(ConnectionStatus, "connection_status"), default=ConnectionStatus.CONNECTED
    )
    # --- extensions: sandbox mode for development/demo, non-secret config, health ---
    mode: Mapped[ConnectionMode] = mapped_column(
        pg_enum(ConnectionMode, "connection_mode"), default=ConnectionMode.LIVE
    )
    display_name: Mapped[str | None] = mapped_column(String(120))
    config_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    scopes: Mapped[list[Any]] = mapped_column(default=list)
    token_expires_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    connected_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    @property
    def is_sandbox(self) -> bool:
        return self.mode == ConnectionMode.SANDBOX

    @property
    def is_usable(self) -> bool:
        return self.status == ConnectionStatus.CONNECTED


class SandboxRecord(UUIDPrimaryKey, Timestamps, Base):
    """What a sandbox connection 'did': virtual sheet rows, would-be-sent messages."""

    __tablename__ = "sandbox_records"

    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), index=True
    )
    resource: Mapped[str] = mapped_column(String(120))  # e.g. sheet name, "outbox"
    row_number: Mapped[int | None]
    data_json: Mapped[dict[str, Any]]
