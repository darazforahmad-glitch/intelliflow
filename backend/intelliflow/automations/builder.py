"""AutomationBuilder: GENERATE_AUTOMATION of Algorithm 5.3 and the automation lifecycle (REQ-AB-1..8,
Figure 4.9). Activation requires a validated, successfully tested latest version (BR-3)."""

from __future__ import annotations

import copy
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Max

from intelliflow.accounts.models import User
from intelliflow.approvals.services import clean_customer_approvals
from intelliflow.audit import services as audit_service
from intelliflow.automations.models import Automation, AutomationVersion, Template
from intelliflow.automations.validator import TRIGGER_PROVIDERS, ValidationIssue, WorkflowValidator
from intelliflow.core.enums import AutomationStatus, OpportunityStatus, RunStatus
from intelliflow.core.errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationFailedError,
)
from intelliflow.core.models import utcnow
from intelliflow.engine.workflow_engine import RetryMode, WorkflowEngine
from intelliflow.integrations.connectors.registry import PROVIDER_LABELS, active_connection
from intelliflow.llm import prompts
from intelliflow.llm.base import LLMError
from intelliflow.llm.service import AIService
from intelliflow.notifications import event_bus
from intelliflow.opportunities.models import Opportunity
from intelliflow.runs.models import Run
from intelliflow.workspaces.models import Workspace

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3  # first draft + at most two automatic repairs (REQ-AB-3)


def providers_used(definition: dict[str, Any]) -> set[str]:
    used: set[str] = set()
    trigger_provider = TRIGGER_PROVIDERS.get((definition.get("trigger") or {}).get("type", ""))
    if trigger_provider:
        used.add(trigger_provider)
    for block in definition.get("blocks", []) or []:
        if block.get("type") == "action" and block.get("connector"):
            used.add(block["connector"])
        if block.get("type") == "approval" and block.get("proposed_action"):
            used.add(block["proposed_action"]["connector"])
    return used


@dataclass(slots=True)
class TestResult:
    run: Run
    passed: bool
    message: str
    trace: list[dict[str, Any]]
    sandbox_records: list[dict[str, Any]]


