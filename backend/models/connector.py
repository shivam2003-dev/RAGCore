import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin, UUIDPKMixin


class ConnectorState(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "connector_states"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), default="disabled")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lag_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("organization_id", "kind", name="uq_connector_states_org_kind"),
        UniqueConstraint("organization_id", "id", name="uq_connector_states_org_id"),
        Index("ix_connector_states_org_kind", "organization_id", "kind"),
    )


class SlackChannelMapping(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "slack_channel_mappings"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    connector_state_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    workspace_id: Mapped[str] = mapped_column(String(64))
    channel_id: Mapped[str] = mapped_column(String(64))
    channel_name: Mapped[str] = mapped_column(String(255))
    visibility: Mapped[str] = mapped_column(String(32), default="public")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_thread_ts: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "connector_state_id"],
            ["connector_states.organization_id", "connector_states.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "knowledge_base_id"],
            ["knowledge_bases.organization_id", "knowledge_bases.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "organization_id",
            "workspace_id",
            "channel_id",
            name="uq_slack_channel_mappings_channel",
        ),
        Index("ix_slack_channel_mappings_org_project", "organization_id", "project_id"),
        Index("ix_slack_channel_mappings_kb", "knowledge_base_id"),
    )


class SlackEventReceipt(UUIDPKMixin, Base):
    __tablename__ = "slack_event_receipts"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    connector_state_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    event_id: Mapped[str] = mapped_column(String(128))
    channel_id: Mapped[str] = mapped_column(String(64))
    thread_ts: Mapped[str] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    payload_hash: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "connector_state_id"],
            ["connector_states.organization_id", "connector_states.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("connector_state_id", "event_id", name="uq_slack_event_receipts_event"),
        Index("ix_slack_event_receipts_status", "connector_state_id", "status"),
    )
