"""Block/connector failures. Messages are written for the business owner (plain language)."""

from __future__ import annotations

from typing import Any


class BlockError(Exception):
    def __init__(self, message: str, *, code: str = "block_failed", details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details


class TransientBlockError(BlockError):
    """Temporary failure (network, rate limit, provider outage): the engine retries with backoff."""


class PermanentBlockError(BlockError):
    """Retrying will not help (bad data, missing permission): the run fails."""


class ConnectionUnavailableError(PermanentBlockError):
    """A connection the automation needs is missing or broken (REQ-WE-7)."""


class WindowClosedError(PermanentBlockError):
    """WhatsApp's 24-hour customer service window is closed (REQ-WE-8, BR-4)."""

    def __init__(self, message: str, *, to: str, text: str | None = None) -> None:
        super().__init__(message, code="whatsapp_window_closed")
        self.to = to
        self.text = text
