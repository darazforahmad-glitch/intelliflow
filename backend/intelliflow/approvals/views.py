"""/workspaces/<id>/approvals: the approvals queue and decisions (UC-11, BR-2, BR-9)."""

from __future__ import annotations

from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from intelliflow.approvals import services
from intelliflow.approvals.models import ApprovalTask
from intelliflow.approvals.serializers import (
    ApprovalQuerySerializer,
    DecisionSerializer,
    approval_out,
)
from intelliflow.core.enums import ApprovalStatus
from intelliflow.core.errors import NotFoundError
from intelliflow.core.api.viewsets import WorkspaceScopedViewSet

OPEN_STATES = [ApprovalStatus.PENDING, ApprovalStatus.REMINDED]


class ApprovalViewSet(WorkspaceScopedViewSet):
    """Staff and owners may both decide (BR-2)."""

    def _queryset(self):  # type: ignore[no-untyped-def]
        return ApprovalTask.objects.select_related("automation", "decided_by").filter(
            workspace=self.ctx.workspace
        )

    def _task(self, pk: str) -> ApprovalTask:
        task = self._queryset().filter(pk=pk).first()
        if task is None:
            raise NotFoundError("Approval not found.")
        return task

    def list(self, request: Request, workspace_id: str) -> Response:
        query = ApprovalQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        state, limit = query.validated_data["state"], query.validated_data["limit"]
        tasks = self._queryset()
        if state == "open":
            tasks = tasks.filter(status__in=OPEN_STATES).order_by("created_at")
        elif state == "decided":
            tasks = tasks.exclude(status__in=OPEN_STATES).order_by("-decided_at")
        else:
            tasks = tasks.order_by("-created_at")
        return Response([approval_out(t) for t in tasks[:limit]])

    def retrieve(self, request: Request, workspace_id: str, pk: str) -> Response:
        return Response(approval_out(self._task(pk)))

    @action(detail=True, methods=["post"])
    def decision(self, request: Request, workspace_id: str, pk: str) -> Response:
        """decideApproval(taskId, decision, editedPayload)."""
        body = DecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        services.decide(
            self._task(pk),
            self.ctx.user,
            data["decision"],
            edited_params=data.get("edited_params"),
            edited_fields=data.get("edited_fields"),
            note=data.get("note"),
        )
        return Response(approval_out(self._task(pk)))
