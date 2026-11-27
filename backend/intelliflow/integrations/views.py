"""Integration Management API (UC-06) and the public webhook endpoints (Algorithm 5.4)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from intelliflow.core.api.permissions import message
from intelliflow.core.api.viewsets import WorkspaceScopedViewSet
from intelliflow.core.enums import ConnectionProvider
from intelliflow.core.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from intelliflow.core.security import constant_time_equals
from intelliflow.integrations import serializers as s
from intelliflow.integrations import services
from intelliflow.integrations.connectors.registry import PROVIDER_LABELS
from intelliflow.integrations.gateway import ingest_webform, ingest_whatsapp
from intelliflow.integrations.models import Connection
from intelliflow.integrations.webhooks import build_whatsapp_payload, sign

MAX_BODY_BYTES = 256 * 1024


def _body(serializer_class: type, request: Request) -> dict[str, Any]:
    body = serializer_class(data=request.data)
    body.is_valid(raise_exception=True)
    return dict(body.validated_data)


class ConnectionViewSet(WorkspaceScopedViewSet):
    owner_actions = {
        "sandbox_create",
        "whatsapp",
        "webform",
        "google_authorize",
        "partial_update",
        "destroy",
        "simulate",
    }

    def _connection(self, pk: str) -> Connection:
        return services.get_connection(self.ctx.workspace_id, pk)

    def list(self, request: Request, workspace_id: str) -> Response:
        return Response(
            [s.connection_out(c) for c in services.list_connections(self.ctx.workspace_id)]
        )

    @action(detail=False, methods=["post"], url_path="sandbox")
    def sandbox_create(self, request: Request, workspace_id: str) -> Response:
        provider = _body(s.SandboxSerializer, request)["provider"]
        connection = services.create_sandbox(self.ctx.workspace, self.ctx.user, provider)
        return Response(s.connection_out(connection), status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def whatsapp(self, request: Request, workspace_id: str) -> Response:
        data = _body(s.WhatsAppConnectSerializer, request)
        connection = services.connect_whatsapp(
            self.ctx.workspace,
            self.ctx.user,
            phone_number_id=data["phone_number_id"],
            waba_id=data["waba_id"],
            access_token=data["access_token"],
            display_phone_number=data.get("display_phone_number"),
        )
        return Response(s.connection_out(connection), status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def webform(self, request: Request, workspace_id: str) -> Response:
        name = _body(s.WebformSerializer, request)["name"]
        connection = services.create_webform(self.ctx.workspace, self.ctx.user, name)
        return Response(s.connection_out(connection), status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="google/authorize")
    def google_authorize(self, request: Request, workspace_id: str) -> Response:
        query = s.GoogleAuthorizeQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        provider = query.validated_data["provider"]
        if provider not in {"gmail", "google_sheets"}:
            raise ConflictError("Choose gmail or google_sheets.")
        url = services.google_authorization(self.ctx.workspace, self.ctx.user, provider)
        return Response({"authorization_url": url})

    def partial_update(self, request: Request, workspace_id: str, pk: str) -> Response:
        config = _body(s.ConnectionConfigSerializer, request)["config"]
        connection = services.update_config(self._connection(pk), config)
        return Response(s.connection_out(connection))

    def destroy(self, request: Request, workspace_id: str, pk: str) -> Response:
        connection = self._connection(pk)
        paused = services.disconnect(self.ctx.workspace, self.ctx.user, connection)
        suffix = f" {paused} automation(s) that use it were paused." if paused else ""
        return Response(
            message(f"{PROVIDER_LABELS[connection.provider]} was disconnected.{suffix}")
        )

    @action(detail=True, methods=["get"])
    def sandbox(self, request: Request, workspace_id: str, pk: str) -> Response:
        connection = self._connection(pk)
        if not connection.is_sandbox:
            raise ConflictError("Only sandbox connections have recorded data.")
        return Response(services.sandbox_view(connection))

    @action(detail=True, methods=["post"])
    def simulate(self, request: Request, workspace_id: str, pk: str) -> Response:
        """Send a realistic inbound event through the real gateway (signature, de-dupe, queue)."""
        data = _body(s.SimulateSerializer, request)
        connection = self._connection(pk)
        if not connection.is_sandbox and connection.provider != ConnectionProvider.WEBFORM:
            raise ConflictError("Simulation is only available for sandbox connections.")
        if connection.provider == ConnectionProvider.WHATSAPP:
            raw = build_whatsapp_payload(
                phone_number_id=str(connection.config_json["phone_number_id"]),
                wa_id=data.get("sender") or "923001234567",
                name=data.get("name") or "Test Customer",
                text=data.get("text") or "",
                message_id=f"wamid.SIM{uuid.uuid4().hex}",
            )
            result = ingest_whatsapp(raw, sign(raw, settings.WHATSAPP_APP_SECRET))
            return Response({"status": "queued", **result}, status=status.HTTP_202_ACCEPTED)
        if connection.provider == ConnectionProvider.WEBFORM:
            token_url = services.webform_url(connection) or ""
            event_id = ingest_webform(
                connection.id, token_url.rsplit("/", 1)[-1], data.get("fields") or {}, None
            )
            return Response(
                {"status": "queued", "event_id": event_id}, status=status.HTTP_202_ACCEPTED
            )
        if connection.provider == ConnectionProvider.GMAIL:
            from intelliflow.runs.tasks import process_trigger

            message_id = f"gmail:SIM{uuid.uuid4().hex}"
            trigger = {
                "message_id": message_id,
                "from": data.get("sender") or "customer@example.com",
                "to": connection.external_account_id,
                "subject": data.get("subject") or "",
                "body": data.get("body") or data.get("text") or "",
                "received_at": None,
            }
            process_trigger.delay(
                str(self.ctx.workspace_id), "gmail.message_received", message_id, trigger
            )
            return Response(
                {"status": "queued", "event_id": message_id}, status=status.HTTP_202_ACCEPTED
            )
        raise ConflictError("Google Sheets does not send events.")


class PublicView(APIView):
    """No session: authenticity comes from signatures or secret URLs."""

    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]
    parser_classes: list[Any] = []  # the raw body is read (and verified) as bytes


class WhatsAppWebhookView(PublicView):
    def get(self, request: Request) -> HttpResponse:
        """Meta's subscription handshake."""
        params = request.query_params
        mode, token = params.get("hub.mode"), params.get("hub.verify_token")
        challenge = params.get("hub.challenge")
        if mode is None or token is None or challenge is None:
            raise ValidationFailedError(
                "hub.mode, hub.verify_token and hub.challenge are required."
            )
        if mode == "subscribe" and constant_time_equals(token, settings.WHATSAPP_VERIFY_TOKEN):
            return HttpResponse(challenge, content_type="text/plain; charset=utf-8")
        raise PermissionDeniedError("Verification failed.")

    def post(self, request: Request) -> Response:
        raw = request.body
        if len(raw) > MAX_BODY_BYTES:
            raise ValidationFailedError("Webhook body too large.")
        result = ingest_whatsapp(raw, request.headers.get("x-hub-signature-256"))
        return Response({"status": "ok", **result})  # acknowledged at once; workers do the rest


