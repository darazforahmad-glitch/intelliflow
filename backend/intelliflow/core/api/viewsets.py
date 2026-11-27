"""Base viewset for everything under /workspaces/<workspace_id>/."""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from intelliflow.core.api.permissions import IsWorkspaceMember, WorkspaceContext

UUID_REGEX = "[0-9a-fA-F-]{36}"
WORKSPACE_PREFIX = rf"workspaces/(?P<workspace_id>{UUID_REGEX})"


class WorkspaceScopedViewSet(viewsets.ViewSet):
    """Members can read; actions listed in `owner_actions` are for the owner only.
    The permission check stores the caller's workspace context in `self.ctx`."""

    permission_classes = [IsAuthenticated, IsWorkspaceMember]
    lookup_value_regex = UUID_REGEX
    owner_actions: set[str] = set()
    ctx: WorkspaceContext
