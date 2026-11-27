"""UC-07 Generate Automation, UC-09 Activate/Pause, Algorithm 5.3, BR-1/BR-3, REQ-AB-1..8, REQ-IN-7, SAF-1/2."""

from __future__ import annotations

import copy
from typing import Any

from app.llm.base import LLMTask
from app.llm.fake_client import ScriptedLLMClient
from app.seeds.templates import TEMPLATE_LIBRARY
from tests.conftest import Api, connect_sandbox, run_order_interview

ORDER_SAMPLE = {
    "text": "Mujhe 2 kurtay chahiye medium black. Address: House 12, Gulberg Lahore. Total Rs 4500",
    "name": "Ayesha",
}


def order_entry_opportunity(process_map: dict[str, Any]) -> dict[str, Any]:
    return next(
        o for o in process_map["opportunities"] if o["template"]["code"] == "whatsapp_order_entry"
    )


def generated_order_automation(api: Api) -> dict[str, Any]:
    process_map = run_order_interview(api)
    connect_sandbox(api, "whatsapp", "google_sheets")
    r = api.post(f"/opportunities/{order_entry_opportunity(process_map)['id']}/automation")
    assert r.status_code == 201, r.text
    return dict(r.json())


def test_generation_requires_connections(owner: Api) -> None:
    process_map = run_order_interview(owner)
    r = owner.post(f"/opportunities/{order_entry_opportunity(process_map)['id']}/automation")
    assert r.status_code == 409
    error = r.json()["error"]
    assert error["code"] == "connections_required"
    assert set(error["details"]["missing"]) == {"whatsapp", "google_sheets"}


def test_generate_validate_test_activate(owner: Api) -> None:
    automation = generated_order_automation(owner)
    assert automation["status"] == "validated"
    version = automation["current_version"]
    assert version["validated"] is True and version["source"] == "generated"
    blocks = {b["key"]: b for b in version["definition_json"]["blocks"]}
    assert blocks["reply"]["language"] == "roman-ur"  # filled from the workspace language
    assert {c["provider"]: c["connected"] for c in automation["connections"]} == {
        "whatsapp": True,
        "google_sheets": True,
    }

    r = owner.post(f"/automations/{automation['id']}/activate")
    assert r.status_code == 409 and r.json()["error"]["code"] == "test_required"  # BR-3

    r = owner.post(
        f"/automations/{automation['id']}/test", {"sample": {"text": "Hi, are you open today?"}}
    )
    assert r.json()["passed"] is False and "stopped at" in r.json()["message"]

    r = owner.post(f"/automations/{automation['id']}/test", {"sample": ORDER_SAMPLE})
    body = r.json()
    assert body["passed"] is True, body
    assert [s["key"] for s in body["steps"]] == [
        "is_order",
        "only_orders",
        "details",
        "big_order",
        "save_row",
        "reply",
        "confirm",
    ]
    assert body["steps"][2]["output"]["amount"] == 4500  # REQ-AB-5: input and output of every step
    assert any(rec["operation"] == "send_text" for rec in body["sandbox_records"])

    r = owner.post(f"/automations/{automation['id']}/activate")
    assert r.status_code == 200 and r.json()["status"] == "active"
    process_map = owner.get(f"/process-maps/{owner.get('/process-maps').json()[0]['id']}").json()
    assert order_entry_opportunity(process_map)["status"] == "automated"


def test_editing_requires_retest_and_rollback_restores(owner: Api) -> None:
    automation = generated_order_automation(owner)
    owner.post(f"/automations/{automation['id']}/test", {"sample": ORDER_SAMPLE})
    assert owner.post(f"/automations/{automation['id']}/activate").status_code == 200

    definition = copy.deepcopy(automation["current_version"]["definition_json"])
    next(b for b in definition["blocks"] if b["key"] == "save_row")["params"][
        "sheet"
    ] = "Orders 2026"
    r = owner.put(f"/automations/{automation['id']}/definition", {"definition": definition})
    edited = r.json()
    assert edited["current_version"]["version_no"] == 2
    assert edited["status"] == "validated"  # Figure 4.9: editing returns it to draft/validated
    assert owner.post(f"/automations/{automation['id']}/activate").status_code == 409

    r = owner.post(f"/automations/{automation['id']}/rollback", {"version_no": 1})
    rolled = r.json()
    assert (
        rolled["current_version"]["version_no"] == 3
        and rolled["current_version"]["source"] == "rollback"
    )
    assert rolled["status"] == "tested"
    assert owner.post(f"/automations/{automation['id']}/activate").status_code == 200
    assert [v["version_no"] for v in rolled["versions"]] == [3, 2, 1]  # nothing is overwritten


def test_invalid_edit_is_saved_as_draft_with_plain_errors(owner: Api) -> None:
    automation = generated_order_automation(owner)
    definition = copy.deepcopy(automation["current_version"]["definition_json"])
    definition["blocks"] = [b for b in definition["blocks"] if b["key"] != "big_order"]
    r = owner.put(f"/automations/{automation['id']}/definition", {"definition": definition})
    body = r.json()
    assert body["status"] == "draft"
    issue = body["current_version"]["validation_errors"][0]
    assert issue["code"] == "missing_money_approval" and "BR-5" in issue["message"]
    # "Fix automatically" repairs it.
    repaired = owner.post(f"/automations/{automation['id']}/repair").json()
    assert repaired["status"] == "validated" and repaired["current_version"]["source"] == "repaired"


