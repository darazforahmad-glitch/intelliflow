"""/workspaces/<id>/runs: run history with drill-down (REQ-DR-4)."""

from __future__ import annotations

from rest_framework.request import Request
from rest_framework.response import Response

from intelliflow.core.errors import NotFoundError
from intelliflow.core.api.viewsets import WorkspaceScopedViewSet
from intelliflow.runs.models import Run
from intelliflow.runs.serializers import RunQuerySerializer, run_detail_out, run_out


class RunViewSet(WorkspaceScopedViewSet):
    def list(self, request: Request, workspace_id: str) -> Response:
        query = RunQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        q = query.validated_data
        runs = Run.objects.select_related("automation", "version").filter(
            workspace=self.ctx.workspace
        )
        if q.get("status"):
            runs = runs.filter(status=q["status"])
        if q.get("automation_id"):
            runs = runs.filter(automation_id=q["automation_id"])
        if not q["include_tests"]:
            runs = runs.filter(is_test=False)
        page = runs.order_by("-created_at")[q["offset"] : q["offset"] + q["limit"]]
        return Response([run_out(r) for r in page])

    def retrieve(self, request: Request, workspace_id: str, pk: str) -> Response:
        run = (
            Run.objects.select_related("automation", "version")
            .filter(pk=pk, workspace=self.ctx.workspace)
            .first()
        )
        if run is None:
            raise NotFoundError("Run not found.")
        return Response(run_detail_out(run))
