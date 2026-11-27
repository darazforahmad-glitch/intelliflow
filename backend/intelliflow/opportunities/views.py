"""/workspaces/<id>/opportunities: dismiss, restore and automate (REQ-OA-6, UC-05, UC-07)."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from intelliflow.automations.builder import AutomationBuilder
from intelliflow.automations.serializers import automation_out
from intelliflow.core.api.viewsets import WorkspaceScopedViewSet
from intelliflow.core.errors import NotFoundError
from intelliflow.flowmapper.serializers import map_out
from intelliflow.opportunities.analyzer import OpportunityAnalyzer
from intelliflow.opportunities.models import Opportunity


class OpportunityViewSet(WorkspaceScopedViewSet):
    owner_actions = {"dismiss", "restore", "automation"}

    def _opportunity(self, pk: str) -> Opportunity:
        opportunity = (
            Opportunity.objects.select_related("process_map", "step", "template")
            .filter(pk=pk, process_map__workspace=self.ctx.workspace)
            .first()
        )
        if opportunity is None:
            raise NotFoundError("Opportunity not found.")
        return opportunity

    @action(detail=True, methods=["post"])
    def dismiss(self, request: Request, workspace_id: str, pk: str) -> Response:
        opportunity = self._opportunity(pk)
        OpportunityAnalyzer().dismiss(opportunity)
        return Response(map_out(opportunity.process_map))

    @action(detail=True, methods=["post"])
    def restore(self, request: Request, workspace_id: str, pk: str) -> Response:
        opportunity = self._opportunity(pk)
        OpportunityAnalyzer().restore(opportunity)
        return Response(map_out(opportunity.process_map))

    @action(detail=True, methods=["post"])
    def automation(self, request: Request, workspace_id: str, pk: str) -> Response:
        """generateAutomation(opportunityId) - Algorithm 5.3."""
        builder = AutomationBuilder(self.ctx.workspace, self.ctx.user)
        automation = builder.generate_from_opportunity(self._opportunity(pk))
        return Response(automation_out(automation), status=status.HTTP_201_CREATED)
