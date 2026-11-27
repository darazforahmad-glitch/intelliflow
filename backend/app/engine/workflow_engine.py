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

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors.base import SandboxRecorder
from app.connectors.registry import ConnectorFactory
from app.core.config import get_settings
from app.core.crypto import get_cipher
from app.core.masking import mask_pii
from app.core.transaction import on_commit
from app.engine.blocks.base import (
    ApprovalDecision,
    Block,
    BlockResult,
    BlockStatus,
    ExecutionServices,
    RunContext,
)
from app.engine.blocks.registry import build_block
from app.engine.errors import ConnectionUnavailableError, PermanentBlockError, TransientBlockError
from app.llm.base import LLMClient
from app.models import ApprovalTask, Automation, Run, StepRun, Workspace
from app.models.base import utcnow
from app.models.enums import (
    AutomationStatus,
    MembershipRole,
    RunStatus,
    StepRunStatus,
    WorkspaceStatus,
)
from app.services import event_bus
from app.services.ai_service import AIService
from app.services.notification_service import notify, workspace_members

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
        db: Session,
        *,
        llm_client: LLMClient | None = None,
        retry_mode: RetryMode = RetryMode.DEFERRED,
        scheduler: Callable[[uuid.UUID, float], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        backoff_scale: float = 1.0,
    ) -> None:
        self.db = db
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
        if self.db.scalar(
            select(Run.id).where(Run.automation_id == automation.id, Run.event_id == event_id)
        ):
            return None
        workspace = self.db.get_one(Workspace, automation.workspace_id)
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
            with self.db.begin_nested():
                self.db.add(run)
                self.db.flush()
        except IntegrityError:
            return None  # a concurrent worker created it first
        return run

    # ------------------------------------------------------------------ execution
    def execute(self, run_id: uuid.UUID) -> Run:
        run = self.db.get(Run, run_id, with_for_update=True)
        if run is None:
            raise LookupError(f"run {run_id} not found")
        if run.status.is_terminal:
            return run
        automation = self.db.get_one(Automation, run.automation_id)
        workspace = self.db.get_one(Workspace, run.workspace_id)
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
            ai=AIService(self.db, workspace, self.llm_client),
            connectors=ConnectorFactory(
                self.db,
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
            if latest is not None and latest.status.is_open:
                run.status = RunStatus.WAITING_APPROVAL
                self._persist(run, ctx)
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
                    self.sleep(delay)
                    continue
                self._persist(run, ctx)
                self.db.commit()
                self.scheduler(run.id, delay)
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
                self._publish(run)
                self.db.commit()
                return run
            step_run.output_json = mask_pii(result.output)
            step_run.finished_at = utcnow()
            step_run.error = None
            if result.status == BlockStatus.REJECTED:
                step_run.status = StepRunStatus.SKIPPED
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
        step_run = self.db.scalar(
            select(StepRun).where(StepRun.run_id == run.id, StepRun.step_key == block.key)
        )
        if step_run is None:
            step_run = StepRun(
                run_id=run.id,
                step_key=block.key,
                seq_no=index,
                block_type=block.type,
                status=StepRunStatus.RUNNING,
                attempt=1,
            )
            self.db.add(step_run)
            self.db.flush()
        return step_run

    def _latest_task(self, step_run: StepRun) -> ApprovalTask | None:
        return self.db.scalar(
            select(ApprovalTask)
            .where(ApprovalTask.step_run_id == step_run.id)
            .order_by(ApprovalTask.created_at.desc())
            .limit(1)
        )

    @staticmethod
    def _decision(task: ApprovalTask) -> ApprovalDecision:
        decided = task.decision_payload_json or {}
        return ApprovalDecision(
            status=task.status.value,
            decided_by=task.decided_by,
            params=decided.get("params"),
            fields=decided.get("fields"),
            note=task.decision_note,
            payload=task.payload_json,
            kind=task.kind.value,
        )

    def _open_approval(
        self, run: Run, step_run: StepRun, block: Block, result: BlockResult, automation: Automation
    ) -> None:
        assert result.approval is not None
        settings = get_settings()
        definition_settings = run.version.definition_json.get("settings") or {}
        reminder = int(
            definition_settings.get("approval_reminder_minutes")
            or settings.approval_reminder_minutes
        )
        timeout = int(
            definition_settings.get("approval_timeout_minutes") or settings.approval_timeout_minutes
        )
        now = utcnow()
        task = ApprovalTask(
            step_run_id=step_run.id,
            run_id=run.id,
            workspace_id=run.workspace_id,
            automation_id=automation.id,
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
        self.db.add(task)
        self.db.flush()
        members = workspace_members(
            self.db, run.workspace_id
        )  # role-based: every active member (REQ-AP-2)
        body = result.approval.payload.get("message") or result.approval.title
        notify(
            self.db,
            members,
            workspace_id=run.workspace_id,
            kind="approval.created",
            title=f"Approval needed: {result.approval.title}",
            body=f"{automation.name}: {body}",
            url=f"/approvals/{task.id}",
        )
        task_id, workspace_id = task.id, run.workspace_id
        on_commit(
            self.db,
            lambda: event_bus.publish(
                workspace_id, "approval.created", {"approval_id": str(task_id)}
            ),
        )

    def _persist(self, run: Run, ctx: RunContext) -> None:
        run.context_encrypted = get_cipher().encrypt_json(ctx.data, aad=_run_aad(run.id))

    def _publish(self, run: Run) -> None:
        payload = {
            "run_id": str(run.id),
            "automation_id": str(run.automation_id),
            "status": run.status.value,
            "is_test": run.is_test,
        }
        workspace_id = run.workspace_id
        on_commit(self.db, lambda: event_bus.publish(workspace_id, "run.updated", payload))

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
        if not run.is_test:
            automation.consecutive_failures = 0
        self._persist(run, ctx)
        self._publish(run)
        self.db.commit()
        return run

    def _cancel(self, run: Run, summary: str, ctx: RunContext | None = None) -> Run:
        run.status = RunStatus.CANCELLED
        run.finished_at = utcnow()
        run.summary = summary
        if ctx is not None:
            self._persist(run, ctx)
        self._publish(run)
        self.db.commit()
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
        run.status = RunStatus.FAILED
        run.error = message
        run.finished_at = utcnow()
        self._persist(run, ctx)
        if not run.is_test:
            automation = self.db.get_one(Automation, run.automation_id)
            automation.consecutive_failures += 1
            threshold = get_settings().automation_failure_threshold
            if connection_problem or automation.consecutive_failures >= threshold:  # REQ-WE-7
                automation.status = AutomationStatus.ERROR
                automation.status_reason = (
                    f"Paused because a connection it needs is not working: {message}"
                    if connection_problem
                    else f"Paused after {automation.consecutive_failures} failed runs in a row. Last error: {message}"
                )
                owners = workspace_members(self.db, run.workspace_id, roles=[MembershipRole.OWNER])
                notify(
                    self.db,
                    owners,
                    workspace_id=run.workspace_id,
                    kind="automation.error",
                    title=f"“{automation.name}” was paused",
                    body=automation.status_reason,
                    url=f"/automations/{automation.id}",
                )
                automation_id, workspace_id = automation.id, run.workspace_id
                on_commit(
                    self.db,
                    lambda: event_bus.publish(
                        workspace_id,
                        "automation.updated",
                        {"automation_id": str(automation_id), "status": "error"},
                    ),
                )
        self._publish(run)
        self.db.commit()
        return run
