"""Algorithm 5.5 (EXECUTE_RUN), REQ-WE-1..9, SAF-1/4/5/6, REQ-AP-3/4 at the service level."""

from __future__ import annotations

from typing import Any

import pytest

from intelliflow.approvals import services as approval_service
from intelliflow.approvals.models import ApprovalTask
from intelliflow.automations.models import Automation
from intelliflow.core.enums import ApprovalStatus, AutomationStatus, RunStatus, StepRunStatus
from intelliflow.engine.errors import TransientBlockError
from intelliflow.engine.workflow_engine import RetryMode, WorkflowEngine
from intelliflow.integrations.connectors import customer_window
from intelliflow.integrations.connectors.sheets import SheetsConnector
from intelliflow.integrations.models import SandboxRecord
from intelliflow.notifications.models import Notification
from intelliflow.runs.models import Run, StepRun
from tests.factories import (
    ORDER_TEXT,
    make_automation,
    make_connection,
    make_workspace,
    template_definition,
    whatsapp_trigger,
)


@pytest.fixture
def order_setup() -> dict[str, Any]:
    workspace, owner = make_workspace()
    whatsapp = make_connection(workspace, "whatsapp")
    sheets = make_connection(workspace, "google_sheets")
    automation = make_automation(workspace, template_definition("whatsapp_order_entry"))
    return {
        "workspace": workspace,
        "owner": owner,
        "whatsapp": whatsapp,
        "sheets": sheets,
        "automation": automation,
    }


def start(automation: Automation, trigger: dict[str, Any] | None = None, **engine_kw: Any) -> Run:
    engine = WorkflowEngine(**engine_kw)
    trigger = trigger or whatsapp_trigger()
    run = engine.create_run(
        automation,
        event_id=trigger["message_id"],
        trigger_type="whatsapp.message_received",
        trigger=trigger,
    )
    assert run is not None
    return engine.execute(run.id)


def open_task(run: Run) -> ApprovalTask:
    return ApprovalTask.objects.get(run_id=run.id, status=ApprovalStatus.PENDING)


def outbox(connection_id: Any) -> list[dict[str, Any]]:
    return [
        r.data_json
        for r in SandboxRecord.objects.filter(
            connection_id=connection_id, resource__startswith="outbox:"
        ).order_by("created_at")
    ]


def test_order_run_pauses_for_confirmation_then_sends(
    order_setup: dict[str, Any]
) -> None:
    run = start(order_setup["automation"])
    assert run.status == RunStatus.WAITING_APPROVAL
    steps = {s.step_key: s for s in StepRun.objects.filter(run_id=run.id)}
    assert steps["is_order"].status == StepRunStatus.SUCCEEDED
    assert (
        steps["big_order"].status == StepRunStatus.SKIPPED
    )  # Rs 4,500 is under the Rs 10,000 threshold (BR-5)
    assert steps["save_row"].status == StepRunStatus.SUCCEEDED
    assert steps["confirm"].status == StepRunStatus.WAITING
    rows = list(SandboxRecord.objects.filter(resource="sheet:Orders"))
    assert rows[0].data_json["Customer"] == "Ayesha" and rows[0].data_json["Amount"] == 4500.0

    task = open_task(run)
    assert task.payload_json["proposed_action"]["params"]["to"] == "923001234567"
    assert "Ayesha" in task.payload_json["proposed_action"]["params"]["text"]
    assert (
        Notification.objects.filter(kind="approval.created").first()
        is not None
    )  # REQ-AP-2
    assert outbox(order_setup["whatsapp"].id) == []  # nothing sent before approval (SAF-1)

    approval_service.decide(task, order_setup["owner"], "approve"
    )  # resumes through the (eager) task queue
    run = Run.objects.get(pk=run.id)
    assert run.status == RunStatus.SUCCEEDED
    assert float(run.minutes_saved) == 3.0  # REQ-WE-9
    sent = outbox(order_setup["whatsapp"].id)
    assert len(sent) == 1 and sent[0]["to"] == "923001234567"


def test_non_order_stops_at_condition(order_setup: dict[str, Any]) -> None:
    run = start(order_setup["automation"], whatsapp_trigger("Aap ki shop kab tak khuli hai?"))
    assert run.status == RunStatus.SUCCEEDED
    assert float(run.minutes_saved) == 0
    assert "condition was not met" in (run.summary or "")


