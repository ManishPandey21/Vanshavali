"""narrowing notices

Revision ID: c7e3a1f5b829
Revises: 7b2e4d9a1c63
Create Date: 2026-11-09

ADR-0027 §5: tell a record's owner when the record was made more private automatically. Two
notification kinds on `user_notification` (the record is the notification's `subject_id`).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "c7e3a1f5b829"
down_revision: str | None = "7b2e4d9a1c63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_BEFORE = (
    "'proposal_to_review', 'proposal_accepted', 'proposal_rejected', 'proposal_stale', "
    "'challenge_opened', 'challenge_upheld', 'challenge_dismissed', 'proposal_comment', "
    "'offer_accepted', 'offer_declined', "
    "'nomination_created', 'nomination_accepted', 'nomination_declined', 'nomination_approved', "
    "'nomination_rejected', 'nomination_expired', 'nomination_lapsed'"
)
NARROWED_KINDS = "'document_narrowed', 'tradition_narrowed'"
CHECK = "ck_user_notification_notificationkind"


def upgrade() -> None:
    op.drop_constraint(op.f(CHECK), "user_notification", type_="check")
    op.create_check_constraint(
        op.f(CHECK), "user_notification", f"kind IN ({KINDS_BEFORE}, {NARROWED_KINDS})"
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM user_notification WHERE kind IN ({NARROWED_KINDS})")  # noqa: S608 - constants
    op.drop_constraint(op.f(CHECK), "user_notification", type_="check")
    op.create_check_constraint(op.f(CHECK), "user_notification", f"kind IN ({KINDS_BEFORE})")
