"""JSON Schemas for process maps and workflow definitions (validated with jsonschema)."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator


@cache
def load_schema(name: str) -> dict[str, Any]:
    text = resources.files(__package__).joinpath(f"{name}.schema.json").read_text(encoding="utf-8")
    schema: dict[str, Any] = json.loads(text)
    Draft202012Validator.check_schema(schema)
    return schema


@cache
def validator_for(name: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(name))


PROCESS_MAP = "process_map"
WORKFLOW = "workflow"
