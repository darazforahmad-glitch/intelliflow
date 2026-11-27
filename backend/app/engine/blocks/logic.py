"""Condition block: continue or stop based on a safe expression."""

from __future__ import annotations

from typing import Any

from app.engine.blocks.base import Block, BlockResult, BlockStatus, ExecutionServices, RunContext
from app.engine.errors import PermanentBlockError
from app.engine.expressions import ExpressionError


class ConditionBlock(Block):
    type = "condition"

    def describe_input(self, ctx: RunContext) -> dict[str, Any]:
        return {"if": self.spec["if"]}

    def execute(self, ctx: RunContext, services: ExecutionServices) -> BlockResult:
        try:
            result = bool(ctx.evaluate(self.spec["if"]))
        except ExpressionError as exc:
            raise PermanentBlockError(str(exc), code="bad_condition") from exc
        if result:
            return BlockResult(BlockStatus.SUCCEEDED, {"result": True})
        if self.spec.get("else", "stop") == "continue":
            return BlockResult(BlockStatus.SUCCEEDED, {"result": False})
        return BlockResult(
            BlockStatus.STOP,
            {"result": False},
            summary=f"Stopped at “{self.title}”: the condition was not met, so there was nothing to do.",
        )
