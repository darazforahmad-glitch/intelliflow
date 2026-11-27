"""UC-12 dashboard (REQ-DR-1..5), platform administration (REQ-PA-1..5), notifications and push."""

from __future__ import annotations

from typing import Any


from intelliflow.accounts.models import User
from tests.api.test_webhooks import ORDER, active_order_automation, post_whatsapp, whatsapp_phone_id
from tests.conftest import Api, register_and_login


def complete_one_order(api: Api, message_id: str) -> None:
    post_whatsapp(api, whatsapp_phone_id(api), ORDER, message_id)
    approval = api.get("/approvals").json()[0]
    api.post(f"/approvals/{approval['id']}/decision", {"decision": "approve"})


def test_dashboard_reports_runs_and_hours_saved(owner: Api) -> None:
    active_order_automation(owner)
    for i in range(3):
        complete_one_order(owner, f"wamid.D{i}")
    post_whatsapp(owner, whatsapp_phone_id(owner), ORDER, "wamid.PENDING")
    data = owner.get("/dashboard").json()
    kpis = data["kpis"]
    assert kpis["runs"] == 4 and kpis["runs_succeeded"] == 3 and kpis["tasks_handled"] == 3
    assert kpis["approvals_pending"] == 1 and kpis["active_automations"] == 1
    assert kpis["hours_saved"] == round(9 / 60, 1)  # 3 runs x 3 minutes
    assert (
        len(data["hours_saved_per_day"]) == 7 and "/" in data["hours_saved_per_day"][0]["date"]
    )  # DD/MM/YYYY
    automations = owner.get("/automations").json()
    assert automations[0]["stats"]["runs_succeeded"] == 3  # REQ-DR-3
    csv_text = owner.get("/reports/weekly.csv").text
    assert csv_text.startswith("Date (DD/MM/YYYY)") and csv_text.count("succeeded") == 3  # REQ-DR-5
    failed = owner.get("/runs", params={"status": "failed"}).json()
    assert failed == []  # REQ-DR-4 filter by status


def test_notifications_are_created_for_approvals(owner: Api) -> None:
    active_order_automation(owner)
    post_whatsapp(owner, whatsapp_phone_id(owner), ORDER, "wamid.N1")
    notes = owner.client.get("/api/v1/notifications", headers=owner.headers).json()
    assert notes["unread"] >= 1 and notes["items"][0]["kind"] == "approval.created"
    owner.client.post("/api/v1/notifications/read-all", headers=owner.headers)
    assert owner.client.get("/api/v1/notifications", headers=owner.headers).json()["unread"] == 0


def test_push_subscription_lifecycle(owner: Api) -> None:
    sub = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
        "keys": {
            "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
            "auth": "tBHItJI5svbpez7KI4CCXg",
        },
    }
    assert (
        owner.client.post("/api/v1/push/subscriptions", json=sub, headers=owner.headers).status_code
        == 200
    )
    assert (
        owner.client.request(
            "DELETE",
            "/api/v1/push/subscriptions",
            json={"endpoint": sub["endpoint"]},
            headers=owner.headers,
        ).status_code
        == 200
    )
    assert owner.client.get("/api/v1/push/config", headers=owner.headers).json()["enabled"] is False


def admin_headers(client) -> dict[str, str]:  # type: ignore[no-untyped-def]
    token = register_and_login(client, email="admin@intelliflow.pk")
    User.objects.filter(email="admin@intelliflow.pk").update(is_platform_admin=True)
    return {"Authorization": f"Bearer {token}"}


def test_admin_requires_platform_admin(owner: Api) -> None:
    assert owner.client.get("/api/v1/admin/metrics", headers=owner.headers).status_code == 403


def test_admin_metrics_and_suspension(owner: Api, client) -> None:  # type: ignore[no-untyped-def]
    active_order_automation(owner)
    complete_one_order(owner, "wamid.ADMIN1")
    headers = admin_headers(client)
    metrics = client.get("/api/v1/admin/metrics", headers=headers).json()
    assert metrics["workspaces"]["active"] == 1 and metrics["active_automations"] == 1
    assert metrics["llm_month"]["calls"] > 0  # REQ-PA-2: LLM usage is metered
    listing = client.get("/api/v1/admin/workspaces", headers=headers).json()
    assert listing[0]["ai_credits_used"] > 0 and "payload" not in str(
        listing
    )  # BR-8: no message content

    r = client.post(
        f"/api/v1/admin/workspaces/{owner.workspace_id}/suspend",
        json={"reason": "Policy violation"},
        headers=headers,
    )
    assert "1 automation(s) paused" in r.json()["message"]  # REQ-PA-4
    assert owner.get("/dashboard").status_code == 403  # suspended workspaces are blocked
    client.post(f"/api/v1/admin/workspaces/{owner.workspace_id}/reactivate", headers=headers)
    assert owner.get("/dashboard").status_code == 200
    logs = client.get("/api/v1/admin/audit-logs", headers=headers).json()  # REQ-PA-5
    assert {"admin.workspace_suspended", "automation.activated", "approval.decided"} <= {
        entry["action"] for entry in logs
    }


def test_ai_credit_limit_pauses_ai_steps(owner: Api, client) -> None:  # type: ignore[no-untyped-def]
    headers = admin_headers(client)
    client.patch(
        f"/api/v1/admin/workspaces/{owner.workspace_id}/limits",
        json={"ai_credit_limit": 0},
        headers=headers,
    )
    r = owner.post("/interviews", {"process_name": "Orders"})
    assert (
        r.status_code == 402 and r.json()["error"]["code"] == "ai_credits_exhausted"
    )  # BR-6 / REQ-PA-3


def test_admin_template_versioning(client) -> None:  # type: ignore[no-untyped-def]
    headers = admin_headers(client)
    templates = client.get("/api/v1/admin/templates", headers=headers).json()
    base = next(t for t in templates if t["code"] == "order_confirmation_reply")
    body: dict[str, Any] = {
        k: base[k]
        for k in ("code", "name", "category", "description", "match", "required_connections")
    }
    body["definition"] = {**base["definition"], "name": "Order confirmation message v2"}
    v2 = client.post(
        "/api/v1/admin/templates/order_confirmation_reply/versions", json=body, headers=headers
    ).json()
    assert v2["version"] == 2 and v2["is_active"] is False
    client.post(f"/api/v1/admin/templates/{v2['id']}/publish", headers=headers)
    active = [
        t
        for t in client.get("/api/v1/admin/templates", headers=headers).json()
        if t["code"] == "order_confirmation_reply" and t["is_active"]
    ]
    assert [t["version"] for t in active] == [2]  # exactly one published version per code
    body["definition"] = {
        "schema_version": 1,
        "name": "bad",
        "trigger": {"type": "manual"},
        "blocks": [],
    }
    assert (
        client.post(
            "/api/v1/admin/templates/order_confirmation_reply/versions", json=body, headers=headers
        ).status_code
        == 422
    )


def test_dev_outbox_lists_emails(client) -> None:  # type: ignore[no-untyped-def]
    client.post(
        "/api/v1/auth/register",
        json={"full_name": "Dev Test", "email": "dev@example.com", "password": "Secret123"},
    )
    outbox = client.get("/api/v1/dev/outbox", params={"to": "dev@example.com"}).json()
    assert outbox[0]["subject"] == "Verify your IntelliFlow e-mail address"
