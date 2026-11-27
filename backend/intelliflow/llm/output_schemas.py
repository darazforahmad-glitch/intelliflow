"""JSON schemas the language model must answer in (schema-first prompting, Section 5.4)."""

from __future__ import annotations

from typing import Any

from intelliflow.jsonschemas import load_schema

INTERVIEW_TURN: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "question", "language", "missing"],
    "properties": {
        "status": {"type": "string", "enum": ["need_more_detail", "enough_detail"]},
        "question": {
            "type": "string",
            "description": "The next question, or a short closing message",
        },
        "language": {"type": "string", "enum": ["en", "ur", "roman-ur"]},
        "missing": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["steps", "trigger", "actor", "app", "frequency", "duration"],
            },
        },
    },
}

DRAFT_REPLY: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text", "language"],
    "properties": {
        "text": {"type": "string", "maxLength": 1000},
        "language": {"type": "string", "enum": ["en", "ur", "roman-ur"]},
    },
}

SUMMARIZE: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text"],
    "properties": {"text": {"type": "string", "maxLength": 2000}},
}


def process_map() -> dict[str, Any]:
    return load_schema("process_map")


def workflow() -> dict[str, Any]:
    return load_schema("workflow")


def classify(labels: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["label", "confidence", "reason"],
        "properties": {
            "label": {"type": "string", "enum": labels},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reason": {"type": "string", "maxLength": 300},
        },
    }


_JSON_TYPES = {"string": "string", "number": "number", "integer": "integer", "boolean": "boolean"}


def extract(fields: list[dict[str, Any]]) -> dict[str, Any]:
    field_props = {
        f["name"]: {
            "anyOf": [
                {"type": _JSON_TYPES.get(f.get("type", "string"), "string")},
                {"type": "null"},
            ],
            "description": f.get("description", ""),
        }
        for f in fields
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["fields", "missing", "confidence"],
        "properties": {
            "fields": {
                "type": "object",
                "additionalProperties": False,
                "required": list(field_props),
                "properties": field_props,
            },
            "missing": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }
