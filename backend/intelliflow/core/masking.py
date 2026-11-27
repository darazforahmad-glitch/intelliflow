"""Personal-data masking for logs and step-run records (REQ-WE-6, SEC-8)."""

from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEYS = frozenset(
    {
        "name",
        "customer_name",
        "full_name",
        "first_name",
        "last_name",
        "contact_name",
        "phone",
        "phone_number",
        "mobile",
        "from",
        "to",
        "wa_id",
        "recipient",
        "email",
        "email_address",
        "address",
        "customer_address",
        "delivery_address",
        "cnic",
        "account_number",
        "iban",
        "card_number",
        "password",
        "access_token",
        "refresh_token",
        "token",
        "secret",
    }
)
SECRET_KEYS = frozenset({"password", "access_token", "refresh_token", "token", "secret"})

_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\s-]{5,}\d)(?!\w)")


def _mask_phone(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(1))
    if len(digits) < 7:
        return match.group(1)
    return f"{digits[:4]}{'*' * (len(digits) - 7)}{digits[-3:]}"


def mask_text(text: str) -> str:
    """Mask e-mail addresses and phone-number-like digit runs inside free text."""
    text = _EMAIL_RE.sub(r"\1***\2", text)
    return _PHONE_RE.sub(_mask_phone, text)


def _mask_scalar(key: str, value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if key in SECRET_KEYS:
        return "***"
    text = str(value)
    if "@" in text:
        return _EMAIL_RE.sub(r"\1***\2", text)
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 7 and len(digits) >= len(text.replace(" ", "")) - 2:
        return f"{digits[:4]}{'*' * max(len(digits) - 7, 1)}{digits[-3:]}"
    if len(text) <= 2:
        return "*" * len(text)
    return text[:2] + "*" * min(len(text) - 2, 8)


def mask_pii(value: Any, key: str = "") -> Any:
    """Return a deep copy of `value` with personal data masked."""
    if isinstance(value, dict):
        return {k: mask_pii(v, str(k).lower()) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_pii(v, key) for v in value]
    if key in SENSITIVE_KEYS and not isinstance(value, dict | list):
        return _mask_scalar(key, value)
    if isinstance(value, str):
        return mask_text(value)
    return value
