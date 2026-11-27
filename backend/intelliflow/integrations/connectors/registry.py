"""Resolves the right connector (live, sandbox connection, or test run) for a run."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from django.conf import settings

from intelliflow.accounts.models import User
from intelliflow.automations.models import Automation
from intelliflow.core.crypto import get_cipher
from intelliflow.core.enums import ConnectionStatus, MembershipRole, MembershipStatus
from intelliflow.core.kv import get_kv
from intelliflow.engine.errors import ConnectionUnavailableError, PermanentBlockError
from intelliflow.integrations.connectors.base import (
    Connector,
    ConnectorContext,
    OperationSpec,
    SandboxRecorder,
)
from intelliflow.integrations.connectors.gmail import GmailConnector
from intelliflow.integrations.connectors.sheet_store import (
    DbSheetStore,
    InMemorySheetStore,
    SheetStore,
)
from intelliflow.integrations.connectors.sheets import SheetsConnector
from intelliflow.integrations.connectors.webform import WebformConnector
from intelliflow.integrations.connectors.whatsapp import WhatsAppConnector
from intelliflow.integrations.models import Connection, SandboxRecord
from intelliflow.workspaces.models import Workspace

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


def active_connection(workspace_id: uuid.UUID, provider: str) -> Connection | None:
    return (
        Connection.objects.filter(
            workspace_id=workspace_id, provider=provider, status=ConnectionStatus.CONNECTED
        )
        .order_by("-created_at")
        .first()
    )


class ConnectorFactory:
    def __init__(
        self,
        workspace: Workspace,
        automation: Automation,
        *,
        test_run: bool,
        trigger: dict[str, Any] | None = None,
        recorder: SandboxRecorder | None = None,
    ) -> None:
        self.workspace = workspace
        self.automation = automation
        self.test_run = test_run
        self.trigger = trigger or {}
        self.recorder = recorder or SandboxRecorder()
        self._cache: dict[str, Connector] = {}

    def _owner_email(self) -> str | None:
        return (
            User.objects.filter(
                memberships__workspace_id=self.workspace.id,
                memberships__role=MembershipRole.OWNER,
                memberships__status=MembershipStatus.ACTIVE,
            )
            .values_list("email", flat=True)
            .first()
        )

    def get(self, provider: str) -> Connector:
        if provider in self._cache:
            return self._cache[provider]
        cls = CONNECTOR_CLASSES.get(provider)
        if cls is None:
            raise PermanentBlockError(f"Unknown app “{provider}”.", code="unknown_connector")
        connection = active_connection(self.workspace.id, provider)
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
                DbSheetStore(connection.id).snapshot()
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
                store = DbSheetStore(connection.id)
                connection_id = connection.id

                def persist(
                    resource: str, data: dict[str, Any], cid: uuid.UUID = connection_id
                ) -> None:
                    SandboxRecord.objects.create(
                        connection_id=cid, resource=resource, data_json=data
                    )

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
                    conn.save(update_fields=["token_encrypted", "updated_at"])

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
            or settings.MESSAGES_PER_HOUR_LIMIT
        )
        hour = datetime.now(UTC).strftime("%Y%m%d%H")
        count = get_kv().incr(f"rl:msg:{self.automation.id}:{hour}", ttl_seconds=3700)
        if count > limit:
            raise PermanentBlockError(
                f"This automation reached its limit of {limit} customer messages per hour, so it stopped sending "
                "to prevent a message flood.",
                code="message_rate_limited",
            )
