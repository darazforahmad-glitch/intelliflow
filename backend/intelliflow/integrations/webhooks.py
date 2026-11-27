"""Webhook helpers: HMAC-SHA256 signature check and WhatsApp payload parsing (Algorithm 5.4, SEC-5)."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any


def sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(raw_body: bytes, header: str | None, secret: str) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    return hmac.compare_digest(header, sign(raw_body, secret))


def _message_text(message: dict[str, Any]) -> str:
    kind = message.get("type")
    if kind == "text":
        return str(message.get("text", {}).get("body", ""))
    if kind in {"image", "video", "document"}:
        return str(message.get(kind, {}).get("caption", ""))
    if kind == "button":
        return str(message.get("button", {}).get("text", ""))
    if kind == "interactive":
        interactive = message.get("interactive", {})
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        return str(reply.get("title", ""))
    return ""


def extract_whatsapp_events(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a WhatsApp Cloud API webhook into one event per inbound message."""
    events: list[dict[str, Any]] = []
    for entry in body.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            if change.get("field") != "messages":
                continue
            value = change.get("value", {}) or {}
            phone_number_id = (value.get("metadata") or {}).get("phone_number_id")
            names = {
                c.get("wa_id"): (c.get("profile") or {}).get("name")
                for c in value.get("contacts", []) or []
            }
            for message in value.get("messages", []) or []:
                if not message.get("id"):
                    continue
                try:
                    sent_at = datetime.fromtimestamp(int(message.get("timestamp")), UTC).isoformat()
                except (TypeError, ValueError):
                    sent_at = datetime.now(UTC).isoformat()
                events.append(
                    {
                        "event_id": message["id"],
                        "phone_number_id": phone_number_id,
                        "trigger": {
                            "message_id": message["id"],
                            "from": message.get("from"),
                            "name": names.get(message.get("from")),
                            "text": _message_text(message),
                            "type": message.get("type", "text"),
                            "timestamp": sent_at,
                        },
                    }
                )
    return events


def build_whatsapp_payload(
    *,
    phone_number_id: str,
    wa_id: str,
    name: str,
    text: str,
    message_id: str,
    timestamp: datetime | None = None,
) -> bytes:
    """A correctly shaped Cloud API webhook body (used by the simulator and tests)."""
    ts = int((timestamp or datetime.now(UTC)).timestamp())
    body = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550000000",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [{"profile": {"name": name}, "wa_id": wa_id}],
                            "messages": [
                                {
                                    "from": wa_id,
                                    "id": message_id,
                                    "timestamp": str(ts),
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    return json.dumps(body, separators=(",", ":")).encode()
