"""Migrations run from an empty database, match the ORM models, and downgrade cleanly."""

from __future__ import annotations

import os
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from alembic import command
from app.models import Base
from tests.conftest import _ADMIN_URL, _BASE

DB = os.environ.get("VSH_TEST_DB_NAME", "vanshavali_test") + "_migrations"
URL = f"{_BASE}/{DB}"


def _cfg() -> Config:
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", URL)
    return cfg


def test_upgrade_check_downgrade_roundtrip():
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{DB}"'))
    try:
        cfg = _cfg()
        command.upgrade(cfg, "head")
        engine = create_engine(URL)
        with engine.connect() as conn:
            diff = compare_metadata(
                MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata
            )
            assert diff == [], f"models and migrations differ: {diff}"
            # the append-only audit trigger exists
            assert (
                conn.execute(
                    text("SELECT count(*) FROM pg_trigger WHERE tgname = 'audit_event_no_update_delete'")
                ).scalar()
                == 1
            )
        command.downgrade(cfg, "base")
        with engine.connect() as conn:
            remaining = conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name <> 'alembic_version'"
                )
            ).scalar()
            assert remaining == 0
        command.upgrade(cfg, "head")
        engine.dispose()
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)'))
        admin.dispose()
