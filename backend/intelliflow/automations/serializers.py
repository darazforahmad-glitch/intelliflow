"""Automation Builder requests and responses (UC-07, UC-09)."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db.models import Count, Max, Q, Sum
from rest_framework import serializers

from intelliflow.approvals.services import clean_customer_approvals
from intelliflow.automations.builder import providers_used
from intelliflow.automations.models import Automation, AutomationVersion
from intelliflow.core.api.fields import dec, dt, uid
from intelliflow.core.enums import RunStatus
from intelliflow.integrations.connectors.registry import PROVIDER_LABELS, active_connection
from intelliflow.runs.models import Run


class DefinitionSerializer(serializers.Serializer):
    definition = serializers.DictField()


class FromTemplateSerializer(serializers.Serializer):
    template_code = serializers.CharField(min_length=2, max_length=60)


class TestSerializer(serializers.Serializer):
    sample = serializers.DictField(default=dict)


class RollbackSerializer(serializers.Serializer):
    version_no = serializers.IntegerField(min_value=1)


class AutoSendSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()


class AutomationQuerySerializer(serializers.Serializer):
    include_archived = serializers.BooleanField(default=False)


def _empty_stats() -> dict[str, Any]:
    return {
        "runs_total": 0,
        "runs_succeeded": 0,
        "runs_failed": 0,
        "runs_waiting": 0,
        "minutes_saved": "0",
        "last_run_at": None,
    }


def stats_for(automation_ids: Iterable[Any]) -> dict[Any, dict[str, Any]]:
    ids = list(automation_ids)
    if not ids:
        return {}
    rows = (
        Run.objects.filter(automation_id__in=ids, is_test=False)
        .order_by()
        .values("automation_id")
        .annotate(
            total=Count("id"),
            succeeded=Count("id", filter=Q(status=RunStatus.SUCCEEDED)),
            failed=Count("id", filter=Q(status=RunStatus.FAILED)),
            waiting=Count("id", filter=Q(status=RunStatus.WAITING_APPROVAL)),
            minutes=Sum("minutes_saved"),
            last=Max("created_at"),
        )
    )
    return {
        r["automation_id"]: {
            "runs_total": r["total"],
            "runs_succeeded": r["succeeded"],
            "runs_failed": r["failed"],
            "runs_waiting": r["waiting"],
            "minutes_saved": dec(Decimal(r["minutes"] or 0)),
            "last_run_at": dt(r["last"]),
        }
        for r in rows
    }


def version_out(version: AutomationVersion) -> dict[str, Any]:
    return {
        "id": str(version.id),
        "version_no": version.version_no,
        "definition_json": version.definition_json,
        "validated": version.validated,
        "test_passed": version.test_passed,
        "validation_errors": version.validation_errors,
        "source": version.source,
        "created_at": dt(version.created_at),
    }


def automation_out(automation: Automation) -> dict[str, Any]:
    automation.refresh_from_db()
    template = automation.template
    current = automation.current_version
    connections = []
    for provider in sorted(providers_used(current.definition_json) if current else set()):
        connection = active_connection(automation.workspace_id, provider)
        connections.append(
            {
                "provider": provider,
                "label": PROVIDER_LABELS.get(provider, provider),
                "connected": connection is not None,
                "mode": connection.mode if connection else None,
            }
        )
    threshold = settings.AUTO_SEND_MIN_CLEAN_APPROVALS
    return {
        "id": str(automation.id),
        "name": automation.name,
        "description": automation.description,
        "status": automation.status,
        "status_reason": automation.status_reason,
        "trigger_type": automation.trigger_type,
        "template_code": template.code if template else None,
        "template_name": template.name if template else None,
        "opportunity_id": uid(automation.opportunity_id),
        "auto_send": automation.auto_send,
        "clean_approvals": clean_customer_approvals(automation.id, threshold),
        "auto_send_threshold": threshold,
        "estimated_minutes_per_run": dec(automation.estimated_minutes_per_run),
        "activated_at": dt(automation.activated_at),
        "created_at": dt(automation.created_at),
        "updated_at": dt(automation.updated_at),
        "current_version": version_out(current) if current else None,
        "versions": [
            {
                "id": str(v.id),
                "version_no": v.version_no,
                "validated": v.validated,
                "test_passed": v.test_passed,
                "source": v.source,
                "created_at": dt(v.created_at),
            }
            for v in automation.versions.order_by("-version_no")
        ],
        "connections": connections,
        "stats": stats_for([automation.id]).get(automation.id, _empty_stats()),
    }


def automation_list(automations: Iterable[Automation]) -> list[dict[str, Any]]:
    items = list(automations)
    stats = stats_for(a.id for a in items)
    return [
        {
            "id": str(a.id),
            "name": a.name,
            "status": a.status,
            "status_reason": a.status_reason,
            "trigger_type": a.trigger_type,
            "template_name": a.template.name if a.template_id else None,
            "auto_send": a.auto_send,
            "version_no": a.current_version.version_no if a.current_version_id else None,
            "stats": stats.get(a.id, _empty_stats()),
        }
        for a in items
    ]
