"""BLOCK_LIBRARY: the only block types workflows may use (REQ-AB-1). Adding a block type
means adding a class here; the engine does not change (NFR extensibility)."""

from __future__ import annotations

from typing import Any

from app.engine.blocks.action import ActionBlock
from app.engine.blocks.ai import (
    AIClassifyBlock,
    AIDraftReplyBlock,
    AIExtractBlock,
    AISummarizeBlock,
)
from app.engine.blocks.approval import ApprovalBlock
from app.engine.blocks.base import Block
from app.engine.blocks.logic import ConditionBlock

BLOCK_LIBRARY: dict[str, type[Block]] = {
    cls.type: cls
    for cls in (
        AIClassifyBlock,
        AIExtractBlock,
        AIDraftReplyBlock,
        AISummarizeBlock,
        ConditionBlock,
        ApprovalBlock,
        ActionBlock,
    )
}


def build_block(spec: dict[str, Any]) -> Block:
    try:
        return BLOCK_LIBRARY[spec["type"]](spec)
    except KeyError as exc:
        raise ValueError(f"Unknown block type: {spec.get('type')}") from exc
