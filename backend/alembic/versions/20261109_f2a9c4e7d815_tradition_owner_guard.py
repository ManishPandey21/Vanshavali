"""tradition ownership: safe writes from older code and a guarded downgrade (ADR-0027 increment 2)

Revision ID: f2a9c4e7d815
Revises: d9b4f2c6a713
Create Date: 2026-11-09

Follow-up to 8d2e6b4f1a37 (PR #51), which stays unchanged because it may already be applied.

Upgrade
* Any tradition still at ``PRIVATE_SELF`` becomes ``ONLY_ME``. On a tradition ``PRIVATE_SELF`` always
  meant *the author only*, but the record evaluator reads a record's ``PRIVATE_SELF`` as "owner and
  tree OWNER". Such rows appear when the previous release runs on this schema (``rollback.sh``) or by
  hand. This only narrows: the tree owner loses a view they were never meant to have. No owner is
  inferred for an ownerless row (that is a decision, see the recovery runbook). Idempotent.
* Trigger ``tradition_entry_record_owner`` (BEFORE INSERT, or UPDATE of ``privacy_level``):
  ``PRIVATE_SELF`` is stored as ``ONLY_ME``; an INSERT without an owner (older code never sets one)
  gets its author's *current* membership of the same tree, which is by definition the membership
  that wrote it. It never touches an existing row's owner, so it revives nothing.

Downgrade
* Refused, before anything is changed, when the downgrade would go on to run 8d2e6b4f1a37's downgrade
  and that would change who can read or own an entry: tradition grants (deleted), Selected members
  (become CUSTOM, which admins read), an orphaned Only me entry (becomes PRIVATE_SELF by user id, so
  its author gets it back if invited again), an orphan whose author is a member again (old code gives
  them author rights, and a re-upgrade makes them owner) or an owner who is not the author (a
  transfer, forgotten). The error gives counts only. Use the recovery runbook
  (docs/operations/tradition-ownership-recovery.md); there is no override switch.
* A downgrade that stops at 8d2e6b4f1a37 or above is not affected by the guard. Otherwise this
  downgrade drops the trigger and function; rows narrowed to ``ONLY_ME`` stay narrowed.
* The target must be an explicit revision id: a relative target (``-1``) or ``base`` is treated as
  reaching 8d2e6b4f1a37 (fail closed).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from app.core.downgrade_guard import LossyDowngrade, refuse_lossy_downgrades

revision: str = "f2a9c4e7d815"
down_revision: str | None = "d9b4f2c6a713"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRADITIONS_REVISION = "8d2e6b4f1a37"

# Keep in step with app/models/culture.py (create_all for the fast tests).
FUNCTION = """
CREATE OR REPLACE FUNCTION tradition_entry_record_owner() RETURNS trigger AS $$
BEGIN
  IF NEW.privacy_level = 'PRIVATE_SELF' THEN
    NEW.privacy_level := 'ONLY_ME';
  END IF;
  IF TG_OP = 'INSERT' AND NEW.owner_membership_id IS NULL AND NEW.created_by IS NOT NULL THEN
    SELECT m.id INTO NEW.owner_membership_id
      FROM tree_membership m
     WHERE m.tree_id = NEW.tree_id AND m.user_id = NEW.created_by;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
TRIGGER = """
CREATE TRIGGER tradition_entry_record_owner
BEFORE INSERT OR UPDATE OF privacy_level ON tradition_entry
FOR EACH ROW EXECUTE FUNCTION tradition_entry_record_owner();
"""

# What 8d2e6b4f1a37's downgrade would lose or widen. Counts only: no ids, titles or names.
TRADITIONS = LossyDowngrade(
    revision=TRADITIONS_REVISION,
    subject="family traditions",
    losses={
        "tradition grants (selected members would lose access)": (
            "SELECT count(*) FROM access_grant WHERE resource_type = 'tradition'"
        ),
        "Selected members entries (tree admins would gain access)": (
            "SELECT count(*) FROM tradition_entry WHERE privacy_level = 'SELECTED_MEMBERS'"
        ),
        "orphaned Only me entries (a re-invited author would get them back)": (
            "SELECT count(*) FROM tradition_entry WHERE privacy_level = 'ONLY_ME' AND owner_membership_id IS NULL"
        ),
        "orphans whose author is a member again (ownership would be revived)": """
        SELECT count(*) FROM tradition_entry e
        WHERE e.owner_membership_id IS NULL AND e.created_by IS NOT NULL
          AND EXISTS (SELECT 1 FROM tree_membership m WHERE m.tree_id = e.tree_id AND m.user_id = e.created_by)
    """,
        "entries owned by someone other than their author (the transfer would be forgotten)": """
        SELECT count(*) FROM tradition_entry e
        JOIN tree_membership m ON m.tree_id = e.tree_id AND m.id = e.owner_membership_id
        WHERE e.created_by IS DISTINCT FROM m.user_id
    """,
    },
)


def upgrade() -> None:
    op.execute("UPDATE tradition_entry SET privacy_level = 'ONLY_ME' WHERE privacy_level = 'PRIVATE_SELF'")
    op.execute(FUNCTION)
    op.execute("DROP TRIGGER IF EXISTS tradition_entry_record_owner ON tradition_entry")
    op.execute(TRIGGER)


def downgrade() -> None:
    refuse_lossy_downgrades(TRADITIONS, runbook="docs/operations/tradition-ownership-recovery.md")
    op.execute("DROP TRIGGER IF EXISTS tradition_entry_record_owner ON tradition_entry")
    op.execute("DROP FUNCTION IF EXISTS tradition_entry_record_owner()")
