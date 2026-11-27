"""Webhook gateway: HANDLE_WEBHOOK of Algorithm 5.4 (REQ-WE-2, REQ-WE-3, SEC-5).

1. verify HMAC-SHA256 of the *raw* body against X-Hub-Signature-256 before parsing
2. drop duplicates with Redis SETNX on the provider event id (24 h TTL)
3. enqueue each new event for the workers and acknowledge immediately
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import (
    AuthenticationError,
    NotFoundError,
    RateLimitedError,
    ValidationFailedError,
)
from app.core.kv import get_kv
from app.core.security import constant_time_equals
from app.models import Connection
from app.models.enums import ConnectionProvider, ConnectionStatus
from app.services.webhooks import extract_whatsapp_events, verify_signature

logger = logging.getLogger(__name__)
MAX_FORM_FIELDS = 50
MAX_FIELD_CHARS = 2000


def ingest_whatsapp(raw_body: bytes, signature: str | None) -> dict[str, int]:
    settings = get_settings()
    if not verify_signature(raw_body, signature, settings.whatsapp_app_secret):
        raise AuthenticationError("Invalid webhook signature.", code="invalid_signature")
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValidationFailedError("Webhook body is not valid JSON.") from exc
    from app.worker.tasks import process_whatsapp_event

    queued = duplicates = 0
    kv = get_kv()
    for event in extract_whatsapp_events(body):
        if not kv.set_if_absent(
            f"evt:whatsapp:{event['event_id']}", "1", settings.webhook_dedupe_ttl_seconds
        ):
            duplicates += 1
            continue
        process_whatsapp_event.delay(event)
        queued += 1
    return {"queued": queued, "duplicates": duplicates}


def _webform_connection(db: Session, connection_id: uuid.UUID, token: str) -> Connection:
    from app.connectors.registry import connection_aad
    from app.core.crypto import get_cipher

    connection = db.scalar(
        select(Connection).where(
            Connection.id == connection_id,
            Connection.provider == ConnectionProvider.WEBFORM,
            Connection.status == ConnectionStatus.CONNECTED,
        )
    )
    if connection is None or not connection.token_encrypted:
        raise NotFoundError("Unknown form.")
    expected = get_cipher().decrypt_json(
        connection.token_encrypted, aad=connection_aad(connection.id)
    )["token"]
    if not constant_time_equals(token, expected):
        raise NotFoundError("Unknown form.")  # same answer as unknown id: no oracle
    return connection


def ingest_webform(
    db: Session,
    connection_id: uuid.UUID,
    token: str,
    data: dict[str, Any],
    idempotency_key: str | None,
) -> str:
    connection = _webform_connection(db, connection_id, token)
    minute = int(datetime.now(UTC).timestamp() // 60)
    if get_kv().incr(f"rl:webform:{connection.id}:{minute}", ttl_seconds=90) > 120:
        raise RateLimitedError("Too many submissions. Please try again in a minute.")
    fields = {
        str(k)[:60]: str(v)[:MAX_FIELD_CHARS] for k, v in list(data.items())[:MAX_FORM_FIELDS]
    }
    event_id = f"webform:{(idempotency_key or uuid.uuid4().hex)[:80]}"
    if not get_kv().set_if_absent(
        f"evt:{event_id}", "1", get_settings().webhook_dedupe_ttl_seconds
    ):
        return event_id
    from app.worker.tasks import process_trigger

    trigger = {
        "form_name": (connection.config_json or {}).get("form_name") or connection.display_name,
        "fields": fields,
        "submitted_at": datetime.now(UTC).isoformat(),
    }
    process_trigger.delay(str(connection.workspace_id), "webform.submitted", event_id, trigger)
    return event_id
