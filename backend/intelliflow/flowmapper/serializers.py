"""Flow Mapper requests and responses: interviews, process maps and opportunities."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db.models import OuterRef, Subquery
from rest_framework import serializers

from intelliflow.automations.models import Automation
from intelliflow.core.api.fields import dec, dt, uid
from intelliflow.core.enums import OpportunityStatus, StepType
from intelliflow.flowmapper.models import InterviewSession, ProcessMap, ProcessStep
from intelliflow.opportunities.analyzer import TOP_N, per_day
from intelliflow.opportunities.models import Opportunity

STEP_TYPES = ["start", "manual", "automated", "human_only", "end"]
APPS = [
    "whatsapp",
    "excel",
    "google_sheets",
    "gmail",
    "paper",
    "phone",
    "webform",
    "website",
    "bank",
    "courier",
    "pos",
    "other",
    "none",
]


# ---------------------------------------------------------------- requests
class InterviewCreateSerializer(serializers.Serializer):
    process_name = serializers.CharField(min_length=2, max_length=120)


class AnswerSerializer(serializers.Serializer):
    content = serializers.CharField(min_length=1, max_length=4000, trim_whitespace=False)


class PositionSerializer(serializers.Serializer):
    x = serializers.FloatField()
    y = serializers.FloatField()


class StepInSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=30, required=False, allow_null=True, allow_blank=True)
    title = serializers.CharField(min_length=2, max_length=150)
    actor = serializers.CharField(min_length=1, max_length=80, default="Owner")
    action = serializers.CharField(
        max_length=1000, required=False, allow_null=True, allow_blank=True
    )
    step_type = serializers.ChoiceField(STEP_TYPES)
    app = serializers.ChoiceField(APPS, default="other")
    minutes_per_run = serializers.FloatField(min_value=0, max_value=600, default=0)
    runs_per_week = serializers.IntegerField(min_value=0, max_value=10000, default=0)
    involves_customer_messaging = serializers.BooleanField(default=False)
    involves_money = serializers.BooleanField(default=False)


class MapVersionSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=2, max_length=120, required=False, allow_null=True)
    note = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    steps = StepInSerializer(many=True, min_length=3, max_length=40)
    positions = serializers.DictField(child=PositionSerializer(), required=False, allow_null=True)


# ---------------------------------------------------------------- interviews
def interview_out(session: InterviewSession) -> dict[str, Any]:
    latest = session.process_maps.order_by("-version").values_list("id", flat=True).first()
    return {
        "id": str(session.id),
        "process_name": session.process_name,
        "status": session.status,
        "started_at": dt(session.started_at),
        "completed_at": dt(session.completed_at),
        "question_count": session.question_count,
        "max_questions": settings.INTERVIEW_MAX_QUESTIONS,
        "ready_for_mapping": session.ready_for_mapping,
        "language": session.language,
        "messages": [
            {
                "id": str(m.id),
                "sender": m.sender,
                "content": m.content,
                "language": m.language,
                "created_at": dt(m.created_at),
                "meta_json": m.meta_json,
            }
            for m in session.messages.all()
        ],
        "latest_map_id": uid(latest),
    }


def interview_summaries(workspace_id: Any) -> list[dict[str, Any]]:
    latest = ProcessMap.objects.filter(session=OuterRef("pk")).order_by("-version")
    sessions = (
        InterviewSession.objects.filter(workspace_id=workspace_id)
        .annotate(
            latest_map_id=Subquery(latest.values("id")[:1]),
            latest_version=Subquery(latest.values("version")[:1]),
        )
        .order_by("-started_at")
    )
    return [
        {
            "id": str(s.id),
            "process_name": s.process_name,
            "status": s.status,
            "started_at": dt(s.started_at),
            "completed_at": dt(s.completed_at),
            "latest_map_id": uid(s.latest_map_id),
            "latest_version": s.latest_version,
        }
        for s in sessions
    ]


# ---------------------------------------------------------------- process maps
def step_out(step: ProcessStep) -> dict[str, Any]:
    return {
        "id": str(step.id),
        "key": step.step_key,
        "seq_no": step.seq_no,
        "title": step.title,
        "actor": step.actor,
        "action": step.action,
        "step_type": step.step_type,
        "app": step.app,
        "minutes_per_run": dec(step.minutes_per_run),
        "runs_per_week": step.runs_per_week,
        "weekly_minutes": dec(step.weekly_minutes),
        "is_manual": step.is_manual,
        "predecessor_key": step.predecessor_key,
        "involves_customer_messaging": step.involves_customer_messaging,
        "involves_money": step.involves_money,
        "support_status": step.support_status,
    }


def opportunity_out(
    opportunity: Opportunity, step: ProcessStep, automation_id: Any = None
) -> dict[str, Any]:
    template = opportunity.template
    return {
        "id": str(opportunity.id),
        "rank": opportunity.rank,
        "score": dec(opportunity.score),
        "status": opportunity.status,
        "fit": dec(opportunity.fit),
        "risk": dec(opportunity.risk),
        "minutes_saved_per_week": dec(opportunity.minutes_saved_per_week),
        "minutes_saved_per_day": dec(per_day(opportunity.minutes_saved_per_week)),
        "reason": opportunity.reason,
        "step_id": str(step.id),
        "step_key": step.step_key,
        "step_title": step.title,
        "template": (
            {
                "id": str(template.id),
                "code": template.code,
                "name": template.name,
                "category": template.category,
                "required_connections": list(template.required_connections or []),
            }
            if template
            else None
        ),
        "automation_id": uid(automation_id),
    }


def _manual_minutes(steps: list[ProcessStep]) -> Decimal:
    manual = [s for s in steps if s.step_type in {StepType.MANUAL, StepType.HUMAN_ONLY}]
    return sum((s.weekly_minutes for s in manual), Decimal(0))


def map_out(process_map: ProcessMap) -> dict[str, Any]:
    steps = list(process_map.steps.all())
    by_id = {s.id: s for s in steps}
    opportunities = list(
        Opportunity.objects.filter(process_map=process_map).select_related("template")
    )
    automation_ids = dict(
        Automation.objects.filter(opportunity_id__in=[o.id for o in opportunities]).values_list(
            "opportunity_id", "id"
        )
    )
    items = sorted(
        (opportunity_out(o, by_id[o.step_id], automation_ids.get(o.id)) for o in opportunities),
        key=lambda o: (o["rank"] is None, o["rank"] or 0),
    )
    versions = list(
        ProcessMap.objects.filter(session_id=process_map.session_id).order_by("version")
    )
    dismissed = OpportunityStatus.DISMISSED.value
    return {
        "id": str(process_map.id),
        "session_id": str(process_map.session_id),
        "name": process_map.name,
        "version": process_map.version,
        "is_latest": process_map.version == max(v.version for v in versions),
        "created_at": dt(process_map.created_at),
        "change_note": process_map.change_note,
        "graph_json": process_map.graph_json,
        "steps": [step_out(s) for s in steps],
        "total_weekly_minutes": dec(sum((s.weekly_minutes for s in steps), Decimal(0))),
        "manual_weekly_minutes": dec(_manual_minutes(steps)),
        "opportunities": [
            o for o in items if o["status"] != dismissed and (o["rank"] or 99) <= TOP_N
        ],
        "other_opportunities": [
            o for o in items if o["status"] != dismissed and (o["rank"] or 99) > TOP_N
        ],
        "dismissed_opportunities": [o for o in items if o["status"] == dismissed],
        "unsupported_steps": [s.step_key for s in steps if s.support_status == "not_yet_supported"],
        "versions": [
            {
                "id": str(v.id),
                "version": v.version,
                "created_at": dt(v.created_at),
                "change_note": v.change_note,
            }
            for v in versions
        ],
    }


def map_summaries(workspace_id: Any) -> list[dict[str, Any]]:
    latest_version = (
        ProcessMap.objects.filter(session=OuterRef("session"))
        .order_by("-version")
        .values("version")[:1]
    )
    maps = (
        ProcessMap.objects.filter(workspace_id=workspace_id)
        .annotate(latest_version=Subquery(latest_version))
        .order_by("-created_at")
        .prefetch_related("steps")
    )
    summaries = []
    for m in maps:
        if m.version != m.latest_version:
            continue
        steps = list(m.steps.all())
        top = (
            Opportunity.objects.filter(process_map=m, rank=1)
            .values_list("step__title", flat=True)
            .first()
        )
        summaries.append(
            {
                "id": str(m.id),
                "session_id": str(m.session_id),
                "name": m.name,
                "version": m.version,
                "created_at": dt(m.created_at),
                "step_count": len(steps),
                "manual_weekly_minutes": dec(_manual_minutes(steps)),
                "top_opportunity": top,
            }
        )
    return summaries
