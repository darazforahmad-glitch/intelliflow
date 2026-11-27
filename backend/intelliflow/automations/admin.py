"""Platform Admin: the template library with versioning (REQ-PA-1) and automation monitoring."""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from intelliflow.automations.models import Automation, Template
from intelliflow.automations.validator import WorkflowValidator
from intelliflow.core.errors import AppError
from intelliflow.platform_admin import services


class TemplateForm(forms.ModelForm):
    class Meta:
        model = Template
        fields = (
            "code",
            "name",
            "category",
            "description",
            "definition_json",
            "match_json",
            "required_connections",
        )

    def clean_definition_json(self) -> dict[str, Any]:
        definition = self.cleaned_data["definition_json"]
        if not isinstance(definition, dict):
            raise forms.ValidationError("The definition must be a JSON object.")
        issues = WorkflowValidator().validate(definition)
        if issues:
            raise forms.ValidationError([i.message for i in issues])
        return definition


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    form = TemplateForm
    list_display = ("code", "name", "version", "is_active", "category", "retired_at", "updated_at")
    list_filter = ("is_active", "category")
    search_fields = ("code", "name")
    ordering = ("code", "-version")
    actions = ["publish", "retire", "new_version"]

    def get_readonly_fields(
        self, request: HttpRequest, obj: Template | None = None
    ) -> tuple[str, ...]:
        # Published versions are immutable: changes go into a new version.
        return ("code",) if obj is not None else ()

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False  # retire instead, so automations keep a reference

    def save_model(self, request: HttpRequest, obj: Template, form: Any, change: bool) -> None:
        if not change:
            obj.is_active = False  # new templates start as drafts; publish when ready
        super().save_model(request, obj, form, change)

    @admin.action(description="Publish selected version (retires the other versions of that code)")
    def publish(self, request: HttpRequest, queryset: QuerySet[Template]) -> None:
        if queryset.values("code").distinct().count() != queryset.count():
            self.message_user(request, "Choose at most one version per template.", messages.ERROR)
            return
        for template in queryset:
            services.publish_template(template, request.user)  # type: ignore[arg-type]
        self.message_user(request, f"Published {queryset.count()} template version(s).")

    @admin.action(description="Retire selected versions")
    def retire(self, request: HttpRequest, queryset: QuerySet[Template]) -> None:
        for template in queryset:
            services.retire_template(template, request.user)  # type: ignore[arg-type]
        self.message_user(request, f"Retired {queryset.count()} template version(s).")

    @admin.action(description="Create a new draft version from the selected one")
    def new_version(self, request: HttpRequest, queryset: QuerySet[Template]) -> None:
        for template in queryset:
            try:
                created = services.new_template_version(
                    request.user,  # type: ignore[arg-type]
                    template.code,
                    {
                        "name": template.name,
                        "category": template.category,
                        "description": template.description,
                        "definition": template.definition_json,
                        "match": template.match_json,
                        "required_connections": template.required_connections,
                    },
                )
            except AppError as exc:
                self.message_user(request, exc.message, messages.ERROR)
                continue
            self.message_user(request, f"Created {created.code} version {created.version} (draft).")


@admin.register(Automation)
class AutomationAdmin(admin.ModelAdmin):
    """Monitoring only: what runs where and how healthy it is (no message content, BR-8)."""

    list_display = (
        "name",
        "workspace",
        "status",
        "trigger_type",
        "consecutive_failures",
        "activated_at",
    )
    list_filter = ("status", "trigger_type")
    search_fields = ("name", "workspace__name")
    fields = (
        "name",
        "workspace",
        "status",
        "status_reason",
        "trigger_type",
        "template",
        "auto_send",
        "consecutive_failures",
        "activated_at",
        "created_at",
        "updated_at",
    )
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
