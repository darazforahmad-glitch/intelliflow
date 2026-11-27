"""Integration management (REQ-IN-1..7): sandbox and live connections, tokens encrypted at
rest, health/refresh, and pausing dependent automations when a connection goes away."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction

from intelliflow.integrations.connectors.google_auth import (
    SCOPES,
    authorization_url,
    build_credentials,
    exchange_code,
)
from intelliflow.integrations.connectors.registry import (
    PROVIDER_LABELS,
    ConnectorFactory,
    connection_aad,
)
from intelliflow.core.crypto import get_cipher
from intelliflow.core.errors import ConflictError, NotFoundError, ValidationFailedError
from intelliflow.core.security import create_signed_state, decode_signed_state
from intelliflow.engine.errors import BlockError
from intelliflow.accounts.models import User
from intelliflow.automations.models import Automation
from intelliflow.integrations.models import Connection, SandboxRecord
from intelliflow.workspaces.models import Workspace
from intelliflow.core.models import utcnow
from intelliflow.core.enums import (
    AutomationStatus,
    ConnectionMode,
    ConnectionProvider,
    ConnectionStatus,
    MembershipRole,
)
from intelliflow.audit import services as audit_service
from intelliflow.notifications import event_bus
from intelliflow.automations.builder import providers_used
from intelliflow.notifications.services import notify, workspace_members

logger = logging.getLogger(__name__)


def list_connections(workspace_id: uuid.UUID) -> list[Connection]:
    return list(
        Connection.objects.filter(workspace_id=workspace_id)
        .exclude(status=ConnectionStatus.DISCONNECTED)
        .order_by("created_at")
    )


def get_connection(workspace_id: uuid.UUID, connection_id: uuid.UUID) -> Connection:
    connection = Connection.objects.filter(id=connection_id, workspace_id=workspace_id).first()
    if connection is None:
        raise NotFoundError("Connection not found.")
    return connection


def _ensure_not_connected(workspace_id: uuid.UUID, provider: ConnectionProvider) -> None:
    if provider == ConnectionProvider.WEBFORM:
        return  # several forms are fine
    existing = (
        Connection.objects.filter(workspace_id=workspace_id, provider=provider)
        .exclude(status=ConnectionStatus.DISCONNECTED)
        .exists()
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
    return f"{settings.API_PUBLIC_URL}/api/v1/webhooks/webform/{connection.id}/{token}"


@transaction.atomic
def create_sandbox(workspace: Workspace, user: User, provider: str) -> Connection:
    """Development/demo connection that records instead of calling the real API."""
    provider = ConnectionProvider(provider)
    _ensure_not_connected(workspace.id, provider)
    connection = Connection(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        provider=provider,
        mode=ConnectionMode.SANDBOX,
        status=ConnectionStatus.CONNECTED,
        connected_by=user,
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
    connection.save()
    audit_service.record(
        "connection.created",
        workspace_id=workspace.id,
        actor_id=user.id,
        entity_type="connection",
        entity_id=connection.id,
        data={"provider": provider.value, "mode": "sandbox"},
    )
    return connection


@transaction.atomic
def create_webform(workspace: Workspace, user: User, name: str) -> Connection:
    connection = Connection(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        provider=ConnectionProvider.WEBFORM,
        mode=ConnectionMode.LIVE,
        status=ConnectionStatus.CONNECTED,
        connected_by=user,
        display_name=name,
        config_json={"form_name": name},
    )
    _store_tokens(connection, {"token": secrets.token_urlsafe(24)})
    connection.save()
    audit_service.record(
        "connection.created",
        workspace_id=workspace.id,
        actor_id=user.id,
        entity_type="connection",
        entity_id=connection.id,
        data={"provider": "webform"},
    )
    return connection


@transaction.atomic
def connect_whatsapp(
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
    _ensure_not_connected(workspace.id, ConnectionProvider.WHATSAPP)
    connection = Connection(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        provider=ConnectionProvider.WHATSAPP,
        mode=ConnectionMode.LIVE,
        status=ConnectionStatus.CONNECTED,
        connected_by=user,
        external_account_id=waba_id,
        display_name=f"WhatsApp {display_phone_number or phone_number_id}",
        config_json={
            "phone_number_id": phone_number_id,
            "waba_id": waba_id,
            "display_phone_number": display_phone_number,
        },
    )
    _store_tokens(connection, {"access_token": access_token})
    connection.save()
    audit_service.record(
        "connection.created",
        workspace_id=workspace.id,
        actor_id=user.id,
        entity_type="connection",
        entity_id=connection.id,
        data={"provider": "whatsapp", "mode": "live"},
    )
    return connection


def google_redirect_uri() -> str:
    return f"{settings.API_PUBLIC_URL}/api/v1/oauth/google/callback"


def google_authorization(workspace: Workspace, user: User, provider: str) -> str:
    provider = ConnectionProvider(provider)
    if not settings.GOOGLE_OAUTH_ENABLED:
        raise ConflictError(
            "Google sign-in is not configured on this server.",
            code="google_oauth_disabled",
            hint="Use a sandbox connection for now, or set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )
    state = create_signed_state(
        {"ws": str(workspace.id), "uid": str(user.id), "provider": provider.value}
    )
    return authorization_url(provider.value, state, google_redirect_uri())


@transaction.atomic
def complete_google_oauth(code: str, state: str) -> Connection:
    claims = decode_signed_state(state)
    workspace = Workspace.objects.get(pk=uuid.UUID(claims["ws"]))
    provider = ConnectionProvider(claims["provider"])
    tokens = exchange_code(code, google_redirect_uri())
    email = None
    if tokens.get("id_token"):
        import jwt

        email = jwt.decode(tokens["id_token"], options={"verify_signature": False}).get(
            "email"
        )  # from Google over TLS
    existing = (
        Connection.objects.filter(workspace=workspace, provider=provider)
        .exclude(status=ConnectionStatus.DISCONNECTED)
        .first()
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
    connection.connected_by_id = uuid.UUID(claims["uid"])
    connection.token_expires_at = utcnow() + timedelta(seconds=int(tokens.get("expires_in", 3600)))
    connection.last_error = None
    _store_tokens(
        connection,
        {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "expiry": connection.token_expires_at.isoformat(),
            "scopes": SCOPES[provider.value],
        },
    )
    connection.save()
    audit_service.record(
        "connection.created",
        workspace_id=workspace.id,
        actor_id=uuid.UUID(claims["uid"]),
        entity_type="connection",
        entity_id=connection.id,
        data={"provider": provider.value, "mode": "live"},
    )
    return connection


def update_config(connection: Connection, config: dict[str, Any]) -> Connection:
    allowed = {"spreadsheet_id", "spreadsheet_name", "form_name", "display_phone_number"}
    unknown = set(config) - allowed
    if unknown:
        raise ValidationFailedError(f"Unknown settings: {', '.join(sorted(unknown))}.")
    connection.config_json = {**(connection.config_json or {}), **config}
    connection.save(update_fields=["config_json", "updated_at"])
    return connection


def pause_dependents(workspace_id: uuid.UUID, provider: str, reason: str) -> int:
    paused = 0
    automations = Automation.objects.select_related("current_version").filter(
        workspace_id=workspace_id,
        status__in=[AutomationStatus.ACTIVE, AutomationStatus.TESTED, AutomationStatus.VALIDATED],
    )
    for automation in automations:
        uses_provider = automation.current_version and provider in providers_used(
            automation.current_version.definition_json
        )
        if uses_provider and automation.status == AutomationStatus.ACTIVE:
            automation.status = AutomationStatus.PAUSED
            automation.status_reason = reason
            automation.save(update_fields=["status", "status_reason", "updated_at"])
            paused += 1
    return paused


def disconnect(workspace: Workspace, user: User, connection: Connection) -> int:
    """REQ-IN-7: disconnecting pauses every automation that depends on the app."""
    with transaction.atomic():
        connection.status = ConnectionStatus.DISCONNECTED
        connection.token_encrypted = None  # forget the credentials immediately
        connection.save(update_fields=["status", "token_encrypted", "updated_at"])
        label = PROVIDER_LABELS[connection.provider]
        paused = pause_dependents(
            workspace.id, connection.provider, f"Paused because {label} was disconnected."
        )
        audit_service.record(
            "connection.disconnected",
            workspace_id=workspace.id,
            actor_id=user.id,
            entity_type="connection",
            entity_id=connection.id,
            data={"provider": connection.provider, "paused_automations": paused},
        )
    event_bus.publish(workspace.id, "automation.updated", {"reason": "connection_disconnected"})
    return paused


@transaction.atomic
def mark_needs_attention(connection: Connection, reason: str) -> None:
    """REQ-IN-6 / REQ-WE-7: a broken connection pauses dependents and tells the owner."""
    connection.status = ConnectionStatus.NEEDS_ATTENTION
    connection.last_error = reason[:500]
    connection.save(update_fields=["status", "last_error", "updated_at"])
    label = PROVIDER_LABELS[connection.provider]
    pause_dependents(
        connection.workspace_id,
        connection.provider,
        f"Paused because {label} needs attention: {reason}",
    )
    owners = workspace_members(connection.workspace_id, roles=[MembershipRole.OWNER])
    notify(
        owners,
        workspace_id=connection.workspace_id,
        kind="connection.needs_attention",
        title=f"{label} needs attention",
        body=f"{reason} Please reconnect it on the Integrations page.",
        url="/integrations",
    )


def refresh_expiring_tokens() -> int:
    soon = utcnow() + timedelta(minutes=30)
    refreshed = 0
    connections = Connection.objects.filter(
        mode=ConnectionMode.LIVE,
        status=ConnectionStatus.CONNECTED,
        provider__in=[ConnectionProvider.GMAIL, ConnectionProvider.GOOGLE_SHEETS],
        token_expires_at__isnull=False,
        token_expires_at__lte=soon,
    )
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
                conn.save(update_fields=["token_encrypted", "token_expires_at", "updated_at"])

            build_credentials(stored, save)
            refreshed += 1
        except BlockError as exc:
            mark_needs_attention(connection, exc.message)
        except Exception as exc:
            logger.warning("token refresh failed", extra={"connection_id": str(connection.id)})
            mark_needs_attention(
                connection, f"Could not refresh access ({exc.__class__.__name__})."
            )
    return refreshed


def poll_gmail_connections() -> int:
    from intelliflow.integrations.connectors.gmail import GmailConnector, fetch_new_messages
    from intelliflow.core.kv import get_kv
    from intelliflow.runs.event_router import route_trigger

    count = 0
    connections = Connection.objects.select_related("workspace").filter(
        provider=ConnectionProvider.GMAIL,
        mode=ConnectionMode.LIVE,
        status=ConnectionStatus.CONNECTED,
    )
    for connection in connections:
        workspace = connection.workspace
        automation = Automation.objects.filter(
            workspace=workspace,
            trigger_type="gmail.message_received",
            status=AutomationStatus.ACTIVE,
        ).first()
        if automation is None:
            continue  # nobody is listening: do not read the inbox
        try:
            connector = ConnectorFactory(workspace, automation, test_run=False).get("gmail")
            assert isinstance(connector, GmailConnector)
            for message in fetch_new_messages(connector):
                if not get_kv().set_if_absent(
                    f"evt:gmail:{message['message_id']}",
                    "1",
                    settings.WEBHOOK_DEDUPE_TTL_SECONDS,
                ):
                    continue
                count += len(
                    route_trigger(
                        workspace_id=workspace.id,
                        trigger_type="gmail.message_received",
                        event_id=f"gmail:{message['message_id']}",
                        trigger=message,
                    )
                )
        except BlockError as exc:
            mark_needs_attention(connection, exc.message)
    return count


def sandbox_view(connection: Connection) -> dict[str, Any]:
    records = SandboxRecord.objects.filter(connection=connection).order_by("created_at")
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
