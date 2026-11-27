"""/workspaces/{id}/connections: Integration Management (UC-06, REQ-IN-1..7)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import DB, WorkspaceMember, WorkspaceOwner
from app.connectors.registry import PROVIDER_LABELS
from app.core.config import get_settings
from app.core.errors import ConflictError
from app.models import Connection
from app.models.enums import ConnectionProvider
from app.schemas.common import MessageOut
from app.schemas.connection import (
    ConnectionConfigIn,
    ConnectionOut,
    SandboxIn,
    SimulateIn,
    WebformIn,
    WhatsAppConnectIn,
)
from app.services import connection_service
from app.services.webhook_gateway import ingest_webform, ingest_whatsapp
from app.services.webhooks import build_whatsapp_payload, sign

router = APIRouter(prefix="/workspaces/{workspace_id}/connections", tags=["integrations"])

_SAFE_CONFIG = {
    "phone_number_id",
    "display_phone_number",
    "waba_id",
    "spreadsheet_id",
    "spreadsheet_name",
    "form_name",
}


def connection_out(connection: Connection) -> ConnectionOut:
    return ConnectionOut(
        id=connection.id,
        provider=connection.provider.value,
        label=PROVIDER_LABELS[connection.provider.value],
        mode=connection.mode.value,
        status=connection.status.value,
        display_name=connection.display_name,
        external_account_id=connection.external_account_id,
        config={k: v for k, v in (connection.config_json or {}).items() if k in _SAFE_CONFIG},
        last_error=connection.last_error,
        created_at=connection.created_at,
        webhook_url=connection_service.webform_url(connection),
        has_credentials=connection.token_encrypted
        is not None,  # tokens themselves are never returned (REQ-IN-5)
    )


@router.get("", response_model=list[ConnectionOut])
def list_connections(ctx: WorkspaceMember, db: DB) -> list[ConnectionOut]:
    return [connection_out(c) for c in connection_service.list_connections(db, ctx.workspace_id)]


@router.post("/sandbox", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
def create_sandbox(body: SandboxIn, ctx: WorkspaceOwner, db: DB) -> ConnectionOut:
    return connection_out(
        connection_service.create_sandbox(
            db, ctx.workspace, ctx.user, ConnectionProvider(body.provider)
        )
    )


@router.post("/whatsapp", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
def connect_whatsapp(body: WhatsAppConnectIn, ctx: WorkspaceOwner, db: DB) -> ConnectionOut:
    return connection_out(
        connection_service.connect_whatsapp(
            db,
            ctx.workspace,
            ctx.user,
            phone_number_id=body.phone_number_id,
            waba_id=body.waba_id,
            access_token=body.access_token,
            display_phone_number=body.display_phone_number,
        )
    )


@router.post("/webform", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
def create_webform(body: WebformIn, ctx: WorkspaceOwner, db: DB) -> ConnectionOut:
    return connection_out(connection_service.create_webform(db, ctx.workspace, ctx.user, body.name))


@router.get("/google/authorize")
def google_authorize(provider: str, ctx: WorkspaceOwner) -> dict[str, str]:
    if provider not in {"gmail", "google_sheets"}:
        raise ConflictError("Choose gmail or google_sheets.")
    return {
        "authorization_url": connection_service.google_authorization(
            ctx.workspace, ctx.user, ConnectionProvider(provider)
        )
    }


@router.patch("/{connection_id}", response_model=ConnectionOut)
def update_connection(
    connection_id: uuid.UUID, body: ConnectionConfigIn, ctx: WorkspaceOwner, db: DB
) -> ConnectionOut:
    connection = connection_service.get_connection(db, ctx.workspace_id, connection_id)
    return connection_out(connection_service.update_config(db, connection, body.config))


@router.delete("/{connection_id}", response_model=MessageOut)
def disconnect(connection_id: uuid.UUID, ctx: WorkspaceOwner, db: DB) -> MessageOut:
    connection = connection_service.get_connection(db, ctx.workspace_id, connection_id)
    paused = connection_service.disconnect(db, ctx.workspace, ctx.user, connection)
    suffix = f" {paused} automation(s) that use it were paused." if paused else ""
    return MessageOut(
        message=f"{PROVIDER_LABELS[connection.provider.value]} was disconnected.{suffix}"
    )


@router.get("/{connection_id}/sandbox")
def sandbox_records(connection_id: uuid.UUID, ctx: WorkspaceMember, db: DB) -> dict[str, Any]:
    connection = connection_service.get_connection(db, ctx.workspace_id, connection_id)
    if not connection.is_sandbox:
        raise ConflictError("Only sandbox connections have recorded data.")
    return connection_service.sandbox_view(db, connection)


@router.post("/{connection_id}/simulate", status_code=status.HTTP_202_ACCEPTED)
async def simulate(
    connection_id: uuid.UUID, body: SimulateIn, ctx: WorkspaceOwner, db: DB
) -> dict[str, Any]:
    """Send a realistic inbound event through the real gateway (signature, de-dupe, queue)."""
    connection = connection_service.get_connection(db, ctx.workspace_id, connection_id)
    if not connection.is_sandbox and connection.provider != ConnectionProvider.WEBFORM:
        raise ConflictError("Simulation is only available for sandbox connections.")
    if connection.provider == ConnectionProvider.WHATSAPP:
        raw = build_whatsapp_payload(
            phone_number_id=str(connection.config_json["phone_number_id"]),
            wa_id=body.sender or "923001234567",
            name=body.name or "Test Customer",
            text=body.text or "",
            message_id=f"wamid.SIM{uuid.uuid4().hex}",
        )
        result = await run_in_threadpool(
            ingest_whatsapp, raw, sign(raw, get_settings().whatsapp_app_secret)
        )
        return {"status": "queued", **result}
    if connection.provider == ConnectionProvider.WEBFORM:
        token_url = connection_service.webform_url(connection) or ""
        event_id = await run_in_threadpool(
            ingest_webform, db, connection.id, token_url.rsplit("/", 1)[-1], body.fields or {}, None
        )
        return {"status": "queued", "event_id": event_id}
    if connection.provider == ConnectionProvider.GMAIL:
        from app.worker.tasks import process_trigger

        message_id = f"gmail:SIM{uuid.uuid4().hex}"
        trigger = {
            "message_id": message_id,
            "from": body.sender or "customer@example.com",
            "to": connection.external_account_id,
            "subject": body.subject or "",
            "body": body.body or body.text or "",
            "received_at": None,
        }
        await run_in_threadpool(
            process_trigger.delay,
            str(ctx.workspace_id),
            "gmail.message_received",
            message_id,
            trigger,
        )
        return {"status": "queued", "event_id": message_id}
    raise ConflictError("Google Sheets does not send events.")
