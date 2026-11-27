"""Platform Admin: the audit log (REQ-PA-5) and LLM usage and cost (REQ-PA-2). Read-only."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from intelliflow.audit.models import AuditLog, LLMUsage


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyAdmin):
    list_display = (
        "created_at",
        "action",
        "workspace",
        "actor",
        "entity_type",
        "entity_id",
        "ip_address",
    )
    list_filter = ("action", "entity_type")
    search_fields = ("action", "workspace__name", "actor__email", "entity_id", "request_id")
    date_hierarchy = "created_at"
    list_select_related = ("workspace", "actor")
    ordering = ("-created_at",)


@admin.register(LLMUsage)
class LLMUsageAdmin(ReadOnlyAdmin):
    list_display = (
        "created_at",
        "workspace",
        "task",
        "model",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "credits",
        "succeeded",
    )
    list_filter = ("task", "provider", "succeeded")
    search_fields = ("workspace__name", "model")
    date_hierarchy = "created_at"
    list_select_related = ("workspace",)
    ordering = ("-created_at",)