def test_repair_loop_fixes_a_bad_draft(owner: Api, llm_override: Any) -> None:
    bad = copy.deepcopy(
        next(t for t in TEMPLATE_LIBRARY if t["code"] == "whatsapp_order_entry")["definition"]
    )
    bad["blocks"] = [b for b in bad["blocks"] if b["key"] != "big_order"]
    confirm = next(b for b in bad["blocks"] if b["key"] == "confirm")
    bad["blocks"][bad["blocks"].index(confirm)] = {
        "key": "confirm",
        "type": "action",
        "connector": "whatsapp",
        "operation": "send_text",
        "params": confirm["proposed_action"]["params"],
    }
    client = llm_override(ScriptedLLMClient({LLMTask.WORKFLOW_FILL: [bad]}))
    process_map = run_order_interview(owner)
    connect_sandbox(owner, "whatsapp", "google_sheets")
    r = owner.post(f"/opportunities/{order_entry_opportunity(process_map)['id']}/automation")
    automation = r.json()
    assert automation["status"] == "validated"
    assert automation["current_version"]["source"] == "repaired"
    repair_calls = [c for c in client.calls if c.task == LLMTask.WORKFLOW_REPAIR]
    assert len(repair_calls) == 1
    codes = {e["code"] for e in repair_calls[0].context["errors"]}
    assert codes == {"missing_money_approval", "unguarded_customer_message"}


def test_repair_gives_up_after_two_attempts(owner: Api, llm_override: Any) -> None:
    broken = {
        "schema_version": 1,
        "name": "Broken",
        "trigger": {"type": "whatsapp.message_received"},
        "blocks": [{"key": "teleporter", "type": "teleport"}],
    }
    llm_override(
        ScriptedLLMClient(
            {LLMTask.WORKFLOW_FILL: [broken], LLMTask.WORKFLOW_REPAIR: [broken, broken, broken]}
        )
    )
    owner_map = run_order_interview(owner)
    connect_sandbox(owner, "whatsapp", "google_sheets")
    automation = owner.post(
        f"/opportunities/{order_entry_opportunity(owner_map)['id']}/automation"
    ).json()
    assert (
        automation["status"] == "draft"
    )  # REQ-AB-3: at most two repairs, then plain-language errors
    messages = [e["message"] for e in automation["current_version"]["validation_errors"]]
    assert any("approved block library" in m for m in messages), messages


def test_create_from_template_without_interview(owner: Api) -> None:
    connect_sandbox(owner, "whatsapp")
    templates = owner.client.get("/api/v1/templates", headers=owner.headers).json()
    assert {t["code"] for t in templates} >= {"whatsapp_order_entry", "order_confirmation_reply"}
    r = owner.post("/automations/from-template", {"template_code": "order_confirmation_reply"})
    assert r.status_code == 201 and r.json()["status"] == "validated"  # REQ-AB-8


def test_disconnecting_pauses_dependent_automations(owner: Api) -> None:
    automation = generated_order_automation(owner)
    owner.post(f"/automations/{automation['id']}/test", {"sample": ORDER_SAMPLE})
    owner.post(f"/automations/{automation['id']}/activate")
    sheets = next(c for c in owner.get("/connections").json() if c["provider"] == "google_sheets")
    r = owner.delete(f"/connections/{sheets['id']}")
    assert "1 automation(s)" in r.json()["message"]
    paused = owner.get(f"/automations/{automation['id']}").json()
    assert paused["status"] == "paused" and "disconnected" in paused["status_reason"]  # REQ-IN-7


def test_kill_switch_pauses_everything(owner: Api) -> None:
    automation = generated_order_automation(owner)
    owner.post(f"/automations/{automation['id']}/test", {"sample": ORDER_SAMPLE})
    owner.post(f"/automations/{automation['id']}/activate")
    r = owner.post("/kill-switch")
    assert r.json() == {"paused_automations": 1}  # SAF-2
    assert owner.get(f"/automations/{automation['id']}").json()["status"] == "paused"


def test_auto_send_is_locked_until_twenty_clean_approvals(owner: Api) -> None:
    automation = generated_order_automation(owner)
    r = owner.post(f"/automations/{automation['id']}/auto-send", {"enabled": True})
    assert r.status_code == 422 and r.json()["error"]["code"] == "auto_send_locked"  # SAF-1


def test_tokens_never_leave_the_server(owner: Api) -> None:
    r = owner.post(
        "/connections/whatsapp",
        {
            "phone_number_id": "1234567890",
            "waba_id": "9876543210",
            "access_token": "EAAG-super-secret-token-value-123456",
        },
    )
    assert r.status_code == 201
    listing = owner.get("/connections").text
    assert "super-secret" not in listing  # REQ-IN-5
    assert r.json()["has_credentials"] is True
