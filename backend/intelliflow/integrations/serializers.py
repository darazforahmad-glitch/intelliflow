"""Integration Management requests and responses (UC-06, REQ-IN-1..7)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from intelliflow.core.api.fields import dt
from intelliflow.integrations import services
from intelliflow.integrations.connectors.registry import PROVIDER_LABELS
from intelliflow.integrations.models import Connection

PROVIDERS = ["whatsapp", "gmail", "google_sheets", "webform"]
SAFE_CONFIG = {
    "phone_number_id",
    "display_phone_number",
    "waba_id",
    "spreadsheet_id",
    "spreadsheet_name",
    "form_name",
}


class SandboxSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(PROVIDERS)


class WhatsAppConnectSerializer(serializers.Serializer):
    phone_number_id = serializers.RegexField(r"^\d+$", min_length=5, max_length=40)
    waba_id = serializers.RegexField(r"^\d+$", min_length=5, max_length=40)
    access_token = serializers.CharField(min_length=20, max_length=1000)
    display_phone_number = serializers.CharField(
        max_length=30, required=False, allow_null=True, allow_blank=True
    )


class WebformSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=2, max_length=120)


class ConnectionConfigSerializer(serializers.Serializer):
    config = serializers.DictField()


class SimulateSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=4000, required=False, allow_null=True, allow_blank=True)
    sender = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    name = serializers.CharField(max_length=80, required=False, allow_null=True, allow_blank=True)
    subject = serializers.CharField(
        max_length=250, required=False, allow_null=True, allow_blank=True
    )
    body = serializers.CharField(max_length=8000, required=False, allow_null=True, allow_blank=True)
    fields = serializers.DictField(required=False, allow_null=True)


class GoogleAuthorizeQuerySerializer(serializers.Serializer):
    provider = serializers.CharField()


def connection_out(connection: Connection) -> dict[str, Any]:
    return {
        "id": str(connection.id),
        "provider": str(connection.provider),
        "label": PROVIDER_LABELS[connection.provider],
        "mode": str(connection.mode),
        "status": str(connection.status),
        "display_name": connection.display_name,
        "external_account_id": connection.external_account_id,
        "config": {k: v for k, v in (connection.config_json or {}).items() if k in SAFE_CONFIG},
        "last_error": connection.last_error,
        "created_at": dt(connection.created_at),
        "webhook_url": services.webform_url(connection),
        # tokens themselves are never returned (REQ-IN-5)
        "has_credentials": connection.token_encrypted is not None,
    }
