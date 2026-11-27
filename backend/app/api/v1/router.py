"""Versioned REST API: every resource is a plural noun under /api/v1 (Section 5.5)."""

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    auth,
    automations,
    catalog,
    connections,
    dashboard,
    interviews,
    notifications,
    process_maps,
    runs,
    webhooks,
    workspaces,
)
from app.core.config import get_settings

api_router = APIRouter()
for module in (
    auth,
    workspaces,
    interviews,
    process_maps,
    automations,
    runs,
    connections,
    dashboard,
    notifications,
    webhooks,
    catalog,
    admin,
):
    api_router.include_router(module.router)

if get_settings().is_dev_like:
    from app.api.v1 import dev

    api_router.include_router(dev.router)
