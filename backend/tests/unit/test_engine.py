"""Algorithm 5.5 (EXECUTE_RUN), REQ-WE-1..9, SAF-1/4/5/6, REQ-AP-3/4 at the service level."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors import customer_window
from app.connectors.sheets import SheetsConnector
from app.engine.errors import TransientBlockError
from app.engine.workflow_engine import RetryMode, WorkflowEngine
from app.models import ApprovalTask, Automation, Notification, Run, SandboxRecord, StepRun
from app.models.enums import ApprovalStatus, AutomationStatus, RunStatus, StepRunStatus
from app.services import approval_service
from tests.factories import (
    ORDER_TEXT,
    make_automation,
    make_connection,
    make_workspace,
    template_definition,
    whatsapp_trigger,
)


@pytest.fixture
def order_setup(db: Session) -> dict[str, Any]:
    workspace, owner = make_workspace(db)
    whatsapp = make_connection(db, workspace, "whatsapp")
    sheets = make_connection(db, workspace, "google_sheets")
    automation = make_automation(db, workspace, template_definition("whatsapp_order_entry"))
    return {
        "workspace": workspace,
        "owner": owner,
        "whatsapp": whatsapp,
        "sheets": sheets,
        "automation": automation,
    }


def start(
    db: Session, automation: Automation, trigger: dict[str, Any] | None = None, **engine_kw: Any
) -> Run:
    engine = WorkflowEngine(db, **engine_kw)
    trigger = trigger or whatsapp_trigger()
    run = engine.create_run(
        automation,
        event_id=trigger["message_id"],
        trigger_type="whatsapp.message_received",
        trigger=trigger,
    )
    assert run is not None
    db.commit()
    return engine.execute(run.id)


def open_task(db: Session, run: Run) -> ApprovalTask:
    db.expire_all()
    task = db.scalars(
        select(ApprovalTask).where(
            ApprovalTask.run_id == run.id, ApprovalTask.status == ApprovalStatus.PENDING
        )
    ).one()
    return task


def outbox(db: Session, connection_id: Any) -> list[dict[str, Any]]:
    return [
        r.data_json
        for r in db.scalars(
            select(SandboxRecord).where(
                SandboxRecord.connection_id == connection_id,
                SandboxRecord.resource.like("outbox:%"),
            )
        )
    ]


def test_order_run_pauses_for_confirmation_then_sends(
    db: Session, order_setup: dict[str, Any]
) -> None:
    run = start(db, order_setup["automation"])
    assert run.status == RunStatus.WAITING_APPROVAL
    steps = {s.step_key: s for s in db.scalars(select(StepRun).where(StepRun.run_id == run.id))}
    assert steps["is_order"].status == StepRunStatus.SUCCEEDED
    assert (
        steps["big_order"].status == StepRunStatus.SKIPPED
    )  # Rs 4,500 is under the Rs 10,000 threshold (BR-5)
    assert steps["save_row"].status == StepRunStatus.SUCCEEDED
    assert steps["confirm"].status == StepRunStatus.WAITING
    rows = db.scalars(select(SandboxRecord).where(SandboxRecord.resource == "sheet:Orders")).all()
    assert rows[0].data_json["Customer"] == "Ayesha" and rows[0].data_json["Amount"] == 4500.0

    task = open_task(db, run)
    assert task.payload_json["proposed_action"]["params"]["to"] == "923001234567"
    assert "Ayesha" in task.payload_json["proposed_action"]["params"]["text"]
    assert (
        db.scalars(select(Notification).where(Notification.kind == "approval.created")).first()
        is not None
    )  # REQ-AP-2
    assert outbox(db, order_setup["whatsapp"].id) == []  # nothing sent before approval (SAF-1)

    approval_service.decide(
        db, task, order_setup["owner"], "approve"
    )  # resumes through the (eager) task queue
    db.expire_all()
    run = db.get_one(Run, run.id)
    assert run.status == RunStatus.SUCCEEDED
    assert float(run.minutes_saved) == 3.0  # REQ-WE-9
    sent = outbox(db, order_setup["whatsapp"].id)
    assert len(sent) == 1 and sent[0]["to"] == "923001234567"


def test_non_order_stops_at_condition(db: Session, order_setup: dict[str, Any]) -> None:
    run = start(db, order_setup["automation"], whatsapp_trigger("Aap ki shop kab tak khuli hai?"))
    assert run.status == RunStatus.SUCCEEDED
    assert float(run.minutes_saved) == 0
    assert "condition was not met" in (run.summary or "")


def test_large_order_needs_money_approval_before_saving(
    db: Session, order_setup: dict[str, Any]
) -> None:
    text = ORDER_TEXT.replace("Total Rs 4500", "Total Rs 15,000")
    run = start(db, order_setup["automation"], whatsapp_trigger(text))
    task = open_task(db, run)
    assert task.kind.value == "money"
    assert (
        db.scalars(select(SandboxRecord).where(SandboxRecord.resource == "sheet:Orders")).all()
        == []
    )
    approval_service.decide(db, task, order_setup["owner"], "approve")
    db.expire_all()
    second = open_task(db, run)
    assert second.kind.value == "customer_message"
    assert (
        len(db.scalars(select(SandboxRecord).where(SandboxRecord.resource == "sheet:Orders")).all())
        == 1
    )


def test_edit_changes_text_but_never_the_recipient(
    db: Session, order_setup: dict[str, Any]
) -> None:
    from app.core.errors import ValidationFailedError

    run = start(db, order_setup["automation"])
    task = open_task(db, run)
    with pytest.raises(ValidationFailedError):
        approval_service.decide(
            db, task, order_setup["owner"], "edit", edited_params={"to": "923339999999"}
        )
    db.rollback()
    task = open_task(db, run)
    approval_service.decide(
        db, task, order_setup["owner"], "edit", edited_params={"text": "Shukriya! Order confirm."}
    )
    db.expire_all()
    assert db.get_one(Run, run.id).status == RunStatus.SUCCEEDED
    assert outbox(db, order_setup["whatsapp"].id)[0]["text"] == "Shukriya! Order confirm."


def test_decisions_are_final(db: Session, order_setup: dict[str, Any]) -> None:
    from app.core.errors import ConflictError

    run = start(db, order_setup["automation"])
    task = open_task(db, run)
    approval_service.decide(db, task, order_setup["owner"], "reject")
    db.expire_all()
    assert db.get_one(Run, run.id).status == RunStatus.CANCELLED
    assert outbox(db, order_setup["whatsapp"].id) == []
    task = db.get_one(ApprovalTask, task.id)
    assert task.decided_by == order_setup["owner"].id and task.decided_at is not None  # REQ-AP-6
    with pytest.raises(ConflictError):  # BR-9
        approval_service.decide(db, task, order_setup["owner"], "approve")


def test_transient_errors_are_retried_with_backoff(
    db: Session, order_setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"n": 0}
    original = SheetsConnector.op_append_row

    def flaky(self: SheetsConnector, params: dict[str, Any]) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientBlockError("Google Sheets is temporarily unavailable (503).")
        return original(self, params)

    monkeypatch.setattr(SheetsConnector, "op_append_row", flaky)
    sleeps: list[float] = []
    run = start(db, order_setup["automation"], retry_mode=RetryMode.INLINE, sleep=sleeps.append)
    assert run.status == RunStatus.WAITING_APPROVAL
    assert sleeps == [10, 60]  # 10 s, 60 s, (5 min) backoff
    step = db.scalars(
        select(StepRun).where(StepRun.run_id == run.id, StepRun.step_key == "save_row")
    ).one()
    assert step.attempt == 3


def test_step_fails_after_four_attempts(
    db: Session, order_setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(self: SheetsConnector, params: dict[str, Any]) -> dict[str, Any]:
        raise TransientBlockError("Google Sheets is temporarily unavailable (503).")

    monkeypatch.setattr(SheetsConnector, "op_append_row", down)
    sleeps: list[float] = []
    run = start(db, order_setup["automation"], retry_mode=RetryMode.INLINE, sleep=sleeps.append)
    assert run.status == RunStatus.FAILED
    assert sleeps == [10, 60, 300]
    assert "after 4 attempts" in (run.error or "")


def test_five_consecutive_failures_pause_the_automation(
    db: Session, order_setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.engine.errors import PermanentBlockError

    def broken(self: SheetsConnector, params: dict[str, Any]) -> dict[str, Any]:
        raise PermanentBlockError("Sheet 'Orders' is protected.")

    monkeypatch.setattr(SheetsConnector, "op_append_row", broken)
    automation = order_setup["automation"]
    for _ in range(5):
        start(db, automation)
    db.expire_all()
    automation = db.get_one(Automation, automation.id)
    assert automation.status == AutomationStatus.ERROR  # REQ-WE-7
    assert "5 failed runs" in (automation.status_reason or "")
    assert (
        db.scalars(select(Notification).where(Notification.kind == "automation.error")).first()
        is not None
    )
    # A new event for a paused automation does not run.
    engine = WorkflowEngine(db)
    trigger = whatsapp_trigger()
    run = engine.create_run(
        automation,
        event_id=trigger["message_id"],
        trigger_type="whatsapp.message_received",
        trigger=trigger,
    )
    db.commit()
    assert run is not None and engine.execute(run.id).status == RunStatus.CANCELLED


def test_missing_connection_pauses_immediately(db: Session) -> None:
    workspace, _ = make_workspace(db)
    make_connection(db, workspace, "whatsapp")  # Google Sheets is NOT connected
    automation = make_automation(db, workspace, template_definition("whatsapp_order_entry"))
    run = start(db, automation)
    assert run.status == RunStatus.FAILED
    assert "Google Sheets is not connected" in (run.error or "")
    db.expire_all()
    assert db.get_one(Automation, automation.id).status == AutomationStatus.ERROR


def test_incomplete_extraction_goes_to_review(db: Session, order_setup: dict[str, Any]) -> None:
    run = start(
        db,
        order_setup["automation"],
        whatsapp_trigger("Mujhe 1 kurta chahiye black, total Rs 2500"),
    )
    task = open_task(db, run)
    assert task.kind.value == "review"  # SAF-6
    assert "address" in task.payload_json["missing"]
    from app.core.errors import ValidationFailedError

    with pytest.raises(ValidationFailedError):  # cannot approve while a required field is empty
        approval_service.decide(db, task, order_setup["owner"], "approve")
    db.rollback()
    task = open_task(db, run)
    approval_service.decide(
        db, task, order_setup["owner"], "edit", edited_fields={"address": "House 7, DHA Lahore"}
    )
    db.expire_all()
    row = db.scalars(select(SandboxRecord).where(SandboxRecord.resource == "sheet:Orders")).one()
    assert row.data_json["Address"] == "House 7, DHA Lahore"


def test_test_runs_auto_approve_and_persist_nothing(
    db: Session, order_setup: dict[str, Any]
) -> None:
    engine = WorkflowEngine(db, retry_mode=RetryMode.INLINE, sleep=lambda _s: None)
    trigger = whatsapp_trigger()
    run = engine.create_run(
        order_setup["automation"],
        event_id="test:1",
        trigger_type="whatsapp.message_received",
        trigger=trigger,
        is_test=True,
    )
    db.commit()
    assert run is not None
    run = engine.execute(run.id)
    assert run.status == RunStatus.SUCCEEDED
    assert [t["key"] for t in engine.trace] == [
        "is_order",
        "only_orders",
        "details",
        "big_order",
        "save_row",
        "reply",
        "confirm",
    ]
    assert engine.trace[-1]["output"]["decision"] == "approved_in_test"
    assert (
        db.scalars(select(SandboxRecord)).all() == []
    )  # SAF-5: nothing persisted, nobody messaged
    assert any(r["operation"] == "send_text" for r in engine.recorder.records)


def test_duplicate_events_start_one_run(db: Session, order_setup: dict[str, Any]) -> None:
    engine = WorkflowEngine(db)
    trigger = whatsapp_trigger()
    first = engine.create_run(
        order_setup["automation"],
        event_id="wamid.SAME",
        trigger_type="whatsapp.message_received",
        trigger=trigger,
    )
    db.commit()
    second = engine.create_run(
        order_setup["automation"],
        event_id="wamid.SAME",
        trigger_type="whatsapp.message_received",
        trigger=trigger,
    )
    assert first is not None and second is None  # REQ-WE-3


def test_step_logs_mask_personal_data(db: Session, order_setup: dict[str, Any]) -> None:
    run = start(db, order_setup["automation"])
    step = db.scalars(
        select(StepRun).where(StepRun.run_id == run.id, StepRun.step_key == "save_row")
    ).one()
    logged = str(step.input_json)
    assert "923001234567" not in logged and "Gulberg" not in logged  # REQ-WE-6
    assert (
        run.context_encrypted is not None and b"Gulberg" not in run.context_encrypted
    )  # encrypted at rest


def test_message_rate_limit(db: Session, order_setup: dict[str, Any]) -> None:
    automation = order_setup["automation"]
    automation.current_version.definition_json = {
        **automation.current_version.definition_json,
        "settings": {"max_messages_per_hour": 1},
    }
    automation.auto_send = True  # sends without waiting for approval
    db.commit()
    assert start(db, automation).status == RunStatus.SUCCEEDED
    run = start(db, automation)
    assert run.status == RunStatus.FAILED and "limit of 1 customer messages per hour" in (
        run.error or ""
    )  # SAF-4


def test_closed_window_offers_template(db: Session, order_setup: dict[str, Any]) -> None:
    from datetime import UTC, datetime, timedelta

    old = whatsapp_trigger()
    old["timestamp"] = (datetime.now(UTC) - timedelta(hours=30)).isoformat()
    run = start(db, order_setup["automation"], old)
    task = open_task(db, run)
    assert not customer_window.is_open(order_setup["workspace"].id, "923001234567")
    approval_service.decide(db, task, order_setup["owner"], "approve")
    db.expire_all()
    template_task = open_task(db, run)
    assert template_task.kind.value == "window_closed"  # REQ-WE-8 / BR-4
    assert template_task.payload_json["proposed_action"]["operation"] == "send_template"
    approval_service.decide(db, template_task, order_setup["owner"], "approve")
    db.expire_all()
    assert db.get_one(Run, run.id).status == RunStatus.SUCCEEDED
    assert outbox(db, order_setup["whatsapp"].id)[0]["operation"] == "send_template"
