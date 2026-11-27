"""Flow Mapper: interview sessions and messages (Tables 4.4, 4.5), process maps and
their steps (Tables 4.6, 4.7)."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from intelliflow.core.enums import InterviewStatus, MessageSender, StepType
from intelliflow.core.models import CreatedModel, UUIDModel, choices_check


class InterviewSession(UUIDModel):
    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.CASCADE, related_name="interviews"
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="started_by",
        related_name="+",
    )
    process_name = models.CharField(max_length=120)
    status = models.CharField(
        max_length=20, choices=InterviewStatus.choices, default=InterviewStatus.IN_PROGRESS
    )
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    # --- extensions: REQ-FM-2 question budget and the detected language ---
    question_count = models.SmallIntegerField(default=0)
    language = models.CharField(max_length=10, null=True, blank=True)
    ready_for_mapping = models.BooleanField(default=False)

    class Meta:
        db_table = "interview_sessions"
        constraints = [
            choices_check("interview_sessions", "status", InterviewStatus),
        ]


class InterviewMessage(UUIDModel):
    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name="messages")
    sender = models.CharField(max_length=10, choices=MessageSender.choices)
    content = models.TextField()
    language = models.CharField(max_length=10, null=True, blank=True)
    meta_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "interview_messages"
        constraints = [
            choices_check("interview_messages", "sender", MessageSender),
        ]
        ordering = ["created_at"]


class ProcessMap(CreatedModel):
    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.CASCADE, related_name="process_maps"
    )
    session = models.ForeignKey(
        InterviewSession, on_delete=models.CASCADE, related_name="process_maps"
    )
    name = models.CharField(max_length=120)
    graph_json = models.JSONField()
    version = models.IntegerField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="created_by",
        related_name="+",
    )
    change_note = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "process_maps"
        constraints = [
            models.UniqueConstraint(
                fields=["session", "version"], name="uq_process_maps_session_id_version"
            )
        ]


class ProcessStep(UUIDModel):
    process_map = models.ForeignKey(
        ProcessMap, on_delete=models.CASCADE, related_name="steps", db_column="map_id"
    )
    seq_no = models.SmallIntegerField()
    title = models.CharField(max_length=150)
    step_type = models.CharField(max_length=20, choices=StepType.choices)
    minutes_per_run = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    runs_per_week = models.IntegerField(null=True, blank=True)
    is_manual = models.BooleanField(default=False)
    # --- extensions used by Algorithm 5.2 and the editable flowchart ---
    step_key = models.CharField(max_length=30)
    actor = models.CharField(max_length=80, null=True, blank=True)
    action = models.TextField(null=True, blank=True)
    app = models.CharField(max_length=40, null=True, blank=True)
    predecessor_key = models.CharField(max_length=30, null=True, blank=True)
    involves_customer_messaging = models.BooleanField(default=False)
    involves_money = models.BooleanField(default=False)
    support_status = models.CharField(
        max_length=20, null=True, blank=True
    )  # supported | not_yet_supported

    class Meta:
        db_table = "process_steps"
        ordering = ["seq_no"]
        constraints = [
            choices_check("process_steps", "step_type", StepType),
            models.UniqueConstraint(
                fields=["process_map", "seq_no"], name="uq_process_steps_map_id_seq_no"
            ),
            models.UniqueConstraint(
                fields=["process_map", "step_key"], name="uq_process_steps_map_id_step_key"
            ),
        ]

    @property
    def weekly_minutes(self) -> Decimal:
        """REQ-OA-1: minutes per run x runs per week."""
        return (self.minutes_per_run or Decimal(0)) * (self.runs_per_week or 0)
