"""Database engine and session management (SQLAlchemy 2.x, synchronous).

A single synchronous code path is shared by the API (sandbox test runs) and the
Celery workers (live runs), so blocks behave identically in both (Section 4.9).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


class Database:
    def __init__(self, url: str, *, echo: bool = False) -> None:
        kwargs: dict[str, Any] = {"echo": echo, "future": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in url or url.endswith("sqlite://"):
                kwargs["poolclass"] = StaticPool
        else:
            kwargs.update(pool_pre_ping=True, pool_size=10, max_overflow=20)
        self.url = url
        self.engine: Engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", _enable_sqlite_foreign_keys)
        self.session_factory = sessionmaker(
            bind=self.engine, autoflush=False, expire_on_commit=False, class_=Session
        )

    @property
    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite")


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


_database: Database | None = None


def init_database(url: str | None = None, *, echo: bool | None = None) -> Database:
    """(Re)initialise the global database. Tests call this with their own URL."""
    global _database  # noqa: PLW0603 - process-wide engine singleton
    settings = get_settings()
    if _database is not None:
        _database.engine.dispose()
    _database = Database(
        url or settings.database_url,
        echo=settings.database_echo if echo is None else echo,
    )
    return _database


def get_database() -> Database:
    if _database is None:
        return init_database()
    return _database


def new_session() -> Session:
    return get_database().session_factory()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for workers and scripts: commit on success, rollback on error."""
    session = new_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
