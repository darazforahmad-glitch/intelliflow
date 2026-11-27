"""Connections to external apps (Table 4.12) and the records sandbox connections keep."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from intelliflow.core.enums import ConnectionMode, ConnectionProvider, ConnectionStatus
from intelliflow.core.models import TimestampedModel, choices_check


class Connection(TimestampedModel):
    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.CASCADE, related_name="connections"
    )
    provider = models.CharField(max_length=20, choices=ConnectionProvider.choices)
    external_account_id = models.CharField(max_length=120, null=True, blank=True, db_index=True)
    token_encrypted = models.BinaryField(null=True, blank=True)  # AES-256-GCM (SEC-2)
    status = models.CharField(
        max_length=20, choices=ConnectionStatus.choices, default=ConnectionStatus.CONNECTED
    )
    # --- extensions: sandbox mode for development/demo, non-secret config, health ---
    mode = models.CharField(
        max_length=10, choices=ConnectionMode.choices, default=ConnectionMode.LIVE
    )
    display_name = models.CharField(max_length=120, null=True, blank=True)
    config_json = models.JSONField(default=dict, blank=True)
    scopes = models.JSONField(default=list, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(null=True, blank=True)
    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="connected_by",
        related_name="+",
    )

    class Meta:
        db_table = "connections"
        constraints = [
            choices_check("connections", "provider", ConnectionProvider),
            choices_check("connections", "status", ConnectionStatus),
            choices_check("connections", "mode", ConnectionMode),
        ]

    @property
    def is_sandbox(self) -> bool:
        return self.mode == ConnectionMode.SANDBOX

    @property
    def is_usable(self) -> bool:
        return self.status == ConnectionStatus.CONNECTED


class SandboxRecord(TimestampedModel):
    """What a sandbox connection 'did': virtual sheet rows, would-be-sent messages."""

    connection = models.ForeignKey(
        Connection, on_delete=models.CASCADE, related_name="sandbox_records"
    )
    resource = models.CharField(max_length=120)  # e.g. sheet name, "outbox"
    row_number = models.IntegerField(null=True, blank=True)
    data_json = models.JSONField()

    class Meta:
        db_table = "sandbox_records"
