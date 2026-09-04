"""Database engine and session management."""

from __future__ import annotations

import logging
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from anvaya.config import settings
from anvaya.migrations import apply_sqlite_migrations

_database_log_level = logging.DEBUG if settings.log_level.lower() == "debug" else logging.WARNING
logging.getLogger("sqlalchemy.engine").setLevel(_database_log_level)
logging.getLogger("sqlalchemy.pool").setLevel(_database_log_level)

engine = create_engine(
    settings.database_url,
    echo=_database_log_level == logging.DEBUG,
    connect_args={"check_same_thread": False} if settings.is_sqlite() else {},
)


def init_db() -> None:
    """Create all tables. Called on startup."""
    from anvaya.models import (  # noqa: F401
        agent_context,
        artifact_build,
        asset,
        audit,
        counterfactual,
        dataset,
        detection,
        execution,
        graph,
        incident,
        model_version,
        project,
        replay,
        rule,
        simulation,
        subagent,
        telemetry,
    )

    SQLModel.metadata.create_all(engine)

    apply_sqlite_migrations(engine)

    if settings.is_sqlite():
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def get_session_sync() -> Session:
    return Session(engine)
