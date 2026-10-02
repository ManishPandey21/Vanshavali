"""Chart presets, render jobs and render artifacts (ADR-0017, docs/architecture/remotion-rendering.md)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TreeScopedMixin, enum_column, tree_fk, tree_unique
from app.models.enums import ChartType, RenderArtifactKind, RenderOutput, RenderStatus


class ChartPreset(TreeScopedMixin, Base):
    """Saved chart settings. Private to the user unless ``shared`` (then readable by tree members).

    Settings hold only filter/display choices (ids, toggles), never person data.
    """

    __tablename__ = "chart_preset"
    __table_args__ = (
        tree_unique("chart_preset"),
        Index("ix_chart_preset_owner", "tree_id", "user_id", "chart_type"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    chart_type: Mapped[ChartType] = mapped_column(enum_column(ChartType))
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    shared: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class RenderJob(TreeScopedMixin, Base):
    """An animated export request. The payload is built as the requester when the job is created,
    stored encrypted in the object store, and rendered by the render worker."""

    __tablename__ = "render_job"
    __table_args__ = (
        tree_unique("render_job"),
        Index("ix_render_job_requester", "tree_id", "requested_by", "created_at"),
    )

    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    chart_type: Mapped[ChartType] = mapped_column(enum_column(ChartType))
    output: Mapped[RenderOutput] = mapped_column(enum_column(RenderOutput))
    status: Mapped[RenderStatus] = mapped_column(
        enum_column(RenderStatus), default=RenderStatus.QUEUED, server_default=RenderStatus.QUEUED.value
    )
    progress: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    payload_storage_key: Mapped[str | None] = mapped_column(String(500))
    payload_sha256: Mapped[str | None] = mapped_column(String(64))
    renderer: Mapped[str | None] = mapped_column(String(80))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(300))
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class RenderArtifact(TreeScopedMixin, Base):
    __tablename__ = "render_artifact"
    __table_args__ = (tree_unique("render_artifact"), tree_fk(["job_id"], "render_job"))

    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    kind: Mapped[RenderArtifactKind] = mapped_column(enum_column(RenderArtifactKind))
    storage_key: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_s: Mapped[float | None] = mapped_column(Float)
