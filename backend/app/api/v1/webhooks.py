"""Public webhook endpoints (no session auth: authenticity comes from signatures/secret URLs)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse

from app.api.deps import DB
from app.core.config import get_settings
from app.core.errors import PermissionDeniedError, ValidationFailedError
from app.core.security import constant_time_equals
from app.services import connection_service
from app.services.webhook_gateway import ingest_webform, ingest_whatsapp

router = APIRouter(tags=["webhooks"])
MAX_BODY_BYTES = 256 * 1024


@router.get("/webhooks/whatsapp", response_class=PlainTextResponse)
def whatsapp_verify(
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
) -> str:
    """Meta's subscription handshake."""
    if mode == "subscribe" and constant_time_equals(token, get_settings().whatsapp_verify_token):
        return challenge
    raise PermissionDeniedError("Verification failed.")


@router.post("/webhooks/whatsapp")
async def whatsapp_receive(request: Request) -> JSONResponse:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise ValidationFailedError("Webhook body too large.")
    result = await run_in_threadpool(
        ingest_whatsapp, raw, request.headers.get("x-hub-signature-256")
    )
    return JSONResponse({"status": "ok", **result})  # acknowledged immediately; workers do the rest


@router.post("/webhooks/webform/{connection_id}/{token}", status_code=status.HTTP_202_ACCEPTED)
async def webform_receive(
    connection_id: uuid.UUID, token: str, request: Request, db: DB
) -> dict[str, Any]:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise ValidationFailedError("Form submission too large.")
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError as exc:
            raise ValidationFailedError("The submission is not valid JSON.") from exc
        if not isinstance(data, dict):
            raise ValidationFailedError("Send the form fields as a JSON object.")
    else:
        form = await request.form()
        data = {k: v for k, v in form.items() if isinstance(v, str)}
    event_id = await run_in_threadpool(
        ingest_webform, db, connection_id, token, data, request.headers.get("idempotency-key")
    )
    return {"status": "received", "event_id": event_id}


@router.get("/oauth/google/callback", include_in_schema=False)
def google_callback(
    db: DB, code: str | None = None, state: str | None = None, error: str | None = None
) -> RedirectResponse:
    frontend = get_settings().frontend_url
    if error or not code or not state:
        return RedirectResponse(f"{frontend}/integrations?error={error or 'cancelled'}")
    connection = connection_service.complete_google_oauth(db, code, state)
    return RedirectResponse(f"{frontend}/integrations?connected={connection.provider.value}")
