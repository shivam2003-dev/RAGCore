"""Add an expiring ownership lease for GitHub repository syncs.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("github_repository_mappings")}
    if "sync_lease_id" not in columns:
        op.add_column(
            "github_repository_mappings",
            sa.Column("sync_lease_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
    if "sync_lease_expires_at" not in columns:
        op.add_column(
            "github_repository_mappings",
            sa.Column("sync_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("github_repository_mappings", "sync_lease_expires_at")
    op.drop_column("github_repository_mappings", "sync_lease_id")
