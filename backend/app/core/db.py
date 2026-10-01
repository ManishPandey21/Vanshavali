"""Database engine and session management, including row-level-security tree binding (ADR-0002)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

RLS_SETTING = "app.tree_id"
_TREE_KEY = "rls_tree_id"


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    connect_args: dict[str, Any] = {}
    if settings.statement_timeout_ms:
        # server-side guard against runaway queries (PRS §49, threat T14)
        connect_args["options"] = f"-c statement_timeout={int(settings.statement_timeout_ms)}"
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
        connect_args=connect_args,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_s,
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def bind_tree(db: Session, tree_id: uuid.UUID | str) -> None:
    """Scope this session to one tree for PostgreSQL row-level security.

    The setting is transaction-local (``set_config(..., true)``), so it can never leak to another
    request through the connection pool; ``_apply_tree`` re-applies it at the start of every later
    transaction of the same session (e.g. after a mid-job commit).
    """
    db.info[_TREE_KEY] = str(tree_id)
    db.execute(text("SELECT set_config(:k, :v, true)"), {"k": RLS_SETTING, "v": str(tree_id)})


@event.listens_for(Session, "after_begin")
def _apply_tree(session: Session, transaction: Any, connection: Any) -> None:
    tree_id = session.info.get(_TREE_KEY)
    if tree_id:
        connection.exec_driver_sql("SELECT set_config(%s, %s, true)", (RLS_SETTING, tree_id))


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request; commit on success, rollback on error."""
    db = get_sessionmaker()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
