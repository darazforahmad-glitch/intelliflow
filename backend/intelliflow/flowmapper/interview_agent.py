"""InterviewAgent: RUN_INTERVIEW of Algorithm 5.1 (REQ-FM-1, REQ-FM-2, REQ-FM-8)."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import transaction
from jsonschema import Draft202012Validator

from intelliflow.accounts.models import User
from intelliflow.audit import services as audit_service
from intelliflow.core.enums import InterviewStatus, MessageSender
from intelliflow.core.errors import ConflictError, ServiceUnavailableError, ValidationFailedError
from intelliflow.flowmapper.models import InterviewMessage, InterviewSession
from intelliflow.llm import output_schemas, prompts
from intelliflow.llm.base import LLMError, LLMUnavailableError
from intelliflow.llm.heuristics import detect_language
from intelliflow.llm.service import AIService
from intelliflow.workspaces.models import Workspace

_TURN_VALIDATOR = Draft202012Validator(output_schemas.INTERVIEW_TURN)
MAX_ANSWER_CHARS = 4000

_LIMIT_REACHED = {
    "en": "Thank you! We have covered the main points. Press “Done” to see your process map.",
    "roman-ur": "Shukriya! Hum ne zaroori baatein cover kar li hain. Process map dekhne ke liye “Done” dabayein.",
    "ur": "شکریہ! ہم نے اہم باتیں مکمل کر لی ہیں۔ نقشہ دیکھنے کے لیے “Done” دبائیں۔",
}


class InterviewAgent:
    def __init__(self, workspace: Workspace, ai: AIService) -> None:
        self.workspace = workspace
        self.ai = ai
        self.max_questions = settings.INTERVIEW_MAX_QUESTIONS

    def _ask(self, session: InterviewSession) -> dict[str, Any]:
        history = [{"sender": str(m.sender), "content": m.content} for m in session.messages.all()]
        try:
            reply = self.ai.run(
                prompts.interview_turn(
                    process_name=session.process_name,
                    history=history,
                    language_pref=self.workspace.language_pref,
                    question_count=session.question_count,
                    max_questions=self.max_questions,
                )
            ).data
        except LLMUnavailableError as exc:
            raise ServiceUnavailableError(
                "The AI assistant is busy right now. Please send your answer again in a moment."
            ) from exc
        except LLMError as exc:
            raise ServiceUnavailableError(
                "The AI assistant could not reply. Please try again."
            ) from exc
        if list(_TURN_VALIDATOR.iter_errors(reply)) or not reply.get("question"):
            raise ServiceUnavailableError(
                "The AI assistant gave an unexpected reply. Please try again."
            )
        return reply

    @transaction.atomic
    def start(self, user: User, process_name: str) -> InterviewSession:
        """startInterview(workspaceId, processName) - Table 4.16."""
        session = InterviewSession.objects.create(
            workspace=self.workspace, started_by=user, process_name=process_name.strip()
        )
        reply = self._ask(session)
        self._add_ai_message(session, reply)
        session.question_count = 1
        session.language = reply["language"]
        session.save()
        audit_service.record(
            "interview.started",
            workspace_id=self.workspace.id,
            actor_id=user.id,
            entity_type="interview_session",
            entity_id=session.id,
        )
        return session

    @transaction.atomic
    def answer(self, session: InterviewSession, text: str) -> InterviewSession:
        """submitAnswer(sessionId, text) - Table 4.16."""
        if session.status != InterviewStatus.IN_PROGRESS:
            raise ConflictError("This interview is already finished.", code="interview_closed")
        text = text.strip()
        if not text:
            raise ValidationFailedError("Please type an answer first.")
        if len(text) > MAX_ANSWER_CHARS:
            raise ValidationFailedError(
                f"Answers can be at most {MAX_ANSWER_CHARS} characters. Please split it into two messages."
            )
        language = detect_language(text)
        InterviewMessage.objects.create(
            session=session, sender=MessageSender.USER, content=text, language=language
        )
        session.refresh_from_db()

        if session.question_count >= self.max_questions:  # REQ-FM-2: at most 12 questions
            lang = session.language or language
            self._add_ai_message(
                session,
                {
                    "question": _LIMIT_REACHED.get(lang, _LIMIT_REACHED["en"]),
                    "language": lang,
                    "status": "enough_detail",
                    "missing": [],
                },
            )
            session.ready_for_mapping = True
        else:
            reply = self._ask(session)
            self._add_ai_message(session, reply)
            session.language = reply["language"]
            if reply["status"] == "enough_detail":
                session.ready_for_mapping = True
            else:
                session.question_count += 1
                session.ready_for_mapping = False
        session.save()
        return session

    def abandon(self, session: InterviewSession) -> InterviewSession:
        if session.status == InterviewStatus.IN_PROGRESS:
            session.status = InterviewStatus.ABANDONED
            session.save(update_fields=["status"])
        return session

    def _add_ai_message(self, session: InterviewSession, reply: dict[str, Any]) -> None:
        InterviewMessage.objects.create(
            session=session,
            sender=MessageSender.AI,
            content=reply["question"],
            language=reply.get("language"),
            meta_json={"status": reply.get("status"), "missing": reply.get("missing", [])},
        )
