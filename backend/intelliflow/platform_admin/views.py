"""/api/v1/admin: the platform administration API (REQ-PA-1..5).

The same operations are available in the Django admin site (/admin/), which is the
primary Platform Admin interface; these endpoints serve the web app and automation.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from intelliflow.core.api.permissions import IsPlatformAdmin, message
from intelliflow.core.api.viewsets import UUID_REGEX
from intelliflow.platform_admin import services


class SuspendSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=3, max_length=500)


class LimitsSerializer(serializers.Serializer):
    ai_credit_limit = serializers.IntegerField(
        min_value=0, max_value=1_000_000, required=False, allow_null=True, default=None
    )


class TemplateInSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^[a-z][a-z0-9_]+$", min_length=3, max_length=60)
    name = serializers.CharField(min_length=3, max_length=120)
    category = serializers.CharField(
        max_length=60, required=False, allow_null=True, allow_blank=True
    )
    description = serializers.CharField(
        max_length=1000, required=False, allow_null=True, allow_blank=True
    )
    definition = serializers.DictField()
    match = serializers.DictField(default=dict)
    required_connections = serializers.ListField(child=serializers.CharField(), default=list)


class AuditQuerySerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField(required=False, allow_null=True)
    limit = serializers.IntegerField(min_value=1, max_value=500, default=100)


def _valid(serializer_class: type, data: Any) -> dict[str, Any]:
    body = serializer_class(data=data)
    body.is_valid(raise_exception=True)
    return dict(body.validated_data)


class AdminViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    @action(detail=False, methods=["get"])
    def metrics(self, request: Request) -> Response:
        return Response(services.metrics())

    @action(detail=False, methods=["get"])
    def workspaces(self, request: Request) -> Response:
        return Response(services.workspace_rows())

    @action(
        detail=False,
        methods=["post"],
        url_path=f"workspaces/(?P<workspace_id>{UUID_REGEX})/suspend",
    )
    def suspend(self, request: Request, workspace_id: str) -> Response:
        reason = _valid(SuspendSerializer, request.data)["reason"]
        paused = services.suspend(services.get_workspace(workspace_id), request.user, reason)
        return Response(message(f"Workspace suspended; {paused} automation(s) paused."))

    @action(
        detail=False,
        methods=["post"],
        url_path=f"workspaces/(?P<workspace_id>{UUID_REGEX})/reactivate",
    )
    def reactivate(self, request: Request, workspace_id: str) -> Response:
        services.reactivate(services.get_workspace(workspace_id), request.user)
        return Response(message("Workspace reactivated. The owner can switch automations back on."))

    @action(
        detail=False,
        methods=["patch"],
        url_path=f"workspaces/(?P<workspace_id>{UUID_REGEX})/limits",
    )
    def limits(self, request: Request, workspace_id: str) -> Response:
        limit = _valid(LimitsSerializer, request.data)["ai_credit_limit"]
        services.set_limits(services.get_workspace(workspace_id), request.user, limit)
        return Response(message("Limits updated."))

    @action(detail=False, methods=["get", "post"])
    def templates(self, request: Request) -> Response:
        if request.method == "GET":
            from intelliflow.automations.models import Template

            return Response(
                [services.template_out(t) for t in Template.objects.order_by("code", "-version")]
            )
        template = services.create_template(
            request.user, _valid(TemplateInSerializer, request.data)
        )
        return Response(services.template_out(template), status=status.HTTP_201_CREATED)

    @action(
        detail=False, methods=["post"], url_path=r"templates/(?P<code>[a-z][a-z0-9_]+)/versions"
    )
    def template_versions(self, request: Request, code: str) -> Response:
        template = services.new_template_version(
            request.user, code, _valid(TemplateInSerializer, request.data)
        )
        return Response(services.template_out(template), status=status.HTTP_201_CREATED)

    @action(
        detail=False, methods=["post"], url_path=f"templates/(?P<template_id>{UUID_REGEX})/publish"
    )
    def publish(self, request: Request, template_id: str) -> Response:
        template = services.publish_template(services.get_template(template_id), request.user)
        return Response(services.template_out(template))

    @action(
        detail=False, methods=["post"], url_path=f"templates/(?P<template_id>{UUID_REGEX})/retire"
    )
    def retire(self, request: Request, template_id: str) -> Response:
        template = services.retire_template(services.get_template(template_id), request.user)
        return Response(services.template_out(template))

    @action(detail=False, methods=["get"], url_path="audit-logs")
    def audit_logs(self, request: Request) -> Response:
        query = _valid(AuditQuerySerializer, request.query_params)
        return Response(services.audit_rows(query.get("workspace_id"), query["limit"]))
