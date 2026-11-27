"""Small helpers that keep JSON output identical to the original API contract."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from rest_framework import serializers

_DATETIME = serializers.DateTimeField()


def dec(value: Decimal | None) -> str | None:
    """Decimals are sent as strings, exactly as stored (e.g. "120.0", "45.60")."""
    return None if value is None else str(value)


def dt(value: datetime | None) -> str | None:
    """ISO 8601 in UTC with a trailing Z."""
    return None if value is None else _DATETIME.to_representation(value)


def uid(value: Any) -> str | None:
    return None if value is None else str(value)
