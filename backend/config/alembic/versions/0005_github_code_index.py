"""Add read-only GitHub repository and file state.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "github_repository_mappings" in set(sa.inspect(bind).get_table_names()):
        return

    op.create_table(
        "github_repository_mappings",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_state_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("repository", sa.String(length=255), nullable=False),
        sa.Column("branch", sa.String(length=255), nullable=False),
        sa.Column("path_allowlist", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("path_denylist", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="configured"),
        sa.Column("head_commit_sha", sa.String(length=64), nullable=True),
        sa.Column("head_tree_sha", sa.String(length=64), nullable=True),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
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
            "organization_id",
            "owner",
            "repository",
            "branch",
            name="uq_github_repository_mappings_repo_branch",
        ),
    )
    op.create_index(
        "ix_github_repository_mappings_org_project",
        "github_repository_mappings",
        ["organization_id", "project_id"],
    )

    op.create_table(
        "github_file_states",
        sa.Column("repository_mapping_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("blob_sha", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=80), nullable=False, server_default="text"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("last_commit_sha", sa.String(length=64), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["repository_mapping_id"], ["github_repository_mappings.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repository_mapping_id", "path", name="uq_github_file_states_mapping_path"),
    )
    op.create_index(
        "ix_github_file_states_mapping_status",
        "github_file_states",
        ["repository_mapping_id", "status"],
    )
    op.create_index(
        "ix_github_file_states_blob",
        "github_file_states",
        ["repository_mapping_id", "blob_sha"],
    )

    for table, column in (
        ("github_repository_mappings", "path_allowlist"),
        ("github_repository_mappings", "path_denylist"),
        ("github_repository_mappings", "is_enabled"),
        ("github_repository_mappings", "status"),
        ("github_file_states", "language"),
        ("github_file_states", "status"),
    ):
        op.alter_column(table, column, server_default=None)


def downgrade() -> None:
    op.drop_index("ix_github_file_states_blob", table_name="github_file_states")
    op.drop_index("ix_github_file_states_mapping_status", table_name="github_file_states")
    op.drop_table("github_file_states")
    op.drop_index(
        "ix_github_repository_mappings_org_project",
        table_name="github_repository_mappings",
    )
    op.drop_table("github_repository_mappings")
