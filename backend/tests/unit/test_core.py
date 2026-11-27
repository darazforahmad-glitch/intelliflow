"""Unit tests: security, crypto, masking, expressions, scoring, validators, webhooks, schedules."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.crypto import DecryptionError, TokenCipher, generate_key
from app.core.masking import mask_pii, mask_text
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.engine.expressions import ExpressionError, evaluate, parse_expression, render_value
from app.seeds.templates import TEMPLATE_LIBRARY
from app.services.opportunity_analyzer import compute_score
from app.services.process_mapper import classify_steps, validate_process_map
from app.services.webhooks import (
    build_whatsapp_payload,
    extract_whatsapp_events,
    sign,
    verify_signature,
)
from app.services.workflow_validator import WorkflowValidator


def test_passwords_use_argon2id() -> None:
    hashed = hash_password("Secret123")
    assert hashed.startswith("$argon2id$")  # SEC-1
    assert verify_password(hashed, "Secret123") and not verify_password(hashed, "secret123")


def test_jwt_round_trip_and_type_check() -> None:
    import uuid

    from app.core.errors import AuthenticationError

    uid = uuid.uuid4()
    token, _ = create_token(uid, 3, "access")
    claims = decode_token(token, "access")
    assert claims.user_id == uid and claims.token_version == 3
    with pytest.raises(AuthenticationError):
        decode_token(token, "refresh")


def test_aes_gcm_binds_ciphertext_to_its_row_and_rotates_keys() -> None:
    import base64

    k1, k2 = (base64.b64decode(generate_key()) for _ in range(2))
    old = TokenCipher({"k1": k1}, "k1")
    blob = old.encrypt_json({"access_token": "EAAG..."}, aad="connection:1")
    assert old.decrypt_json(blob, aad="connection:1") == {"access_token": "EAAG..."}
    with pytest.raises(DecryptionError):
        old.decrypt(blob, aad="connection:2")  # copied to another row: rejected (SEC-2)
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(DecryptionError):
        old.decrypt(tampered, aad="connection:1")
    rotated = TokenCipher(
        {"k2": k2, "k1": k1}, "k2"
    )  # new primary key, old key kept for decryption
    assert rotated.decrypt_json(blob, aad="connection:1")["access_token"] == "EAAG..."
    assert rotated.encrypt(b"x")[2:4] == b"k2"
    with pytest.raises(DecryptionError):
        TokenCipher({"k2": k2}, "k2").decrypt(blob, aad="connection:1")  # retired key: unreadable


def test_masking_hides_personal_data() -> None:
    masked = mask_pii(
        {
            "customer_name": "Ayesha Khan",
            "to": "923001234567",
            "address": "House 12 Gulberg",
            "amount": 4500,
            "note": "call me on 0300-1234567 or a.khan@example.com",
        }
    )
    assert masked["amount"] == 4500
    assert "Ayesha" not in masked["customer_name"] and "Gulberg" not in masked["address"]
    assert masked["to"].startswith("9230") and "1234567" not in masked["to"]
    assert "1234567" not in masked["note"] and "khan@" not in masked["note"]
    assert mask_text("no personal data here") == "no personal data here"


@pytest.mark.parametrize(
    "expression",
    ["__import__('os')", "a.__class__", "f(1)", "a[0]", "x if y else z", "(lambda: 1)()"],
)
def test_expressions_reject_code(expression: str) -> None:
    with pytest.raises(ExpressionError):
        parse_expression(expression)


def test_expressions_evaluate_business_rules() -> None:
    ctx = {"details": {"amount": "12,500"}, "is_order": {"label": "order"}}
    assert evaluate("details.amount > 10000 and is_order.label == 'order'", ctx) is True
    assert (
        evaluate("details.missing > 1", ctx) is False
    )  # missing data never satisfies a comparison
    assert render_value({"n": "{{details.amount}}", "s": "Rs {{details.amount}}"}, ctx) == {
        "n": "12,500",
        "s": "Rs 12,500",
    }


@pytest.mark.parametrize(
    ("weekly", "fit", "risk", "expected"),
    [
        (Decimal(120), Decimal("1.0"), Decimal(0), Decimal("120.00")),
        (Decimal(200), Decimal("1.0"), Decimal("0.3"), Decimal("170.00")),
        (Decimal(80), Decimal("1.0"), Decimal("0.4"), Decimal("64.00")),
        (Decimal(100), Decimal("0.6"), Decimal("0.7"), Decimal("39.00")),
        (Decimal(100), Decimal("1.0"), Decimal("1.4"), Decimal("50.00")),  # risk is capped at 1
    ],
)
def test_algorithm_5_2_score(
    weekly: Decimal, fit: Decimal, risk: Decimal, expected: Decimal
) -> None:
    assert compute_score(weekly, fit, risk) == expected


def _map(steps: list[dict]) -> dict:  # type: ignore[type-arg]
    return {"process_name": "Orders", "language": "en", "steps": steps}


def _step(key: str, step_type: str, predecessor: str | None) -> dict:  # type: ignore[type-arg]
    return {
        "key": key,
        "title": f"Step {key}",
        "actor": "Owner",
        "action": "",
        "step_type": step_type,
        "app": "other",
        "minutes_per_run": 2,
        "runs_per_week": 10,
        "predecessor": predecessor,
        "involves_customer_messaging": False,
        "involves_money": False,
    }


def test_process_map_semantic_validation() -> None:
    good = _map([_step("s1", "start", None), _step("s2", "manual", "s1"), _step("s3", "end", "s2")])
    assert validate_process_map(good) == []
    forward = _map(
        [_step("s1", "start", None), _step("s2", "manual", "s3"), _step("s3", "end", "s2")]
    )
    assert any("not an earlier step" in e for e in validate_process_map(forward))
    too_short = _map([_step("s1", "start", None)])
    assert "at least 3 steps" in validate_process_map(too_short)[0]
    classified = classify_steps(good["steps"])
    assert [s["is_manual"] for s in classified] == [False, True, False]


def test_all_templates_pass_validation() -> None:
    for template in TEMPLATE_LIBRARY:
        assert WorkflowValidator().validate(template["definition"]) == [], template["code"]


def test_validator_flags_safety_rules() -> None:
    definition = copy.deepcopy(TEMPLATE_LIBRARY[0]["definition"])
    definition["blocks"] = [b for b in definition["blocks"] if b["key"] != "big_order"]
    codes = {i.code for i in WorkflowValidator().validate(definition)}
    assert codes == {"missing_money_approval"}
    definition["blocks"].append(
        {
            "key": "wipe",
            "type": "action",
            "connector": "google_sheets",
            "operation": "delete_row",
            "params": {},
        }
    )
    assert "forbidden_operation" in {
        i.code for i in WorkflowValidator().validate(definition)
    }  # SAF-3


def test_whatsapp_signature_and_parsing() -> None:
    raw = build_whatsapp_payload(
        phone_number_id="123", wa_id="923001234567", name="Ayesha", text="Hi", message_id="wamid.X"
    )
    assert verify_signature(raw, sign(raw, "s3cret"), "s3cret")
    assert not verify_signature(raw, sign(raw, "other"), "s3cret")
    assert not verify_signature(
        raw + b" ", sign(raw, "s3cret"), "s3cret"
    )  # body changed after signing
    events = extract_whatsapp_events(__import__("json").loads(raw))
    assert events[0]["event_id"] == "wamid.X" and events[0]["trigger"]["name"] == "Ayesha"


def test_daily_schedule_fires_once_per_day(db) -> None:  # type: ignore[no-untyped-def]
    from app.models import Run
    from app.services.scheduler_service import fire_due_schedules
    from tests.factories import (
        make_automation,
        make_connection,
        make_workspace,
        template_definition,
    )

    workspace, _ = make_workspace(db)
    make_connection(db, workspace, "google_sheets")
    make_connection(db, workspace, "gmail")
    make_automation(db, workspace, template_definition("daily_order_summary"))
    at = datetime(2026, 11, 27, 16, 2, tzinfo=UTC)  # 21:02 in Asia/Karachi (UTC+5)
    assert fire_due_schedules(db, at) == 1
    assert fire_due_schedules(db, at + timedelta(minutes=1)) == 0  # same slot: idempotent
    assert fire_due_schedules(db, at + timedelta(hours=2)) == 0  # outside the window
    db.expire_all()
    run = db.query(Run).one()
    assert run.status.value == "succeeded"


def test_approval_reminder_then_expiry(db) -> None:  # type: ignore[no-untyped-def]
    from app.engine.workflow_engine import WorkflowEngine
    from app.models import ApprovalTask, Run
    from app.services.approval_service import process_timeouts
    from tests.factories import (
        make_automation,
        make_connection,
        make_workspace,
        template_definition,
        whatsapp_trigger,
    )

    workspace, _ = make_workspace(db)
    make_connection(db, workspace, "whatsapp")
    make_connection(db, workspace, "google_sheets")
    automation = make_automation(db, workspace, template_definition("whatsapp_order_entry"))
    engine = WorkflowEngine(db)
    trigger = whatsapp_trigger()
    run = engine.create_run(
        automation, event_id="wamid.T", trigger_type="whatsapp.message_received", trigger=trigger
    )
    db.commit()
    engine.execute(run.id)  # type: ignore[union-attr]
    now = datetime.now(UTC)
    assert process_timeouts(db, now + timedelta(hours=3)) == (1, 0)  # REQ-AP-5: reminder after 2 h
    assert process_timeouts(db, now + timedelta(hours=25)) == (
        0,
        1,
    )  # expiry after 24 h cancels the run
    db.expire_all()
    assert db.query(ApprovalTask).one().status.value == "expired"
    assert db.get(Run, run.id).status.value == "cancelled"  # type: ignore[union-attr]
