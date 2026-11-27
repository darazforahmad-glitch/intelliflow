"""Platform Admin: user accounts (who can sign in; platform admin flag)."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from intelliflow.accounts.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "full_name",
        "email_verified",
        "is_platform_admin",
        "locked_until",
        "created_at",
    )
    list_filter = ("is_platform_admin", "email_verified")
    search_fields = ("email", "full_name")
    fields = (
        "email",
        "full_name",
        "phone",
        "email_verified",
        "is_platform_admin",
        "failed_login_attempts",
        "locked_until",
        "last_login",
        "created_at",
    )
    readonly_fields = ("email", "last_login", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False  # people register in the app; admins are created with `create_admin`

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


# IntelliFlow roles live on memberships, not Django groups.
from django.contrib.auth.models import Group  # noqa: E402

admin.site.unregister(Group)
