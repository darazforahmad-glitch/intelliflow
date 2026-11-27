"""Workflow engine records: runs (Table 4.13) and step runs (Table 4.14)."""

from __future__ import annotations

from decimal import Decimal

from django.db import models

from intelliflow.core.enums import RunStatus, StepRunStatus
from intelliflow.core.models import CreatedModel, UUIDModel, choices_check


class Run(CreatedModel):
    automation = models.ForeignKey(
        "automations.Automation", on_delete=models.CASCADE, related_name="runs"
    )
    # RESTRICT: a version cannot be deleted while runs use it, unless they go with it.
    version = models.ForeignKey(
        "automations.AutomationVersion", on_delete=models.RESTRICT, related_name="runs"
    )
    event_id = models.CharField(max_length=120)
    status = models.CharField(max_length=20, choices=RunStatus.choices, default=RunStatus.QUEUED)
    minutes_saved = models.DecimalField(max_digits=6, decimal_places=1, default=Decimal(0))
    # --- extensions ---
    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.CASCADE, related_name="runs"
    )
    is_test = models.BooleanField(default=False)
    trigger_type = models.CharField(max_length=60)
    resume_point = models.SmallIntegerField(default=0)
    # Execution context (trigger payload + step outputs) needed to resume: encrypted at rest.
    context_encrypted = models.BinaryField(null=True, blank=True)
    summary = models.TextField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "runs"
        constraints = [
            choices_check("runs", "status", RunStatus),
            # Idempotency (REQ-WE-3): one run per provider event per automation. A single
            # inbound event may legitimately trigger several different automations.
            models.UniqueConstraint(
                fields=["automation", "event_id"], name="uq_runs_automation_id_event_id"
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "created_at"], name="ix_runs_workspace_created")
        ]


class StepRun(UUIDModel):
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="step_runs")
    step_key = models.CharField(max_length=60)
    status = models.CharField(max_length=20, choices=StepRunStatus.choices)
    input_json = models.JSONField(null=True, blank=True)  # masked (REQ-WE-6)
    output_json = models.JSONField(null=True, blank=True)  # masked (REQ-WE-6)
    attempt = models.SmallIntegerField(default=1)
    # --- extensions ---
    seq_no = models.SmallIntegerField()
    block_type = models.CharField(max_length=40)
    error = models.TextField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "step_runs"
        ordering = ["seq_no"]
        constraints = [
            choices_check("step_runs", "status", StepRunStatus),
            models.UniqueConstraint(
                fields=["run", "step_key"], name="uq_step_runs_run_id_step_key"
            ),
        ]
