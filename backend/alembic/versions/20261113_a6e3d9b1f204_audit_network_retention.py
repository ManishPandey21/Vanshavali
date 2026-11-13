"""audit network-identifier retention: scrub-only trigger exception and scrub index (ADR-0033)

The append-only trigger on ``audit_event`` now allows exactly one change: erasing ``ip`` and
``user_agent`` of an entry more than 365 days old, with the rest of the row unchanged. DELETE stays
forbidden. The downgrade restores the strict trigger; values already erased stay erased, so it loses
nothing.

Revision ID: a6e3d9b1f204
Revises: d4a8e6f1b209
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a6e3d9b1f204"
down_revision: str | None = "d4a8e6f1b209"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copies: later model changes must not alter what this revision did.
SCRUB_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_event_append_only() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'UPDATE'
     AND OLD.created_at < now() - interval '365 days'
     AND NEW.ip IS NULL AND NEW.user_agent IS NULL
     AND (to_jsonb(NEW) - 'ip' - 'user_agent') = (to_jsonb(OLD) - 'ip' - 'user_agent')
  THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'audit_event is append-only';
END;
$$ LANGUAGE plpgsql;
"""

STRICT_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_event_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_event is append-only';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(SCRUB_ONLY_FUNCTION)
    op.create_index(
        "ix_audit_event_network_scrub",
        "audit_event",
        ["created_at"],
        postgresql_where=sa.text("ip IS NOT NULL OR user_agent IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_audit_event_network_scrub", table_name="audit_event")
    op.execute(STRICT_FUNCTION)
