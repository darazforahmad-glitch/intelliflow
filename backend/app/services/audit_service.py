"""Audit trail for security-relevant and business-relevant actions (REQ-PA-5)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.models import AuditLog


def record(
    db: Session,
    action: str,
    *,
    workspace_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | str | None = None,
    data: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        workspace_id=workspace_id,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        data_json=data or {},
        ip_address=ip_address,
        request_id=request_id_var.get(),
    )
    db.add(entry)
    return entry
