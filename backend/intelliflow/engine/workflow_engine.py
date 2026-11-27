"""WorkflowEngine: EXECUTE_RUN of Algorithm 5.5 (REQ-WE-1..9).

Blocks run in order with their outputs passed forward. Transient failures are retried
up to 3 times (4 attempts) with 10 s / 60 s / 5 min backoff; approvals pause the run and
store a resume point; every step is logged with personal data masked. The context needed
to resume is stored encrypted on the run.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction

from intelliflow.approvals.models import ApprovalTask
from intelliflow.automations.models import Automation
from intelliflow.core.crypto import get_cipher
from intelliflow.core.enums import (
    ApprovalStatus,
    AutomationStatus,
    MembershipRole,
    RunStatus,
    StepRunStatus,
    WorkspaceStatus,
)
from intelliflow.core.masking import mask_pii
from intelliflow.core.models import utcnow
from intelliflow.engine.blocks.base import (
    ApprovalDecision,
    Block,
    BlockResult,
    BlockStatus,
    ExecutionServices,
    RunContext,
)
from intelliflow.engine.blocks.registry import build_block
from intelliflow.engine.errors import (
    ConnectionUnavailableError,
    PermanentBlockError,
    TransientBlockError,
)
from intelliflow.integrations.connectors.base import SandboxRecorder
from intelliflow.integrations.connectors.registry import ConnectorFactory
from intelliflow.llm.base import LLMClient
from intelliflow.llm.service import AIService
from intelliflow.notifications import event_bus
from intelliflow.notifications.services import notify, workspace_members
from intelliflow.runs.models import Run, StepRun
from intelliflow.workspaces.models import Workspace

logger = logging.getLogger(__name__)

RETRY_DELAYS_SECONDS = (10, 60, 300)
MAX_ATTEMPTS = 4  # first try + 3 retries (REQ-WE-5)


class RetryMode(StrEnum):
    INLINE = "inline"  # sleep and retry in-process (test runs)
    DEFERRED = "deferred"  # persist the resume point and reschedule through the task queue


def _run_aad(run_id: uuid.UUID) -> str:
    return f"run:{run_id}"


class WorkflowEngine:
    def __init__(
        self,
        *,
        llm_client: LLMClient | None = None,
        retry_mode: RetryMode = RetryMode.DEFERRED,
        scheduler: Callable[[uuid.UUID, float], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        backoff_scale: float = 1.0,
    ) -> None:
        self.llm_client = llm_client
        self.retry_mode = retry_mode
        self.scheduler = scheduler
        self.sleep = sleep
        self.backoff_scale = backoff_scale
        self.recorder = SandboxRecorder()
        self.trace: list[dict[str, Any]] = (
            []
        )  # unmasked per-step trace, returned to the owner for test runs

    # ------------------------------------------------------------------ run creation
    def create_run(
        self,
        automation: Automation,
        *,
        event_id: str,
        trigger_type: str,
        trigger: dict[str, Any],
        is_test: bool = False,
    ) -> Run | None:
        """Create a queued run; returns None when this event already started a run (REQ-WE-3)."""
        version = automation.current_version
        if version is None:
            raise ValueError("automation has no version to run")
        if Run.objects.filter(automation=automation, event_id=event_id[:120]).exists():
            return None
        workspace = Workspace.objects.get(pk=automation.workspace_id)
        run = Run(
            id=uuid.uuid4(),
            automation_id=automation.id,
            version_id=version.id,
            workspace_id=automation.workspace_id,
            event_id=event_id[:120],
            status=RunStatus.QUEUED,
            is_test=is_test,
            trigger_type=trigger_type,
            resume_point=0,
        )
        now_local = datetime.now(ZoneInfo(workspace.timezone))
        context = {
            "trigger": trigger,
            "run": {
                "id": str(run.id),
                "date": now_local.strftime("%d/%m/%Y"),
                "time": now_local.strftime("%H:%M"),
                "is_test": is_test,
            },
            "workspace": {"name": workspace.name, "currency": workspace.currency},
        }
        run.context_encrypted = get_cipher().encrypt_json(context, aad=_run_aad(run.id))
        try:
            with transaction.atomic():  # savepoint: a duplicate must not spoil the outer work
                run.save(force_insert=True)
        except IntegrityError:
            return None  # a concurrent worker created it first
        return run

    # ------------------------------------------------------------------ execution
    def execute(self, run_id: uuid.UUID | str) -> Run:
        """Execute (or resume) one run. The run row stays locked until the work commits,
        so two workers can never execute the same run at once."""
        with transaction.atomic():
            run = (
                Run.objects.select_for_update(of=("self",))
                .select_related("version")
                .filter(pk=run_id)
                .first()
            )
            if run is None:
                raise LookupError(f"run {run_id} not found")
            if RunStatus(run.status).is_terminal:
                return run
            return self._execute(run)

    def _execute(self, run: Run) -> Run:
        automation = Automation.objects.select_related("current_version").get(pk=run.automation_id)
        workspace = Workspace.objects.get(pk=run.workspace_id)
        self._automation = automation
        if not run.is_test and (
            automation.status != AutomationStatus.ACTIVE
            or workspace.status != WorkspaceStatus.ACTIVE
        ):
            return self._cancel(
                run, "Cancelled because the automation was paused before this run finished."
            )

        ctx = RunContext(
            get_cipher().decrypt_json(run.context_encrypted, aad=_run_aad(run.id))
            if run.context_encrypted
            else {}
        )
        services = ExecutionServices(
            workspace=workspace,
            automation=automation,
            run=run,
            ai=AIService(workspace, self.llm_client),
            connectors=ConnectorFactory(
                workspace,
                automation,
                test_run=run.is_test,
                trigger=ctx.data.get("trigger") or {},
                recorder=self.recorder,
            ),
            sandbox=run.is_test,
        )
        if run.started_at is None:
            run.started_at = utcnow()
        run.status = RunStatus.RUNNING
        blocks: list[dict[str, Any]] = run.version.definition_json["blocks"]

        index = run.resume_point
        while index < len(blocks):
            block = build_block(blocks[index])
            step_run = self._step_run(run, block, index)
            latest = self._latest_task(step_run)
            if latest is not None and ApprovalStatus(latest.status).is_open:
                run.status = RunStatus.WAITING_APPROVAL
                self._persist(run, ctx)
                run.save()
                return run
            services.decision = self._decision(latest) if latest is not None else None
            step_run.status = StepRunStatus.RUNNING
            step_run.started_at = step_run.started_at or utcnow()
            rendered_input = self._describe(block, ctx)
            step_run.input_json = mask_pii(rendered_input)
            try:
                result = block.execute(ctx, services)
            except TransientBlockError as exc:
                if step_run.attempt >= MAX_ATTEMPTS:
                    return self._fail(
                        run,
                        step_run,
                        f"{exc.message} It still failed after {MAX_ATTEMPTS} attempts.",
                        ctx,
                    )
                delay = RETRY_DELAYS_SECONDS[step_run.attempt - 1] * self.backoff_scale
                step_run.attempt += 1
                step_run.error = exc.message
                run.resume_point = index
                if self.retry_mode == RetryMode.INLINE or self.scheduler is None:
                    step_run.save(update_fields=["attempt", "error"])  # next pass re-reads it
                    self.sleep(delay)
                    continue
                self._persist(run, ctx)
                step_run.save()
                run.save()
                scheduler, run_id = self.scheduler, run.id
                transaction.on_commit(
                    lambda s=scheduler, r=run_id, d=delay: s(r, d)  # bind now, run after commit
                )
                return run
            except ConnectionUnavailableError as exc:
                return self._fail(run, step_run, exc.message, ctx, connection_problem=True)
            except PermanentBlockError as exc:
                return self._fail(run, step_run, exc.message, ctx)
            except Exception:
                logger.exception(
                    "unexpected block failure", extra={"block": block.key, "run_id": str(run.id)}
                )
                return self._fail(
                    run, step_run, "Something unexpected went wrong in this step.", ctx
                )

            self.trace.append(
                {
                    "key": block.key,
                    "type": block.type,
                    "title": block.title,
                    "status": result.status.value,
                    "input": rendered_input,
                    "output": result.output,
                    "attempts": step_run.attempt,
                }
            )
            if result.status == BlockStatus.NEEDS_APPROVAL:
                self._open_approval(run, step_run, block, result, automation)
                step_run.status = StepRunStatus.WAITING
                run.status = RunStatus.WAITING_APPROVAL
                run.resume_point = index
                run.summary = result.summary
                self._persist(run, ctx)
                step_run.save()
                run.save()
                self._publish(run)
                return run
            step_run.output_json = mask_pii(result.output)
            step_run.finished_at = utcnow()
            step_run.error = None
            if result.status == BlockStatus.REJECTED:
                step_run.status = StepRunStatus.SKIPPED
                step_run.save()
                decision = result.output.get("decision")
                return self._cancel(
                    run,
                    (
                        "Cancelled: the approval expired."
                        if decision == "expired"
                        else "Cancelled: the approval was rejected."
                    ),
                    ctx,
                )
            ctx.set_output(block.key, result.output)
            step_run.status = (
                StepRunStatus.SKIPPED
                if result.status == BlockStatus.SKIPPED
                else StepRunStatus.SUCCEEDED
            )
            step_run.save()
            if result.status == BlockStatus.STOP:
                return self._succeed(run, ctx, automation, summary=result.summary, completed=False)
            index += 1
            run.resume_point = index
        return self._succeed(run, ctx, automation, summary="Completed every step.", completed=True)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _describe(block: Block, ctx: RunContext) -> dict[str, Any]:
        try:
            return block.describe_input(ctx)
        except Exception:
            return {}

    def _step_run(self, run: Run, block: Block, index: int) -> StepRun:
        step_run = StepRun.objects.filter(run=run, step_key=block.key).first()
        if step_run is None:
            step_run = StepRun.objects.create(
                run=run,
                step_key=block.key,
                seq_no=index,
                block_type=block.type,
                status=StepRunStatus.RUNNING,
                attempt=1,
            )
        return step_run

    def _latest_task(self, step_run: StepRun) -> ApprovalTask | None:
        return ApprovalTask.objects.filter(step_run=step_run).order_by("-created_at").first()

    @staticmethod
    def _decision(task: ApprovalTask) -> ApprovalDecision:
        decided = task.decision_payload_json or {}
        return ApprovalDecision(
            status=str(task.status),
            decided_by=task.decided_by_id,
            params=decided.get("params"),
            fields=decided.get("fields"),
            note=task.decision_note,
            payload=task.payload_json,
            kind=str(task.kind),
        )

    def _open_approval(
        self, run: Run, step_run: StepRun, block: Block, result: BlockResult, automation: Automation
    ) -> None:
        assert result.approval is not None
        definition_settings = run.version.definition_json.get("settings") or {}
        reminder = int(
            definition_settings.get("approval_reminder_minutes")
            or settings.APPROVAL_REMINDER_MINUTES
        )
        timeout = int(
            definition_settings.get("approval_timeout_minutes") or settings.APPROVAL_TIMEOUT_MINUTES
        )
        now = utcnow()
        task = ApprovalTask.objects.create(
            step_run=step_run,
            run=run,
            workspace_id=run.workspace_id,
            automation=automation,
            kind=result.approval.kind,
            title=result.approval.title[:150],
            payload_json={
                **result.approval.payload,
                "automation_name": automation.name,
                "step_title": block.title,
            },
            remind_at=now + timedelta(minutes=reminder),
            expires_at=now + timedelta(minutes=timeout),
        )
        members = workspace_members(run.workspace_id)  # role-based: every active member (REQ-AP-2)
        body = result.approval.payload.get("message") or result.approval.title
        notify(
            members,
            workspace_id=run.workspace_id,
            kind="approval.created",
            title=f"Approval needed: {result.approval.title}",
            body=f"{automation.name}: {body}",
            url=f"/approvals/{task.id}",
        )
        task_id, workspace_id = task.id, run.workspace_id
        transaction.on_commit(
            lambda: event_bus.publish(
                workspace_id, "approval.created", {"approval_id": str(task_id)}
            )
        )

    def _persist(self, run: Run, ctx: RunContext) -> None:
        run.context_encrypted = get_cipher().encrypt_json(ctx.data, aad=_run_aad(run.id))

    def _publish(self, run: Run) -> None:
        payload = {
            "run_id": str(run.id),
            "automation_id": str(run.automation_id),
            "status": str(run.status),
            "is_test": run.is_test,
        }
        workspace_id = run.workspace_id
        transaction.on_commit(lambda: event_bus.publish(workspace_id, "run.updated", payload))

    def _succeed(
        self,
        run: Run,
        ctx: RunContext,
        automation: Automation,
        *,
        summary: str | None,
        completed: bool,
    ) -> Run:
        run.status = RunStatus.SUCCEEDED
        run.finished_at = utcnow()
        run.summary = summary
        run.error = None
        run.minutes_saved = (
            automation.estimated_minutes_per_run if completed and not run.is_test else Decimal(0)
        )  # REQ-WE-9
        if not run.is_test and automation.consecutive_failures:
            automation.consecutive_failures = 0
            automation.save(update_fields=["consecutive_failures", "updated_at"])
        self._persist(run, ctx)
        run.save()
        self._publish(run)
        return run

    def _cancel(self, run: Run, summary: str, ctx: RunContext | None = None) -> Run:
        run.status = RunStatus.CANCELLED
        run.finished_at = utcnow()
        run.summary = summary
        if ctx is not None:
            self._persist(run, ctx)
        run.save()
        self._publish(run)
        return run

    def _fail(
        self,
        run: Run,
        step_run: StepRun,
        message: str,
        ctx: RunContext,
        *,
        connection_problem: bool = False,
    ) -> Run:
        step_run.status = StepRunStatus.FAILED
        step_run.error = message
        step_run.finished_at = utcnow()
        step_run.save()
        run.status = RunStatus.FAILED
        run.error = message
        run.finished_at = utcnow()
        self._persist(run, ctx)
        if not run.is_test:
            automation = Automation.objects.get(pk=run.automation_id)
            automation.consecutive_failures += 1
            threshold = settings.AUTOMATION_FAILURE_THRESHOLD
            if connection_problem or automation.consecutive_failures >= threshold:  # REQ-WE-7
                automation.status = AutomationStatus.ERROR
                automation.status_reason = (
                    f"Paused because a connection it needs is not working: {message}"
                    if connection_problem
                    else f"Paused after {automation.consecutive_failures} failed runs in a row. Last error: {message}"
                )
                owners = workspace_members(run.workspace_id, roles=[MembershipRole.OWNER])
                notify(
                    owners,
                    workspace_id=run.workspace_id,
                    kind="automation.error",
                    title=f"“{automation.name}” was paused",
                    body=automation.status_reason,
                    url=f"/automations/{automation.id}",
                )
                automation_id, workspace_id = automation.id, run.workspace_id
                transaction.on_commit(
                    lambda: event_bus.publish(
                        workspace_id,
                        "automation.updated",
                        {"automation_id": str(automation_id), "status": "error"},
                    )
                )
            automation.save()
        run.save()
        self._publish(run)
        return run
