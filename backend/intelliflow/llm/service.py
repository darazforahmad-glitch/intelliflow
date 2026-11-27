"""Metered access to the LLM: AI credit quota per workspace (BR-6, REQ-PA-3) and usage/cost
records for platform monitoring (REQ-PA-2)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce

from intelliflow.audit.models import LLMUsage
from intelliflow.core.enums import MembershipRole
from intelliflow.core.errors import QuotaExceededError
from intelliflow.core.kv import get_kv
from intelliflow.llm import get_llm_client
from intelliflow.llm.anthropic_client import estimate_cost_usd
from intelliflow.llm.base import LLMClient, LLMError, LLMRequest, LLMResponse
from intelliflow.workspaces.models import Workspace

logger = logging.getLogger(__name__)


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def credits_used(workspace_id: object) -> int:
    used = LLMUsage.objects.filter(
        workspace_id=workspace_id, created_at__gte=month_start()
    ).aggregate(total=Coalesce(Sum("credits"), 0))["total"]
    return int(used or 0)


class AIService:
    """One AI call = one credit. Credits reset on the first day of each month."""

    def __init__(self, workspace: Workspace, client: LLMClient | None = None) -> None:
        self.workspace = workspace
        self.client = client or get_llm_client()

    def ensure_credits(self) -> None:
        limit = self.workspace.ai_credit_limit
        if limit is None:
            return
        used = credits_used(self.workspace.id)
        if used >= limit:
            raise QuotaExceededError(
                "This workspace has used all of its AI credits for this month, so AI steps are paused.",
                code="ai_credits_exhausted",
                hint="Ask IntelliFlow support to raise the limit, or wait until next month.",
            )
        if used >= 0.8 * limit:
            self._warn_once(used, limit)

    def _warn_once(self, used: int, limit: int) -> None:
        key = f"ai-credit-warning:{self.workspace.id}:{month_start():%Y-%m}"
        if not get_kv().set_if_absent(key, "1", ttl_seconds=40 * 24 * 3600):
            return
        from intelliflow.notifications.services import notify, workspace_members

        owners = workspace_members(self.workspace.id, roles=[MembershipRole.OWNER])
        notify(
            owners,
            workspace_id=self.workspace.id,
            kind="ai_credits.warning",
            title="AI credits are running low",
            body=f"Your workspace has used {used} of {limit} AI credits this month (80%). AI steps pause at 100%.",
            url="/settings",
        )

    def run(self, request: LLMRequest) -> LLMResponse:
        self.ensure_credits()
        try:
            response = self.client.generate(request)
        except LLMError:
            self._record(request, None, succeeded=False)
            raise
        self._record(request, response, succeeded=True)
        return response

    def _record(
        self, request: LLMRequest, response: LLMResponse | None, *, succeeded: bool
    ) -> None:
        model = response.model if response else getattr(self.client, "model", "unknown")
        input_tokens = response.input_tokens if response else 0
        output_tokens = response.output_tokens if response else 0
        LLMUsage.objects.create(
            workspace_id=self.workspace.id,
            task=request.task.value,
            provider=response.provider if response else self.client.provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=(
                estimate_cost_usd(model, input_tokens, output_tokens) if response else Decimal(0)
            ),
            credits=1 if succeeded else 0,
            succeeded=succeeded,
        )
