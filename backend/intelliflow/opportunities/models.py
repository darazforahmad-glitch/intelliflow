"""Ranked automation opportunities (Table 4.8), produced by Algorithm 5.2."""

from __future__ import annotations

from django.db import models

from intelliflow.core.enums import OpportunityStatus
from intelliflow.core.models import CreatedModel, choices_check


class Opportunity(CreatedModel):
    process_map = models.ForeignKey(
        "flowmapper.ProcessMap",
        on_delete=models.CASCADE,
        related_name="opportunities",
        db_column="map_id",
    )
    step = models.ForeignKey(
        "flowmapper.ProcessStep", on_delete=models.CASCADE, related_name="opportunities"
    )
    template = models.ForeignKey(
        "automations.Template",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opportunities",
    )
    rank = models.SmallIntegerField(null=True, blank=True)
    score = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=OpportunityStatus.choices, default=OpportunityStatus.SUGGESTED
    )
    # --- extensions: explainability (REQ-OA-4, REQ-OA-5) ---
    fit = models.DecimalField(max_digits=3, decimal_places=2)
    risk = models.DecimalField(max_digits=3, decimal_places=2)
    minutes_saved_per_week = models.DecimalField(max_digits=8, decimal_places=1)
    reason = models.TextField()

    class Meta:
        db_table = "opportunities"
        constraints = [
            choices_check("opportunities", "status", OpportunityStatus),
        ]
        verbose_name_plural = "opportunities"
