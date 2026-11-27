"""/workspaces/<id>/automations: AI Automation Builder and lifecycle (UC-07, UC-09)."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from intelliflow.automations import serializers as s
from intelliflow.automations.builder import AutomationBuilder
from intelliflow.automations.models import Automation, AutomationVersion
from intelliflow.core.api.viewsets import WorkspaceScopedViewSet
from intelliflow.core.enums import AutomationStatus
from intelliflow.core.errors import NotFoundError
from intelliflow.runs.serializers import run_out


class AutomationViewSet(WorkspaceScopedViewSet):
    # Members can look and validate; building, testing and switching on/off is the owner's (BR-1).
    owner_actions = {
        "from_template",
        "definition",
        "repair",
        "test",
        "activate",
        "pause",
        "archive",
        "rollback",
        "auto_send",
    }

    def _automation(self, pk: str) -> Automation:
        automation = Automation.objects.filter(pk=pk, workspace=self.ctx.workspace).first()
        if automation is None:
            raise NotFoundError("Automation not found.")
        return automation

    def _builder(self) -> AutomationBuilder:
        return AutomationBuilder(self.ctx.workspace, self.ctx.user)

    def _body(self, serializer_class: type, request: Request) -> dict:  # type: ignore[type-arg]
        body = serializer_class(data=request.data)
        body.is_valid(raise_exception=True)
        return dict(body.validated_data)

    def list(self, request: Request, workspace_id: str) -> Response:
        query = s.AutomationQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        automations = Automation.objects.select_related("template", "current_version").filter(
            workspace=self.ctx.workspace
        )
        if not query.validated_data["include_archived"]:
            automations = automations.exclude(status=AutomationStatus.ARCHIVED)
        return Response(s.automation_list(automations.order_by("-created_at")))

    def retrieve(self, request: Request, workspace_id: str, pk: str) -> Response:
        return Response(s.automation_out(self._automation(pk)))

    @action(detail=False, methods=["post"], url_path="from-template")
    def from_template(self, request: Request, workspace_id: str) -> Response:
        code = self._body(s.FromTemplateSerializer, request)["template_code"]
        automation = self._builder().generate_from_template(code)
        return Response(s.automation_out(automation), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path=r"versions/(?P<version_no>[0-9]+)")
    def version(self, request: Request, workspace_id: str, pk: str, version_no: str) -> Response:
        automation = self._automation(pk)
        version = AutomationVersion.objects.filter(
            automation=automation, version_no=int(version_no)
        ).first()
        if version is None:
            raise NotFoundError("Version not found.")
        return Response(s.version_out(version))

    @action(detail=True, methods=["put"])
    def definition(self, request: Request, workspace_id: str, pk: str) -> Response:
        automation = self._automation(pk)
        definition = self._body(s.DefinitionSerializer, request)["definition"]
        self._builder().save_definition(automation, definition)
        return Response(s.automation_out(automation))

    @action(detail=True, methods=["post"])
    def validate(self, request: Request, workspace_id: str, pk: str) -> Response:
        self._automation(pk)
        definition = self._body(s.DefinitionSerializer, request)["definition"]
        issues = self._builder().validate(definition, check_connections=True)
        return Response({"valid": not issues, "issues": [i.to_dict() for i in issues]})

    @action(detail=True, methods=["post"])
    def repair(self, request: Request, workspace_id: str, pk: str) -> Response:
        automation = self._automation(pk)
        self._builder().repair(automation)
        return Response(s.automation_out(automation))

    @action(detail=True, methods=["post"])
    def test(self, request: Request, workspace_id: str, pk: str) -> Response:
        automation = self._automation(pk)
        sample = self._body(s.TestSerializer, request)["sample"]
        result = self._builder().test(automation, sample)
        return Response(
            {
                "passed": result.passed,
                "message": result.message,
                "run": run_out(result.run),
                "steps": [
                    {
                        k: step[k]
                        for k in ("key", "type", "title", "status", "input", "output", "attempts")
                    }
                    for step in result.trace
                ],
                "sandbox_records": result.sandbox_records,
            }
        )

    @action(detail=True, methods=["post"])
    def activate(self, request: Request, workspace_id: str, pk: str) -> Response:
        return Response(s.automation_out(self._builder().activate(self._automation(pk))))

    @action(detail=True, methods=["post"])
    def pause(self, request: Request, workspace_id: str, pk: str) -> Response:
        return Response(s.automation_out(self._builder().pause(self._automation(pk))))

    @action(detail=True, methods=["post"])
    def archive(self, request: Request, workspace_id: str, pk: str) -> Response:
        return Response(s.automation_out(self._builder().archive(self._automation(pk))))

    @action(detail=True, methods=["post"])
    def rollback(self, request: Request, workspace_id: str, pk: str) -> Response:
        automation = self._automation(pk)
        version_no = self._body(s.RollbackSerializer, request)["version_no"]
        self._builder().rollback(automation, version_no)
        return Response(s.automation_out(automation))

    @action(detail=True, methods=["post"], url_path="auto-send")
    def auto_send(self, request: Request, workspace_id: str, pk: str) -> Response:
        automation = self._automation(pk)
        enabled = self._body(s.AutoSendSerializer, request)["enabled"]
        return Response(s.automation_out(self._builder().set_auto_send(automation, enabled)))
