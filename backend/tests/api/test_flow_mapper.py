"""UC-03 Conduct Process Interview and UC-05 Review Automation Opportunities."""

from __future__ import annotations

from decimal import Decimal

from tests.conftest import Api, run_order_interview


def test_interview_asks_follow_ups_in_roman_urdu(owner: Api) -> None:
    r = owner.post("/interviews", {"process_name": "Order process"})
    assert r.status_code == 201
    session = r.json()
    assert session["messages"][0]["sender"] == "ai"
    assert "step by step" in session["messages"][0]["content"]
    r = owner.post(
        f"/interviews/{session['id']}/messages",
        {
            "content": "Customer WhatsApp pe order bhejta hai, phir main Excel mein likhta hoon aur phir customer ko confirmation bhejta hoon."
        },
    )
    body = r.json()
    assert body["language"] == "roman-ur"
    assert body["ready_for_mapping"] is False
    assert "kitni baar" in body["messages"][-1]["content"]  # asks how often (REQ-FM-2)


def test_full_flow_builds_map_and_ranks_top_three(owner: Api) -> None:
    process_map = run_order_interview(owner)
    steps = {s["key"]: s for s in process_map["steps"]}
    assert len(steps) == 7
    assert steps["s1"]["step_type"] == "start" and steps["s7"]["step_type"] == "end"
    assert steps["s5"]["step_type"] == "human_only"  # packing cannot be automated
    assert Decimal(steps["s2"]["weekly_minutes"]) == Decimal("120")  # REQ-OA-1: 3 min x 40/week

    top = process_map["opportunities"]
    assert [o["rank"] for o in top] == [1, 2, 3]
    # Algorithm 5.2: courier 5x40x1.0x(1-0.15)=170 > order entry 3x40=120 > payment 2x40x0.8=64
    assert [o["template"]["code"] for o in top] == [
        "courier_tracking_update",
        "whatsapp_order_entry",
        "payment_screenshot_check",
    ]
    assert [Decimal(o["score"]) for o in top] == [
        Decimal("170.00"),
        Decimal("120.00"),
        Decimal("64.00"),
    ]
    assert "40 times a week" in top[1]["reason"]
    assert Decimal(top[1]["minutes_saved_per_day"]) == Decimal("17.1")  # 120 / 7
    assert process_map["other_opportunities"][0]["template"]["code"] == "order_confirmation_reply"


def test_dismiss_recalculates_ranking(owner: Api) -> None:
    process_map = run_order_interview(owner)
    first = process_map["opportunities"][0]
    r = owner.post(f"/opportunities/{first['id']}/dismiss")
    assert r.status_code == 200
    updated = r.json()
    assert [o["template"]["code"] for o in updated["opportunities"]] == [
        "whatsapp_order_entry",
        "payment_screenshot_check",
        "order_confirmation_reply",
    ]
    assert updated["dismissed_opportunities"][0]["id"] == first["id"]
    r = owner.post(f"/opportunities/{first['id']}/restore")
    assert r.json()["opportunities"][0]["id"] == first["id"]


def test_edit_creates_new_version_and_keeps_old(owner: Api) -> None:
    process_map = run_order_interview(owner)
    steps = [
        {
            k: s[k]
            for k in (
                "title",
                "actor",
                "action",
                "step_type",
                "app",
                "minutes_per_run",
                "runs_per_week",
                "involves_customer_messaging",
                "involves_money",
            )
        }
        for s in process_map["steps"]
    ]
    steps[1]["minutes_per_run"] = "6"  # the owner corrects the estimate
    del steps[4]  # and deletes the packing step
    r = owner.post(
        f"/process-maps/{process_map['id']}/versions", {"steps": steps, "note": "Fixed timings"}
    )
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert v2["version"] == 2 and v2["is_latest"] is True
    assert len(v2["steps"]) == 6
    assert len(v2["versions"]) == 2
    # Version 1 is untouched (REQ-FM-7).
    v1 = owner.get(f"/process-maps/{process_map['id']}").json()
    assert v1["is_latest"] is False and len(v1["steps"]) == 7
    # The ranking was recomputed for v2: order entry is now 6 x 40 = 240.
    assert v2["opportunities"][0]["template"]["code"] == "whatsapp_order_entry"


def test_invalid_edit_rejected_with_plain_errors(owner: Api) -> None:
    process_map = run_order_interview(owner)
    steps = [
        {"title": "Pack", "step_type": "manual"},
        {"title": "Ship", "step_type": "manual"},
        {"title": "Done", "step_type": "manual"},
    ]
    r = owner.post(f"/process-maps/{process_map['id']}/versions", {"steps": steps})
    assert r.status_code == 422
    assert any("start" in d for d in r.json()["error"]["details"])


def test_staff_cannot_run_interviews(owner: Api, client) -> None:  # type: ignore[no-untyped-def]
    from tests.conftest import latest_link, register_and_login

    r = owner.post("/invitations", {"email": "staff@example.com"})
    assert r.status_code == 201
    invite_token = latest_link("staff@example.com", "invite?token")
    staff_token = register_and_login(client, email="staff@example.com")
    headers = {"Authorization": f"Bearer {staff_token}"}
    assert (
        client.post(
            "/api/v1/invitations/accept", json={"token": invite_token}, headers=headers
        ).status_code
        == 200
    )
    r = client.post(owner.url("/interviews"), json={"process_name": "Orders"}, headers=headers)
    assert r.status_code == 403  # BR-2: staff cannot change automations or processes
    assert r.json()["error"]["code"] == "owner_only"
    assert client.get(owner.url("/interviews"), headers=headers).status_code == 200  # but can view
