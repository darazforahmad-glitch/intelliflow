"""Metered access to the LLM: AI credit quota per workspace (BR-6, REQ-PA-3) and usage/cost
records for platform monitoring (REQ-PA-2)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import QuotaExceededError
from app.core.kv import get_kv
from app.llm import get_llm_client
from app.llm.anthropic_client import estimate_cost_usd
from app.llm.base import LLMClient, LLMError, LLMRequest, LLMResponse
from app.models import LLMUsage, Workspace
from app.models.enums import MembershipRole

logger = logging.getLogger(__name__)


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def credits_used(db: Session, workspace_id: object) -> int:
    used = db.scalar(
        select(func.coalesce(func.sum(LLMUsage.credits), 0)).where(
            LLMUsage.workspace_id == workspace_id, LLMUsage.created_at >= month_start()
        )
    )
    return int(used or 0)


class AIService:
    """One AI call = one credit. Credits reset on the first day of each month."""

    def __init__(self, db: Session, workspace: Workspace, client: LLMClient | None = None) -> None:
        self.db = db
        self.workspace = workspace
        self.client = client or get_llm_client()

    def ensure_credits(self) -> None:
        limit = self.workspace.ai_credit_limit
        if limit is None:
            return
        used = credits_used(self.db, self.workspace.id)
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
        from app.services.notification_service import notify, workspace_members

        owners = workspace_members(self.db, self.workspace.id, roles=[MembershipRole.OWNER])
        notify(
            self.db,
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
        self.db.add(
            LLMUsage(
                workspace_id=self.workspace.id,
                task=request.task.value,
                provider=response.provider if response else self.client.provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=(
                    estimate_cost_usd(model, input_tokens, output_tokens)
                    if response
                    else Decimal(0)
                ),
                credits=1 if succeeded else 0,
                succeeded=succeeded,
            )
        )
