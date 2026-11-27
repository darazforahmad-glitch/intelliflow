"""Block interface (Strategy pattern, Section 4.4): every block type implements execute(ctx)."""

from __future__ import annotations

import abc
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar

from intelliflow.core.enums import ApprovalKind
from intelliflow.engine.expressions import evaluate, render, render_value, resolve_path

if TYPE_CHECKING:
    from intelliflow.automations.models import Automation
    from intelliflow.integrations.connectors.registry import ConnectorFactory
    from intelliflow.llm.service import AIService
    from intelliflow.runs.models import Run
    from intelliflow.workspaces.models import Workspace


class BlockStatus(StrEnum):
    SUCCEEDED = "succeeded"
    SKIPPED = "skipped"
    STOP = "stop"  # a condition ended the run early (nothing more to do)
    NEEDS_APPROVAL = "needs_approval"
    REJECTED = "rejected"


@dataclass(slots=True)
class ApprovalRequest:
    kind: ApprovalKind
    title: str
    payload: dict[str, Any]


@dataclass(slots=True)
class BlockResult:
    status: BlockStatus
    output: dict[str, Any] = field(default_factory=dict)
    approval: ApprovalRequest | None = None
    summary: str | None = None


@dataclass(slots=True)
class ApprovalDecision:
    status: str  # approved | edited | rejected | expired
    decided_by: uuid.UUID | None
    params: dict[str, Any] | None
    fields: dict[str, Any] | None
    note: str | None
    payload: dict[str, Any]  # the approval task's payload_json (proposed action, AI output...)
    kind: str

    @property
    def proposed_action(self) -> dict[str, Any] | None:
        action = self.payload.get("proposed_action")
        return action if isinstance(action, dict) else None


@dataclass(slots=True)
class ExecutionServices:
    workspace: Workspace
    automation: Automation
    run: Run
    ai: AIService
    connectors: ConnectorFactory
    sandbox: bool
    decision: ApprovalDecision | None = None


class RunContext:
    """Execution context: {"trigger": ..., "run": ..., "workspace": ..., <block key>: <output>}."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    def resolve(self, path: str) -> Any:
        return resolve_path(self.data, path)

    def render(self, text: str | None) -> str:
        return render(text or "", self.data)

    def render_value(self, value: Any) -> Any:
        return render_value(value, self.data)

    def evaluate(self, expression: str) -> Any:
        return evaluate(expression, self.data)

    def set_output(self, key: str, output: dict[str, Any]) -> None:
        self.data[key] = output


class Block(abc.ABC):
    type: ClassVar[str]

    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec

    @property
    def key(self) -> str:
        return str(self.spec["key"])

    @property
    def title(self) -> str:
        return str(self.spec.get("title") or self.key.replace("_", " ").capitalize())

    def describe_input(self, ctx: RunContext) -> dict[str, Any]:
        """What the step works on, for the step-run log (masked before storing)."""
        return {}

    @abc.abstractmethod
    def execute(self, ctx: RunContext, services: ExecutionServices) -> BlockResult:
        raise NotImplementedError
