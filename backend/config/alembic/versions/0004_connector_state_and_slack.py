"""Add connector state and allowlisted Slack mappings.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "connector_states" in set(sa.inspect(bind).get_table_names()):
        # Revision 0001 historically creates current ORM metadata on fresh
        # databases, so the additive tables may already exist.
        return

    op.create_table(
        "connector_states",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="disabled"),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lag_seconds", sa.Integer(), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "kind", name="uq_connector_states_org_kind"),
        sa.UniqueConstraint("organization_id", "id", name="uq_connector_states_org_id"),
    )
    op.create_index("ix_connector_states_org_kind", "connector_states", ["organization_id", "kind"])

    op.create_table(
        "slack_channel_mappings",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_state_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("channel_id", sa.String(length=64), nullable=False),
        sa.Column("channel_name", sa.String(length=255), nullable=False),
        sa.Column("visibility", sa.String(length=32), nullable=False, server_default="public"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_thread_ts", sa.String(length=32), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["organization_id", "connector_state_id"],
            ["connector_states.organization_id", "connector_states.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "knowledge_base_id"],
            ["knowledge_bases.organization_id", "knowledge_bases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "workspace_id", "channel_id", name="uq_slack_channel_mappings_channel"
        ),
    )
    op.create_index(
        "ix_slack_channel_mappings_org_project",
        "slack_channel_mappings",
        ["organization_id", "project_id"],
    )
    op.create_index("ix_slack_channel_mappings_kb", "slack_channel_mappings", ["knowledge_base_id"])

    op.create_table(
        "slack_event_receipts",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_state_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("channel_id", sa.String(length=64), nullable=False),
        sa.Column("thread_ts", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "connector_state_id"],
            ["connector_states.organization_id", "connector_states.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_state_id", "event_id", name="uq_slack_event_receipts_event"),
    )
    op.create_index(
        "ix_slack_event_receipts_status",
        "slack_event_receipts",
        ["connector_state_id", "status"],
    )

    op.alter_column("connector_states", "status", server_default=None)
    op.alter_column("connector_states", "config", server_default=None)
    op.alter_column("connector_states", "failure_count", server_default=None)
    op.alter_column("slack_channel_mappings", "visibility", server_default=None)
    op.alter_column("slack_channel_mappings", "is_enabled", server_default=None)
    op.alter_column("slack_event_receipts", "status", server_default=None)
    op.alter_column("slack_event_receipts", "attempts", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_slack_event_receipts_status", table_name="slack_event_receipts")
    op.drop_table("slack_event_receipts")
    op.drop_index("ix_slack_channel_mappings_kb", table_name="slack_channel_mappings")
    op.drop_index("ix_slack_channel_mappings_org_project", table_name="slack_channel_mappings")
    op.drop_table("slack_channel_mappings")
    op.drop_index("ix_connector_states_org_kind", table_name="connector_states")
    op.drop_table("connector_states")
