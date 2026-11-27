"""Algorithm 5.4 webhook handling, UC-10 Execute Automation Run, UC-11 Review Approval Request."""

from __future__ import annotations

from typing import Any

from django.conf import settings

from intelliflow.integrations.webhooks import build_whatsapp_payload, sign
from tests.api.test_automations import ORDER_SAMPLE, generated_order_automation
from tests.conftest import Api, connect_sandbox

ORDER = "Assalam o alaikum, mujhe 2 kurtay chahiye medium size black colour. Address: House 12, Street 5, Gulberg Lahore. Total Rs 4500"


def active_order_automation(api: Api) -> dict[str, Any]:
    automation = generated_order_automation(api)
    api.post(f"/automations/{automation['id']}/test", {"sample": ORDER_SAMPLE})
    assert api.post(f"/automations/{automation['id']}/activate").status_code == 200
    return automation


def post_whatsapp(
    api: Api, phone_number_id: str, text: str, message_id: str, signature: str | None = "valid"
) -> Any:
    raw = build_whatsapp_payload(
        phone_number_id=phone_number_id,
        wa_id="923001234567",
        name="Ayesha",
        text=text,
        message_id=message_id,
    )
    headers = {"Content-Type": "application/json"}
    if signature == "valid":
        headers["X-Hub-Signature-256"] = sign(raw, settings.WHATSAPP_APP_SECRET)
    elif signature:
        headers["X-Hub-Signature-256"] = signature
    return api.client.post("/api/v1/webhooks/whatsapp", content=raw, headers=headers)


def whatsapp_phone_id(api: Api) -> str:
    return next(c for c in api.get("/connections").json() if c["provider"] == "whatsapp")["config"][
        "phone_number_id"
    ]


def test_meta_verification_handshake(client) -> None:  # type: ignore[no-untyped-def]
    ok = client.get(
        "/api/v1/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.WHATSAPP_VERIFY_TOKEN,
            "hub.challenge": "42",
        },
    )
    assert ok.status_code == 200 and ok.text == "42"
    bad = client.get(
        "/api/v1/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "42"},
    )
    assert bad.status_code == 403


def test_unsigned_or_forged_webhooks_are_rejected(owner: Api) -> None:
    active_order_automation(owner)
    phone_id = whatsapp_phone_id(owner)
    assert post_whatsapp(owner, phone_id, ORDER, "wamid.A1", signature=None).status_code == 401
    assert (
        post_whatsapp(
            owner, phone_id, ORDER, "wamid.A2", signature="sha256=" + "0" * 64
        ).status_code
        == 401
    )
    assert owner.get("/runs").json() == []  # SEC-5: nothing was processed


def test_signed_webhook_runs_automation_and_approval_completes_it(owner: Api) -> None:
    active_order_automation(owner)
    r = post_whatsapp(owner, whatsapp_phone_id(owner), ORDER, "wamid.ORDER1")
    assert r.status_code == 200 and r.json()["queued"] == 1
    runs = owner.get("/runs").json()
    assert len(runs) == 1 and runs[0]["status"] == "waiting_approval"

    approvals = owner.get("/approvals").json()
    assert len(approvals) == 1
    approval = approvals[0]
    assert (
        approval["payload"]["input"] == ORDER
    )  # REQ-AP-1: original input, AI output and proposed action
    assert approval["payload"]["proposed_action"]["operation"] == "send_text"

    r = owner.post(
        f"/approvals/{approval['id']}/decision",
        {"decision": "edit", "edited_params": {"text": "Shukriya Ayesha! Order confirm ho gaya."}},
    )
    assert (
        r.status_code == 200
        and r.json()["status"] == "edited"
        and r.json()["decided_by_name"] == "Ayesha Khan"
    )
    detail = owner.get(f"/runs/{runs[0]['id']}").json()
    assert detail["status"] == "succeeded" and float(detail["minutes_saved"]) == 3.0
    assert [s["status"] for s in detail["steps"]] == [
        "succeeded",
        "succeeded",
        "succeeded",
        "skipped",
        "succeeded",
        "succeeded",
        "succeeded",
    ]

    whatsapp = next(c for c in owner.get("/connections").json() if c["provider"] == "whatsapp")
    sandbox = owner.get(f"/connections/{whatsapp['id']}/sandbox").json()
    assert sandbox["outbox"][0]["text"] == "Shukriya Ayesha! Order confirm ho gaya."
    sheets = next(c for c in owner.get("/connections").json() if c["provider"] == "google_sheets")
    rows = owner.get(f"/connections/{sheets['id']}/sandbox").json()["sheets"]["Orders"]
    assert rows[0]["Items"].startswith("2 kurtay") and rows[0]["Status"] == "New"


