"""Shared catalogues for the builder UI: templates (REQ-AB-8), blocks and connector operations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.connectors.registry import CONNECTOR_CLASSES
from app.engine.blocks.registry import BLOCK_LIBRARY
from app.models import Template

router = APIRouter(tags=["catalog"])

BLOCK_DESCRIPTIONS = {
    "ai.classify": (
        "AI: sort the message",
        "Puts each message into one of your categories, e.g. order or question.",
    ),
    "ai.extract": (
        "AI: read the details",
        "Pulls fields such as name, items, address and amount out of a message.",
    ),
    "ai.draft_reply": (
        "AI: draft a reply",
        "Writes a short reply in the customer's language for you to approve.",
    ),
    "ai.summarize": ("AI: summarise", "Writes a short summary, e.g. of today's orders."),
    "condition": ("Check", "Continues only when a rule is true, e.g. the message is an order."),
    "approval": ("Approval", "Waits for you or your staff to approve, edit or reject."),
    "action": ("Action", "Does something in a connected app, e.g. add a row to Google Sheets."),
}


@router.get("/templates")
def list_templates(_user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    templates = db.scalars(
        select(Template)
        .where(Template.is_active.is_(True))
        .order_by(Template.category, Template.name)
    )
    return [
        {
            "id": str(t.id),
            "code": t.code,
            "name": t.name,
            "category": t.category,
            "description": t.description,
            "version": t.version,
            "required_connections": t.required_connections,
            "trigger_type": t.definition_json.get("trigger", {}).get("type"),
            "steps": [b.get("title") or b["key"] for b in t.definition_json.get("blocks", [])],
            "estimated_minutes_saved": (t.definition_json.get("settings") or {}).get(
                "estimated_minutes_saved"
            ),
        }
        for t in templates
    ]


@router.get("/blocks")
def list_blocks(_user: CurrentUser) -> list[dict[str, str]]:
    return [
        {
            "type": name,
            "label": BLOCK_DESCRIPTIONS[name][0],
            "description": BLOCK_DESCRIPTIONS[name][1],
        }
        for name in BLOCK_LIBRARY
    ]


@router.get("/connectors")
def list_connectors(_user: CurrentUser) -> list[dict[str, Any]]:
    return [
        {
            "provider": provider,
            "label": cls.label,
            "operations": [
                {
                    "name": op.name,
                    "label": op.label,
                    "writes": op.writes,
                    "customer_message": op.customer_message,
                    "required": list(op.required),
                }
                for op in cls.operations.values()
            ],
        }
        for provider, cls in CONNECTOR_CLASSES.items()
    ]
