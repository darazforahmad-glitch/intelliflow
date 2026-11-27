"""Platform Admin: workspaces, AI credit limits (REQ-PA-3) and suspension (REQ-PA-4)."""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse

from intelliflow.core.enums import MembershipRole
from intelliflow.llm.service import credits_used
from intelliflow.platform_admin import services
from intelliflow.workspaces.models import Membership, Workspace


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    fields = ("user", "role", "status", "created_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "business_type",
        "status",
        "owner_email",
        "credits",
        "ai_credit_limit",
        "created_at",
    )
    list_filter = ("status", "language_pref")
    search_fields = ("name", "business_type", "memberships__user__email")
    list_editable = ("ai_credit_limit",)
    fields = (
        "name",
        "business_type",
        "language_pref",
        "timezone",
        "status",
        "suspended_reason",
        "ai_credit_limit",
        "approval_threshold",
        "currency",
        "created_at",
        "deleted_at",
    )
    readonly_fields = ("status", "suspended_reason", "created_at", "deleted_at")
    inlines = [MembershipInline]
    actions = ["suspend_workspaces", "reactivate_workspaces"]
    ordering = ("-created_at",)

    @admin.display(description="Owner")
    def owner_email(self, workspace: Workspace) -> str | None:
        owner = (
            workspace.memberships.filter(role=MembershipRole.OWNER).select_related("user").first()
        )
        return owner.user.email if owner else None

    @admin.display(description="AI credits used")
    def credits(self, workspace: Workspace) -> int:
        return credits_used(workspace.id)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False  # owners create workspaces in the app

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False  # deletion follows the BR-7 retention process

    def save_model(self, request: HttpRequest, obj: Workspace, form: Any, change: bool) -> None:
        if change and "ai_credit_limit" in form.changed_data:  # REQ-PA-3, audited
            services.set_limits(obj, request.user, obj.ai_credit_limit)  # type: ignore[arg-type]
            form.changed_data.remove("ai_credit_limit")
        super().save_model(request, obj, form, change)

    @admin.action(description="Suspend selected workspaces")
    def suspend_workspaces(
        self, request: HttpRequest, queryset: QuerySet[Workspace]
    ) -> HttpResponse | None:
        reason = (request.POST.get("reason") or "").strip()
        if request.POST.get("apply") and len(reason) >= 3:
            paused = sum(services.suspend(ws, request.user, reason[:500]) for ws in queryset)  # type: ignore[arg-type]
            self.message_user(
                request,
                f"Suspended {queryset.count()} workspace(s); {paused} automation(s) paused.",
            )
            return None
        return TemplateResponse(
            request,
            "admin/platform/suspend.html",
            {
                **self.admin_site.each_context(request),
                "workspaces": queryset,
                "title": "Suspend workspaces",
            },
        )

    @admin.action(description="Reactivate selected workspaces")
    def reactivate_workspaces(self, request: HttpRequest, queryset: QuerySet[Workspace]) -> None:
        for workspace in queryset:
            services.reactivate(workspace, request.user)  # type: ignore[arg-type]
        self.message_user(
            request,
            f"Reactivated {queryset.count()} workspace(s). Owners can switch automations back on.",
            messages.SUCCESS,
        )
