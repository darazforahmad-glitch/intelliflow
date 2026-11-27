"""Connector interface. New apps are added by implementing `Connector` (NFR maintainability).

Every connector supports sandbox mode: test runs (SAF-5) and sandbox connections record
what would be sent instead of calling the real API.
"""

from __future__ import annotations

import abc
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

from app.engine.errors import PermanentBlockError
from app.models import Connection, Workspace


@dataclass(frozen=True, slots=True)
class OperationSpec:
    name: str
    label: str
    writes: bool
    customer_message: bool = False
    required: tuple[str, ...] = ()


@dataclass(slots=True)
class SandboxRecorder:
    """Collects what sandboxed connectors 'did' during one run."""

    records: list[dict[str, Any]] = field(default_factory=list)

    def record(self, provider: str, operation: str, payload: dict[str, Any]) -> str:
        ref = f"sandbox-{uuid.uuid4().hex[:12]}"
        self.records.append(
            {"ref": ref, "provider": provider, "operation": operation, "payload": payload}
        )
        return ref


@dataclass(slots=True)
class ConnectorContext:
    workspace: Workspace
    connection: Connection | None
    sandbox: bool
    recorder: SandboxRecorder
    persist: Callable[[str, dict[str, Any]], None] | None = (
        None  # stores sandbox records for sandbox connections
    )
    credentials: dict[str, Any] | None = None
    save_credentials: Callable[[dict[str, Any]], None] | None = None
    extras: dict[str, Any] = field(default_factory=dict)


class Connector(abc.ABC):
    provider: ClassVar[str]
    label: ClassVar[str]
    operations: ClassVar[dict[str, OperationSpec]] = {}

    def __init__(self, ctx: ConnectorContext) -> None:
        self.ctx = ctx

    @property
    def sandbox(self) -> bool:
        return self.ctx.sandbox

    def execute(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        spec = self.operations.get(operation)
        if spec is None:
            raise PermanentBlockError(
                f"{self.label} cannot do “{operation}”.", code="unknown_operation"
            )
        missing = [p for p in spec.required if params.get(p) in (None, "", [])]
        if missing:
            raise PermanentBlockError(
                f"{self.label} “{spec.label}” is missing: {', '.join(missing)}.",
                code="missing_params",
                details={"missing": missing},
            )
        handler = getattr(self, f"op_{operation}")
        result: dict[str, Any] = handler(params)
        return result

    def record_sandbox(self, operation: str, payload: dict[str, Any]) -> str:
        ref = self.ctx.recorder.record(self.provider, operation, payload)
        if self.ctx.persist is not None:
            self.ctx.persist(
                f"outbox:{self.provider}", {"operation": operation, "ref": ref, **payload}
            )
        return ref


def normalize_msisdn(value: Any) -> str:
    """Normalise a Pakistani/international number to WhatsApp's digits-only format."""
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("03") and len(digits) == 11:
        digits = "92" + digits[1:]
    if len(digits) < 10 or len(digits) > 15:
        raise PermanentBlockError(f"“{value}” is not a valid phone number.", code="invalid_phone")
    return digits
