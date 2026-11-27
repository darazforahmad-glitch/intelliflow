"""Celery application: task queue, workers and scheduler (Celery Beat) on Redis (Section 4.1).

celery -A config worker -Q intelliflow      celery -A config beat
"""

from __future__ import annotations

import os
from typing import Any

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("intelliflow")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.beat_schedule = {
    "approval-timeouts": {"task": "intelliflow.check_approval_timeouts", "schedule": 60.0},
    "scheduled-automations": {"task": "intelliflow.run_scheduled_automations", "schedule": 60.0},
    "poll-gmail": {"task": "intelliflow.poll_gmail", "schedule": 120.0},
    "refresh-tokens": {"task": "intelliflow.refresh_expiring_tokens", "schedule": 900.0},
    "purge-deleted-workspaces": {
        "task": "intelliflow.purge_deleted_workspaces",
        "schedule": crontab(hour=3, minute=17),
    },
}
app.autodiscover_tasks()


@setup_logging.connect
def _use_django_logging(**_kwargs: Any) -> None:
    """Keep Django's LOGGING (structured JSON) instead of Celery's own handlers."""
    from logging.config import dictConfig

    from django.conf import settings

    dictConfig(settings.LOGGING)
