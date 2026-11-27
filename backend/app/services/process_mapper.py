"""ProcessMapper: BUILD_MAP of Algorithm 5.1 plus versioned editing (REQ-FM-4..7).

The LLM proposes steps in the process-map JSON schema; we validate the structure and
the graph semantics, feed errors back for at most two regenerations (REQ-FM-5), then
classify each step and store an immutable map version.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from jsonschema.exceptions import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ValidationFailedError
from app.jsonschemas import PROCESS_MAP, validator_for
from app.llm import prompts
from app.models import InterviewMessage, InterviewSession, ProcessMap, ProcessStep, User
from app.models.base import utcnow
from app.models.enums import InterviewStatus, MessageSender, StepType
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3  # first attempt + at most two regenerations (REQ-FM-5)

_FIELD_LABELS = {
    "steps": "the list of steps",
    "title": "a step title",
    "actor": "who does the step",
    "minutes_per_run": "the minutes a step takes",
    "runs_per_week": "how often a step happens",
    "step_type": "the step type",
    "app": "the app used",
}


def _plain_schema_error(error: ValidationError) -> str:
    path = list(error.absolute_path)
    where = ""
    if len(path) >= 2 and path[0] == "steps" and isinstance(path[1], int):
        where = f"Step {path[1] + 1}: "
    field = next((p for p in reversed(path) if isinstance(p, str)), None)
    label = _FIELD_LABELS.get(field or "", field or "the map")
    if error.validator == "minItems" and field == "steps":
        return "The process needs at least 3 steps (a start, at least one task and an end)."
    if error.validator == "required":
        return f"{where}{error.message.replace(chr(39), '')}."
    if error.validator in {"minimum", "maximum"}:
        return f"{where}{label} is out of range ({error.message})."
    return f"{where}{label} is invalid ({error.message})."


def validate_process_map(data: dict[str, Any]) -> list[str]:
    """Return plain-language problems; an empty list means the map is valid."""
    errors = [_plain_schema_error(e) for e in validator_for(PROCESS_MAP).iter_errors(data)]
    if errors:
        return errors
    steps = data["steps"]
    keys = [s["key"] for s in steps]
    if len(set(keys)) != len(keys):
        errors.append("Two steps share the same key; every step needs its own key.")
    seen: set[str] = set()
    for index, step in enumerate(steps):
        number = index + 1
        if index == 0:
            if step["step_type"] != "start":
                errors.append("The first step must be the start (the trigger) of the process.")
            if step["predecessor"] is not None:
                errors.append("The first step cannot have a step before it.")
        else:
            if step["step_type"] == "start":
                errors.append(f"Step {number}: only the first step can be the start.")
            if step["predecessor"] not in seen:
                errors.append(
                    f"Step {number}: its previous step '{step['predecessor']}' is not an earlier step."
                )
        seen.add(step["key"])
    if steps[-1]["step_type"] != "end":
        errors.append("The last step must be the end of the process.")
    return errors


def classify_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`step.type <- classify(step)`: enforce start/end structure, derive is_manual."""
    out = []
    last = len(steps) - 1
    for index, original in enumerate(steps):
        step = dict(original)
        if index == 0:
            step["step_type"] = StepType.START.value
        elif index == last:
            step["step_type"] = StepType.END.value
        elif step["step_type"] in {StepType.START.value, StepType.END.value}:
            step["step_type"] = StepType.MANUAL.value
        if step["step_type"] in {StepType.START.value, StepType.END.value}:
            step["minutes_per_run"] = 0
        step["is_manual"] = step["step_type"] in {StepType.MANUAL.value, StepType.HUMAN_ONLY.value}
        out.append(step)
    return out


def build_graph(
    steps: list[dict[str, Any]], positions: dict[str, dict[str, float]] | None = None
) -> dict[str, Any]:
    nodes, edges = [], []
    for index, step in enumerate(steps):
        weekly = float(step["minutes_per_run"] or 0) * int(step["runs_per_week"] or 0)
        nodes.append(
            {
                "id": step["key"],
                "type": "step",
                "position": (positions or {}).get(step["key"]) or {"x": 0, "y": index * 130},
                "data": {
                    k: step[k]
                    for k in (
                        "title",
                        "actor",
                        "step_type",
                        "app",
                        "minutes_per_run",
                        "runs_per_week",
                        "involves_customer_messaging",
                        "involves_money",
                    )
                }
                | {"weekly_minutes": weekly},
            }
        )
        if step.get("predecessor"):
            edges.append(
                {
                    "id": f"e-{step['predecessor']}-{step['key']}",
                    "source": step["predecessor"],
                    "target": step["key"],
                }
            )
    return {"nodes": nodes, "edges": edges}


