"""PostgreSQL row-level security: the second isolation barrier (ADR-0002).

These tests bypass the service layer entirely and talk to the database as the application role, to
prove that even a buggy query cannot read or write another tree's rows.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.db import bind_tree, get_sessionmaker
from app.models import Base, Person
from app.models.rls import RLS_TABLES
from tests.conftest import new_tree
from tests.helpers import create_person

# Tables with tree_id that are deliberately *not* under RLS (read before a tree is bound, or
# append-only audit). Everything else that carries tree_id must be protected. A calendar feed is
# resolved by its token before the tree is known (ADR-0022 §7), like an invitation.
NOT_RLS = {"tree_membership", "tree_invitation", "profile_claim_invite", "audit_event", "calendar_feed"}


def test_every_tree_scoped_table_is_covered():
    tree_scoped = {t.name for t in Base.metadata.sorted_tables if "tree_id" in t.c}
    assert tree_scoped - NOT_RLS == set(RLS_TABLES), "new tree-scoped table without an RLS policy?"


def test_policies_installed_and_app_role_is_restricted():
    with get_sessionmaker()() as db:
        rows = dict(
            db.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relname = ANY(:t)"
                ),
                {"t": list(RLS_TABLES)},
            ).all()
        )
        assert rows and all(rows[t] for t in RLS_TABLES)
        policies = set(
            db.scalars(text("SELECT tablename FROM pg_policies WHERE policyname = 'tree_isolation'"))
        )
        assert policies == set(RLS_TABLES)
        su, bypass = db.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        assert not su and not bypass, "tests must run as a restricted role or RLS is not exercised"


def _two_trees(owner, make_client):  # type: ignore[no-untyped-def]
    ta = new_tree(owner, "A")["id"]
    pa = create_person(owner, ta, "InA")
    other = make_client()
    other.register()
    tb = new_tree(other, "B")["id"]
    pb = create_person(other, tb, "InB")
    return ta, pa, tb, pb


def test_unbound_session_sees_nothing(owner, make_client):
    _two_trees(owner, make_client)
    with get_sessionmaker()() as db:
        assert db.scalars(select(Person)).all() == []


def test_bound_session_cannot_read_other_tree(owner, make_client):
    ta, pa, _tb, pb = _two_trees(owner, make_client)
    with get_sessionmaker()() as db:
        bind_tree(db, ta)
        ids = {str(p.id) for p in db.scalars(select(Person))}
        assert ids == {pa["id"]}
        # even selecting by the other tree's primary key returns nothing
        assert db.get(Person, uuid.UUID(pb["id"])) is None
        # and the binding survives a commit (re-applied at the next transaction)
        db.commit()
        assert {str(p.id) for p in db.scalars(select(Person))} == {pa["id"]}


def test_bound_session_cannot_write_other_tree(owner, make_client):
    ta, pa, tb, pb = _two_trees(owner, make_client)
    with get_sessionmaker()() as db:
        bind_tree(db, ta)
        db.add(Person(tree_id=uuid.UUID(tb), preferred_display_name="Smuggled"))
        with pytest.raises(DBAPIError, match="row-level security"):
            db.flush()
        db.rollback()
        bind_tree(db, ta)
        n = db.execute(
            text("UPDATE person SET preferred_display_name = 'Hacked' WHERE id = :id"), {"id": pb["id"]}
        ).rowcount
        assert n == 0
        db.commit()
    assert owner.get(f"/trees/{ta}/people/{pa['id']}").status_code == 200


def test_binding_never_leaks_between_pooled_sessions(owner, make_client):
    ta, _pa, _tb, _pb = _two_trees(owner, make_client)
    maker = get_sessionmaker()
    with maker() as db:
        bind_tree(db, ta)
        assert db.scalars(select(Person)).all()
        db.commit()
    with maker() as db2:  # likely reuses the same pooled connection
        assert db2.scalars(select(Person)).all() == []
