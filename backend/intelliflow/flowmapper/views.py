"""Flow Mapper API: the interview chat (UC-03) and versioned process maps (REQ-FM-6/7)."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from intelliflow.audit import services as audit_service
from intelliflow.core.api.permissions import WorkspaceContext
from intelliflow.core.api.viewsets import WorkspaceScopedViewSet
from intelliflow.core.errors import NotFoundError
from intelliflow.flowmapper import serializers as s
from intelliflow.flowmapper.interview_agent import InterviewAgent
from intelliflow.flowmapper.models import InterviewSession, ProcessMap
from intelliflow.flowmapper.process_mapper import ProcessMapper
from intelliflow.llm.service import AIService
from intelliflow.opportunities.analyzer import OpportunityAnalyzer


class InterviewViewSet(WorkspaceScopedViewSet):
    owner_actions = {"create", "messages", "complete", "abandon"}

    def _session(self, pk: str) -> InterviewSession:
        session = InterviewSession.objects.filter(pk=pk, workspace=self.ctx.workspace).first()
        if session is None:
            raise NotFoundError("Interview not found.")
        return session

    def _agent(self) -> InterviewAgent:
        return InterviewAgent(self.ctx.workspace, AIService(self.ctx.workspace))

    def list(self, request: Request, workspace_id: str) -> Response:
        return Response(s.interview_summaries(self.ctx.workspace_id))

    def create(self, request: Request, workspace_id: str) -> Response:
        body = s.InterviewCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        session = self._agent().start(self.ctx.user, body.validated_data["process_name"])
        return Response(s.interview_out(session), status=status.HTTP_201_CREATED)

    def retrieve(self, request: Request, workspace_id: str, pk: str) -> Response:
        return Response(s.interview_out(self._session(pk)))

    @action(detail=True, methods=["post"])
    def messages(self, request: Request, workspace_id: str, pk: str) -> Response:
        body = s.AnswerSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        session = self._agent().answer(self._session(pk), body.validated_data["content"])
        return Response(s.interview_out(session))

    @action(detail=True, methods=["post"])
    def complete(self, request: Request, workspace_id: str, pk: str) -> Response:
        """buildProcessMap(sessionId): map + validated steps + ranked opportunities (Table 4.16)."""
        threshold = self.ctx.workspace.approval_threshold
        process_map = ProcessMapper(AIService(self.ctx.workspace)).build(
            self._session(pk),
            self.ctx.user,
            on_stored=lambda pm: OpportunityAnalyzer().analyze(pm, threshold),
        )
        return Response(s.map_out(process_map), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def abandon(self, request: Request, workspace_id: str, pk: str) -> Response:
        return Response(s.interview_out(self._agent().abandon(self._session(pk))))


def get_map(ctx: WorkspaceContext, pk: Any) -> ProcessMap:
    process_map = ProcessMap.objects.filter(pk=pk, workspace=ctx.workspace).first()
    if process_map is None:
        raise NotFoundError("Process map not found.")
    return process_map


class ProcessMapViewSet(WorkspaceScopedViewSet):
    owner_actions = {"versions"}

    def list(self, request: Request, workspace_id: str) -> Response:
        return Response(s.map_summaries(self.ctx.workspace_id))

    def retrieve(self, request: Request, workspace_id: str, pk: str) -> Response:
        return Response(s.map_out(get_map(self.ctx, pk)))

    @action(detail=True, methods=["post"])
    def versions(self, request: Request, workspace_id: str, pk: str) -> Response:
        """REQ-FM-6/7: the owner's edited map becomes a new version, re-analysed."""
        body = s.MapVersionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        base = get_map(self.ctx, pk)
        with transaction.atomic():
            new_map = ProcessMapper(AIService(self.ctx.workspace)).save_edited_version(
                base,
                [dict(step) for step in data["steps"]],
                self.ctx.user,
                name=data.get("name"),
                note=data.get("note"),
                positions={k: dict(v) for k, v in (data.get("positions") or {}).items()},
            )
            OpportunityAnalyzer().analyze(new_map, self.ctx.workspace.approval_threshold)
            audit_service.record(
                "process_map.version_saved",
                workspace_id=self.ctx.workspace_id,
                actor_id=self.ctx.user.id,
                entity_type="process_map",
                entity_id=new_map.id,
                data={"version": new_map.version},
            )
        return Response(s.map_out(new_map), status=status.HTTP_201_CREATED)
