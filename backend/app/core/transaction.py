"""Run side effects only after the database transaction commits.

Enqueueing a Celery task or publishing an SSE event *inside* a transaction is a
classic race: the worker may read the row before it is committed (or after it was
rolled back). `on_commit` defers the callback until the commit has succeeded.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy import event
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
_KEY = "intelliflow_on_commit"


def on_commit(session: Session, callback: Callable[[], None]) -> None:
    session.info.setdefault(_KEY, []).append(callback)


@event.listens_for(Session, "after_commit")
def _run_callbacks(session: Session) -> None:
    callbacks: list[Callable[[], None]] = session.info.pop(_KEY, [])
    for callback in callbacks:
        try:
            callback()
        except Exception:
            logger.exception("on_commit callback failed")


@event.listens_for(Session, "after_rollback")
def _discard_callbacks(session: Session) -> None:
    session.info.pop(_KEY, None)
