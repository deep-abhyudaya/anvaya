"""Lightweight SQLite schema migrations.

SQLModel's ``create_all`` only creates missing tables; it does not add
new columns to existing tables. For local SQLite development this module
applies idempotent migrations so that evolving models do not break
pre-existing databases.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel

from anvaya.config import settings
from anvaya.logging import get_logger

logger = get_logger("anvaya.db.migrations")


def _default_for_column(col: Any) -> str | None:
    """Return a SQL default expression for a missing non-nullable column."""

    if col.default is not None:
        default = getattr(col.default, "arg", None)
        if default is None:
            return None
        if isinstance(default, (int, float, bool)):
            return str(default)
        if isinstance(default, str):
            return f"'{default.replace(chr(39), chr(39) * 2)}'"
        if isinstance(default, datetime.datetime):
            return f"'{default.isoformat()}'"
        return None

    type_name = str(col.type).upper()
    if "BOOL" in type_name:
        return "0"
    if "INT" in type_name:
        return "0"
    if (
        "FLOAT" in type_name
        or "DOUBLE" in type_name
        or "REAL" in type_name
        or "NUMERIC" in type_name
    ):
        return "0.0"
    if "DATETIME" in type_name:
        return "CURRENT_TIMESTAMP"
    if "JSON" in type_name:
        return "'[]'"
    return "''"


def apply_sqlite_migrations(engine: Engine) -> None:
    """Add missing columns to existing SQLite tables for all SQLModel models.

    This is intentionally conservative: it only adds columns and only runs
    against SQLite. Production PostgreSQL deployments should use a proper
    migration tool such as Alembic.
    """
    if not settings.is_sqlite():
        return

    inspector = inspect(engine)
    with engine.begin() as conn:
        for table_name, table in SQLModel.metadata.tables.items():
            if not inspector.has_table(table_name):
                continue

            existing = {c["name"] for c in inspector.get_columns(table_name)}
            for col in table.columns:
                if col.name in existing:
                    continue

                type_str = str(col.type.compile(dialect=engine.dialect))
                parts = [f"ALTER TABLE {table_name} ADD COLUMN {col.name} {type_str}"]

                if not col.nullable:
                    default = _default_for_column(col)
                    if default is not None:
                        parts.append(f"DEFAULT {default}")
                    parts.append("NOT NULL")

                sql = " ".join(parts)
                try:
                    conn.execute(text(sql))
                    logger.info("applied_migration_add_column", table=table_name, column=col.name)
                except Exception:
                    logger.warning(
                        "migration_add_column_failed",
                        table=table_name,
                        column=col.name,
                        sql=sql,
                    )
