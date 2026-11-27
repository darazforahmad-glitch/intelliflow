"""Integration management (REQ-IN-1..7): sandbox and live connections, tokens encrypted at
rest, health/refresh, and pausing dependent automations when a connection goes away."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.google_auth import SCOPES, authorization_url, build_credentials, exchange_code
from app.connectors.registry import PROVIDER_LABELS, ConnectorFactory, connection_aad
from app.core.config import get_settings
from app.core.crypto import get_cipher
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.security import create_signed_state, decode_signed_state
from app.engine.errors import BlockError
from app.models import Automation, Connection, SandboxRecord, User, Workspace
from app.models.base import utcnow
from app.models.enums import (
    AutomationStatus,
    ConnectionMode,
    ConnectionProvider,
    ConnectionStatus,
    MembershipRole,
)
from app.services import audit_service, event_bus
from app.services.automation_builder import providers_used
from app.services.notification_service import notify, workspace_members

logger = logging.getLogger(__name__)


def list_connections(db: Session, workspace_id: uuid.UUID) -> list[Connection]:
    return list(
        db.scalars(
            select(Connection)
            .where(
                Connection.workspace_id == workspace_id,
                Connection.status != ConnectionStatus.DISCONNECTED,
            )
            .order_by(Connection.created_at)
        )
    )


def get_connection(db: Session, workspace_id: uuid.UUID, connection_id: uuid.UUID) -> Connection:
    connection = db.scalar(
        select(Connection).where(
            Connection.id == connection_id, Connection.workspace_id == workspace_id
        )
    )
    if connection is None:
        raise NotFoundError("Connection not found.")
    return connection


def _ensure_not_connected(
    db: Session, workspace_id: uuid.UUID, provider: ConnectionProvider
) -> None:
    if provider == ConnectionProvider.WEBFORM:
        return  # several forms are fine
    existing = db.scalar(
        select(Connection.id).where(
            Connection.workspace_id == workspace_id,
            Connection.provider == provider,
            Connection.status != ConnectionStatus.DISCONNECTED,
        )
    )
    if existing:
        raise ConflictError(
            f"{PROVIDER_LABELS[provider.value]} is already connected. Disconnect it first to connect another account.",
            code="already_connected",
        )


def _store_tokens(connection: Connection, tokens: dict[str, Any]) -> None:
    connection.token_encrypted = get_cipher().encrypt_json(
        tokens, aad=connection_aad(connection.id)
    )


def webform_url(connection: Connection) -> str | None:
    if connection.provider != ConnectionProvider.WEBFORM or not connection.token_encrypted:
        return None
    token = get_cipher().decrypt_json(
        connection.token_encrypted, aad=connection_aad(connection.id)
    )["token"]
    return f"{get_settings().api_public_url}/api/v1/webhooks/webform/{connection.id}/{token}"


def create_sandbox(
    db: Session, workspace: Workspace, user: User, provider: ConnectionProvider
) -> Connection:
    """Development/demo connection that records instead of calling the real API."""
    _ensure_not_connected(db, workspace.id, provider)
    connection = Connection(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        provider=provider,
        mode=ConnectionMode.SANDBOX,
        status=ConnectionStatus.CONNECTED,
        connected_by=user.id,
    )
    if provider == ConnectionProvider.WHATSAPP:
        connection.config_json = {
            "phone_number_id": f"sandbox-{uuid.uuid4().hex[:10]}",
            "display_phone_number": "+92 300 0000000",
        }
        connection.display_name = "WhatsApp (sandbox number)"
    elif provider == ConnectionProvider.GOOGLE_SHEETS:
        connection.config_json = {
            "spreadsheet_id": "sandbox",
            "spreadsheet_name": "IntelliFlow sandbox sheet",
        }
        connection.display_name = "Google Sheets (sandbox sheet)"
    elif provider == ConnectionProvider.GMAIL:
        connection.external_account_id = user.email
        connection.display_name = f"Gmail (sandbox inbox for {user.email})"
    else:
        connection.config_json = {"form_name": "Website form"}
        connection.display_name = "Website form (sandbox)"
        _store_tokens(connection, {"token": secrets.token_urlsafe(24)})
    db.add(connection)
    audit_service.record(
        db,
        "connection.created",
        workspace_id=workspace.id,
        actor_id=user.id,
        entity_type="connection",
        entity_id=connection.id,
        data={"provider": provider.value, "mode": "sandbox"},
    )
    db.commit()
    return connection


def create_webform(db: Session, workspace: Workspace, user: User, name: str) -> Connection:
    connection = Connection(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        provider=ConnectionProvider.WEBFORM,
        mode=ConnectionMode.LIVE,
        status=ConnectionStatus.CONNECTED,
        connected_by=user.id,
        display_name=name,
        config_json={"form_name": name},
    )
    _store_tokens(connection, {"token": secrets.token_urlsafe(24)})
    db.add(connection)
    audit_service.record(
        db,
        "connection.created",
        workspace_id=workspace.id,
        actor_id=user.id,
        entity_type="connection",
        entity_id=connection.id,
        data={"provider": "webform"},
    )
    db.commit()
    return connection


def connect_whatsapp(
    db: Session,
    workspace: Workspace,
    user: User,
    *,
    phone_number_id: str,
    waba_id: str,
    access_token: str,
    display_phone_number: str | None,
) -> Connection:
    """Live WhatsApp Cloud API number (Meta test number in development, REQ-IN-2).
    In production these identifiers come from Meta Embedded Signup."""
    _ensure_not_connected(db, workspace.id, ConnectionProvider.WHATSAPP)
    connection = Connection(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        provider=ConnectionProvider.WHATSAPP,
        mode=ConnectionMode.LIVE,
        status=ConnectionStatus.CONNECTED,
        connected_by=user.id,
        external_account_id=waba_id,
        display_name=f"WhatsApp {display_phone_number or phone_number_id}",
        config_json={
            "phone_number_id": phone_number_id,
            "waba_id": waba_id,
            "display_phone_number": display_phone_number,
        },
    )
    _store_tokens(connection, {"access_token": access_token})
    db.add(connection)
    audit_service.record(
        db,
        "connection.created",
        workspace_id=workspace.id,
        actor_id=user.id,
        entity_type="connection",
        entity_id=connection.id,
        data={"provider": "whatsapp", "mode": "live"},
    )
    db.commit()
    return connection


def google_redirect_uri() -> str:
    return f"{get_settings().api_public_url}/api/v1/oauth/google/callback"


def google_authorization(workspace: Workspace, user: User, provider: ConnectionProvider) -> str:
    if not get_settings().google_oauth_enabled:
        raise ConflictError(
            "Google sign-in is not configured on this server.",
            code="google_oauth_disabled",
            hint="Use a sandbox connection for now, or set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )
    state = create_signed_state(
        {"ws": str(workspace.id), "uid": str(user.id), "provider": provider.value}
    )
    return authorization_url(provider.value, state, google_redirect_uri())


def complete_google_oauth(db: Session, code: str, state: str) -> Connection:
    claims = decode_signed_state(state)
    workspace = db.get_one(Workspace, uuid.UUID(claims["ws"]))
    provider = ConnectionProvider(claims["provider"])
    tokens = exchange_code(code, google_redirect_uri())
    email = None
    if tokens.get("id_token"):
        import jwt

        email = jwt.decode(tokens["id_token"], options={"verify_signature": False}).get(
            "email"
        )  # from Google over TLS
    existing = db.scalar(
        select(Connection).where(
            Connection.workspace_id == workspace.id,
            Connection.provider == provider,
            Connection.status != ConnectionStatus.DISCONNECTED,
        )
    )
    connection = existing or Connection(
        id=uuid.uuid4(), workspace_id=workspace.id, provider=provider, mode=ConnectionMode.LIVE
    )
    connection.status = ConnectionStatus.CONNECTED
    connection.external_account_id = email
    connection.display_name = (
        f"{PROVIDER_LABELS[provider.value]} ({email})" if email else PROVIDER_LABELS[provider.value]
    )
    connection.scopes = SCOPES[provider.value]
    connection.connected_by = uuid.UUID(claims["uid"])
    connection.token_expires_at = utcnow() + timedelta(seconds=int(tokens.get("expires_in", 3600)))
    connection.last_error = None
    db.add(connection)
    _store_tokens(
        connection,
        {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "expiry": connection.token_expires_at.isoformat(),
            "scopes": SCOPES[provider.value],
        },
    )
    audit_service.record(
        db,
        "connection.created",
        workspace_id=workspace.id,
        actor_id=uuid.UUID(claims["uid"]),
        entity_type="connection",
        entity_id=connection.id,
        data={"provider": provider.value, "mode": "live"},
    )
    db.commit()
    return connection


def update_config(db: Session, connection: Connection, config: dict[str, Any]) -> Connection:
    allowed = {"spreadsheet_id", "spreadsheet_name", "form_name", "display_phone_number"}
    unknown = set(config) - allowed
    if unknown:
        raise ValidationFailedError(f"Unknown settings: {', '.join(sorted(unknown))}.")
    connection.config_json = {**(connection.config_json or {}), **config}
    db.commit()
    return connection


def pause_dependents(db: Session, workspace_id: uuid.UUID, provider: str, reason: str) -> int:
    paused = 0
    automations = db.scalars(
        select(Automation).where(
            Automation.workspace_id == workspace_id,
            Automation.status.in_(
                [AutomationStatus.ACTIVE, AutomationStatus.TESTED, AutomationStatus.VALIDATED]
            ),
        )
    ).all()
    for automation in automations:
        uses_provider = automation.current_version and provider in providers_used(
            automation.current_version.definition_json
        )
        if uses_provider and automation.status == AutomationStatus.ACTIVE:
            automation.status = AutomationStatus.PAUSED
            automation.status_reason = reason
            paused += 1
    return paused


def disconnect(db: Session, workspace: Workspace, user: User, connection: Connection) -> int:
    """REQ-IN-7: disconnecting pauses every automation that depends on the app."""
    connection.status = ConnectionStatus.DISCONNECTED
    connection.token_encrypted = None  # forget the credentials immediately
    label = PROVIDER_LABELS[connection.provider.value]
    paused = pause_dependents(
        db, workspace.id, connection.provider.value, f"Paused because {label} was disconnected."
    )
    audit_service.record(
        db,
        "connection.disconnected",
        workspace_id=workspace.id,
        actor_id=user.id,
        entity_type="connection",
        entity_id=connection.id,
        data={"provider": connection.provider.value, "paused_automations": paused},
    )
    db.commit()
    event_bus.publish(workspace.id, "automation.updated", {"reason": "connection_disconnected"})
    return paused


def mark_needs_attention(db: Session, connection: Connection, reason: str) -> None:
    """REQ-IN-6 / REQ-WE-7: a broken connection pauses dependents and tells the owner."""
    connection.status = ConnectionStatus.NEEDS_ATTENTION
    connection.last_error = reason[:500]
    label = PROVIDER_LABELS[connection.provider.value]
    pause_dependents(
        db,
        connection.workspace_id,
        connection.provider.value,
        f"Paused because {label} needs attention: {reason}",
    )
    owners = workspace_members(db, connection.workspace_id, roles=[MembershipRole.OWNER])
    notify(
        db,
        owners,
        workspace_id=connection.workspace_id,
        kind="connection.needs_attention",
        title=f"{label} needs attention",
        body=f"{reason} Please reconnect it on the Integrations page.",
        url="/integrations",
    )


def refresh_expiring_tokens(db: Session) -> int:
    soon = utcnow() + timedelta(minutes=30)
    refreshed = 0
    connections = db.scalars(
        select(Connection).where(
            Connection.mode == ConnectionMode.LIVE,
            Connection.status == ConnectionStatus.CONNECTED,
            Connection.provider.in_([ConnectionProvider.GMAIL, ConnectionProvider.GOOGLE_SHEETS]),
            Connection.token_expires_at.is_not(None),
            Connection.token_expires_at <= soon,
        )
    ).all()
    for connection in connections:
        try:
            stored = (
                get_cipher().decrypt_json(
                    connection.token_encrypted, aad=connection_aad(connection.id)
                )
                if connection.token_encrypted
                else {}
            )
            stored["expiry"] = utcnow().isoformat()  # force a refresh now

            def save(new: dict[str, Any], conn: Connection = connection) -> None:
                _store_tokens(conn, new)
                conn.token_expires_at = utcnow() + timedelta(minutes=55)

            build_credentials(stored, save)
            refreshed += 1
        except BlockError as exc:
            mark_needs_attention(db, connection, exc.message)
        except Exception as exc:
            logger.warning("token refresh failed", extra={"connection_id": str(connection.id)})
            mark_needs_attention(
                db, connection, f"Could not refresh access ({exc.__class__.__name__})."
            )
    db.commit()
    return refreshed


def poll_gmail_connections(db: Session) -> int:
    from app.connectors.gmail import GmailConnector, fetch_new_messages
    from app.core.kv import get_kv
    from app.services.event_router import route_trigger

    count = 0
    connections = db.scalars(
        select(Connection).where(
            Connection.provider == ConnectionProvider.GMAIL,
            Connection.mode == ConnectionMode.LIVE,
            Connection.status == ConnectionStatus.CONNECTED,
        )
    ).all()
    for connection in connections:
        workspace = db.get_one(Workspace, connection.workspace_id)
        automation = db.scalar(
            select(Automation)
            .where(
                Automation.workspace_id == workspace.id,
                Automation.trigger_type == "gmail.message_received",
                Automation.status == AutomationStatus.ACTIVE,
            )
            .limit(1)
        )
        if automation is None:
            continue  # nobody is listening: do not read the inbox
        try:
            connector = ConnectorFactory(db, workspace, automation, test_run=False).get("gmail")
            assert isinstance(connector, GmailConnector)
            for message in fetch_new_messages(connector):
                if not get_kv().set_if_absent(
                    f"evt:gmail:{message['message_id']}",
                    "1",
                    get_settings().webhook_dedupe_ttl_seconds,
                ):
                    continue
                count += len(
                    route_trigger(
                        db,
                        workspace_id=workspace.id,
                        trigger_type="gmail.message_received",
                        event_id=f"gmail:{message['message_id']}",
                        trigger=message,
                    )
                )
        except BlockError as exc:
            mark_needs_attention(db, connection, exc.message)
            db.commit()
    return count


def sandbox_view(db: Session, connection: Connection) -> dict[str, Any]:
    records = db.scalars(
        select(SandboxRecord)
        .where(SandboxRecord.connection_id == connection.id)
        .order_by(SandboxRecord.created_at)
    ).all()
    sheets: dict[str, list[dict[str, Any]]] = {}
    outbox: list[dict[str, Any]] = []
    for record in records:
        if record.resource.startswith("sheet:"):
            sheets.setdefault(record.resource.removeprefix("sheet:"), []).append(
                {**record.data_json, "row_number": record.row_number}
            )
        else:
            outbox.append({**record.data_json, "created_at": record.created_at.isoformat()})
    return {"sheets": sheets, "outbox": list(reversed(outbox))}
