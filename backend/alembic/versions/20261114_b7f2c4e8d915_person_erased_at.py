"""person.erased_at: explicit "permanently deleted" lifecycle state (ADR-0034)

Until now a permanently erased person was an ordinary live row named "Erased person"; nothing
recorded the state. ``erased_at`` records it. It is backfilled only from the append-only audit log
(``person.erased``, matched on tree and person id), never from a display name: a family may
legitimately have recorded someone under that name. An erased person is also marked removed
(``deleted_at``), so every existing "live people only" filter leaves them out.

Nothing else is changed: relationship rows of people erased before this revision stay in the
database and are left out of every projection by ``authz.lifecycle``.

Downgrade: refused while any person carries the marker. Older code would show those tombstones as
ordinary people again. Roll forward, or restore from backup.

Revision ID: b7f2c4e8d915
Revises: a6e3d9b1f204
Create Date: 2026-11-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7f2c4e8d915"
down_revision: str | None = "a6e3d9b1f204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("person", sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        UPDATE person AS p
           SET erased_at = a.erased_at,
               deleted_at = COALESCE(p.deleted_at, a.erased_at)
          FROM (
              SELECT tree_id, target_id, MAX(created_at) AS erased_at
                FROM audit_event
               WHERE action = 'person.erased' AND target_type = 'person'
                 AND tree_id IS NOT NULL AND target_id IS NOT NULL
               GROUP BY tree_id, target_id
          ) AS a
         WHERE p.tree_id = a.tree_id AND p.id = a.target_id
        """
    )
    # the removed/erased set is read once per request (authz.lifecycle.inactive_person_ids)
    op.create_index(
        "ix_person_inactive",
        "person",
        ["tree_id"],
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )


def downgrade() -> None:
    count = op.get_bind().execute(sa.text("SELECT count(*) FROM person WHERE erased_at IS NOT NULL")).scalar()
    if count:
        raise RuntimeError(
            f"lossy downgrade refused: {count} permanently deleted person record(s) would lose their "
            "lifecycle marker and reappear as ordinary people. Roll forward or restore from backup."
        )
    op.drop_index("ix_person_inactive", table_name="person")
    op.drop_column("person", "erased_at")
