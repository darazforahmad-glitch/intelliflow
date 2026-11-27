"""Approval queue responses and the decision request (UC-11)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from intelliflow.approvals.models import ApprovalTask
from intelliflow.core.api.fields import dt


class ApprovalQuerySerializer(serializers.Serializer):
    state = serializers.ChoiceField(["open", "decided", "all"], default="open")
    limit = serializers.IntegerField(min_value=1, max_value=200, default=50)


class DecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(["approve", "edit", "reject"])
    edited_params = serializers.DictField(required=False, allow_null=True)
    edited_fields = serializers.DictField(required=False, allow_null=True)
    note = serializers.CharField(max_length=500, required=False, allow_null=True, allow_blank=True)


def approval_out(task: ApprovalTask) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "status": task.status,
        "kind": task.kind,
        "title": task.title,
        "automation_id": str(task.automation_id),
        "automation_name": task.automation.name,
        "run_id": str(task.run_id),
        "step_title": (task.payload_json or {}).get("step_title"),
        "payload": task.payload_json,
        "decision_payload": task.decision_payload_json,
        "decided_by_name": task.decided_by.full_name if task.decided_by_id else None,
        "decided_at": dt(task.decided_at),
        "decision_note": task.decision_note,
        "created_at": dt(task.created_at),
        "remind_at": dt(task.remind_at),
        "expires_at": dt(task.expires_at),
    }
