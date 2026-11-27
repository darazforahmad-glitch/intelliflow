"""OpportunityAnalyzer: RANK_OPPORTUNITIES of Algorithm 5.2 (REQ-OA-1..6).

    score = weekly_minutes x fit x (1 - 0.5 x min(risk, 1))
    fit  in {1.0 exact, 0.6 partial, 0 none};  risk = 0.3 (messages customers) + 0.4 (money)
Candidates are sorted by score (descending) then risk (ascending); the top three are shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.heuristics import has_any, normalize, tokens
from app.models import Opportunity, ProcessMap, ProcessStep, Template
from app.models.enums import OpportunityStatus, StepType

FIT_EXACT = Decimal("1.0")
FIT_PARTIAL = Decimal("0.6")
RISK_CUSTOMER_MESSAGE = Decimal("0.3")
RISK_MONEY = Decimal("0.4")
TOP_N = 3
DAYS_PER_WEEK = 7


@dataclass(frozen=True, slots=True)
class TemplateMatch:
    template: Template | None
    fit: Decimal
    keyword_hits: int


def match_template(step: ProcessStep, templates: list[Template]) -> TemplateMatch:
    """`best matching template(step)`: keywords decide whether it matches, the app decides how well."""
    text = normalize(f"{step.title} {step.action or ''}")
    words = tokens(text)
    best = TemplateMatch(None, Decimal(0), 0)
    for template in templates:
        rules = template.match_json or {}
        hits = 0
        for raw_keyword in rules.get("keywords", []):
            keyword = raw_keyword.lower()
            if (" " in keyword and keyword in text) or has_any(words, {keyword}):
                hits += 1
        if hits == 0:
            continue
        fit = FIT_EXACT if (step.app or "other") in rules.get("apps", []) else FIT_PARTIAL
        if (fit, hits) > (best.fit, best.keyword_hits):
            best = TemplateMatch(template, fit, hits)
    return best


def step_risk(step: ProcessStep) -> Decimal:
    risk = Decimal(0)
    if step.involves_customer_messaging:
        risk += RISK_CUSTOMER_MESSAGE
    if step.involves_money:
        risk += RISK_MONEY
    return risk


def compute_score(weekly_minutes: Decimal, fit: Decimal, risk: Decimal) -> Decimal:
    score = weekly_minutes * fit * (Decimal(1) - Decimal("0.5") * min(risk, Decimal(1)))
    return score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _fmt_minutes(value: Decimal) -> str:
    return f"{value.normalize():f}".rstrip(".") if value % 1 else f"{int(value)}"


def explain(
    step: ProcessStep, match: TemplateMatch, saved_per_week: Decimal, threshold: Decimal
) -> str:
    """REQ-OA-5: one sentence on why it was ranked."""
    minutes = step.minutes_per_run or Decimal(0)
    hours = (saved_per_week / 60).quantize(Decimal("0.1"))
    parts = [
        f"Repeats about {step.runs_per_week} times a week and takes about {_fmt_minutes(minutes)} min each time "
        f"(≈{hours} h a week)"
    ]
    if match.fit < FIT_EXACT and match.template is not None:
        parts.append(f"the “{match.template.name}” template covers most of it")
    if step.involves_customer_messaging:
        parts.append("messages to customers wait for your approval")
    if step.involves_money:
        parts.append(f"amounts above Rs {threshold:,.0f} wait for your approval")
    return "; ".join(parts) + "."


class OpportunityAnalyzer:
    def __init__(self, db: Session) -> None:
        self.db = db

    def active_templates(self) -> list[Template]:
        return list(
            self.db.scalars(
                select(Template).where(Template.is_active.is_(True)).order_by(Template.code)
            )
        )

    def analyze(self, process_map: ProcessMap, approval_threshold: Decimal) -> list[Opportunity]:
        """Create scored opportunities for a (new) map version and rank them."""
        templates = self.active_templates()
        created: list[Opportunity] = []
        for step in process_map.steps:
            if step.step_type != StepType.MANUAL:  # only manual steps are candidates
                step.support_status = None
                continue
            match = match_template(step, templates)
            if match.fit == 0 or match.template is None:
                step.support_status = "not_yet_supported"
                continue
            step.support_status = "supported"
            risk = step_risk(step)
            weekly = step.weekly_minutes
            saved = (weekly * match.fit).quantize(Decimal("0.1"))
            opportunity = Opportunity(
                map_id=process_map.id,
                step_id=step.id,
                template_id=match.template.id,
                score=compute_score(weekly, match.fit, risk),
                fit=match.fit,
                risk=risk,
                minutes_saved_per_week=saved,
                reason=explain(step, match, saved, approval_threshold),
                status=OpportunityStatus.SUGGESTED,
            )
            self.db.add(opportunity)
            created.append(opportunity)
        self.db.flush()
        self.rerank(process_map)
        return created

    def rerank(self, process_map: ProcessMap) -> list[Opportunity]:
        """Ranks every non-dismissed opportunity: score desc, then risk asc (REQ-OA-6 recalculation)."""
        opportunities = list(
            self.db.scalars(select(Opportunity).where(Opportunity.map_id == process_map.id))
        )
        ranked = sorted(
            (o for o in opportunities if o.status != OpportunityStatus.DISMISSED),
            key=lambda o: (-o.score, o.risk, str(o.id)),
        )
        for position, opportunity in enumerate(ranked, start=1):
            opportunity.rank = position
        for opportunity in opportunities:
            if opportunity.status == OpportunityStatus.DISMISSED:
                opportunity.rank = None
        self.db.flush()
        return ranked

    def dismiss(self, opportunity: Opportunity) -> list[Opportunity]:
        opportunity.status = OpportunityStatus.DISMISSED
        self.db.flush()
        return self.rerank(opportunity.process_map)

    def restore(self, opportunity: Opportunity) -> list[Opportunity]:
        if opportunity.status == OpportunityStatus.DISMISSED:
            opportunity.status = OpportunityStatus.SUGGESTED
        self.db.flush()
        return self.rerank(opportunity.process_map)


def per_day(minutes_per_week: Decimal) -> Decimal:
    return (minutes_per_week / DAYS_PER_WEEK).quantize(Decimal("0.1"))
