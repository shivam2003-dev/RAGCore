"""Persist structured answer-quality observations.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Revision 0001 historically bootstraps from ORM metadata. On a fresh install
    # using a newer checkout this column can already exist, while databases that
    # reached 0001 before 2026-07-10 still need the additive migration.
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("messages")}
    if "evaluation" in columns:
        return
    op.add_column(
        "messages",
        sa.Column(
            "evaluation",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("messages", "evaluation")