def test_large_order_needs_money_approval_before_saving(
    order_setup: dict[str, Any]
) -> None:
    text = ORDER_TEXT.replace("Total Rs 4500", "Total Rs 15,000")
    run = start(order_setup["automation"], whatsapp_trigger(text))
    task = open_task(run)
    assert task.kind == "money"
    assert (
        list(SandboxRecord.objects.filter(resource="sheet:Orders"))
        == []
    )
    approval_service.decide(task, order_setup["owner"], "approve")
    second = open_task(run)
    assert second.kind == "customer_message"
    assert (
        len(list(SandboxRecord.objects.filter(resource="sheet:Orders")))
        == 1
    )


def test_edit_changes_text_but_never_the_recipient(
    order_setup: dict[str, Any]
) -> None:
    from intelliflow.core.errors import ValidationFailedError

    run = start(order_setup["automation"])
    task = open_task(run)
    with pytest.raises(ValidationFailedError):
        approval_service.decide(task, order_setup["owner"], "edit", edited_params={"to": "923339999999"}
        )
    task = open_task(run)
    approval_service.decide(task, order_setup["owner"], "edit", edited_params={"text": "Shukriya! Order confirm."}
    )
    assert Run.objects.get(pk=run.id).status == RunStatus.SUCCEEDED
    assert outbox(order_setup["whatsapp"].id)[0]["text"] == "Shukriya! Order confirm."


def test_decisions_are_final(order_setup: dict[str, Any]) -> None:
    from intelliflow.core.errors import ConflictError

    run = start(order_setup["automation"])
    task = open_task(run)
    approval_service.decide(task, order_setup["owner"], "reject")
    assert Run.objects.get(pk=run.id).status == RunStatus.CANCELLED
    assert outbox(order_setup["whatsapp"].id) == []
    task = ApprovalTask.objects.get(pk=task.id)
    assert task.decided_by_id == order_setup["owner"].id and task.decided_at is not None  # REQ-AP-6
    with pytest.raises(ConflictError):  # BR-9
        approval_service.decide(task, order_setup["owner"], "approve")


