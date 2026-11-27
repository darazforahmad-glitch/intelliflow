"""Human approval tasks (Table 4.15), states per Figure 4.10."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from intelliflow.core.enums import ApprovalKind, ApprovalStatus
from intelliflow.core.models import CreatedModel, choices_check


class ApprovalTask(CreatedModel):
    step_run = models.ForeignKey(
        "runs.StepRun", on_delete=models.CASCADE, related_name="approval_tasks"
    )
    # NULL = role-based: every active member of the workspace
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="decided_by",
        related_name="+",
    )
    # {"title", "reason", "input", "ai_output", "proposed_action", "editable_fields"}
    payload_json = models.JSONField()
    status = models.CharField(
        max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    # --- extensions ---
    run = models.ForeignKey("runs.Run", on_delete=models.CASCADE, related_name="approval_tasks")
    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.CASCADE, related_name="approval_tasks"
    )
    automation = models.ForeignKey(
        "automations.Automation", on_delete=models.CASCADE, related_name="approval_tasks"
    )
    kind = models.CharField(max_length=20, choices=ApprovalKind.choices)
    title = models.CharField(max_length=150)
    decision_payload_json = models.JSONField(null=True, blank=True)  # the edited proposed action
    decision_note = models.TextField(null=True, blank=True)
    remind_at = models.DateTimeField(null=True, blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "approval_tasks"
        constraints = [
            choices_check("approval_tasks", "status", ApprovalStatus),
            choices_check("approval_tasks", "kind", ApprovalKind),
        ]
        indexes = [models.Index(fields=["workspace", "status"], name="ix_approval_tasks_ws_status")]
