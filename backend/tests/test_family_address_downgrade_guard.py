from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from alembic import command
from tests.test_migrations import _cfg
from tests.test_tradition_ownership_recovery import _drop, _fresh, _seed, _version

HEAD = "d4a8e6f1b209"
PREVIOUS = "c8f4a2d7e901"


def test_populated_reusable_address_downgrade_is_refused_atomically():
    admin, url = _fresh("_family_address_guard")
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, HEAD)
        engine = create_engine(url)
        family_id = uuid.uuid4()
        with engine.begin() as conn:
            ids = _seed(conn)
            conn.execute(
                text(
                    "INSERT INTO family_address "
                    "(id, tree_id, label, controller_membership_id, privacy_level, created_by) "
                    "VALUES (:id, :tree, 'Private home', :controller, 'ONLY_ME', :author)"
                ),
                {
                    "id": family_id,
                    "tree": ids["t"],
                    "controller": ids["m_author"],
                    "author": ids["author"],
                },
            )
        with pytest.raises(RuntimeError, match="lossy downgrade refused") as refused:
            command.downgrade(cfg, PREVIOUS)
        message = str(refused.value)
        assert "Nothing was changed" in message
        assert str(family_id) not in message and "Private home" not in message
        with engine.begin() as conn:
            assert _version(conn) == HEAD
            assert conn.execute(text("SELECT count(*) FROM family_address")).scalar_one() == 1
            conn.execute(text("DELETE FROM family_address"))
        command.downgrade(cfg, PREVIOUS)
        command.upgrade(cfg, HEAD)
        engine.dispose()
    finally:
        _drop(admin, url)
