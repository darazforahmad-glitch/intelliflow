"""Template library (Table 4.9), automations (Table 4.10) and their immutable
versions (Table 4.11)."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from intelliflow.core.enums import AutomationStatus
from intelliflow.core.models import CreatedModel, TimestampedModel, choices_check


class Template(TimestampedModel):
    # A code can have many versions; at most one is published (is_active) at a time.
    code = models.CharField(max_length=60, db_index=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=60, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    definition_json = models.JSONField()
    version = models.IntegerField(default=1)
    is_active = models.BooleanField(default=True)
    # --- extensions: matching rules for Algorithm 5.2 and connection prerequisites ---
    match_json = models.JSONField(default=dict, blank=True)
    required_connections = models.JSONField(default=list, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "templates"
        constraints = [
            models.UniqueConstraint(fields=["code", "version"], name="uq_templates_code_version"),
            models.UniqueConstraint(
                fields=["code"], condition=Q(is_active=True), name="uq_templates_active_code"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} (v{self.version})"


class Automation(TimestampedModel):
    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.CASCADE, related_name="automations"
    )
    opportunity = models.ForeignKey(
        "opportunities.Opportunity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="automations",
    )
    # Circular reference automations <-> automation_versions.
    current_version = models.ForeignKey(
        "AutomationVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    name = models.CharField(max_length=120)
    status = models.CharField(
        max_length=20, choices=AutomationStatus.choices, default=AutomationStatus.DRAFT
    )
    # --- extensions ---
    template = models.ForeignKey(
        Template, on_delete=models.SET_NULL, null=True, blank=True, related_name="automations"
    )
    description = models.TextField(null=True, blank=True)
    trigger_type = models.CharField(max_length=60, null=True, blank=True, db_index=True)
    estimated_minutes_per_run = models.DecimalField(
        max_digits=6, decimal_places=1, default=Decimal(0)
    )
    auto_send = models.BooleanField(default=False)  # SAF-1
    consecutive_failures = models.SmallIntegerField(default=0)  # REQ-WE-7
    status_reason = models.TextField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="created_by",
        related_name="+",
    )

    class Meta:
        db_table = "automations"
        constraints = [
            choices_check("automations", "status", AutomationStatus),
        ]

    def __str__(self) -> str:
        return self.name


class AutomationVersion(CreatedModel):
    automation = models.ForeignKey(Automation, on_delete=models.CASCADE, related_name="versions")
    version_no = models.IntegerField()
    definition_json = models.JSONField()
    validated = models.BooleanField(default=False)
    test_passed = models.BooleanField(default=False)
    # --- extensions ---
    validation_errors = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=20, default="manual")  # generated|repaired|manual|rollback
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="created_by",
        related_name="+",
    )

    class Meta:
        db_table = "automation_versions"
        ordering = ["version_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["automation", "version_no"],
                name="uq_automation_versions_automation_id_version_no",
            )
        ]
