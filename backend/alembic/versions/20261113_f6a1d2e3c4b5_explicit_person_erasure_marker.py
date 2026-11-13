"""Explicit person erasure lifecycle marker (ADR-0033).

Revision ID: f6a1d2e3c4b5
Revises: d4a8e6f1b209
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f6a1d2e3c4b5"
down_revision: str | None = "d4a8e6f1b209"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("person", sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True))
    # Earlier privacy-erasure actions were audited, but there was no lifecycle
    # field. Recover their timestamps from the append-only audit log, keyed by
    # tree AND person UUID. Never infer an erasure from a person's display name.
    op.execute(
        """
        UPDATE person AS p
           SET erased_at = audit.erased_at
          FROM (
              SELECT tree_id, target_id, MAX(created_at) AS erased_at
                FROM audit_event
               WHERE action = 'person.erased' AND target_type = 'person'
                 AND tree_id IS NOT NULL AND target_id IS NOT NULL
               GROUP BY tree_id, target_id
          ) AS audit
         WHERE p.tree_id = audit.tree_id AND p.id = audit.target_id
        """
    )


def downgrade() -> None:
    # Losing the only reliable lifecycle state could show privacy-erased
    # records as normal people on older code. Fail closed, without exposing IDs.
    count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM person WHERE erased_at IS NOT NULL")
    ).scalar()
    if count:
        raise RuntimeError(
            f"lossy downgrade refused: {count} erased person record(s) would lose "
            "their lifecycle marker. Roll forward or restore from backup."
        )
    op.drop_column("person", "erased_at")
