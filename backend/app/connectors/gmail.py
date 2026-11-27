"""Gmail connector: send e-mails, notify the owner, and poll new messages (Table 5.2)."""

from __future__ import annotations

import base64
import re
from email.message import EmailMessage
from typing import Any

from app.connectors.base import Connector, OperationSpec
from app.engine.errors import ConnectionUnavailableError, PermanentBlockError, TransientBlockError

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class GmailConnector(Connector):
    provider = "gmail"
    label = "Gmail"
    operations = {
        "send_email": OperationSpec(
            "send_email",
            "Send an e-mail",
            writes=True,
            customer_message=True,
            required=("to", "subject", "body"),
        ),
        "notify_owner": OperationSpec(
            "notify_owner", "E-mail the owner", writes=True, required=("subject", "body")
        ),
    }

    def op_send_email(self, params: dict[str, Any]) -> dict[str, Any]:
        to = self._address(params["to"])
        return self._send(to, str(params["subject"])[:250], str(params["body"]), "send_email")

    def op_notify_owner(self, params: dict[str, Any]) -> dict[str, Any]:
        owner_email = self.ctx.extras.get("owner_email") or (
            self.ctx.connection.external_account_id if self.ctx.connection else None
        )
        if not owner_email:
            raise PermanentBlockError(
                "There is no owner e-mail address to send to.", code="no_owner_email"
            )
        return self._send(
            self._address(owner_email),
            str(params["subject"])[:250],
            str(params["body"]),
            "notify_owner",
        )

    @staticmethod
    def _address(value: Any) -> str:
        match = re.search(r"[^<\s]+@[^>\s]+", str(value or ""))
        address = match.group(0) if match else ""
        if not _EMAIL.match(address):
            raise PermanentBlockError(
                f"“{value}” is not a valid e-mail address.", code="invalid_email"
            )
        return address

    def _send(self, to: str, subject: str, body: str, operation: str) -> dict[str, Any]:
        if self.sandbox:
            ref = self.record_sandbox(operation, {"to": to, "subject": subject, "body": body})
            return {"message_id": ref, "to": to, "status": "sandbox"}
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        from app.connectors.google_auth import build_credentials

        if not self.ctx.credentials:
            raise ConnectionUnavailableError("Gmail is not connected.")
        message = EmailMessage()
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        try:
            service = build(
                "gmail",
                "v1",
                credentials=build_credentials(self.ctx.credentials, self.ctx.save_credentials),
                cache_discovery=False,
            )
            sent = (
                service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute(num_retries=0)
            )
        except HttpError as exc:
            if exc.resp.status == 429 or exc.resp.status >= 500:
                raise TransientBlockError("Gmail is temporarily unavailable. Will retry.") from exc
            raise PermanentBlockError(
                f"Gmail refused the e-mail ({exc.resp.status}).", code="gmail_rejected"
            ) from exc
        return {"message_id": sent.get("id"), "to": to, "status": "sent"}


def fetch_new_messages(connector: GmailConnector, max_results: int = 20) -> list[dict[str, Any]]:
    """Poll unread inbox messages (live mode) and convert them to trigger payloads."""
    from googleapiclient.discovery import build

    from app.connectors.google_auth import build_credentials

    if not connector.ctx.credentials:
        raise ConnectionUnavailableError("Gmail is not connected.")
    service = build(
        "gmail",
        "v1",
        credentials=build_credentials(connector.ctx.credentials, connector.ctx.save_credentials),
        cache_discovery=False,
    )
    listing = (
        service.users()
        .messages()
        .list(userId="me", q="is:unread in:inbox newer_than:2d", maxResults=max_results)
        .execute()
    )
    messages = []
    for item in listing.get("messages", []):
        full = service.users().messages().get(userId="me", id=item["id"], format="full").execute()
        headers = {
            h["name"].lower(): h["value"] for h in full.get("payload", {}).get("headers", [])
        }
        messages.append(
            {
                "message_id": full["id"],
                "from": headers.get("from", ""),
                "to": headers.get("to", ""),
                "subject": headers.get("subject", ""),
                "body": _plain_body(full.get("payload", {})),
                "received_at": full.get("internalDate"),
            }
        )
    return messages


def _plain_body(payload: dict[str, Any]) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode(errors="replace")
    for part in payload.get("parts", []) or []:
        text = _plain_body(part)
        if text:
            return text
    return ""
