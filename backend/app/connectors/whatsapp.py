"""WhatsApp Cloud API connector (Meta Graph API), Table 5.2."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.connectors import customer_window
from app.connectors.base import Connector, OperationSpec, normalize_msisdn
from app.core.config import get_settings
from app.engine.errors import (
    ConnectionUnavailableError,
    PermanentBlockError,
    TransientBlockError,
    WindowClosedError,
)


class WhatsAppConnector(Connector):
    provider = "whatsapp"
    label = "WhatsApp"
    operations = {
        "send_text": OperationSpec(
            "send_text",
            "Send a message",
            writes=True,
            customer_message=True,
            required=("to", "text"),
        ),
        "send_template": OperationSpec(
            "send_template",
            "Send an approved template",
            writes=True,
            customer_message=True,
            required=("to", "template"),
        ),
    }

    # ------------------------------------------------------------------ operations
    def op_send_text(self, params: dict[str, Any]) -> dict[str, Any]:
        to = normalize_msisdn(params["to"])
        text = str(params["text"]).strip()
        if not text:
            raise PermanentBlockError("The WhatsApp message is empty.", code="empty_message")
        if len(text) > 4096:
            raise PermanentBlockError(
                "WhatsApp messages can be at most 4,096 characters.", code="message_too_long"
            )
        if not self._window_open(to):
            template = params.get("fallback_template")
            if template:  # BR-4: outside the window only approved templates may be sent
                result = self.op_send_template(
                    {
                        "to": to,
                        "template": template,
                        "language": params.get("language", "en"),
                        "variables": params.get("template_variables") or [],
                    }
                )
                return {**result, "sent_as": "template", "reason": "customer_window_closed"}
            raise WindowClosedError(
                "More than 24 hours have passed since the customer's last message, so WhatsApp only allows an "
                "approved template message.",
                to=to,
                text=text,
            )
        if self.sandbox:
            ref = self.record_sandbox("send_text", {"to": to, "text": text})
            return {"message_id": ref, "to": to, "status": "sandbox", "sent_as": "text"}
        body = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        return {**self._post_message(body), "to": to, "sent_as": "text"}

    def op_send_template(self, params: dict[str, Any]) -> dict[str, Any]:
        to = normalize_msisdn(params["to"])
        variables = [str(v) for v in (params.get("variables") or [])]
        if self.sandbox:
            ref = self.record_sandbox(
                "send_template", {"to": to, "template": params["template"], "variables": variables}
            )
            return {
                "message_id": ref,
                "to": to,
                "status": "sandbox",
                "sent_as": "template",
                "template": params["template"],
            }
        components = (
            [{"type": "body", "parameters": [{"type": "text", "text": v} for v in variables]}]
            if variables
            else []
        )
        body = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": params["template"],
                "language": {"code": params.get("language", "en")},
                "components": components,
            },
        }
        return {
            **self._post_message(body),
            "to": to,
            "sent_as": "template",
            "template": params["template"],
        }

    # ------------------------------------------------------------------ helpers
    def _window_open(self, to: str) -> bool:
        if self.ctx.extras.get("test_run"):
            return True  # test runs never reach customers (SAF-5)
        trigger = self.ctx.extras.get("trigger") or {}
        fallback: datetime | None = None
        try:
            if (
                trigger.get("from")
                and normalize_msisdn(trigger["from"]) == to
                and trigger.get("timestamp")
            ):
                fallback = datetime.fromisoformat(str(trigger["timestamp"]))
        except (PermanentBlockError, ValueError):
            fallback = None
        return customer_window.is_open(self.ctx.workspace.id, to, fallback_last_inbound=fallback)

    def _post_message(self, body: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        connection = self.ctx.connection
        creds = self.ctx.credentials or {}
        phone_number_id = (connection.config_json if connection else {}).get("phone_number_id")
        if not phone_number_id or not creds.get("access_token"):
            raise ConnectionUnavailableError(
                "WhatsApp is not fully connected (missing phone number or access token)."
            )
        url = f"{settings.whatsapp_graph_base_url}/{settings.whatsapp_graph_api_version}/{phone_number_id}/messages"
        try:
            response = httpx.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {creds['access_token']}"},
                timeout=15,
            )
        except httpx.TransportError as exc:
            raise TransientBlockError("Could not reach WhatsApp. Will retry.") from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientBlockError(
                f"WhatsApp is temporarily unavailable ({response.status_code}). Will retry."
            )
        if response.status_code in {401, 403}:
            raise ConnectionUnavailableError(
                "WhatsApp rejected the access token. Please reconnect WhatsApp."
            )
        if response.status_code >= 400:
            message = (
                response.json().get("error", {}).get("message", response.text[:200])
                if response.content
                else ""
            )
            raise PermanentBlockError(
                f"WhatsApp refused the message: {message}", code="whatsapp_rejected"
            )
        data = response.json()
        return {"message_id": data.get("messages", [{}])[0].get("id"), "status": "sent"}
