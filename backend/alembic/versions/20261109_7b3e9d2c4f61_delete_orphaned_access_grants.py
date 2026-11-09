"""delete orphaned access grants

Revision ID: 7b3e9d2c4f61
Revises: 6a1d9c3e5f27
Create Date: 2026-11-09

Data-only hotfix ahead of ADR-0027 §3. ``access_grant`` is keyed by ``user_id``, and removing a
member never deleted their grants, so re-inviting the same person revived every old grant. The
service now deletes a departing member's grants (``trees.service.delete_member_grants``); this
migration removes the grants already left behind: every grant with no ``tree_membership`` for the
same ``(tree_id, user_id)``.

Downgrade is a no-op: the deleted rows were stale access that must not come back.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "7b3e9d2c4f61"
down_revision: str | None = "6a1d9c3e5f27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM access_grant g
        WHERE NOT EXISTS (
            SELECT 1 FROM tree_membership m
            WHERE m.tree_id = g.tree_id AND m.user_id = g.user_id
        )
        """
    )


def downgrade() -> None:
    """No-op: orphaned grants are not restored."""
