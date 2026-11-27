"""Resolves the right connector (live, sandbox connection, or test run) for a run."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import Connector, ConnectorContext, OperationSpec, SandboxRecorder
from app.connectors.gmail import GmailConnector
from app.connectors.sheet_store import DbSheetStore, InMemorySheetStore, SheetStore
from app.connectors.sheets import SheetsConnector
from app.connectors.webform import WebformConnector
from app.connectors.whatsapp import WhatsAppConnector
from app.core.config import get_settings
from app.core.crypto import get_cipher
from app.core.kv import get_kv
from app.engine.errors import ConnectionUnavailableError, PermanentBlockError
from app.models import Automation, Connection, Membership, SandboxRecord, User, Workspace
from app.models.enums import ConnectionStatus, MembershipRole, MembershipStatus

CONNECTOR_CLASSES: dict[str, type[Connector]] = {
    "whatsapp": WhatsAppConnector,
    "google_sheets": SheetsConnector,
    "gmail": GmailConnector,
    "webform": WebformConnector,
}
PROVIDER_LABELS = {name: cls.label for name, cls in CONNECTOR_CLASSES.items()}


def operation_spec(provider: str, operation: str) -> OperationSpec | None:
    cls = CONNECTOR_CLASSES.get(provider)
    return cls.operations.get(operation) if cls else None


def connection_aad(connection_id: uuid.UUID) -> str:
    return f"connection:{connection_id}"


def active_connection(db: Session, workspace_id: uuid.UUID, provider: str) -> Connection | None:
    return db.scalar(
        select(Connection)
        .where(
            Connection.workspace_id == workspace_id,
            Connection.provider == provider,
            Connection.status == ConnectionStatus.CONNECTED,
        )
        .order_by(Connection.created_at.desc())
        .limit(1)
    )


class ConnectorFactory:
    def __init__(
        self,
        db: Session,
        workspace: Workspace,
        automation: Automation,
        *,
        test_run: bool,
        trigger: dict[str, Any] | None = None,
        recorder: SandboxRecorder | None = None,
    ) -> None:
        self.db = db
        self.workspace = workspace
        self.automation = automation
        self.test_run = test_run
        self.trigger = trigger or {}
        self.recorder = recorder or SandboxRecorder()
        self._cache: dict[str, Connector] = {}

    def _owner_email(self) -> str | None:
        return self.db.scalar(
            select(User.email)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.workspace_id == self.workspace.id,
                Membership.role == MembershipRole.OWNER,
                Membership.status == MembershipStatus.ACTIVE,
            )
            .limit(1)
        )

    def get(self, provider: str) -> Connector:
        if provider in self._cache:
            return self._cache[provider]
        cls = CONNECTOR_CLASSES.get(provider)
        if cls is None:
            raise PermanentBlockError(f"Unknown app “{provider}”.", code="unknown_connector")
        connection = active_connection(self.db, self.workspace.id, provider)
        extras = {
            "trigger": self.trigger,
            "owner_email": self._owner_email(),
            "test_run": self.test_run,
        }
        store: SheetStore | None = None
        if self.test_run:
            # Test runs never touch real apps or persist anything (SAF-5); they read a copy
            # of the sandbox sheet so lookups behave realistically.
            seed = (
                DbSheetStore(self.db, connection.id).snapshot()
                if connection and connection.is_sandbox
                else None
            )
            store = InMemorySheetStore(seed)
            ctx = ConnectorContext(
                self.workspace, connection, sandbox=True, recorder=self.recorder, extras=extras
            )
        else:
            if connection is None:
                raise ConnectionUnavailableError(
                    f"{cls.label} is not connected. Connect it on the Integrations page.",
                    code="connection_missing",
                    details={"provider": provider},
                )
            if connection.is_sandbox:
                store = DbSheetStore(self.db, connection.id)
                connection_id = connection.id

                def persist(
                    resource: str, data: dict[str, Any], cid: uuid.UUID = connection_id
                ) -> None:
                    self.db.add(SandboxRecord(connection_id=cid, resource=resource, data_json=data))

                ctx = ConnectorContext(
                    self.workspace,
                    connection,
                    sandbox=True,
                    recorder=self.recorder,
                    persist=persist,
                    extras=extras,
                )
            else:
                credentials = (
                    get_cipher().decrypt_json(
                        connection.token_encrypted, aad=connection_aad(connection.id)
                    )
                    if connection.token_encrypted
                    else None
                )

                def save(new: dict[str, Any], conn: Connection = connection) -> None:
                    conn.token_encrypted = get_cipher().encrypt_json(
                        new, aad=connection_aad(conn.id)
                    )

                ctx = ConnectorContext(
                    self.workspace,
                    connection,
                    sandbox=False,
                    recorder=self.recorder,
                    credentials=credentials,
                    save_credentials=save,
                    extras=extras,
                )
        connector: Connector = SheetsConnector(ctx, store) if cls is SheetsConnector else cls(ctx)
        self._cache[provider] = connector
        return connector

    def execute(self, provider: str, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        spec = operation_spec(provider, operation)
        if spec and spec.customer_message and not self.test_run:
            self._check_message_rate_limit()
        return self.get(provider).execute(operation, params)

    def _check_message_rate_limit(self) -> None:
        """SAF-4: cap outgoing messages per automation per hour to stop floods from loops."""
        definition = (
            self.automation.current_version.definition_json
            if self.automation.current_version
            else {}
        )
        limit = int(
            (definition.get("settings") or {}).get("max_messages_per_hour")
            or get_settings().messages_per_hour_limit
        )
        hour = datetime.now(UTC).strftime("%Y%m%d%H")
        count = get_kv().incr(f"rl:msg:{self.automation.id}:{hour}", ttl_seconds=3700)
        if count > limit:
            raise PermanentBlockError(
                f"This automation reached its limit of {limit} customer messages per hour, so it stopped sending "
                "to prevent a message flood.",
                code="message_rate_limited",
            )