class WebformWebhookView(PublicView):
    def post(self, request: Request, connection_id: uuid.UUID, token: str) -> Response:
        raw = request.body
        if len(raw) > MAX_BODY_BYTES:
            raise ValidationFailedError("Form submission too large.")
        if "application/json" in request.headers.get("content-type", ""):
            try:
                data = json.loads(raw or b"{}")
            except json.JSONDecodeError as exc:
                raise ValidationFailedError("The submission is not valid JSON.") from exc
            if not isinstance(data, dict):
                raise ValidationFailedError("Send the form fields as a JSON object.")
        else:
            data = {k: v for k, v in request._request.POST.items() if isinstance(v, str)}
        event_id = ingest_webform(
            connection_id, token, data, request.headers.get("idempotency-key")
        )
        return Response(
            {"status": "received", "event_id": event_id}, status=status.HTTP_202_ACCEPTED
        )


class GoogleCallbackView(PublicView):
    def get(self, request: Request) -> HttpResponseRedirect:
        frontend = settings.FRONTEND_URL
        code, state = request.query_params.get("code"), request.query_params.get("state")
        error = request.query_params.get("error")
        if error or not code or not state:
            return HttpResponseRedirect(f"{frontend}/integrations?error={error or 'cancelled'}")
        connection = services.complete_google_oauth(code, state)
        return HttpResponseRedirect(f"{frontend}/integrations?connected={connection.provider}")
