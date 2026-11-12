"""Guarded downgrades for documents, photo collections and takedown (migration a4d7e2c9b153).

The downgrades of 3f6a8c1d2e94 (record sharing), b5c1e7a93d42 (photo collections) and d9b4f2c6a713
(record takedown) widen or discard access: Only me documents become readable by the tree owner,
Selected members by admins, collections and their grants are deleted, and every suspended record
becomes readable again. While any row they would affect exists, a downgrade that reaches them is
refused before anything changes, with counts only; one that stops above them is allowed.
"""

from __future__ import annotations

import io
import uuid
from contextlib import redirect_stdout
from typing import Any

import pytest
from sqlalchemy import create_engine, text

from alembic import command
from tests.test_migrations import _cfg
from tests.test_tradition_ownership_recovery import _drop, _entry, _fresh, _orphan, _seed, _version

GUARD_REVISION = "a4d7e2c9b153"
DOCUMENTS = "3f6a8c1d2e94"  # its downgrade: ONLY_ME → PRIVATE_SELF, SELECTED_MEMBERS → CUSTOM, owner dropped
COLLECTIONS = "b5c1e7a93d42"  # its downgrade: collection grants deleted, tables dropped
TAKEDOWN = "d9b4f2c6a713"  # its downgrade: suspended_at dropped, every suspension lifted


def _doc(conn: Any, ids: dict[str, uuid.UUID], level: str = "TREE_MEMBERS", **cols: Any) -> uuid.UUID:
    did = uuid.uuid4()
    values = {
        "id": did,
        "tree_id": ids["t"],
        "category": "letter",
        "storage_class": "STANDARD",
        "title": "Chitthi",
        "original_filename": "c.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 1,
        "checksum_sha256": "0" * 64,
        "storage_key": f"k/{did}",
        "encryption_key_id": "local",
        "privacy_level": level,
        "scan_status": "clean",
        "ocr_status": "not_requested",
        "extraction_status": "not_requested",
        "preview_status": "not_requested",
        "created_by": ids["author"],
        "owner_membership_id": ids["m_author"],
        **cols,
    }
    conn.execute(
        text(f"INSERT INTO document ({', '.join(values)}) VALUES ({', '.join(':' + k for k in values)})"),
        values,
    )
    return did


def _collection(conn: Any, ids: dict[str, uuid.UUID]) -> uuid.UUID:
    cid = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO photo_collection (id, tree_id, title, privacy_level, owner_membership_id, created_by) "
            "VALUES (:id, :t, 'Shaadi', 'TREE_MEMBERS', :o, :u)"
        ),
        {"id": cid, "t": ids["t"], "o": ids["m_author"], "u": ids["author"]},
    )
    return cid


def _grant(conn: Any, ids: dict[str, uuid.UUID], resource: str, rid: uuid.UUID) -> None:
    conn.execute(
        text(
            "INSERT INTO access_grant (id, tree_id, membership_id, user_id, resource_type, resource_id, permission) "
            "VALUES (:id, :t, :m, :u, :r, :rid, 'view')"
        ),
        {
            "id": uuid.uuid4(),
            "t": ids["t"],
            "m": ids["m_cousin"],
            "u": ids["cousin"],
            "r": resource,
            "rid": rid,
        },
    )


def _suspend(conn: Any, ids: dict[str, uuid.UUID], did: uuid.UUID, status: str = "active") -> None:
    rid = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO record_report (id, tree_id, reference, resource_type, resource_id, reason, status) "
            "VALUES (:id, :t, :ref, 'document', :d, 'privacy', 'actioned')"
        ),
        {"id": rid, "t": ids["t"], "ref": uuid.uuid4().hex[:12], "d": did},
    )
    conn.execute(
        text(
            "INSERT INTO record_suspension (id, tree_id, report_id, resource_type, resource_id, status) "
            "VALUES (:id, :t, :r, 'document', :d, :s)"
        ),
        {"id": uuid.uuid4(), "t": ids["t"], "r": rid, "d": did, "s": status},
    )
    if status == "active":
        conn.execute(text("UPDATE document SET suspended_at = now() WHERE id = :d"), {"d": did})