class AutomationBuilder:
    def __init__(
        self, workspace: Workspace, user: User | None, ai: AIService | None = None
    ) -> None:
        self.workspace = workspace
        self.user = user
        self.ai = ai or AIService(workspace)

    @property
    def _actor_id(self) -> uuid.UUID | None:
        return self.user.id if self.user else None

    def _audit(
        self, action: str, automation: Automation, data: dict[str, Any] | None = None
    ) -> None:
        audit_service.record(
            action,
            workspace_id=self.workspace.id,
            actor_id=self._actor_id,
            entity_type="automation",
            entity_id=automation.id,
            data=data,
        )

    # ------------------------------------------------------------------ helpers
    def connected_providers(self) -> set[str]:
        return {p for p in PROVIDER_LABELS if active_connection(self.workspace.id, p) is not None}

    def missing_connections(self, providers: set[str] | list[str]) -> list[str]:
        connected = self.connected_providers()
        return sorted(p for p in providers if p not in connected)

    def _require_connections(self, providers: set[str] | list[str]) -> None:
        missing = self.missing_connections(providers)
        if missing:
            names = " and ".join(PROVIDER_LABELS.get(p, p) for p in missing)
            raise ConflictError(
                f"Connect {names} first.",
                code="connections_required",
                hint="Open the Integrations page to connect the apps this automation uses.",
                details={"missing": missing},
            )

    def _workspace_context(self) -> dict[str, Any]:
        return {
            "name": self.workspace.name,
            "business_type": self.workspace.business_type,
            "language_pref": self.workspace.language_pref,
            "approval_threshold": float(self.workspace.approval_threshold),
            "currency": self.workspace.currency,
        }

    def _llm(self, request: Any) -> dict[str, Any]:
        try:
            return self.ai.run(request).data
        except LLMError as exc:
            raise ServiceUnavailableError(
                "The AI assistant could not build the automation right now. Please try again."
            ) from exc

    def validate(
        self, definition: dict[str, Any], *, check_connections: bool = False
    ) -> list[ValidationIssue]:
        available = self.connected_providers() if check_connections else None
        return WorkflowValidator(available_connectors=available).validate(definition)

    # ------------------------------------------------------------------ generation (Algorithm 5.3)
    @transaction.atomic
    def generate_from_opportunity(self, opportunity: Opportunity) -> Automation:
        """generateAutomation(opportunityId) - Table 4.16."""
        existing = (
            Automation.objects.filter(opportunity=opportunity)
            .exclude(status=AutomationStatus.ARCHIVED)
            .first()
        )
        if existing is not None:
            return existing
        if opportunity.status == OpportunityStatus.DISMISSED:
            raise ConflictError(
                "This opportunity was dismissed. Restore it first.", code="opportunity_dismissed"
            )
        template = opportunity.template
        if template is None:
            raise ConflictError("There is no template for this step yet.", code="not_yet_supported")
        self._require_connections(template.required_connections or [])
        step = opportunity.step
        context = {
            "title": step.title,
            "action": step.action,
            "app": step.app,
            "actor": step.actor,
            "minutes_per_run": float(step.minutes_per_run or 0),
            "runs_per_week": step.runs_per_week,
            "fit": float(opportunity.fit),
        }
        estimate = (step.minutes_per_run or Decimal(0)) * opportunity.fit
        automation = self._generate(template, context, opportunity=opportunity, estimate=estimate)
        opportunity.status = OpportunityStatus.SELECTED
        opportunity.save(update_fields=["status"])
        return automation

    @transaction.atomic
    def generate_from_template(self, template_code: str) -> Automation:
        """REQ-AB-8: create an automation directly from a template, without an interview."""
        template = Template.objects.filter(code=template_code, is_active=True).first()
        if template is None:
            raise NotFoundError("Template not found.")
        self._require_connections(template.required_connections or [])
        estimate = Decimal(
            str((template.definition_json.get("settings") or {}).get("estimated_minutes_saved", 0))
        )
        return self._generate(
            template, {"title": template.name, "fit": 1.0}, opportunity=None, estimate=estimate
        )

    def _generate(
        self,
        template: Template,
        step: dict[str, Any],
        *,
        opportunity: Opportunity | None,
        estimate: Decimal,
    ) -> Automation:
        connections = sorted(self.connected_providers())
        draft = self._llm(
            prompts.workflow_fill(
                template_definition=template.definition_json,
                step=step,
                workspace=self._workspace_context(),
                connections=connections,
            )
        )
        source = "generated"
        issues: list[ValidationIssue] = []
        for attempt in range(1, MAX_ATTEMPTS + 1):
            issues = self.validate(draft)
            if not issues:
                break
            logger.info(
                "generated workflow failed validation",
                extra={"attempt": attempt, "issues": len(issues)},
            )
            if attempt < MAX_ATTEMPTS:
                draft = self._llm(
                    prompts.workflow_repair(
                        definition=draft,
                        errors=[i.to_dict() for i in issues],
                        workspace=self._workspace_context(),
                    )
                )
                source = "repaired"
        name = (
            str(draft.get("name") or template.name)[:120]
            if isinstance(draft, dict)
            else template.name
        )
        automation = Automation.objects.create(
            workspace=self.workspace,
            opportunity=opportunity,
            template=template,
            name=name,
            description=template.description,
            status=AutomationStatus.VALIDATED if not issues else AutomationStatus.DRAFT,
            trigger_type=(draft.get("trigger") or {}).get("type") if not issues else None,
            estimated_minutes_per_run=estimate.quantize(Decimal("0.1")),
            created_by=self.user,
        )
        version = AutomationVersion.objects.create(
            automation=automation,
            version_no=1,
            definition_json=draft,
            validated=not issues,
            validation_errors=[i.to_dict() for i in issues],
            source=source,
            created_by=self.user,
        )
        automation.current_version = version
        automation.save(update_fields=["current_version", "updated_at"])
        self._audit(
            "automation.generated",
            automation,
            {"template": template.code, "validated": not issues, "source": source},
        )
        return automation

    # ------------------------------------------------------------------ editing and versions (REQ-AB-4, REQ-AB-7)
    def _new_version(
        self,
        automation: Automation,
        definition: dict[str, Any],
        *,
        source: str,
        test_passed: bool = False,
    ) -> AutomationVersion:
        issues = self.validate(definition)
        current = AutomationVersion.objects.filter(automation=automation).aggregate(
            top=Max("version_no")
        )["top"]
        version = AutomationVersion.objects.create(
            automation=automation,
            version_no=(current or 0) + 1,
            definition_json=definition,
            validated=not issues,
            test_passed=test_passed and not issues,
            validation_errors=[i.to_dict() for i in issues],
            source=source,
            created_by=self.user,
        )
        automation.current_version = version
        if not issues:
            automation.trigger_type = definition["trigger"]["type"]
            minutes = (definition.get("settings") or {}).get("estimated_minutes_saved")
            if minutes is not None:
                automation.estimated_minutes_per_run = Decimal(str(minutes)).quantize(
                    Decimal("0.1")
                )
            automation.name = str(definition.get("name", automation.name))[:120]
        # Figure 4.9: editing returns the automation to Draft/Validated; it must be tested again.
        if automation.status != AutomationStatus.ARCHIVED:
            automation.status = (
                AutomationStatus.TESTED
                if version.test_passed
                else AutomationStatus.VALIDATED if version.validated else AutomationStatus.DRAFT
            )
            automation.status_reason = None
        automation.save()
        return version

    def save_definition(
        self, automation: Automation, definition: dict[str, Any]
    ) -> AutomationVersion:
        with transaction.atomic():
            version = self._new_version(automation, copy.deepcopy(definition), source="manual")
            self._audit("automation.edited", automation, {"version": version.version_no})
        self._publish(automation)
        return version

    @transaction.atomic
    def repair(self, automation: Automation) -> AutomationVersion:
        version = automation.current_version
        if version is None or version.validated:
            raise ConflictError("This version has no problems to fix.", code="nothing_to_repair")
        issues = self.validate(version.definition_json)
        repaired = self._llm(
            prompts.workflow_repair(
                definition=version.definition_json,
                errors=[i.to_dict() for i in issues],
                workspace=self._workspace_context(),
            )
        )
        return self._new_version(automation, repaired, source="repaired")

    @transaction.atomic
    def rollback(self, automation: Automation, version_no: int) -> AutomationVersion:
        old = AutomationVersion.objects.filter(automation=automation, version_no=version_no).first()
        if old is None:
            raise NotFoundError(f"Version {version_no} not found.")
        new = self._new_version(
            automation,
            copy.deepcopy(old.definition_json),
            source="rollback",
            test_passed=old.test_passed,
        )
        self._audit(
            "automation.rolled_back",
            automation,
            {"from_version": version_no, "new_version": new.version_no},
        )
        return new

    # ------------------------------------------------------------------ test runs (REQ-AB-5, SAF-5)
    @staticmethod
    def sample_trigger(trigger_type: str, sample: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        if trigger_type == "whatsapp.message_received":
            return {
                "message_id": f"test-{uuid.uuid4().hex[:10]}",
                "from": str(sample.get("from") or "923001234567"),
                "name": sample.get("name") or "Test Customer",
                "text": str(sample.get("text") or ""),
                "type": sample.get("type") or "text",
                "timestamp": now,
            }
        if trigger_type == "gmail.message_received":
            return {
                "message_id": f"test-{uuid.uuid4().hex[:10]}",
                "from": sample.get("from") or "customer@example.com",
                "to": sample.get("to") or "shop@example.com",
                "subject": sample.get("subject") or "",
                "body": sample.get("body") or sample.get("text") or "",
                "received_at": now,
            }
        if trigger_type == "webform.submitted":
            return {
                "form_name": sample.get("form_name") or "Website form",
                "fields": sample.get("fields") or {},
                "submitted_at": now,
            }
        return {"scheduled_for": now, **sample}

    def test(self, automation: Automation, sample: dict[str, Any]) -> TestResult:
        version = automation.current_version
        if version is None or not version.validated:
            raise ConflictError(
                "Fix the problems in this automation before testing it.", code="not_validated"
            )
        engine = WorkflowEngine(
            llm_client=self.ai.client, retry_mode=RetryMode.INLINE, sleep=lambda _s: None
        )
        trigger_type = version.definition_json["trigger"]["type"]
        run = engine.create_run(
            automation,
            event_id=f"test:{uuid.uuid4().hex}",
            trigger_type=trigger_type,
            trigger=self.sample_trigger(trigger_type, sample),
            is_test=True,
        )
        if run is None:  # pragma: no cover - test event ids are unique
            raise ConflictError("Could not start the test run.")
        run = engine.execute(run.id)  # its own transaction: the run is visible like a live one
        blocks = version.definition_json["blocks"]
        reached_end = len(engine.trace) == len(blocks) and run.status == RunStatus.SUCCEEDED
        if run.status == RunStatus.SUCCEEDED and not reached_end:
            stopped_at = engine.trace[-1]["title"] if engine.trace else "the first step"
            message = f"The test stopped at “{stopped_at}”. Try a sample that should go through every step."
        elif run.status == RunStatus.SUCCEEDED:
            message = "Test passed: every step worked. Nothing was sent to real customers."
        else:
            message = f"The test failed: {run.error or 'a step did not finish.'}"
        with transaction.atomic():
            version = AutomationVersion.objects.get(pk=version.pk)
            automation.refresh_from_db()
            if reached_end:
                version.test_passed = True
                version.save(update_fields=["test_passed"])
                if automation.status in {AutomationStatus.DRAFT, AutomationStatus.VALIDATED}:
                    automation.status = AutomationStatus.TESTED
                    automation.save(update_fields=["status", "updated_at"])
            self._audit("automation.tested", automation, {"passed": reached_end})
        return TestResult(
            run=run,
            passed=reached_end,
            message=message,
            trace=engine.trace,
            sandbox_records=engine.recorder.records,
        )

    # ------------------------------------------------------------------ lifecycle (UC-09)
    def activate(self, automation: Automation) -> Automation:
        """activateAutomation(automationId) - Table 4.16, BR-3, REQ-AB-6."""
        version = automation.current_version
        if automation.status == AutomationStatus.ARCHIVED:
            raise ConflictError("Archived automations cannot be activated.", code="archived")
        if version is None or not version.validated or not version.test_passed:
            raise ConflictError(
                "Run a successful test of the latest version before activating it.",
                code="test_required",
                hint="Use 'Run test' with a sample message.",
            )
        self._require_connections(providers_used(version.definition_json))
        with transaction.atomic():
            automation.status = AutomationStatus.ACTIVE
            automation.activated_at = utcnow()
            automation.consecutive_failures = 0
            automation.status_reason = None
            automation.save()
            if automation.opportunity_id:
                Opportunity.objects.filter(pk=automation.opportunity_id).update(
                    status=OpportunityStatus.AUTOMATED
                )
            self._audit("automation.activated", automation)
        self._publish(automation)
        return automation

    def pause(self, automation: Automation, reason: str = "Paused by the owner.") -> Automation:
        if automation.status not in {AutomationStatus.ACTIVE, AutomationStatus.ERROR}:
            raise ConflictError("Only active automations can be paused.", code="not_active")
        with transaction.atomic():
            automation.status = AutomationStatus.PAUSED
            automation.status_reason = reason
            automation.save(update_fields=["status", "status_reason", "updated_at"])
            self._audit("automation.paused", automation)
        self._publish(automation)
        return automation

    def archive(self, automation: Automation) -> Automation:
        with transaction.atomic():
            automation.status = AutomationStatus.ARCHIVED
            automation.status_reason = "Archived by the owner."
            automation.save(update_fields=["status", "status_reason", "updated_at"])
            self._audit("automation.archived", automation)
        self._publish(automation)
        return automation

    @transaction.atomic
    def set_auto_send(self, automation: Automation, enabled: bool) -> Automation:
        """SAF-1: auto-send only after 20 approved customer messages in a row without edits."""
        if enabled:
            needed = settings.AUTO_SEND_MIN_CLEAN_APPROVALS
            clean = clean_customer_approvals(automation.id, needed)
            if clean < needed:
                raise ValidationFailedError(
                    f"Auto-send unlocks after {needed} customer messages are approved without edits "
                    f"({clean} so far).",
                    code="auto_send_locked",
                )
        automation.auto_send = enabled
        automation.save(update_fields=["auto_send", "updated_at"])
        self._audit("automation.auto_send_changed", automation, {"enabled": enabled})
        return automation

    def _publish(self, automation: Automation) -> None:
        event_bus.publish(
            self.workspace.id,
            "automation.updated",
            {"automation_id": str(automation.id), "status": str(automation.status)},
        )
