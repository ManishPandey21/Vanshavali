"""merge heads: claim-link removal requests and external identity

Revision ID: f0a1b2c3d4e5
Revises: d5f2a9c1e7b3, edcd174a0123
Create Date: 2026-09-26

Two migrations were written in parallel on top of c4e8f1a2b3d5 (PR #6 claim-link "not me" /
"remove me", PR #7 sign in with Google) and both reached main, leaving two heads. They touch
different tables, so this merge revision only joins the history; it changes nothing.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "f0a1b2c3d4e5"
down_revision: str | tuple[str, ...] | None = ("d5f2a9c1e7b3", "edcd174a0123")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
