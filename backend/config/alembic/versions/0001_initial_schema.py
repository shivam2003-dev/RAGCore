"""Initial schema — bootstrapped from ORM metadata.

The initial revision materializes the full model graph (14 tables, HNSW +
GIN indexes). Subsequent revisions must use explicit op.* calls.

Revision ID: 0001
Revises:
Create Date: 2026-07-04
"""

from alembic import op
from sqlalchemy import MetaData, inspect

from models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgvector types and indexes cannot be created in a brand-new database until
    # the extension exists. Existing databases keep the extension unchanged.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    # Reflect the tables that actually exist at revision 0001. Importing current
    # ORM metadata here can include later use_alter constraints already removed
    # by their own downgrade revisions.
    bind = op.get_bind()
    metadata = MetaData()
    current_table_names = set(sa_table.name for sa_table in Base.metadata.sorted_tables)
    existing_table_names = current_table_names.intersection(inspect(bind).get_table_names())
    metadata.reflect(bind=bind, only=existing_table_names)
    metadata.drop_all(bind=bind)
