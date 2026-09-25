from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import DDL, DateTime, Index, String, Text, event, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base


class AuditEvent(Base):
    """Append-only audit trail (PRS §34). No FKs: history must outlive deleted trees/users.

    ``details`` must never contain sensitive values (field *names* only, never DOB/deed contents).
    """

    __tablename__ = "audit_event"
    __table_args__ = (
        Index("ix_audit_event_tree_time", "tree_id", "created_at"),
        Index("ix_audit_event_target", "target_type", "target_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    tree_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(80))
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    summary: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


AUDIT_APPEND_ONLY_FUNCTION = DDL(
    """
CREATE OR REPLACE FUNCTION audit_event_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_event is append-only';
END;
$$ LANGUAGE plpgsql;
"""
)
AUDIT_APPEND_ONLY_TRIGGER = DDL(
    """
CREATE TRIGGER audit_event_no_update_delete
BEFORE UPDATE OR DELETE ON audit_event
FOR EACH ROW EXECUTE FUNCTION audit_event_append_only();
"""
)

# Keep create_all() (used by fast tests) equivalent to the migration.
event.listen(AuditEvent.__table__, "after_create", AUDIT_APPEND_ONLY_FUNCTION)
event.listen(AuditEvent.__table__, "after_create", AUDIT_APPEND_ONLY_TRIGGER)
