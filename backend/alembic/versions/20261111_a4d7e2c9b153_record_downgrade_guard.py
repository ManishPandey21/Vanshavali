"""guard the lossy downgrades of documents, photo collections and takedown (ADR-0027)

Revision ID: a4d7e2c9b153
Revises: f2a9c4e7d815
Create Date: 2026-11-11

Follow-up to f2a9c4e7d815, which guards only the tradition downgrade (8d2e6b4f1a37). The migrations
below stay unchanged because they may already be applied; their downgrades would silently widen or
discard access:

* d9b4f2c6a713 (record takedown) drops ``suspended_at`` on document, tradition_entry and
  photo_collection, so every taken-down record becomes readable again by its normal audience, and
  drops the reports and suspensions.
* b5c1e7a93d42 (photo collections) deletes collection grants and drops the collection tables.
* 3f6a8c1d2e94 (record sharing) turns ``ONLY_ME`` into ``PRIVATE_SELF`` (the tree OWNER reads it)
  and ``SELECTED_MEMBERS`` into ``CUSTOM`` (tree admins read it), and drops the owner (ownership
  transfers forgotten; a re-invited author gets author rights back by user id), the Selected branch
  audience and the download switch.

Upgrade: nothing (no schema change).

Downgrade: refused, before anything is changed, whenever the run would go on to execute one of
those downgrades while it would change access. The error gives counts only. There is no override
switch (recovery runbook, decision D4): roll forward, or restore from backup. A downgrade that stops
above a guarded revision is not checked for it. A relative target (``-1``), ``base`` or any target
that cannot be placed exactly is treated as reaching all of them (fail closed); so is offline
``--sql`` mode, where nothing can be counted.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.downgrade_guard import LossyDowngrade, refuse_lossy_downgrades

revision: str = "a4d7e2c9b153"
down_revision: str | None = "f2a9c4e7d815"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNBOOK = "docs/operations/tradition-ownership-recovery.md"

# Counts only: no ids, titles or names. Listed in the order the downgrades would run.
TAKEDOWN = LossyDowngrade(
    revision="d9b4f2c6a713",
    subject="taken-down records",
    losses={
        "active suspensions (the suspended records would become readable again)": (
            "SELECT count(*) FROM record_suspension WHERE status = 'active'"
        ),
        "records marked suspended (they would become readable again)": """
            SELECT (SELECT count(*) FROM document WHERE suspended_at IS NOT NULL)
                 + (SELECT count(*) FROM tradition_entry WHERE suspended_at IS NOT NULL)
                 + (SELECT count(*) FROM photo_collection WHERE suspended_at IS NOT NULL)
        """,
    },
)

COLLECTIONS = LossyDowngrade(
    revision="b5c1e7a93d42",
    subject="photo collections",
    losses={
        "photo collections (they would be deleted)": "SELECT count(*) FROM photo_collection",
        "collection grants (selected members would lose access)": (
            "SELECT count(*) FROM access_grant WHERE resource_type = 'collection'"
        ),
    },
)

DOCUMENTS = LossyDowngrade(
    revision="3f6a8c1d2e94",
    subject="documents",
    losses={
        "Only me documents (the tree owner would gain access)": (
            "SELECT count(*) FROM document WHERE privacy_level = 'ONLY_ME'"
        ),
        "Selected members documents (tree admins would gain access)": (
            "SELECT count(*) FROM document WHERE privacy_level = 'SELECTED_MEMBERS'"
        ),
        "document grants (they would be read under the older sharing rules)": (
            "SELECT count(*) FROM access_grant WHERE resource_type = 'document'"
        ),
        "Selected branch documents (the branch audience would be forgotten)": (
            "SELECT count(*) FROM document WHERE audience_branch_id IS NOT NULL"
        ),
        "documents with downloads turned off (downloads would be allowed again)": (
            "SELECT count(*) FROM document WHERE NOT allow_download"
        ),
        "orphans whose author is a member again (ownership would be revived)": """
            SELECT count(*) FROM document d
            WHERE d.owner_membership_id IS NULL AND d.created_by IS NOT NULL
              AND EXISTS (SELECT 1 FROM tree_membership m WHERE m.tree_id = d.tree_id AND m.user_id = d.created_by)
        """,
        "documents owned by someone other than their author (the transfer would be forgotten)": """
            SELECT count(*) FROM document d
            JOIN tree_membership m ON m.tree_id = d.tree_id AND m.id = d.owner_membership_id
            WHERE d.created_by IS DISTINCT FROM m.user_id
        """,
    },
)


def upgrade() -> None:
    pass


def downgrade() -> None:
    refuse_lossy_downgrades(TAKEDOWN, COLLECTIONS, DOCUMENTS, runbook=RUNBOOK)
