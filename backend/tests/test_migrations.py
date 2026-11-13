"""Migrations run from an empty database, match the ORM models, and downgrade cleanly."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
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


def test_legacy_profile_details_are_encrypted_verbatim_and_restore_on_downgrade():
    """c8f4a2d7e901: plaintext legacy values move once into VAULT records and can safely roll back."""
    import uuid

    from app.core.encrypted_json import decrypt_json

    db = DB + "_profile_details"
    url = f"{_BASE}/{db}"
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{db}"'))
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "a4d7e2c9b153")
        engine = create_engine(url)
        tree_id, person_id = uuid.uuid4(), uuid.uuid4()
        address = "घर १२, Secret Lane — जैसा दर्ज है"
        contact = "पुराना संपर्क: +91 98xx"
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO tree (id, name, slug) VALUES (:id, 'Family', :slug)"),
                {"id": tree_id, "slug": str(tree_id)},
            )
            connection.execute(
                text(
                    "INSERT INTO person (id, tree_id, preferred_display_name, residential_address, contact_info) "
                    "VALUES (:id, :tree, 'Legacy Person', :address, :contact)"
                ),
                {"id": person_id, "tree": tree_id, "address": address, "contact": contact},
            )
        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            person = connection.execute(
                text("SELECT residential_address, contact_info FROM person WHERE id = :id"),
                {"id": person_id},
            ).one()
            assert person == (None, None)
            address_row = connection.execute(
                text(
                    "SELECT id, payload_enc, purpose, status, is_primary_current "
                    "FROM person_address WHERE person_id = :id AND legacy_imported"
                ),
                {"id": person_id},
            ).one()
            contact_row = connection.execute(
                text(
                    "SELECT id, value_enc FROM person_contact_method "
                    "WHERE person_id = :id AND legacy_imported"
                ),
                {"id": person_id},
            ).one()
            assert address not in address_row.payload_enc and contact not in contact_row.value_enc
            assert (address_row.purpose, address_row.status, address_row.is_primary_current) == (
                "unknown",
                "unknown",
                False,
            )
            assert (
                decrypt_json(address_row.payload_enc, f"person-address:{address_row.id}")["as_recorded"]
                == address
            )
            assert decrypt_json(contact_row.value_enc, f"person-contact:{contact_row.id}")["value"] == contact
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE person_address SET revision = 2 WHERE person_id = :id"),
                {"id": person_id},
            )
        with pytest.raises(RuntimeError, match="cannot be represented"):
            command.downgrade(cfg, "a4d7e2c9b153")
        with engine.connect() as connection:
            # Alembic runs the requested multi-revision downgrade transactionally. Once D is the
            # head, c8's refusal rolls the preceding D downgrade back as well.
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "d4a8e6f1b209"
            )
            assert (
                connection.execute(
                    text("SELECT residential_address FROM person WHERE id = :id"), {"id": person_id}
                ).scalar()
                is None
            )
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE person_address SET revision = 1 WHERE person_id = :id"),
                {"id": person_id},
            )
        command.downgrade(cfg, "a4d7e2c9b153")
        with engine.connect() as connection:
            restored = connection.execute(
                text("SELECT residential_address, contact_info FROM person WHERE id = :id"),
                {"id": person_id},
            ).one()
            assert restored == (address, contact)
        engine.dispose()
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
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


def test_ownership_offers_column_and_downgrade():
    """e4b8c2d6f913: pending offers on documents, traditions and collections lapse with the member."""
    import uuid

    db = DB + "_offers"
    url = f"{_BASE}/{db}"
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{db}"'))
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "b5c1e7a93d42")
        engine = create_engine(url)
        t, u1, u2, m1, m2, e = (uuid.uuid4() for _ in range(6))
        with engine.begin() as conn:
            for uid, email in ((u1, "a@example.com"), (u2, "b@example.com")):
                conn.execute(
                    text(
                        "INSERT INTO app_user (id, email, password_hash, display_name) VALUES (:id, :e, 'x', 'U')"
                    ),
                    {"id": uid, "e": email},
                )
            conn.execute(
                text("INSERT INTO tree (id, name, slug) VALUES (:id, 'T', :s)"), {"id": t, "s": str(t)}
            )
            for mid, uid in ((m1, u1), (m2, u2)):
                conn.execute(
                    text(
                        "INSERT INTO tree_membership (id, tree_id, user_id, roles) VALUES (:id, :t, :u, ARRAY['CONTRIBUTOR'])"
                    ),
                    {"id": mid, "t": t, "u": uid},
                )
            conn.execute(
                text(
                    "INSERT INTO tradition_entry (id, tree_id, kind, title, privacy_level, created_by, owner_membership_id)"
                    " VALUES (:id, :t, 'recipe', 'R', 'ONLY_ME', :u, :m)"
                ),
                {"id": e, "t": t, "u": u1, "m": m1},
            )
        command.upgrade(cfg, "e4b8c2d6f913")
        with engine.begin() as conn:
            for table in ("document", "tradition_entry", "photo_collection"):
                cols = set(
                    conn.execute(
                        text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
                        {"t": table},
                    ).scalars()
                )
                assert "pending_owner_membership_id" in cols, table
            conn.execute(text("UPDATE tradition_entry SET pending_owner_membership_id = :m"), {"m": m2})
            conn.execute(text("DELETE FROM tree_membership WHERE id = :m"), {"m": m2})  # the member leaves
            row = conn.execute(
                text("SELECT owner_membership_id, pending_owner_membership_id FROM tradition_entry")
            ).one()
            assert (row.owner_membership_id, row.pending_owner_membership_id) == (
                m1,
                None,
            )  # the offer lapsed
        command.downgrade(cfg, "b5c1e7a93d42")
        with engine.connect() as conn:
            for table in ("document", "tradition_entry", "photo_collection"):
                cols = set(
                    conn.execute(
                        text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
                        {"t": table},
                    ).scalars()
                )
                assert "pending_owner_membership_id" not in cols, table
            assert conn.execute(text("SELECT owner_membership_id FROM tradition_entry")).scalar() == m1
        engine.dispose()
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        admin.dispose()


def test_erasure_marker_backfill_is_audit_scoped_and_downgrade_is_lossless():
    """A display name alone is not an erasure signal; older audited erasures are."""
    import uuid

    db_name = DB + "_erasure"
    url = f"{_BASE}/{db_name}"
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{db_name}"'))
    engine = None
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "d4a8e6f1b209")
        engine = create_engine(url)
        tree_id = uuid.uuid4()
        erased_id, named_id = uuid.uuid4(), uuid.uuid4()
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO tree (id, name, slug) VALUES (:id, 'Legacy tree', :slug)"),
                {"id": tree_id, "slug": str(tree_id)},
            )
            for pid in (erased_id, named_id):
                connection.execute(
                    text(
                        "INSERT INTO person (id, tree_id, preferred_display_name) "
                        "VALUES (:pid, :tree, 'Erased person')"
                    ),
                    {"pid": pid, "tree": tree_id},
                )
            connection.execute(
                text(
                    "INSERT INTO audit_event (id, tree_id, target_id, target_type, action) "
                    "VALUES (:id, :tree, :target, 'person', 'person.erased')"
                ),
                {"id": uuid.uuid4(), "tree": tree_id, "target": erased_id},
            )
        command.upgrade(cfg, "head")
        with engine.connect() as connection:
            records = dict(
                connection.execute(
                    text(
                        "SELECT id, erased_at FROM person WHERE tree_id = :tree"
                    ),
                    {"tree": tree_id},
                ).all()
            )
            assert records[erased_id] is not None
            assert records[named_id] is None
        with pytest.raises(RuntimeError, match="lossy downgrade refused"):
            command.downgrade(cfg, "d4a8e6f1b209")
    finally:
        if engine is not None:
            engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        admin.dispose()
