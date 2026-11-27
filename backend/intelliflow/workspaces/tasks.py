"""Retention (BR-7): a deleted workspace's data is permanently removed within 30 days."""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.db import transaction

from intelliflow.core.models import utcnow
from intelliflow.workspaces.models import Workspace


@shared_task(name="intelliflow.purge_deleted_workspaces")
def purge_deleted_workspaces() -> int:
    cutoff = utcnow() - timedelta(days=30)
    with transaction.atomic():
        expired = Workspace.objects.filter(deleted_at__isnull=False, deleted_at__lt=cutoff)
        count = expired.count()
        expired.delete()  # cascades to every row that belongs to the workspace
    return count
