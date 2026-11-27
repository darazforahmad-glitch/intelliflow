"""WorkflowValidator: JSON-schema + business-rule validation of workflow definitions (REQ-AB-2).

Every problem is reported in plain language with a stable code, so the builder can show
it to the owner and the LLM repair loop can fix it (Algorithm 5.3).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from jsonschema.exceptions import ValidationError

from intelliflow.engine.blocks.registry import BLOCK_LIBRARY
from intelliflow.engine.expressions import ExpressionError, expression_references, value_references
from intelliflow.integrations.connectors.registry import PROVIDER_LABELS, operation_spec
from intelliflow.jsonschemas import WORKFLOW, validator_for

RESERVED_ROOTS = frozenset({"trigger", "run", "workspace"})
MONEY_FIELDS = frozenset({"amount", "total", "price", "payment_amount", "order_total"})
TRIGGER_PROVIDERS = {
    "whatsapp.message_received": "whatsapp",
    "gmail.message_received": "gmail",
    "webform.submitted": "webform",
}


@dataclass(slots=True)
class ValidationIssue:
    code: str
    message: str
    path: list[str | int] = field(default_factory=list)
    block: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _block_label(definition: dict[str, Any], index: int) -> str:
    blocks = definition.get("blocks") or []
    block = (
        blocks[index]
        if isinstance(blocks, list) and index < len(blocks) and isinstance(blocks[index], dict)
        else {}
    )
    name = block.get("title") or block.get("key")
    return f"Step {index + 1}" + (f" (“{name}”)" if name else "")


def _schema_issue(definition: dict[str, Any], error: ValidationError) -> ValidationIssue:
    path = list(error.absolute_path)
    where = "The automation"
    block_key = None
    if len(path) >= 2 and path[0] == "blocks" and isinstance(path[1], int):
        where = _block_label(definition, path[1])
        blocks = definition.get("blocks") or []
        block_key = blocks[path[1]].get("key") if isinstance(blocks[path[1]], dict) else None
    elif path and path[0] == "trigger":
        where = "The trigger"
    if error.validator == "required":
        missing = error.message.split("'")[1] if "'" in error.message else error.message
        return ValidationIssue(
            "missing_setting", f"{where} is missing “{missing}”.", path, block_key
        )
    if error.validator == "additionalProperties":
        extra = error.message.split("'")[1] if "'" in error.message else ""
        return ValidationIssue(
            "unexpected_property",
            f"{where} has an unknown setting “{extra}”.",
            [*path, extra],
            block_key,
        )
    if (
        error.validator == "enum"
        and path
        and path[-1] == "type"
        and len(path) >= 2
        and path[0] == "blocks"
    ):
        return ValidationIssue(
            "unknown_block_type",
            f"{where} uses “{error.instance}”, which is not in the approved block "
            "library (AI step, condition, approval or action).",
            path,
            block_key,
        )
    if error.validator == "pattern" and path and path[-1] == "key":
        return ValidationIssue(
            "invalid_key",
            f"{where} has an invalid key “{error.instance}”: use lower-case letters, "
            "numbers and underscores, starting with a letter.",
            path,
            block_key,
        )
    return ValidationIssue("schema", f"{where}: {error.message}.", path, block_key)


class WorkflowValidator:
    def __init__(self, *, available_connectors: set[str] | None = None) -> None:
        self.available = available_connectors

    def validate(self, definition: Any) -> list[ValidationIssue]:
        if not isinstance(definition, dict):
            return [ValidationIssue("schema", "The automation definition must be a JSON object.")]
        errors = sorted(
            validator_for(WORKFLOW).iter_errors(definition),
            key=lambda e: list(map(str, e.absolute_path)),
        )
        if errors:
            return [_schema_issue(definition, e) for e in errors[:20]]
        return self._business_rules(definition)

    # ------------------------------------------------------------------ business rules
    def _business_rules(self, definition: dict[str, Any]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        blocks: list[dict[str, Any]] = definition["blocks"]
        seen: set[str] = set()
        for index, block in enumerate(blocks):
            key, label = block["key"], _block_label(definition, index)
            path: list[str | int] = ["blocks", index]
            if block["type"] not in BLOCK_LIBRARY:
                issues.append(
                    ValidationIssue(
                        "unknown_block_type", f"{label} is not an approved block.", path, key
                    )
                )
            if key in RESERVED_ROOTS:
                issues.append(
                    ValidationIssue(
                        "reserved_key",
                        f"{label} cannot be called “{key}”; that name is reserved.",
                        path,
                        key,
                    )
                )
            if key in seen:
                issues.append(
                    ValidationIssue(
                        "duplicate_key",
                        f"{label} reuses the key “{key}”; every step needs its own key.",
                        path,
                        key,
                    )
                )
            issues += self._references(block, label, path, seen | RESERVED_ROOTS)
            issues += self._connector_rules(block, label, path)
            seen.add(key)
        issues += self._money_rule(definition)
        trigger_provider = TRIGGER_PROVIDERS.get(definition["trigger"]["type"])
        if (
            trigger_provider
            and self.available is not None
            and trigger_provider not in self.available
        ):
            issues.append(
                ValidationIssue(
                    "connection_missing",
                    f"The trigger needs {PROVIDER_LABELS[trigger_provider]}, which is not connected yet. "
                    "Connect it on the Integrations page.",
                    ["trigger"],
                    None,
                    {"provider": trigger_provider},
                )
            )
        return issues

    @staticmethod
    def _references(
        block: dict[str, Any], label: str, path: list[str | int], known: set[str]
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        roots: set[str] = set()
        for expr_field in ("if", "when"):
            expression = block.get(expr_field)
            if expression:
                try:
                    roots |= expression_references(expression)
                except ExpressionError as exc:
                    issues.append(
                        ValidationIssue(
                            "bad_expression", f"{label}: {exc}", [*path, expr_field], block["key"]
                        )
                    )
        for value_field in ("input", "message", "facts", "params"):
            if value_field in block:
                roots |= value_references(block[value_field])
        if block.get("proposed_action"):
            roots |= value_references(block["proposed_action"].get("params", {}))
        roots |= {p.split(".")[0] for p in block.get("show", [])}
        for root in sorted(roots - known):
            issues.append(
                ValidationIssue(
                    "unknown_reference",
                    f"{label} uses “{root}”, which is not an earlier step.",
                    path,
                    block["key"],
                    {"reference": root},
                )
            )
        return issues

    def _connector_rules(
        self, block: dict[str, Any], label: str, path: list[str | int]
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        actions: list[tuple[dict[str, Any], bool]] = []
        if block["type"] == "action":
            actions.append((block, False))
        if block["type"] == "approval" and block.get("proposed_action"):
            actions.append((block["proposed_action"], True))
        for action, approved in actions:
            connector, operation = action["connector"], action["operation"]
            if any(word in operation for word in ("delete", "remove", "clear", "drop")):  # SAF-3
                issues.append(
                    ValidationIssue(
                        "forbidden_operation",
                        f"{label} tries to delete data, which IntelliFlow never does.",
                        path,
                        block["key"],
                    )
                )
                continue
            spec = operation_spec(connector, operation)
            if spec is None:
                issues.append(
                    ValidationIssue(
                        "unknown_operation",
                        f"{label}: {PROVIDER_LABELS.get(connector, connector)} cannot “{operation}”.",
                        path,
                        block["key"],
                    )
                )
                continue
            if spec.customer_message and not approved:  # SAF-1
                issues.append(
                    ValidationIssue(
                        "unguarded_customer_message",
                        f"{label} sends a message to a customer without an approval step. Messages to "
                        "customers must be approved first.",
                        path,
                        block["key"],
                        {"block": block["key"]},
                    )
                )
            if self.available is not None and connector not in self.available:
                issues.append(
                    ValidationIssue(
                        "connection_missing",
                        f"{label} uses {PROVIDER_LABELS.get(connector, connector)}, which is not connected yet. "
                        "Connect it on the Integrations page.",
                        path,
                        block["key"],
                        {"provider": connector},
                    )
                )
        return issues

    @staticmethod
    def _money_rule(definition: dict[str, Any]) -> list[ValidationIssue]:
        """BR-5: an extracted amount must pass a money approval before the first unapproved write."""
        blocks = definition["blocks"]
        for index, block in enumerate(blocks):
            if block["type"] != "ai.extract":
                continue
            money = next(
                (
                    f["name"]
                    for f in block["fields"]
                    if f["name"] in MONEY_FIELDS and f.get("type") in {"number", "integer"}
                ),
                None,
            )
            if money is None:
                continue
            for later in blocks[index + 1 :]:
                if later["type"] == "approval" and later.get("kind") == "money":
                    return []
                spec = (
                    operation_spec(later.get("connector", ""), later.get("operation", ""))
                    if later["type"] == "action"
                    else None
                )
                if spec is not None and spec.writes:
                    return [
                        ValidationIssue(
                            "missing_money_approval",
                            f"Orders above the approval amount must wait for approval before “{later.get('title') or later['key']}” "
                            f"(BR-5). Add an approval step after “{block.get('title') or block['key']}”.",
                            ["blocks", index],
                            block["key"],
                            {"after": block["key"], "field": money},
                        )
                    ]
            return []
        return []