class ProcessMapper:
    def __init__(self, db: Session, ai: AIService) -> None:
        self.db = db
        self.ai = ai

    def build(self, session: InterviewSession, user: User) -> ProcessMap:
        if session.status != InterviewStatus.IN_PROGRESS:
            raise ConflictError("This interview is already finished.", code="interview_closed")
        transcript = [{"sender": m.sender.value, "content": m.content} for m in session.messages]
        if not any(m["sender"] == "user" for m in transcript):
            raise ConflictError(
                "Answer at least one question before creating the map.", code="no_answers"
            )

        language = session.language or self.ai.workspace.language_pref
        feedback: list[str] = []
        data: dict[str, Any] = {}
        for attempt in range(1, MAX_ATTEMPTS + 1):
            data = self.ai.run(
                prompts.process_map(
                    process_name=session.process_name,
                    transcript=transcript,
                    language=language,
                    feedback=feedback,
                )
            ).data
            feedback = validate_process_map(data)
            if not feedback:
                break
            logger.info(
                "process map failed validation", extra={"attempt": attempt, "errors": len(feedback)}
            )

        if feedback:
            # Algorithm 5.1: ask the owner a clarifying question and stop.
            question = self._clarifying_question(language)
            self.db.add(
                InterviewMessage(
                    session_id=session.id,
                    sender=MessageSender.AI,
                    content=question,
                    language=language,
                    meta_json={"kind": "clarification", "errors": feedback[:5]},
                )
            )
            session.ready_for_mapping = False
            self.db.commit()
            raise ValidationFailedError(
                "I could not draw the process map yet. Please answer the new question in the chat.",
                code="map_needs_clarification",
                details=feedback[:5],
            )

        steps = classify_steps(data["steps"])
        process_map = self._store_version(
            session, session.process_name, steps, user, note="Generated from interview"
        )
        session.status = InterviewStatus.COMPLETED
        session.completed_at = utcnow()
        session.language = data.get("language", language)
        self.db.flush()
        return process_map

    @staticmethod
    def _clarifying_question(language: str) -> str:
        if language == "roman-ur":
            return (
                "Maazrat, mujhe abhi poora process samajh nahi aaya. Kya aap steps dobara ek ek kar ke "
                "batayenge — shuru kahan se hota hai, phir kya hota hai, aur aakhir mein kya hota hai?"
            )
        if language == "ur":
            return "معذرت، مجھے ابھی پورا عمل سمجھ نہیں آیا۔ کیا آپ مراحل دوبارہ ایک ایک کر کے بتائیں گے؟"
        return (
            "Sorry, I could not map the whole process yet. Could you list the steps again, one by one — "
            "how it starts, what happens next, and how it ends?"
        )

    def _store_version(
        self,
        session: InterviewSession,
        name: str,
        steps: list[dict[str, Any]],
        user: User | None,
        *,
        note: str,
        positions: dict[str, dict[str, float]] | None = None,
    ) -> ProcessMap:
        current = self.db.scalar(
            select(func.max(ProcessMap.version)).where(ProcessMap.session_id == session.id)
        )
        process_map = ProcessMap(
            workspace_id=session.workspace_id,
            session_id=session.id,
            name=name,
            version=(current or 0) + 1,
            graph_json=build_graph(steps, positions),
            created_by=user.id if user else None,
            change_note=note,
        )
        self.db.add(process_map)
        self.db.flush()
        for index, step in enumerate(steps, start=1):
            self.db.add(
                ProcessStep(
                    map_id=process_map.id,
                    seq_no=index,
                    step_key=step["key"],
                    title=step["title"],
                    actor=step["actor"],
                    action=step.get("action"),
                    step_type=StepType(step["step_type"]),
                    app=step["app"],
                    minutes_per_run=Decimal(str(step["minutes_per_run"])),
                    runs_per_week=int(step["runs_per_week"]),
                    is_manual=bool(step["is_manual"]),
                    predecessor_key=step.get("predecessor"),
                    involves_customer_messaging=bool(step["involves_customer_messaging"]),
                    involves_money=bool(step["involves_money"]),
                )
            )
        self.db.flush()
        self.db.refresh(process_map)
        return process_map

    def save_edited_version(
        self,
        base: ProcessMap,
        steps_in: list[dict[str, Any]],
        user: User,
        *,
        name: str | None = None,
        note: str | None = None,
        positions: dict[str, dict[str, float]] | None = None,
    ) -> ProcessMap:
        """REQ-FM-6/7: the edited, re-ordered list of steps becomes a new version."""
        old_keys = [s.get("key") for s in steps_in]
        rekeyed: list[dict[str, Any]] = []
        for index, step in enumerate(steps_in, start=1):
            rekeyed.append(
                {
                    "key": f"s{index}",
                    "title": str(step["title"]).strip(),
                    "actor": str(step.get("actor") or "Owner").strip(),
                    "action": str(step.get("action") or ""),
                    "step_type": step["step_type"],
                    "app": step.get("app") or "other",
                    "minutes_per_run": float(step.get("minutes_per_run") or 0),
                    "runs_per_week": int(step.get("runs_per_week") or 0),
                    "predecessor": f"s{index - 1}" if index > 1 else None,
                    "involves_customer_messaging": bool(step.get("involves_customer_messaging")),
                    "involves_money": bool(step.get("involves_money")),
                }
            )
        data: dict[str, Any] = {
            "process_name": name or base.name,
            "language": "en",
            "steps": rekeyed,
        }
        errors = validate_process_map(data)
        if errors:
            raise ValidationFailedError(
                "The map has problems that need fixing before it can be saved.",
                code="invalid_map",
                details=errors,
            )
        known_positions = positions or {}
        moved: dict[str, dict[str, float]] = {
            f"s{i}": known_positions[k]
            for i, k in enumerate(old_keys, start=1)
            if k and k in known_positions
        }
        session = self.db.get_one(InterviewSession, base.session_id)
        return self._store_version(
            session,
            data["process_name"],
            classify_steps(rekeyed),
            user,
            note=note or "Edited by owner",
            positions=moved,
        )
