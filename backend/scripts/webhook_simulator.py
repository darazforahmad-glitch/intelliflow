#!/usr/bin/env python3
"""Webhook simulator (Section 5.2 stubs): sends correctly signed WhatsApp Cloud API
webhook payloads to a running IntelliFlow API, so automations can be exercised end to
end without a real WhatsApp number.

    python scripts/webhook_simulator.py --phone-number-id <id> --text "Mujhe 2 kurtay chahiye..."
    python scripts/webhook_simulator.py --phone-number-id <id> --sample-orders --repeat 3

The phone-number id is shown on the Integrations page for the sandbox WhatsApp connection.
The app secret defaults to WHATSAPP_APP_SECRET (or the development default).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import uuid

import httpx

SAMPLE_ORDERS = [
    ("Ayesha", "923001234567", "Assalam o alaikum, mujhe 2 kurtay chahiye medium size black colour. Address: House 12, Street 5, Gulberg Lahore. Total Rs 4500"),
    ("Bilal", "923211112233", "Mujhe 1 shirt chahiye large white. Address: Flat 3, Block B, Johar Town Lahore. Total Rs 2200"),
    ("Hamza", "923455556677", "I want 4 suits medium navy. Address: Street 9, F-10 Islamabad. Total Rs 18,000"),
    ("Usman", "923127778899", "Kurta ki price kya hai? Available hai?"),
]


def payload(phone_number_id: str, wa_id: str, name: str, text: str) -> bytes:
    body = {"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "15550000000", "phone_number_id": phone_number_id},
        "contacts": [{"profile": {"name": name}, "wa_id": wa_id}],
        "messages": [{"from": wa_id, "id": f"wamid.SIM{uuid.uuid4().hex}", "timestamp": str(int(time.time())),
                      "type": "text", "text": {"body": text}}],
    }}]}]}
    return json.dumps(body, separators=(",", ":")).encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=os.environ.get("API_PUBLIC_URL", "http://localhost:8000"))
    parser.add_argument("--phone-number-id", required=True)
    parser.add_argument("--secret", default=os.environ.get("WHATSAPP_APP_SECRET", "dev-whatsapp-app-secret"))
    parser.add_argument("--text", help="message text (ignored with --sample-orders)")
    parser.add_argument("--from", dest="sender", default="923001234567")
    parser.add_argument("--name", default="Test Customer")
    parser.add_argument("--sample-orders", action="store_true", help="send a mix of Roman Urdu / English sample orders")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--bad-signature", action="store_true", help="send an invalid signature (should get 401)")
    args = parser.parse_args()
    messages = SAMPLE_ORDERS if args.sample_orders else [(args.name, args.sender, args.text or "Hello")]
    with httpx.Client(timeout=10) as client:
        for _ in range(args.repeat):
            for name, wa_id, text in messages:
                raw = payload(args.phone_number_id, wa_id, name, text)
                digest = hmac.new(args.secret.encode(), raw, hashlib.sha256).hexdigest()
                signature = "sha256=" + ("0" * 64 if args.bad_signature else digest)
                response = client.post(f"{args.url}/api/v1/webhooks/whatsapp", content=raw,
                                       headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature})
                print(f"{response.status_code} {name}: {text[:50]}... -> {response.text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
