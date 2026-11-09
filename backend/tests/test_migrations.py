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


def test_orphaned_access_grants_are_deleted():
    """7b3e9d2c4f61: grants left behind by removed members are deleted; members' grants stay."""
    import uuid

    db = DB + "_grants"
    url = f"{_BASE}/{db}"
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{db}"'))
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "6a1d9c3e5f27")
        engine = create_engine(url)
        tree_id, other_tree = uuid.uuid4(), uuid.uuid4()
        member, leaver = uuid.uuid4(), uuid.uuid4()
        doc = uuid.uuid4()
        with engine.begin() as conn:
            for uid, email in ((member, "m@example.com"), (leaver, "l@example.com")):
                conn.execute(
                    text(
                        "INSERT INTO app_user (id, email, password_hash, display_name) "
                        "VALUES (:id, :e, 'x', 'U')"
                    ),
                    {"id": uid, "e": email},
                )
            for tid in (tree_id, other_tree):
                conn.execute(
                    text("INSERT INTO tree (id, name, slug) VALUES (:id, 'T', :s)"),
                    {"id": tid, "s": str(tid)},
                )
            # member belongs to tree_id; leaver belongs only to other_tree
            for mid, uid, tid in ((uuid.uuid4(), member, tree_id), (uuid.uuid4(), leaver, other_tree)):
                conn.execute(
                    text(
                        "INSERT INTO tree_membership (id, tree_id, user_id, roles) "
                        "VALUES (:id, :t, :u, ARRAY['VIEWER'])"
                    ),
                    {"id": mid, "t": tid, "u": uid},
                )
            kept, orphan = uuid.uuid4(), uuid.uuid4()
            for gid, uid in ((kept, member), (orphan, leaver)):
                conn.execute(
                    text(
                        "INSERT INTO access_grant (id, tree_id, user_id, resource_type, resource_id, permission) "
                        "VALUES (:id, :t, :u, 'document', :r, 'view')"
                    ),
                    {"id": gid, "t": tree_id, "u": uid, "r": doc},
                )
        command.upgrade(cfg, "7b3e9d2c4f61")
        with engine.connect() as conn:
            ids = set(conn.execute(text("SELECT id FROM access_grant")).scalars())
        assert ids == {kept}  # a membership in another tree does not keep a grant alive
        command.downgrade(cfg, "6a1d9c3e5f27")  # no-op downgrade runs
        with engine.connect() as conn:
            assert set(conn.execute(text("SELECT id FROM access_grant")).scalars()) == {kept}
        engine.dispose()
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        admin.dispose()


def test_access_grants_move_onto_memberships():
    """9c4f2a7d1e83: grants are backfilled onto the membership; orphans go; downgrade restores user_id."""
    import uuid

    db = DB + "_grant_membership"
    url = f"{_BASE}/{db}"
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{db}"'))
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "7b3e9d2c4f61")
        engine = create_engine(url)
        tree_id, member, leaver, membership = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        kept, orphan = uuid.uuid4(), uuid.uuid4()
        with engine.begin() as conn:
            for uid, email in ((member, "m@example.com"), (leaver, "l@example.com")):
                conn.execute(
                    text(
                        "INSERT INTO app_user (id, email, password_hash, display_name) VALUES (:id, :e, 'x', 'U')"
                    ),
                    {"id": uid, "e": email},
                )
            conn.execute(
                text("INSERT INTO tree (id, name, slug) VALUES (:id, 'T', :s)"),
                {"id": tree_id, "s": str(tree_id)},
            )
            conn.execute(
                text(
                    "INSERT INTO tree_membership (id, tree_id, user_id, roles) VALUES (:id, :t, :u, ARRAY['VIEWER'])"
                ),
                {"id": membership, "t": tree_id, "u": member},
            )
            # an orphan written after 7b3e9d2c4f61 ran (the leaver has no membership)
            for gid, uid in ((kept, member), (orphan, leaver)):
                conn.execute(
                    text(
                        "INSERT INTO access_grant (id, tree_id, user_id, resource_type, resource_id, permission) "
                        "VALUES (:id, :t, :u, 'document', :r, 'view')"
                    ),
                    {"id": gid, "t": tree_id, "u": uid, "r": uuid.uuid4()},
                )
        command.upgrade(cfg, "9c4f2a7d1e83")
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT id, membership_id FROM access_grant")).all()
        assert [(r.id, r.membership_id) for r in rows] == [(kept, membership)]
        with engine.begin() as conn:  # deleting the membership deletes the grant
            conn.execute(text("DELETE FROM tree_membership WHERE id = :id"), {"id": membership})
            assert conn.execute(text("SELECT count(*) FROM access_grant")).scalar() == 0
        command.downgrade(cfg, "7b3e9d2c4f61")
        with engine.connect() as conn:
            cols = set(
                conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns WHERE table_name = 'access_grant'"
                    )
                ).scalars()
            )
        assert "membership_id" not in cols and "user_id" in cols
        engine.dispose()
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        admin.dispose()