def test_duplicate_webhooks_start_one_run(owner: Api) -> None:
    active_order_automation(owner)
    phone_id = whatsapp_phone_id(owner)
    assert post_whatsapp(owner, phone_id, ORDER, "wamid.DUP").json()["queued"] == 1
    assert post_whatsapp(owner, phone_id, ORDER, "wamid.DUP").json() == {
        "status": "ok",
        "queued": 0,
        "duplicates": 1,
    }
    assert len(owner.get("/runs").json()) == 1  # REQ-WE-3


def test_staff_can_decide_approvals_but_not_change_automations(owner: Api, client) -> None:  # type: ignore[no-untyped-def]
    from tests.conftest import latest_link, register_and_login

    automation = active_order_automation(owner)
    post_whatsapp(owner, whatsapp_phone_id(owner), ORDER, "wamid.STAFF")
    owner.post("/invitations", {"email": "staff2@example.com"})
    invite = latest_link("staff2@example.com", "invite?token")
    token = register_and_login(client, email="staff2@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/invitations/accept", json={"token": invite}, headers=headers)
    approval = client.get(owner.url("/approvals"), headers=headers).json()[0]
    r = client.post(
        owner.url(f"/approvals/{approval['id']}/decision"),
        json={"decision": "approve"},
        headers=headers,
    )
    assert r.status_code == 200  # BR-2: staff review approvals
    assert (
        client.post(
            owner.url(f"/automations/{automation['id']}/pause"), headers=headers
        ).status_code
        == 403
    )  # BR-1


def test_webform_accepts_json_and_form_data(owner: Api) -> None:
    connect_sandbox(owner, "whatsapp", "google_sheets")
    form = owner.post("/connections/webform", {"name": "Contact form"}).json()
    url = form["webhook_url"].split("/api/v1")[1]
    automation = owner.post(
        "/automations/from-template", {"template_code": "webform_lead_capture"}
    ).json()
    owner.post(
        f"/automations/{automation['id']}/test",
        {"sample": {"fields": {"name": "Bilal", "phone": "03001112233"}}},
    )
    assert owner.post(f"/automations/{automation['id']}/activate").status_code == 200

    r = owner.client.post(
        f"/api/v1{url}",
        json={"name": "Bilal", "phone": "03001112233", "message": "Price list please"},
    )
    assert r.status_code == 202
    r = owner.client.post(f"/api/v1{url}", data={"name": "Sana", "phone": "03214445566"})
    assert r.status_code == 202  # REQ-IN-4: JSON and form-encoded
    assert len(owner.get("/runs").json()) == 2
    wrong = url.rsplit("/", 1)[0] + "/not-the-token"
    assert owner.client.post(f"/api/v1{wrong}", json={"name": "x"}).status_code == 404


def test_simulator_drives_the_real_gateway(owner: Api) -> None:
    active_order_automation(owner)
    whatsapp = next(c for c in owner.get("/connections").json() if c["provider"] == "whatsapp")
    r = owner.post(f"/connections/{whatsapp['id']}/simulate", {"text": ORDER, "name": "Ayesha"})
    assert r.status_code == 202 and r.json()["queued"] == 1
    assert owner.get("/runs").json()[0]["status"] == "waiting_approval"


_ = connect_sandbox
