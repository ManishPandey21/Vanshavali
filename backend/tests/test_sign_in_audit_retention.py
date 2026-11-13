"""ADR-0033: sign-in records and audit-log network identifiers are kept for one year.

The audit trail stays append-only except for one database-enforced change: erasing ``ip`` and
``user_agent`` of an entry more than 365 days old. These tests run as the restricted app role.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.config import Settings
from app.core.db import get_engine
from app.core.retention import purge_ended_sessions, scrub_audit_network

NOW = dt.datetime.now(dt.UTC)


def _days(n: int) -> dt.datetime:
    return NOW - dt.timedelta(days=n)


def _session(
    user_id: str, *, created: dt.datetime, idle: dt.datetime, absolute: dt.datetime, revoked=None
) -> str:
    sid = str(uuid.uuid4())
    with get_engine().begin() as c:
        c.execute(
            text(
                "INSERT INTO user_session (id, user_id, token_hash, created_at, last_seen_at, idle_expires_at,"
                " absolute_expires_at, revoked_at, ip, user_agent)"
                " VALUES (:id, :u, :h, :c, :c, :i, :a, :r, '203.0.113.7', 'TestBrowser/1.0')"
            ),
            {
                "id": sid,
                "u": user_id,
                "h": hashlib.sha256(sid.encode()).hexdigest(),
                "c": created,
                "i": idle,
                "a": absolute,
                "r": revoked,
            },
        )
    return sid


def _session_ids() -> set[str]:
    with get_engine().connect() as c:
        return {str(x) for x in c.execute(text("SELECT id FROM user_session")).scalars()}


def _audit(
    *, created: dt.datetime, ip: str | None = "203.0.113.7", ua: str | None = "TestBrowser/1.0"
) -> str:
    aid = str(uuid.uuid4())
    with get_engine().begin() as c:
        c.execute(
            text(
                "INSERT INTO audit_event (id, action, target_type, summary, details, ip, user_agent, created_at)"
                " VALUES (:id, 'retention.test', 'person', 'kept history', '{\"field\": \"name\"}', :ip, :ua, :c)"
            ),
            {"id": aid, "ip": ip, "ua": ua, "c": created},
        )
    return aid


def _audit_row(aid: str):
    with get_engine().connect() as c:
        return c.execute(
            text(
                "SELECT action, target_type, summary, details, ip, user_agent, created_at FROM audit_event WHERE id = :id"
            ),
            {"id": aid},
        ).one()


# ---------------------------------------------------------------- sign-in records
def test_sign_in_records_are_deleted_a_year_after_the_session_ended(owner):
    uid = owner.user["id"]
    revoked_long_ago = _session(
        uid, created=_days(500), idle=_days(480), absolute=_days(470), revoked=_days(400)
    )
    expired_long_ago = _session(uid, created=_days(420), idle=_days(406), absolute=_days(390))
    revoked_recently = _session(
        uid, created=_days(500), idle=_days(480), absolute=_days(470), revoked=_days(30)
    )
    expired_recently = _session(uid, created=_days(120), idle=_days(100), absolute=_days(90))
    # idle expiry passed long ago even though the absolute one is later: the session ended at the idle expiry
    idle_ended_long_ago = _session(uid, created=_days(400), idle=_days(380), absolute=_days(370))
    live = _session(
        uid, created=_days(1), idle=NOW + dt.timedelta(days=13), absolute=NOW + dt.timedelta(days=29)
    )

    assert purge_ended_sessions(now=NOW) == 3
    remaining = _session_ids()
    assert {revoked_long_ago, expired_long_ago, idle_ended_long_ago}.isdisjoint(remaining)
    assert {revoked_recently, expired_recently, live} <= remaining
    # the signed-in user's own current session is untouched
    assert owner.get("/auth/me").status_code == 200
    # idempotent
    assert purge_ended_sessions(now=NOW) == 0


# ---------------------------------------------------------------- audit network identifiers
def test_scrub_erases_only_network_identifiers_of_year_old_entries():
    old = _audit(created=_days(400))
    old_without_ip = _audit(created=_days(400), ip=None, ua=None)
    recent = _audit(created=_days(30))
    before = _audit_row(old)

    assert scrub_audit_network(now=NOW) >= 1
    after = _audit_row(old)
    assert (after.ip, after.user_agent) == (None, None)
    # the family's change history is unchanged
    assert (after.action, after.target_type, after.summary, after.details, after.created_at) == (
        before.action,
        before.target_type,
        before.summary,
        before.details,
        before.created_at,
    )
    assert _audit_row(old_without_ip).ip is None
    assert (_audit_row(recent).ip, _audit_row(recent).user_agent) == ("203.0.113.7", "TestBrowser/1.0")
    assert scrub_audit_network(now=NOW) == 0  # idempotent


def test_scrub_works_in_batches():
    ids = [_audit(created=_days(500)) for _ in range(5)]
    assert scrub_audit_network(now=NOW, batch_size=2) >= 5
    assert all(_audit_row(a).ip is None for a in ids)


def test_database_refuses_to_scrub_entries_younger_than_a_year_whatever_the_caller_asks():
    young = _audit(created=_days(100))
    with pytest.raises(DBAPIError, match="append-only"):
        scrub_audit_network(now=NOW, older_than_days=30)
    assert _audit_row(young).ip == "203.0.113.7"


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_event SET ip = NULL, user_agent = NULL, action = 'tampered' WHERE id = :id",
        "UPDATE audit_event SET ip = '198.51.100.1' WHERE id = :id",
        "UPDATE audit_event SET ip = NULL WHERE id = :id",  # user agent left in place
        "UPDATE audit_event SET ip = NULL, user_agent = NULL, details = '{}' WHERE id = :id",
        "UPDATE audit_event SET ip = NULL, user_agent = NULL, created_at = now() WHERE id = :id",
        "DELETE FROM audit_event WHERE id = :id",
    ],
)
def test_old_audit_entries_stay_append_only_apart_from_the_scrub(statement):
    old = _audit(created=_days(400))
    with pytest.raises(DBAPIError, match="append-only"), get_engine().begin() as c:
        c.execute(text(statement), {"id": old})
    row = _audit_row(old)
    assert (row.action, row.ip, row.user_agent) == ("retention.test", "203.0.113.7", "TestBrowser/1.0")


def test_recent_audit_entries_cannot_be_scrubbed_directly():
    recent = _audit(created=_days(364))
    with pytest.raises(DBAPIError, match="append-only"), get_engine().begin() as c:
        c.execute(text("UPDATE audit_event SET ip = NULL, user_agent = NULL WHERE id = :id"), {"id": recent})


@pytest.mark.parametrize("field", ["session_record_retention_days", "audit_network_retention_days"])
def test_settings_cannot_go_below_a_year(field):
    with pytest.raises(ValidationError):
        Settings(**{field: 364})
    assert getattr(Settings(**{field: 730}), field) == 730


def test_maintenance_commands(owner, capsys):
    from app.cli.maintenance import main

    assert main(["purge-sign-in-records"]) == 0
    assert main(["scrub-audit-network"]) == 0
    out = capsys.readouterr().out
    assert "sign-in record(s)" in out
    assert "audit entries" in out