def test_record_owners_are_backfilled_and_downgrade_maps_the_new_levels():
    """b5e8d1f3a2c6: owner from created_by while still a member; ONLY_ME/SELECTED_MEMBERS map back."""
    import uuid

    db = DB + "_record_owners"
    url = f"{_BASE}/{db}"
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{db}"'))
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "9c4e2a7d5b18")
        engine = create_engine(url)
        tree_id, member, leaver, membership = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        kept, orphan, entry = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        with engine.begin() as conn:
            for uid, email in ((member, "m@example.com"), (leaver, "l@example.com")):
                conn.execute(
                    text(
                        "INSERT INTO app_user (id, email, password_hash, display_name) VALUES (:id, :e, 'x', 'U')"
                    ),
                    {"id": uid, "e": email},
                )
            conn.execute(
                text("INSERT INTO tree (id, name, slug) VALUES (:id, 'T', :s)"),
                {"id": tree_id, "s": str(tree_id)},
            )
            conn.execute(
                text(
                    "INSERT INTO tree_membership (id, tree_id, user_id, roles) VALUES (:id, :t, :u, ARRAY['VIEWER'])"
                ),
                {"id": membership, "t": tree_id, "u": member},
            )
            for did, uid in ((kept, member), (orphan, leaver)):
                conn.execute(
                    text(
                        "INSERT INTO document (id, tree_id, category, storage_class, title, original_filename,"
                        " mime_type, size_bytes, checksum_sha256, storage_key, encryption_key_id, privacy_level,"
                        " scan_status, ocr_status, extraction_status, preview_status, created_by)"
                        " VALUES (:id, :t, 'photo', 'STANDARD', 'D', 'd.png', 'image/png', 1, 'x',"
                        " :k, 'STANDARD', 'TREE_MEMBERS', 'clean', 'not_requested', 'not_requested',"
                        " 'not_requested', :u)"
                    ),
                    {"id": did, "t": tree_id, "k": str(did), "u": uid},
                )
            conn.execute(
                text(
                    "INSERT INTO tradition_entry (id, tree_id, kind, title, created_by) VALUES (:id, :t, 'recipe', 'R', :u)"
                ),
                {"id": entry, "t": tree_id, "u": member},
            )
        command.upgrade(cfg, "b5e8d1f3a2c6")
        with engine.begin() as conn:
            owners = dict(conn.execute(text("SELECT id, owner_membership_id FROM document")).all())
            assert owners == {kept: membership, orphan: None}
            assert (
                conn.execute(text("SELECT owner_membership_id FROM tradition_entry")).scalar() == membership
            )
            conn.execute(text("UPDATE document SET privacy_level = 'ONLY_ME' WHERE id = :id"), {"id": kept})
            conn.execute(
                text("UPDATE document SET privacy_level = 'SELECTED_MEMBERS' WHERE id = :id"), {"id": orphan}
            )
            conn.execute(text("UPDATE tradition_entry SET privacy_level = 'ONLY_ME'"))
        command.downgrade(cfg, "9c4e2a7d5b18")
        with engine.connect() as conn:
            levels = dict(conn.execute(text("SELECT id, privacy_level FROM document")).all())
            assert levels == {kept: "PRIVATE_SELF", orphan: "CUSTOM"}
            assert conn.execute(text("SELECT privacy_level FROM tradition_entry")).scalar() == "PRIVATE_SELF"
        engine.dispose()
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        admin.dispose()
