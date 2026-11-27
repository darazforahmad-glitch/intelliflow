"""Helpers to adapt our validation JSON schemas for provider-side structured outputs."""

from __future__ import annotations

import copy
from typing import Any

# Keywords that provider-side structured outputs do not support; they are still
# enforced locally by jsonschema after the response arrives.
_UNSUPPORTED = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minProperties",
    "maxProperties",
    "default",
    "examples",
    "$schema",
    "$id",
    "title",
}
_SUPPORTED_FORMATS = {
    "date-time",
    "time",
    "date",
    "duration",
    "email",
    "hostname",
    "uri",
    "ipv4",
    "ipv6",
    "uuid",
}


def to_structured_output_schema(schema: dict[str, Any]) -> dict[str, Any]:
    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            out: dict[str, Any] = {}
            for key, value in node.items():
                if key in _UNSUPPORTED:
                    continue
                if key == "format" and value not in _SUPPORTED_FORMATS:
                    continue
                out[key] = walk(value)
            if out.get("type") == "object" or "properties" in out:
                out["additionalProperties"] = False
            return out
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    return walk(copy.deepcopy(schema))
