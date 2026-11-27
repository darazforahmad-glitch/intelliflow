"""WhatsApp customer service window tracking (REQ-WE-8, BR-4).

Free-form messages are allowed only within 24 hours of the customer's last message.
Every inbound message refreshes a Redis key that expires after 24 hours.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from intelliflow.core.kv import get_kv

WINDOW = timedelta(hours=24)


def _key(workspace_id: uuid.UUID, wa_id: str) -> str:
    return f"csw:{workspace_id}:{wa_id}"


def mark_inbound(workspace_id: uuid.UUID, wa_id: str, at: datetime | None = None) -> None:
    at = at or datetime.now(UTC)
    remaining = WINDOW - (datetime.now(UTC) - at)
    if remaining.total_seconds() > 0:
        get_kv().set(
            _key(workspace_id, wa_id), at.isoformat(), ttl_seconds=int(remaining.total_seconds())
        )


def is_open(
    workspace_id: uuid.UUID, wa_id: str, *, fallback_last_inbound: datetime | None = None
) -> bool:
    if get_kv().get(_key(workspace_id, wa_id)):
        return True
    return bool(fallback_last_inbound and datetime.now(UTC) - fallback_last_inbound < WINDOW)
