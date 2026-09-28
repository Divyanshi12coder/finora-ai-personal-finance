"""Database engine, session factory and declarative base."""

from __future__ import annotations

import logging
from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


def _create_engine() -> Engine:
    url = settings.effective_database_url

    if settings.is_sqlite:
        if settings.DATABASE_URL:
            logger.info("Using SQLite at %s", url)
        else:
            logger.warning(
                "DATABASE_URL is not set - falling back to SQLite at %s. "
                "PostgreSQL is the supported target; set DATABASE_URL for parity.",
                url,
            )
        engine = create_engine(
            url,
            echo=settings.SQL_ECHO,
            future=True,
            connect_args={"check_same_thread": False},
        )

        # SQLite does not enforce foreign keys unless asked to. Without this the
        # ON DELETE CASCADE rules below are silently ignored in local dev.
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):  # pragma: no cover - driver glue
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    logger.info("Connecting to database %s", url.split("@")[-1])
    return create_engine(
        url,
        echo=settings.SQL_ECHO,
        future=True,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


engine: Engine = _create_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for scripts: commits on success, rolls back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all() -> None:
    """Create tables directly from the ORM metadata.

    Alembic migrations are the source of truth for schema changes; this helper
    exists for the test suite and for the SQLite dev fallback where running a
    migration chain for a throwaway database is unnecessary ceremony.
    """
    from app import models  # noqa: F401  (ensures every model is registered)

    Base.metadata.create_all(bind=engine)
