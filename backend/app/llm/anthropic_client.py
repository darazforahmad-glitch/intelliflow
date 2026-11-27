"""Claude adapter behind the LLMClient interface (official Anthropic Python SDK).

- Strict requests use structured outputs (`output_config.format`), so the response is
  constrained to the JSON schema; it is still validated locally afterwards.
- Effort is set explicitly per task (the model's default is `medium`).
- Server-side fallbacks are enabled so a classifier decline is retried on the model
  Anthropic recommends; a final `refusal` stop reason is surfaced as LLMRefusalError.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

import anthropic

from app.llm.base import (
    LLMClient,
    LLMOutputError,
    LLMRefusalError,
    LLMRequest,
    LLMResponse,
    LLMUnavailableError,
)
from app.llm.schema_utils import to_structured_output_schema

logger = logging.getLogger(__name__)

# USD per million tokens (input, output), first-party API list prices.
PRICES_PER_MTOK: dict[str, tuple[Decimal, Decimal]] = {
    "claude-opus-5-5": (Decimal("4"), Decimal("20")),
    "claude-sonnet-5-5": (Decimal("2"), Decimal("10")),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
    "claude-fable-5-2": (Decimal("8"), Decimal("40")),
    "claude-opus-5": (Decimal("5"), Decimal("25")),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    price_in, price_out = PRICES_PER_MTOK.get(model, (Decimal(0), Decimal(0)))
    return (price_in * input_tokens + price_out * output_tokens) / Decimal(1_000_000)


def _parse_json(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMOutputError("The model did not return a JSON object.")
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMOutputError(f"The model returned invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise LLMOutputError("The model returned JSON that is not an object.")
    return value


class AnthropicLLMClient(LLMClient):
    provider = "anthropic"

    def __init__(self, model: str, *, timeout: float = 90.0, max_retries: int = 2) -> None:
        self.model = model
        # Credentials resolve from the environment (ANTHROPIC_API_KEY or an `ant` profile).
        self._client = anthropic.Anthropic(timeout=timeout, max_retries=max_retries)

    def generate(self, request: LLMRequest) -> LLMResponse:
        output_config: dict[str, Any] = {"effort": request.effort}
        system = request.system
        if request.strict:
            output_config["format"] = {
                "type": "json_schema",
                "schema": to_structured_output_schema(request.schema),
            }
        else:
            system += "\n\nRespond with exactly one JSON object and no other text."
        try:
            response = self._client.beta.messages.create(  # type: ignore[call-overload]
                model=self.model,
                max_tokens=request.max_tokens,
                system=system,
                messages=request.messages,
                output_config=output_config,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.RateLimitError as exc:
            raise LLMUnavailableError("The AI service is busy (rate limited).") from exc
        except anthropic.InternalServerError as exc:
            raise LLMUnavailableError("The AI service had a temporary error.") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMUnavailableError("The AI service had a temporary error.") from exc
            logger.error(
                "LLM request rejected",
                extra={"status": exc.status_code, "task": request.task.value},
            )
            raise LLMOutputError(
                f"The AI service rejected the request ({exc.status_code})."
            ) from exc
        except anthropic.APIConnectionError as exc:  # includes APITimeoutError
            raise LLMUnavailableError("Could not reach the AI service.") from exc

        if response.stop_reason == "refusal":
            category = (
                getattr(response.stop_details, "category", None) if response.stop_details else None
            )
            raise LLMRefusalError(f"The AI declined this request (category: {category}).")
        if response.stop_reason == "max_tokens":
            raise LLMOutputError("The AI response was cut off before it finished.")
        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMResponse(
            data=_parse_json(text),
            provider=self.provider,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
