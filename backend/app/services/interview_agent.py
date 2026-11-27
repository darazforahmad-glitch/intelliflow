"""InterviewAgent: RUN_INTERVIEW of Algorithm 5.1 (REQ-FM-1, REQ-FM-2, REQ-FM-8)."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, ServiceUnavailableError, ValidationFailedError
from app.llm import output_schemas, prompts
from app.llm.base import LLMError, LLMUnavailableError
from app.llm.heuristics import detect_language
from app.models import InterviewMessage, InterviewSession, User, Workspace
from app.models.enums import InterviewStatus, MessageSender
from app.services import audit_service
from app.services.ai_service import AIService

_TURN_VALIDATOR = Draft202012Validator(output_schemas.INTERVIEW_TURN)
MAX_ANSWER_CHARS = 4000

_LIMIT_REACHED = {
    "en": "Thank you! We have covered the main points. Press “Done” to see your process map.",
    "roman-ur": "Shukriya! Hum ne zaroori baatein cover kar li hain. Process map dekhne ke liye “Done” dabayein.",
    "ur": "شکریہ! ہم نے اہم باتیں مکمل کر لی ہیں۔ نقشہ دیکھنے کے لیے “Done” دبائیں۔",
}


class InterviewAgent:
    def __init__(self, db: Session, workspace: Workspace, ai: AIService) -> None:
        self.db = db
        self.workspace = workspace
        self.ai = ai
        self.max_questions = get_settings().interview_max_questions

    def _ask(self, session: InterviewSession) -> dict[str, Any]:
        history = [{"sender": m.sender.value, "content": m.content} for m in session.messages]
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

    def start(self, user: User, process_name: str) -> InterviewSession:
        """startInterview(workspaceId, processName) - Table 4.16."""
        session = InterviewSession(
            workspace_id=self.workspace.id, started_by=user.id, process_name=process_name.strip()
        )
        self.db.add(session)
        self.db.flush()
        reply = self._ask(session)
        self._add_ai_message(session, reply)
        session.question_count = 1
        session.language = reply["language"]
        audit_service.record(
            self.db,
            "interview.started",
            workspace_id=self.workspace.id,
            actor_id=user.id,
            entity_type="interview_session",
            entity_id=session.id,
        )
        self.db.commit()
        self.db.refresh(session)
        return session

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
        self.db.add(
            InterviewMessage(
                session_id=session.id, sender=MessageSender.USER, content=text, language=language
            )
        )
        self.db.flush()
        self.db.refresh(session)

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
        self.db.commit()
        self.db.refresh(session)
        return session

    def abandon(self, session: InterviewSession) -> InterviewSession:
        if session.status == InterviewStatus.IN_PROGRESS:
            session.status = InterviewStatus.ABANDONED
            self.db.commit()
        return session

    def _add_ai_message(self, session: InterviewSession, reply: dict[str, Any]) -> None:
        self.db.add(
            InterviewMessage(
                session_id=session.id,
                sender=MessageSender.AI,
                content=reply["question"],
                language=reply.get("language"),
                meta_json={"status": reply.get("status"), "missing": reply.get("missing", [])},
            )
        )
        self.db.flush()
