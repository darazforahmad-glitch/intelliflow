"""Platform Admin: connection health. Tokens are encrypted and never shown (REQ-IN-5)."""

from __future__ import annotations

from django.contrib import admin

from intelliflow.audit.admin import ReadOnlyAdmin
from intelliflow.integrations.models import Connection


@admin.register(Connection)
class ConnectionAdmin(ReadOnlyAdmin):
    list_display = ("workspace", "provider", "mode", "status", "display_name", "created_at")
    list_filter = ("provider", "mode", "status")
    search_fields = ("workspace__name", "display_name")
    fields = (
        "workspace",
        "provider",
        "mode",
        "status",
        "display_name",
        "last_error",
        "token_expires_at",
        "created_at",
    )
    list_select_related = ("workspace",)
