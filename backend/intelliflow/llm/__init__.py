"""LLM access through a provider-agnostic client (Section 5.2)."""

from __future__ import annotations

from functools import lru_cache

from django.conf import settings
from intelliflow.llm.base import LLMClient

_override: LLMClient | None = None


@lru_cache(maxsize=1)
def _configured_client() -> LLMClient:
    if settings.LLM_PROVIDER == "anthropic":
        from intelliflow.llm.anthropic_client import AnthropicLLMClient

        return AnthropicLLMClient(
            settings.LLM_MODEL,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_retries=settings.LLM_MAX_RETRIES,
        )
    from intelliflow.llm.fake_client import FakeLLMClient

    return FakeLLMClient()


def get_llm_client() -> LLMClient:
    return _override or _configured_client()


def set_llm_client(client: LLMClient | None) -> None:
    """Swap the client (tests, or a per-environment override)."""
    global _override  # noqa: PLW0603 - explicit test/ops override hook
    _override = client
