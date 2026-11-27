"""AI blocks: classify, extract, draft a reply, summarise. Output is schema-checked before use."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from app.core.errors import QuotaExceededError
from app.engine.blocks.base import (
    ApprovalRequest,
    Block,
    BlockResult,
    BlockStatus,
    ExecutionServices,
    RunContext,
)
from app.engine.errors import PermanentBlockError, TransientBlockError
from app.llm import output_schemas, prompts
from app.llm.base import LLMOutputError, LLMRefusalError, LLMRequest, LLMUnavailableError
from app.llm.heuristics import detect_language
from app.models.enums import ApprovalKind

LOW_CONFIDENCE = 0.6


def call_ai(services: ExecutionServices, request: LLMRequest) -> dict[str, Any]:
    try:
        data = services.ai.run(request).data
    except QuotaExceededError as exc:  # BR-6: AI steps pause when the quota is used up
        raise PermanentBlockError(exc.message, code="ai_credits_exhausted") from exc
    except LLMUnavailableError as exc:
        raise TransientBlockError("The AI service is busy right now. Will retry.") from exc
    except LLMRefusalError as exc:
        raise PermanentBlockError(
            "The AI declined to process this message.", code="ai_refused"
        ) from exc
    except LLMOutputError as exc:
        raise PermanentBlockError(
            "The AI returned an answer that could not be used.", code="ai_bad_output"
        ) from exc
    if any(True for _ in Draft202012Validator(request.schema).iter_errors(data)):
        raise PermanentBlockError(
            "The AI returned an answer in the wrong format.", code="ai_bad_output"
        )
    return data


class AIClassifyBlock(Block):
    type = "ai.classify"

    def describe_input(self, ctx: RunContext) -> dict[str, Any]:
        return {"input": ctx.render(self.spec["input"]), "labels": self.spec["labels"]}

    def execute(self, ctx: RunContext, services: ExecutionServices) -> BlockResult:
        text = ctx.render(self.spec["input"])
        data = call_ai(
            services,
            prompts.classify(
                text=text,
                labels=list(self.spec["labels"]),
                instructions=self.spec.get("instructions"),
            ),
        )
        return BlockResult(
            BlockStatus.SUCCEEDED,
            {"label": data["label"], "confidence": data["confidence"], "reason": data["reason"]},
        )


class AIExtractBlock(Block):
    type = "ai.extract"

    def describe_input(self, ctx: RunContext) -> dict[str, Any]:
        return {
            "input": ctx.render(self.spec["input"]),
            "fields": [f["name"] for f in self.spec["fields"]],
        }

    def execute(self, ctx: RunContext, services: ExecutionServices) -> BlockResult:
        fields: list[dict[str, Any]] = self.spec["fields"]
        decision = services.decision
        if decision is not None:  # the owner reviewed what the AI could not read
            if decision.status in {"rejected", "expired"}:
                return BlockResult(BlockStatus.REJECTED, {"decision": decision.status})
            reviewed = {**(decision.payload.get("ai_output") or {}), **(decision.fields or {})}
            return BlockResult(
                BlockStatus.SUCCEEDED,
                {
                    **{f["name"]: reviewed.get(f["name"]) for f in fields},
                    "_missing": [],
                    "_confidence": 1.0,
                    "_reviewed": True,
                },
            )
        text = ctx.render(self.spec["input"])
        sender = ctx.resolve("trigger.name")
        try:
            data = call_ai(
                services,
                prompts.extract(
                    text=text,
                    fields=fields,
                    instructions=self.spec.get("instructions"),
                    sender_name=str(sender) if sender else None,
                ),
            )
            values = {f["name"]: data["fields"].get(f["name"]) for f in fields}
            confidence = float(data.get("confidence", 0))
        except PermanentBlockError as exc:
            if exc.code not in {"ai_bad_output", "ai_refused"}:
                raise
            values, confidence = {f["name"]: None for f in fields}, 0.0
        missing = [
            f["name"] for f in fields if f.get("required") and values.get(f["name"]) in (None, "")
        ]
        if missing or confidence < LOW_CONFIDENCE:
            # SAF-6: incomplete or uncertain extraction goes to a person, never acts automatically.
            return BlockResult(
                BlockStatus.NEEDS_APPROVAL,
                approval=ApprovalRequest(
                    kind=ApprovalKind.REVIEW,
                    title=f"Check the details: {self.title}",
                    payload={
                        "message": "The AI could not read every detail with confidence. Please check them and fill in what is missing.",
                        "input": text,
                        "ai_output": values,
                        "missing": missing,
                        "confidence": confidence,
                        "fields": fields,
                        "editable": [f["name"] for f in fields],
                    },
                ),
                summary="Waiting for a person to check the extracted details.",
            )
        return BlockResult(
            BlockStatus.SUCCEEDED, {**values, "_missing": [], "_confidence": confidence}
        )


class AIDraftReplyBlock(Block):
    type = "ai.draft_reply"

    def describe_input(self, ctx: RunContext) -> dict[str, Any]:
        return {
            "facts": ctx.render_value(self.spec.get("facts") or {}),
            "instructions": self.spec["instructions"],
        }

    def _language(self, ctx: RunContext, services: ExecutionServices) -> str:
        language = self.spec.get("language") or "auto"
        if language != "auto":
            return str(language)
        source = ctx.render(self.spec.get("input")) or str(ctx.resolve("trigger.text") or "")
        if source.strip():
            return detect_language(source)
        settings = (
            (services.automation.current_version.definition_json.get("settings") or {})
            if services.automation.current_version
            else {}
        )
        return str(settings.get("language") or services.workspace.language_pref or "en")

    def execute(self, ctx: RunContext, services: ExecutionServices) -> BlockResult:
        language = self._language(ctx, services)
        facts = ctx.render_value(self.spec.get("facts") or {})
        input_text = ctx.render(self.spec.get("input")) or None
        data = call_ai(
            services,
            prompts.draft_reply(
                language=language,
                instructions=self.spec["instructions"],
                facts=facts,
                input_text=input_text,
            ),
        )
        return BlockResult(
            BlockStatus.SUCCEEDED, {"text": data["text"], "language": data["language"]}
        )


class AISummarizeBlock(Block):
    type = "ai.summarize"

    def describe_input(self, ctx: RunContext) -> dict[str, Any]:
        return {"input": ctx.render(self.spec["input"])[:500]}

    def execute(self, ctx: RunContext, services: ExecutionServices) -> BlockResult:
        data = call_ai(
            services,
            prompts.summarize(
                input_text=ctx.render(self.spec["input"]),
                instructions=self.spec["instructions"],
                language=services.workspace.language_pref,
            ),
        )
        return BlockResult(BlockStatus.SUCCEEDED, {"text": data["text"]})


_ = output_schemas  # schemas are referenced through the prompt builders
