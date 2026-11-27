"""Celery application: task queue, workers and scheduler (Celery Beat) on Redis (Section 4.1)."""

from __future__ import annotations

from typing import Any

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("intelliflow", include=["app.worker.tasks"])
celery_app.conf.update(
    broker_url=settings.redis_url or "memory://",
    result_backend=None,
    task_ignore_result=True,
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=False,
    task_acks_late=True,  # a crashed worker's task is redelivered
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_default_queue="intelliflow",
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "approval-timeouts": {"task": "intelliflow.check_approval_timeouts", "schedule": 60.0},
        "scheduled-automations": {
            "task": "intelliflow.run_scheduled_automations",
            "schedule": 60.0,
        },
        "poll-gmail": {"task": "intelliflow.poll_gmail", "schedule": 120.0},
        "refresh-tokens": {"task": "intelliflow.refresh_expiring_tokens", "schedule": 900.0},
        "purge-deleted-workspaces": {
            "task": "intelliflow.purge_deleted_workspaces",
            "schedule": crontab(hour=3, minute=17),
        },
    },
)


@setup_logging.connect
def _configure_logging(**_kwargs: Any) -> None:
    from app.core.logging import configure_logging

    configure_logging(settings.log_level)
