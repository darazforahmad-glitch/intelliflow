"""LLM access through a provider-agnostic client (Section 5.2)."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.llm.base import LLMClient

_override: LLMClient | None = None


@lru_cache(maxsize=1)
def _configured_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        from app.llm.anthropic_client import AnthropicLLMClient

        return AnthropicLLMClient(
            settings.llm_model,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    from app.llm.fake_client import FakeLLMClient

    return FakeLLMClient()


def get_llm_client() -> LLMClient:
    return _override or _configured_client()


def set_llm_client(client: LLMClient | None) -> None:
    """Swap the client (tests, or a per-environment override)."""
    global _override  # noqa: PLW0603 - explicit test/ops override hook
    _override = client
