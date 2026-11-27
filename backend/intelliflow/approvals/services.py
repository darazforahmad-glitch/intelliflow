"""Human-in-the-loop approvals: decideApproval (Table 4.16), reminders and expiry (REQ-AP-3..6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from django.db import transaction

from intelliflow.accounts.models import User
from intelliflow.approvals.models import ApprovalTask
from intelliflow.audit import services as audit_service
from intelliflow.core.enums import ApprovalKind, ApprovalStatus
from intelliflow.core.errors import ConflictError, ValidationFailedError
from intelliflow.core.models import utcnow
from intelliflow.notifications import event_bus
from intelliflow.notifications.services import notify, workspace_members

Decision = Literal["approve", "edit", "reject"]


def _enqueue_resume(run_id: uuid.UUID) -> None:
    def _dispatch() -> None:
        from intelliflow.runs.tasks import execute_run

        execute_run.delay(str(run_id))

    transaction.on_commit(_dispatch)


def _coerce_field(value: Any, type_: str) -> Any:
    if value in (None, ""):
        return None
    try:
        if type_ == "number":
            return float(str(value).replace(",", ""))
        if type_ == "integer":
            return int(float(str(value).replace(",", "")))
        if type_ == "boolean":
            return (
                value
                if isinstance(value, bool)
                else str(value).lower() in {"true", "yes", "1", "haan"}
            )
    except ValueError as exc:
        raise ValidationFailedError(f"“{value}” is not a valid {type_}.") from exc
    return str(value)


@transaction.atomic
def decide(
    task: ApprovalTask,
    user: User,
    decision: Decision,
    *,
    edited_params: dict[str, Any] | None = None,
    edited_fields: dict[str, Any] | None = None,
    note: str | None = None,
) -> ApprovalTask:
    # Lock the row so two people deciding at the same moment cannot both win (BR-9).
    task = ApprovalTask.objects.select_for_update().get(pk=task.pk)
    if not ApprovalStatus(task.status).is_open:  # BR-9: a decision is final
        raise ConflictError(
            "This approval has already been decided and cannot be changed.", code="already_decided"
        )
    if task.assignee_id is not None and task.assignee_id != user.id:
        raise ConflictError("This approval is assigned to someone else.", code="not_assignee")
    payload = task.payload_json or {}
    editable = set(payload.get("editable") or [])
    proposed = payload.get("proposed_action") or None
    decided: dict[str, Any] | None = None

    if decision == "reject":
        status = ApprovalStatus.REJECTED
    elif task.kind == ApprovalKind.REVIEW:
        fields_spec = {f["name"]: f for f in payload.get("fields", [])}
        merged = dict(payload.get("ai_output") or {})
        for name, value in (edited_fields or {}).items():
            if name not in editable:
                raise ValidationFailedError(f"“{name}” cannot be changed here.")
            merged[name] = _coerce_field(value, fields_spec.get(name, {}).get("type", "string"))
        still_missing = [
            n for n, f in fields_spec.items() if f.get("required") and merged.get(n) in (None, "")
        ]
        if still_missing:
            raise ValidationFailedError(
                f"Please fill in: {', '.join(still_missing)}.",
                code="fields_missing",
                details={"missing": still_missing},
            )
        status = ApprovalStatus.EDITED if edited_fields else ApprovalStatus.APPROVED
        decided = {"fields": merged}
    elif decision == "edit":
        if not proposed or not edited_params:
            raise ValidationFailedError("There is nothing to edit in this approval.")
        not_allowed = sorted(set(edited_params) - editable)
        if not_allowed:  # e.g. the recipient can never be changed, only the text
            raise ValidationFailedError(
                f"Only these can be changed: {', '.join(sorted(editable)) or 'nothing'}.",
                code="field_not_editable",
                details={"not_editable": not_allowed},
            )
        status = ApprovalStatus.EDITED
        decided = {"params": {**proposed.get("params", {}), **edited_params}}
    else:
        status = ApprovalStatus.APPROVED
        decided = {"params": proposed.get("params") if proposed else None}

    task.status = status
    task.decided_by = user  # REQ-AP-6
    task.decided_at = utcnow()
    task.decision_note = (note or "").strip()[:500] or None
    task.decision_payload_json = decided
    task.save()
    audit_service.record(
        "approval.decided",
        workspace_id=task.workspace_id,
        actor_id=user.id,
        entity_type="approval_task",
        entity_id=task.id,
        data={"status": status.value},
    )
    _enqueue_resume(task.run_id)  # REQ-AP-4: resume right after the decision
    task_id, workspace_id = task.id, task.workspace_id
    transaction.on_commit(
        lambda: event_bus.publish(
            workspace_id, "approval.decided", {"approval_id": str(task_id), "status": status.value}
        )
    )
    return task


@transaction.atomic
def process_timeouts(now: datetime | None = None) -> tuple[int, int]:
    """Beat task body: remind after 2 h, expire and cancel after 24 h (REQ-AP-5)."""
    now = now or utcnow()
    expired = list(
        ApprovalTask.objects.select_for_update(skip_locked=True).filter(
            status__in=[ApprovalStatus.PENDING, ApprovalStatus.REMINDED], expires_at__lte=now
        )
    )
    for task in expired:
        task.status = ApprovalStatus.EXPIRED
        task.decided_at = now
        task.save(update_fields=["status", "decided_at"])
        _enqueue_resume(task.run_id)
    reminded = list(
        ApprovalTask.objects.select_for_update(skip_locked=True).filter(
            status=ApprovalStatus.PENDING, remind_at__lte=now
        )
    )
    for task in reminded:
        task.status = ApprovalStatus.REMINDED
        task.reminded_at = now
        task.save(update_fields=["status", "reminded_at"])
        notify(
            workspace_members(task.workspace_id),
            workspace_id=task.workspace_id,
            kind="approval.reminder",
            title=f"Reminder: {task.title}",
            body="An approval is still waiting for you.",
            url=f"/approvals/{task.id}",
        )
    return len(reminded), len(expired)


def clean_customer_approvals(automation_id: uuid.UUID, window: int) -> int:
    """Number of most recent customer-message approvals that were approved without edits (SAF-1)."""
    recent = (
        ApprovalTask.objects.filter(
            automation_id=automation_id,
            kind=ApprovalKind.CUSTOMER_MESSAGE,
            status__in=[ApprovalStatus.APPROVED, ApprovalStatus.EDITED, ApprovalStatus.REJECTED],
        )
        .order_by("-decided_at")
        .values_list("status", flat=True)[:window]
    )
    clean = 0
    for status in recent:
        if status != ApprovalStatus.APPROVED:
            break
        clean += 1
    return clean
