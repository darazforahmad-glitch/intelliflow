"""Load tests (Section 5.4, PERF-1, PERF-2, PERF-5).

    locust -f loadtests/locustfile.py --host http://localhost:8000 \
        --users 50 --spawn-rate 10 --run-time 2m --headless

Environment:
    LOCUST_EMAIL / LOCUST_PASSWORD   an owner account (python manage.py demo creates one)
    LOCUST_PHONE_NUMBER_ID           phone-number id of a sandbox WhatsApp connection
    WHATSAPP_APP_SECRET              the API's webhook secret (dev default otherwise)

The run fails (exit code 1) when the 95th percentile of page/API reads exceeds 2 s
(PERF-1) or of webhook acknowledgements exceeds 1 s (PERF-2 target).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid

from locust import HttpUser, between, events, task

EMAIL = os.environ.get("LOCUST_EMAIL", "demo@intelliflow.pk")
PASSWORD = os.environ.get("LOCUST_PASSWORD", "Demo12345")
PHONE_NUMBER_ID = os.environ.get("LOCUST_PHONE_NUMBER_ID", "")
SECRET = os.environ.get("WHATSAPP_APP_SECRET", "dev-whatsapp-app-secret")


SESSION: dict[str, str] = {}


@events.test_start.add_listener
def sign_in_once(environment, **_kwargs) -> None:  # type: ignore[no-untyped-def]
    """Sign in once and share the session: sign-in itself is rate limited per IP (SEC-7),
    and real users are already signed in while they work."""
    import httpx

    host = environment.host
    pair = httpx.post(f"{host}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=10).json()
    if "access_token" not in pair:
        raise RuntimeError(f"Could not sign in as {EMAIL}: {pair}")
    me = httpx.get(f"{host}/api/v1/auth/me", headers={"Authorization": f"Bearer {pair['access_token']}"}, timeout=10).json()
    SESSION["token"] = pair["access_token"]
    SESSION["ws"] = f"/api/v1/workspaces/{me['memberships'][0]['workspace_id']}"


class OwnerUser(HttpUser):
    """Owners and staff reading the dashboard, approvals and automations."""

    weight = 4
    wait_time = between(1, 3)

    def on_start(self) -> None:
        self.client.headers["Authorization"] = f"Bearer {SESSION['token']}"
        self.ws = SESSION["ws"]

    @task(4)
    def dashboard(self) -> None:
        self.client.get(f"{self.ws}/dashboard?days=7", name="GET /dashboard")

    @task(3)
    def approvals(self) -> None:
        self.client.get(f"{self.ws}/approvals", name="GET /approvals")

    @task(2)
    def automations(self) -> None:
        self.client.get(f"{self.ws}/automations", name="GET /automations")

    @task(1)
    def runs(self) -> None:
        self.client.get(f"{self.ws}/runs?limit=50", name="GET /runs")


class WhatsAppWebhook(HttpUser):
    """Meta delivering signed customer messages (PERF-2: acknowledged fast, processed async)."""

    weight = 1
    wait_time = between(0.5, 2)

    @task
    def inbound_message(self) -> None:
        if not PHONE_NUMBER_ID:
            return
        body = json.dumps({"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "15550000000", "phone_number_id": PHONE_NUMBER_ID},
            "contacts": [{"profile": {"name": "Load Test"}, "wa_id": "923001234567"}],
            "messages": [{"from": "923001234567", "id": f"wamid.LOAD{uuid.uuid4().hex}", "timestamp": str(int(time.time())),
                          "type": "text", "text": {"body": "Mujhe 1 kurta chahiye medium black. Address: House 1 Lahore. Total Rs 2500"}}],
        }}]}]}, separators=(",", ":")).encode()
        signature = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        self.client.post("/api/v1/webhooks/whatsapp", data=body, name="POST /webhooks/whatsapp",
                         headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature})


@events.quitting.add_listener
def check_thresholds(environment, **_kwargs) -> None:  # type: ignore[no-untyped-def]
    stats = environment.stats
    failures = []
    for name in ("GET /dashboard", "GET /approvals", "GET /automations", "GET /runs"):
        entry = stats.get(name, "GET")
        if entry.num_requests and entry.get_response_time_percentile(0.95) > 2000:
            failures.append(f"{name} p95 {entry.get_response_time_percentile(0.95)} ms > 2000 ms (PERF-1)")
    webhook = stats.get("POST /webhooks/whatsapp", "POST")
    if webhook.num_requests and webhook.get_response_time_percentile(0.95) > 1000:
        failures.append(f"webhook p95 {webhook.get_response_time_percentile(0.95)} ms > 1000 ms (PERF-2 target)")
    if stats.total.fail_ratio > 0.01:
        failures.append(f"error ratio {stats.total.fail_ratio:.2%} > 1%")
    for failure in failures:
        print("THRESHOLD FAILED:", failure)
    if failures:
        environment.process_exit_code = 1