def test_transient_errors_are_retried_with_backoff(
    order_setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch
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
    run = start(order_setup["automation"], retry_mode=RetryMode.INLINE, sleep=sleeps.append)
    assert run.status == RunStatus.WAITING_APPROVAL
    assert sleeps == [10, 60]  # 10 s, 60 s, (5 min) backoff
    step = StepRun.objects.get(run_id=run.id, step_key="save_row")
    assert step.attempt == 3


def test_step_fails_after_four_attempts(
    order_setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(self: SheetsConnector, params: dict[str, Any]) -> dict[str, Any]:
        raise TransientBlockError("Google Sheets is temporarily unavailable (503).")

    monkeypatch.setattr(SheetsConnector, "op_append_row", down)
    sleeps: list[float] = []
    run = start(order_setup["automation"], retry_mode=RetryMode.INLINE, sleep=sleeps.append)
    assert run.status == RunStatus.FAILED
    assert sleeps == [10, 60, 300]
    assert "after 4 attempts" in (run.error or "")


def test_five_consecutive_failures_pause_the_automation(
    order_setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from intelliflow.engine.errors import PermanentBlockError

    def broken(self: SheetsConnector, params: dict[str, Any]) -> dict[str, Any]:
        raise PermanentBlockError("Sheet 'Orders' is protected.")

    monkeypatch.setattr(SheetsConnector, "op_append_row", broken)
    automation = order_setup["automation"]
    for _ in range(5):
        start(automation)
    automation = Automation.objects.get(pk=automation.id)
    assert automation.status == AutomationStatus.ERROR  # REQ-WE-7
    assert "5 failed runs" in (automation.status_reason or "")
    assert (
        Notification.objects.filter(kind="automation.error").first()
        is not None
    )
    # A new event for a paused automation does not run.
    engine = WorkflowEngine()
    trigger = whatsapp_trigger()
    run = engine.create_run(
        automation,
        event_id=trigger["message_id"],
        trigger_type="whatsapp.message_received",
        trigger=trigger,
    )
    assert run is not None and engine.execute(run.id).status == RunStatus.CANCELLED


def test_missing_connection_pauses_immediately() -> None:
    workspace, _ = make_workspace()
    make_connection(workspace, "whatsapp")  # Google Sheets is NOT connected
    automation = make_automation(workspace, template_definition("whatsapp_order_entry"))
    run = start(automation)
    assert run.status == RunStatus.FAILED
    assert "Google Sheets is not connected" in (run.error or "")
    assert Automation.objects.get(pk=automation.id).status == AutomationStatus.ERROR


def test_incomplete_extraction_goes_to_review(order_setup: dict[str, Any]) -> None:
    run = start(
        order_setup["automation"],
        whatsapp_trigger("Mujhe 1 kurta chahiye black, total Rs 2500"),
    )
    task = open_task(run)
    assert task.kind == "review"  # SAF-6
    assert "address" in task.payload_json["missing"]
    from intelliflow.core.errors import ValidationFailedError

    with pytest.raises(ValidationFailedError):  # cannot approve while a required field is empty
        approval_service.decide(task, order_setup["owner"], "approve")
    task = open_task(run)
    approval_service.decide(task, order_setup["owner"], "edit", edited_fields={"address": "House 7, DHA Lahore"}
    )
    row = SandboxRecord.objects.get(resource="sheet:Orders")
    assert row.data_json["Address"] == "House 7, DHA Lahore"


def test_test_runs_auto_approve_and_persist_nothing(
    order_setup: dict[str, Any]
) -> None:
    engine = WorkflowEngine(retry_mode=RetryMode.INLINE, sleep=lambda _s: None)
    trigger = whatsapp_trigger()
    run = engine.create_run(
        order_setup["automation"],
        event_id="test:1",
        trigger_type="whatsapp.message_received",
        trigger=trigger,
        is_test=True,
    )
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
        list(SandboxRecord.objects.all()) == []
    )  # SAF-5: nothing persisted, nobody messaged
    assert any(r["operation"] == "send_text" for r in engine.recorder.records)


def test_duplicate_events_start_one_run(order_setup: dict[str, Any]) -> None:
    engine = WorkflowEngine()
    trigger = whatsapp_trigger()
    first = engine.create_run(
        order_setup["automation"],
        event_id="wamid.SAME",
        trigger_type="whatsapp.message_received",
        trigger=trigger,
    )
    second = engine.create_run(
        order_setup["automation"],
        event_id="wamid.SAME",
        trigger_type="whatsapp.message_received",
        trigger=trigger,
    )
    assert first is not None and second is None  # REQ-WE-3


def test_step_logs_mask_personal_data(order_setup: dict[str, Any]) -> None:
    run = start(order_setup["automation"])
    step = StepRun.objects.get(run_id=run.id, step_key="save_row")
    logged = str(step.input_json)
    assert "923001234567" not in logged and "Gulberg" not in logged  # REQ-WE-6
    assert (
        run.context_encrypted is not None and b"Gulberg" not in bytes(run.context_encrypted)
    )  # encrypted at rest


def test_message_rate_limit(order_setup: dict[str, Any]) -> None:
    automation = order_setup["automation"]
    automation.current_version.definition_json = {
        **automation.current_version.definition_json,
        "settings": {"max_messages_per_hour": 1},
    }
    automation.auto_send = True  # sends without waiting for approval
    automation.current_version.save(update_fields=["definition_json"])
    automation.save(update_fields=["auto_send"])
    assert start(automation).status == RunStatus.SUCCEEDED
    run = start(automation)
    assert run.status == RunStatus.FAILED and "limit of 1 customer messages per hour" in (
        run.error or ""
    )  # SAF-4


def test_closed_window_offers_template(order_setup: dict[str, Any]) -> None:
    from datetime import UTC, datetime, timedelta

    old = whatsapp_trigger()
    old["timestamp"] = (datetime.now(UTC) - timedelta(hours=30)).isoformat()
    run = start(order_setup["automation"], old)
    task = open_task(run)
    assert not customer_window.is_open(order_setup["workspace"].id, "923001234567")
    approval_service.decide(task, order_setup["owner"], "approve")
    template_task = open_task(run)
    assert template_task.kind == "window_closed"  # REQ-WE-8 / BR-4
    assert template_task.payload_json["proposed_action"]["operation"] == "send_template"
    approval_service.decide(template_task, order_setup["owner"], "approve")
    assert Run.objects.get(pk=run.id).status == RunStatus.SUCCEEDED
    assert outbox(order_setup["whatsapp"].id)[0]["operation"] == "send_template"
