"""Platform Admin: run monitoring. Status and timings only, never the run context (BR-8)."""

from __future__ import annotations

from django.contrib import admin

from intelliflow.audit.admin import ReadOnlyAdmin
from intelliflow.runs.models import Run


@admin.register(Run)
class RunAdmin(ReadOnlyAdmin):
    list_display = (
        "created_at",
        "automation",
        "workspace",
        "status",
        "is_test",
        "trigger_type",
        "minutes_saved",
    )
    list_filter = ("status", "is_test", "trigger_type")
    search_fields = ("automation__name", "workspace__name", "event_id")
    date_hierarchy = "created_at"
    list_select_related = ("automation", "workspace")
    fields = (
        "automation",
        "workspace",
        "status",
        "is_test",
        "trigger_type",
        "event_id",
        "minutes_saved",
        "error",
        "created_at",
        "started_at",
        "finished_at",
    )
    ordering = ("-created_at",)
