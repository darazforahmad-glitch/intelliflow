"""Audit log (REQ-PA-5, SEC-6) and LLM usage for credits and cost (REQ-PA-2, REQ-PA-3)."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

from intelliflow.core.models import CreatedModel


class AuditLog(CreatedModel):
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    action = models.CharField(max_length=80)  # e.g. automation.activated
    entity_type = models.CharField(max_length=40, null=True, blank=True)
    entity_id = models.CharField(max_length=64, null=True, blank=True)
    data_json = models.JSONField(default=dict, blank=True)
    ip_address = models.CharField(max_length=45, null=True, blank=True)
    request_id = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "audit_logs"
        indexes = [
            models.Index(fields=["workspace", "created_at"], name="ix_audit_logs_ws_created")
        ]


class LLMUsage(CreatedModel):
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="llm_usage",
    )
    task = models.CharField(max_length=40)  # interview_turn | process_map | ai.extract ...
    provider = models.CharField(max_length=20)
    model = models.CharField(max_length=60)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=Decimal(0))
    credits = models.IntegerField(default=1)
    succeeded = models.BooleanField(default=True)

    class Meta:
        db_table = "llm_usage"
        verbose_name = "LLM usage record"
        indexes = [models.Index(fields=["workspace", "created_at"], name="ix_llm_usage_ws_created")]
