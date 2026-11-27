"""Run history responses (REQ-DR-4) and query parameters."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from intelliflow.core.api.fields import dec, dt, uid
from intelliflow.core.enums import RunStatus
from intelliflow.runs.models import Run


class RunQuerySerializer(serializers.Serializer):
    status = serializers.ChoiceField(RunStatus.values, required=False, allow_null=True)
    automation_id = serializers.UUIDField(required=False, allow_null=True)
    include_tests = serializers.BooleanField(default=False)
    limit = serializers.IntegerField(min_value=1, max_value=200, default=50)
    offset = serializers.IntegerField(min_value=0, default=0)


def run_out(run: Run) -> dict[str, Any]:
    duration = (
        (run.finished_at - run.started_at).total_seconds()
        if run.finished_at and run.started_at
        else None
    )
    return {
        "id": str(run.id),
        "automation_id": str(run.automation_id),
        "automation_name": run.automation.name,
        "version_no": run.version.version_no if run.version_id else None,
        "status": str(run.status),
        "is_test": run.is_test,
        "trigger_type": run.trigger_type,
        "minutes_saved": dec(run.minutes_saved),
        "summary": run.summary,
        "error": run.error,
        "created_at": dt(run.created_at),
        "started_at": dt(run.started_at),
        "finished_at": dt(run.finished_at),
        "duration_seconds": duration,
    }


def run_detail_out(run: Run) -> dict[str, Any]:
    return {
        **run_out(run),
        "steps": [
            {
                "id": str(s.id),
                "step_key": s.step_key,
                "seq_no": s.seq_no,
                "block_type": s.block_type,
                "status": s.status,
                "input_json": s.input_json,
                "output_json": s.output_json,
                "error": s.error,
                "attempt": s.attempt,
                "started_at": dt(s.started_at),
                "finished_at": dt(s.finished_at),
            }
            for s in run.step_runs.order_by("seq_no")
        ],
        "approvals": [
            {
                "id": str(a.id),
                "kind": a.kind,
                "title": a.title,
                "status": a.status,
                "created_at": dt(a.created_at),
                "decided_at": dt(a.decided_at),
            }
            for a in run.approval_tasks.order_by("created_at")
        ],
    }


__all__ = ["RunQuerySerializer", "dec", "run_detail_out", "run_out", "uid"]
