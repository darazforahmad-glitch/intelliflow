"""Ops Dashboard (UC-12), CSV report (REQ-DR-5) and live updates over Server-Sent Events (REQ-DR-6)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from intelliflow.accounts.tokens import user_from_token
from intelliflow.core.api.permissions import IsWorkspaceMember, workspace_context
from intelliflow.core.errors import AppError, ValidationFailedError
from intelliflow.core.logging import request_id_var
from intelliflow.dashboard.reporting import dashboard, weekly_csv
from intelliflow.notifications import event_bus


class PeriodSerializer(serializers.Serializer):
    days = serializers.IntegerField(min_value=1, max_value=90, default=7)


def _days(request: Request) -> int:
    query = PeriodSerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    return int(query.validated_data["days"])


class DashboardView(APIView):
    permission_classes = [IsWorkspaceMember]

    def get(self, request: Request, workspace_id: str) -> Response:
        return Response(dashboard(self.ctx.workspace, _days(request)))  # type: ignore[attr-defined]


class WeeklyReportView(APIView):
    permission_classes = [IsWorkspaceMember]

    def get(self, request: Request, workspace_id: str) -> HttpResponse:
        days = _days(request)
        body = weekly_csv(self.ctx.workspace, days)  # type: ignore[attr-defined]
        response = HttpResponse(body, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="intelliflow-report-{days}d.csv"'
        return response


def _stream(workspace_id: str) -> Iterator[str]:
    yield "retry: 5000\n\n"
    for event in event_bus.subscribe(workspace_id):
        yield ": keep-alive\n\n" if event == "" else f"data: {event}\n\n"


def stream_events(request: HttpRequest, workspace_id: str) -> HttpResponse:
    """GET /workspaces/<id>/events?access_token=...

    EventSource cannot send headers, so the access token comes as a query parameter
    (query strings are never written to our logs). One thread serves each open stream."""
    try:
        token = request.GET.get("access_token", "")
        if len(token) < 10:
            raise ValidationFailedError(
                "Some fields need attention.",
                details=[{"field": "access_token", "message": "This field is required."}],
            )
        workspace_context(user_from_token(token), workspace_id)
    except AppError as exc:
        import json

        return HttpResponse(
            json.dumps(exc.to_dict(request_id_var.get())),
            status=exc.status_code,
            content_type="application/json",
        )
    response = StreamingHttpResponse(_stream(workspace_id), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


__all__: list[Any] = ["DashboardView", "WeeklyReportView", "stream_events"]
