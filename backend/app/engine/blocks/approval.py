"""Approval block: pauses the run for a person (REQ-AP-1..4) and then performs the approved action."""

from __future__ import annotations

from typing import Any

from app.engine.blocks.base import (
    ApprovalRequest,
    Block,
    BlockResult,
    BlockStatus,
    ExecutionServices,
    RunContext,
)
from app.engine.errors import PermanentBlockError, WindowClosedError
from app.engine.expressions import ExpressionError
from app.models.enums import ApprovalKind


class ApprovalBlock(Block):
    type = "approval"

    def describe_input(self, ctx: RunContext) -> dict[str, Any]:
        return {"kind": self.spec["kind"], "when": self.spec.get("when")}

    def _proposed(self, ctx: RunContext) -> dict[str, Any] | None:
        action = self.spec.get("proposed_action")
        if not action:
            return None
        return {
            "connector": action["connector"],
            "operation": action["operation"],
            "params": ctx.render_value(action.get("params") or {}),
        }

    def _perform(
        self,
        services: ExecutionServices,
        action: dict[str, Any] | None,
        params: dict[str, Any] | None,
        decision: str,
    ) -> BlockResult:
        if action is None:
            return BlockResult(BlockStatus.SUCCEEDED, {"decision": decision, "approved": True})
        final = params if params is not None else action["params"]
        try:
            result = services.connectors.execute(action["connector"], action["operation"], final)
        except WindowClosedError as exc:
            # REQ-WE-8: outside the 24-hour window, offer the approved follow-up template instead.
            template = (services.workspace.settings_json or {}).get(
                "whatsapp_followup_template", "order_update"
            )
            fallback = {
                "connector": "whatsapp",
                "operation": "send_template",
                "params": {
                    "to": exc.to,
                    "template": template,
                    "language": "en",
                    "variables": [(exc.text or "")[:900]],
                },
            }
            return BlockResult(
                BlockStatus.NEEDS_APPROVAL,
                approval=ApprovalRequest(
                    ApprovalKind.WINDOW_CLOSED,
                    "Customer window closed: send a template instead?",
                    {
                        "message": exc.message
                        + f" Approve to send the approved template “{template}” instead.",
                        "proposed_action": fallback,
                        "editable": [],
                    },
                ),
                summary="WhatsApp window closed; waiting for approval to send a template.",
            )
        return BlockResult(
            BlockStatus.SUCCEEDED,
            {"decision": decision, "approved": True, "params": final, "result": result},
        )

    def execute(self, ctx: RunContext, services: ExecutionServices) -> BlockResult:
        decision = services.decision
        if decision is not None:  # resumed after a person decided (decideApproval, Table 4.16)
            if decision.status in {"rejected", "expired"}:
                return BlockResult(
                    BlockStatus.REJECTED, {"decision": decision.status, "note": decision.note}
                )
            return self._perform(
                services, decision.proposed_action, decision.params, decision.status
            )

        when = self.spec.get("when")
        if when:
            try:
                needed = bool(ctx.evaluate(when))
            except ExpressionError as exc:
                raise PermanentBlockError(str(exc), code="bad_condition") from exc
            if not needed:
                return BlockResult(BlockStatus.SKIPPED, {"required": False})

        kind = ApprovalKind(self.spec["kind"])
        proposed = self._proposed(ctx)
        if services.sandbox:  # test runs approve automatically and never reach customers (SAF-5)
            return self._perform(services, proposed, None, "approved_in_test")
        if kind == ApprovalKind.CUSTOMER_MESSAGE and services.automation.auto_send:
            return self._perform(services, proposed, None, "auto_sent")  # SAF-1 earned auto-send

        shown = {path: ctx.resolve(path) for path in self.spec.get("show", [])}
        payload = {
            "message": ctx.render(self.spec.get("message")) or None,
            "input": ctx.resolve("trigger.text") or ctx.resolve("trigger.body"),
            "show": shown,
            "ai_output": {k: v for k, v in shown.items() if k != "trigger.text"},
            "proposed_action": proposed,
            "editable": list(self.spec.get("editable", [])),
        }
        return BlockResult(
            BlockStatus.NEEDS_APPROVAL,
            approval=ApprovalRequest(kind, self.title, payload),
            summary=f"Waiting for approval: {self.title}",
        )