def _snapshot(conn: Any) -> dict[str, Any]:
    """Everything the guarded downgrades would change (compared before and after a refusal)."""
    return {
        "documents": conn.execute(
            text(
                "SELECT id, privacy_level, owner_membership_id, audience_branch_id, allow_download, suspended_at "
                "FROM document ORDER BY id"
            )
        ).all(),
        "grants": conn.execute(text("SELECT id, resource_type FROM access_grant ORDER BY id")).all(),
        "collections": conn.execute(text("SELECT id FROM photo_collection ORDER BY id")).all(),
        "suspensions": conn.execute(text("SELECT id, status FROM record_suspension ORDER BY id")).all(),
    }


def _arrange(conn: Any, ids: dict[str, uuid.UUID], case: str) -> str:
    """Seed one lossy case; return the lowest revision a downgrade may still stop at."""
    if case == "active_suspension":
        _suspend(conn, ids, _doc(conn, ids))
        return TAKEDOWN
    if case == "collection":
        _collection(conn, ids)
        return COLLECTIONS
    if case == "collection_grant":
        _grant(conn, ids, "collection", _collection(conn, ids))
        return COLLECTIONS
    if case == "only_me_document":
        _doc(conn, ids, "ONLY_ME")
    elif case == "selected_members_document":
        _doc(conn, ids, "SELECTED_MEMBERS")
    elif case == "document_grant":
        _grant(conn, ids, "document", _doc(conn, ids, "CUSTOM"))
    elif case == "selected_branch_document":
        bid = uuid.uuid4()
        conn.execute(
            text("INSERT INTO family_branch (id, tree_id, name) VALUES (:id, :t, 'Mama ka parivar')"),
            {"id": bid, "t": ids["t"]},
        )
        _doc(conn, ids, "FAMILY_BRANCH", audience_branch_id=bid)
    elif case == "download_off_document":
        _doc(conn, ids, allow_download=False)
    elif case == "transferred_document":
        _doc(conn, ids, owner_membership_id=ids["m_cousin"])  # the author gave it to the cousin
    elif case == "orphan_author_back":
        did = _doc(conn, ids, created_by=ids["leaver"], owner_membership_id=ids["m_leaver"])
        conn.execute(text("DELETE FROM tree_membership WHERE id = :m"), {"m": ids["m_leaver"]})
        assert (
            conn.execute(text("SELECT owner_membership_id FROM document WHERE id = :d"), {"d": did}).scalar()
            is None
        )
        conn.execute(
            text(
                "INSERT INTO tree_membership (id, tree_id, user_id, roles) VALUES (:id, :t, :u, ARRAY['VIEWER'])"
            ),
            {"id": uuid.uuid4(), "t": ids["t"], "u": ids["leaver"]},
        )
    else:  # pragma: no cover - parametrisation typo
        raise AssertionError(case)
    return DOCUMENTS


CASES = [
    "active_suspension",
    "collection",
    "collection_grant",
    "only_me_document",
    "selected_members_document",
    "document_grant",
    "selected_branch_document",
    "download_off_document",
    "transferred_document",
    "orphan_author_back",
]


@pytest.mark.parametrize("case", CASES)
def test_a_lossy_record_downgrade_is_refused_atomically(case):
    """Every target that would run the lossy downgrade is refused (explicit revision below it,
    ``base`` and the relative ``-1``, which fails closed); ``alembic_version`` and the data are
    unchanged, and the error names counts only. A downgrade that stops at the guarded revision is
    allowed and the upgrade re-runs."""
    admin, url = _fresh(f"_rguard_{case}")
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        with engine.begin() as conn:
            ids = _seed(conn)
            lowest = _arrange(conn, ids, case)
            before = _snapshot(conn)
            head = _version(conn)
        assert head == GUARD_REVISION
        below = {TAKEDOWN: "c7e3a1f5b829", COLLECTIONS: "8d2e6b4f1a37", DOCUMENTS: "9c4e2a7d5b18"}[lowest]
        for target in (below, "base", "-1"):
            with pytest.raises(RuntimeError, match="lossy downgrade refused") as refused:
                command.downgrade(cfg, target)
            message = str(refused.value)
            assert "Nothing was changed" in message
            assert not any(str(v) in message for v in ids.values())  # counts only, no ids
            assert "Chitthi" not in message and "Shaadi" not in message and "@example.com" not in message
            with engine.connect() as conn:
                assert _version(conn) == head
                assert _snapshot(conn) == before
        command.downgrade(cfg, lowest)  # stops above the lossy downgrade
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert _version(conn) == head
            after = _snapshot(conn)
        if case == "active_suspension":  # the takedown step was not run
            assert after == before
        engine.dispose()
    finally:
        _drop(admin, url)


