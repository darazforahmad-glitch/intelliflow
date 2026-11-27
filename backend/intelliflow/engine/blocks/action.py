"""Action block: performs one operation in a connected app through the Connector interface."""

from __future__ import annotations

from typing import Any

from intelliflow.integrations.connectors.registry import operation_spec
from intelliflow.engine.blocks.base import (
    Block,
    BlockResult,
    BlockStatus,
    ExecutionServices,
    RunContext,
)
from intelliflow.engine.errors import PermanentBlockError


class ActionBlock(Block):
    type = "action"

    def describe_input(self, ctx: RunContext) -> dict[str, Any]:
        return {
            "connector": self.spec["connector"],
            "operation": self.spec["operation"],
            "params": ctx.render_value(self.spec.get("params") or {}),
        }

    def execute(self, ctx: RunContext, services: ExecutionServices) -> BlockResult:
        spec = operation_spec(self.spec["connector"], self.spec["operation"])
        if spec is not None and spec.customer_message:
            # Defence in depth for SAF-1; the validator already rejects such definitions.
            raise PermanentBlockError(
                "Messages to customers must go through an approval step first.",
                code="unguarded_customer_message",
            )
        params = ctx.render_value(self.spec.get("params") or {})
        result = services.connectors.execute(self.spec["connector"], self.spec["operation"], params)
        return BlockResult(BlockStatus.SUCCEEDED, result)
