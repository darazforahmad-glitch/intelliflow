"""Provider-agnostic LLM interface (Section 5.2: 'LLM provider SDK behind an LLMClient wrapper').

Every call is schema-first: the request carries the JSON schema the output must match,
and callers validate the output again before use (Section 5.4).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


class LLMTask(StrEnum):
    INTERVIEW_TURN = "interview_turn"
    PROCESS_MAP = "process_map"
    CLASSIFY = "ai.classify"
    EXTRACT = "ai.extract"
    DRAFT_REPLY = "ai.draft_reply"
    SUMMARIZE = "ai.summarize"
    WORKFLOW_FILL = "workflow_fill"
    WORKFLOW_REPAIR = "workflow_repair"


Effort = Literal["low", "medium", "high"]


@dataclass(slots=True)
class LLMRequest:
    task: LLMTask
    system: str
    messages: list[dict[str, str]]
    schema: dict[str, Any]
    # strict=True: the provider constrains decoding to `schema` (structured outputs).
    # strict=False: the schema is described in the prompt and validated locally only
    # (used for workflow definitions, whose free-form params maps cannot be strict).
    strict: bool = True
    effort: Effort = "low"
    max_tokens: int = 4096
    # Structured inputs the prompt was rendered from. The FakeLLMClient reads these
    # instead of parsing prose; real providers ignore them.
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LLMResponse:
    data: dict[str, Any]
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMError(Exception):
    """Base class for LLM failures."""


class LLMUnavailableError(LLMError):
    """Transient: network error, rate limit or provider outage. Safe to retry."""


class LLMRefusalError(LLMError):
    """The provider declined the request."""


class LLMOutputError(LLMError):
    """The response was truncated or was not valid JSON."""


class LLMClient(abc.ABC):
    provider: str = "abstract"
    model: str = "none"

    @abc.abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