def test_the_refusal_lists_every_guarded_loss_the_run_would_reach():
    admin, url = _fresh("_rguard_all")
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        with engine.begin() as conn:
            ids = _seed(conn)
            _suspend(conn, ids, _doc(conn, ids, "SELECTED_MEMBERS"))
            _collection(conn, ids)
        with pytest.raises(RuntimeError) as refused:
            command.downgrade(cfg, "base")
        message = str(refused.value)
        assert f"below {TAKEDOWN}" in message and "1 active suspensions" in message
        assert f"below {COLLECTIONS}" in message and "1 photo collections" in message
        assert f"below {DOCUMENTS}" in message and "1 Selected members documents" in message
        # stopping between the guarded downgrades reports only what it reaches
        with pytest.raises(RuntimeError) as refused:
            command.downgrade(cfg, COLLECTIONS)
        message = str(refused.value)
        assert f"below {TAKEDOWN}" in message
        assert f"below {COLLECTIONS}" not in message and f"below {DOCUMENTS}" not in message
        engine.dispose()
    finally:
        _drop(admin, url)


def test_a_lifted_suspension_does_not_block_the_takedown_downgrade():
    """Only an *active* suspension hides a record; a lifted one has already given it back."""
    admin, url = _fresh("_rguard_lifted")
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        with engine.begin() as conn:
            ids = _seed(conn)
            _suspend(conn, ids, _doc(conn, ids), status="lifted")
        command.downgrade(cfg, "c7e3a1f5b829")
        command.upgrade(cfg, "head")
        engine.dispose()
    finally:
        _drop(admin, url)


def test_a_downgrade_that_changes_no_access_runs_and_the_upgrade_re_runs():
    """Documents owned by their author at levels the older code reads the same way, no grants, no
    collections and no suspensions: the downgrade below every guarded revision is allowed, the
    documents keep their audiences, and re-upgrading backfills the same owners."""
    admin, url = _fresh("_rguard_clean")
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        with engine.begin() as conn:
            ids = _seed(conn)
            fam = _doc(conn, ids, "TREE_MEMBERS")
            admins = _doc(conn, ids, "PRIVATE_TREE_ADMINS")
            _orphan(conn, ids, "TREE_MEMBERS")  # a tradition orphan whose author stays away
        command.downgrade(cfg, "9c4e2a7d5b18")
        with engine.connect() as conn:
            assert _version(conn) == "9c4e2a7d5b18"
            assert dict(conn.execute(text("SELECT id, privacy_level FROM document")).all()) == {
                fam: "TREE_MEMBERS",
                admins: "PRIVATE_TREE_ADMINS",
            }
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert _version(conn) == GUARD_REVISION
            got = dict(conn.execute(text("SELECT id, owner_membership_id FROM document")).all())
            assert got == {fam: ids["m_author"], admins: ids["m_author"]}
        engine.dispose()
    finally:
        _drop(admin, url)


def test_an_offline_sql_downgrade_through_a_guarded_revision_is_refused():
    """``alembic downgrade --sql`` cannot count anything, so it refuses (fail closed)."""
    cfg = _cfg()
    with redirect_stdout(io.StringIO()), pytest.raises(RuntimeError, match="offline"):
        command.downgrade(cfg, f"{GUARD_REVISION}:c7e3a1f5b829", sql=True)


def test_the_record_guard_revision_is_the_single_head():
    from alembic.script import ScriptDirectory

    assert ScriptDirectory.from_config(_cfg()).get_heads() == [GUARD_REVISION]


def test_a_downgrade_that_stops_exactly_at_the_tradition_revision_is_allowed():
    """Regression: the shared guard once treated a target *equal* to the guarded revision as running
    that revision's downgrade (``iterate_revisions`` excludes its lower bound unless ``inclusive``).
    Stopping at 8d2e6b4f1a37 keeps its schema, so a Selected members tradition does not block it."""
    admin, url = _fresh("_rguard_boundary")
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        with engine.begin() as conn:
            ids = _seed(conn)
            _entry(conn, ids, "SELECTED_MEMBERS", ids["m_author"])
        command.downgrade(cfg, "8d2e6b4f1a37")
        command.upgrade(cfg, "head")  # below the guards nothing is checked (runbook section 7)
        with pytest.raises(RuntimeError, match="lossy downgrade refused"):
            command.downgrade(cfg, "3f6a8c1d2e94")
        engine.dispose()
    finally:
        _drop(admin, url)
