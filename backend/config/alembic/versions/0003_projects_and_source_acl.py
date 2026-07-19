"""Add project scope and enforceable source ACLs.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

access_scope = postgresql.ENUM("organization", "restricted", name="access_scope", create_type=False)
project_role = postgresql.ENUM("member", "manager", name="project_role", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "projects" in tables:
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        kb_columns = {column["name"] for column in inspector.get_columns("knowledge_bases")}
        conversation_columns = {column["name"] for column in inspector.get_columns("conversations")}
        if (
            {
                "default_project_id",
            }.issubset(user_columns)
            and {"access_scope"}.issubset(kb_columns)
            and {
                "project_id",
            }.issubset(conversation_columns)
        ):
            # Revision 0001 historically creates from current ORM metadata. A
            # fresh database therefore already has this additive schema.
            return
    access_scope.create(bind, checkfirst=True)
    project_role.create(bind, checkfirst=True)

    op.add_column(
        "knowledge_bases",
        sa.Column(
            "access_scope",
            access_scope,
            nullable=False,
            server_default="organization",
        ),
    )
    op.create_unique_constraint("uq_kb_org_id", "knowledge_bases", ["organization_id", "id"])
    op.create_unique_constraint("uq_users_org_id", "users", ["organization_id", "id"])
    op.create_unique_constraint("uq_conversations_org_id", "conversations", ["organization_id", "id"])

    op.create_table(
        "projects",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_projects_org_slug"),
        sa.UniqueConstraint("organization_id", "id", name="uq_projects_org_id"),
    )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])

    op.create_table(
        "project_sources",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
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
        sa.UniqueConstraint("project_id", "knowledge_base_id", name="uq_project_sources_pair"),
    )
    op.create_index(
        "ix_project_sources_org_project",
        "project_sources",
        ["organization_id", "project_id"],
    )
    op.create_index("ix_project_sources_knowledge_base_id", "project_sources", ["knowledge_base_id"])

    op.create_table(
        "project_members",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "project_role",
            project_role,
            nullable=False,
            server_default="member",
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_pair"),
    )
    op.create_index("ix_project_members_org_user", "project_members", ["organization_id", "user_id"])

    op.create_table(
        "source_access_grants",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["organization_id", "knowledge_base_id"],
            ["knowledge_bases.organization_id", "knowledge_bases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("knowledge_base_id", "user_id", name="uq_source_access_grants_pair"),
    )
    op.create_index(
        "ix_source_access_grants_org_user",
        "source_access_grants",
        ["organization_id", "user_id"],
    )

    op.add_column(
        "users",
        sa.Column("default_project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_users_default_project_id", "users", ["default_project_id"])
    op.add_column(
        "conversations",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_conversations_project_id", "conversations", ["project_id"])

    op.execute(
        """
        INSERT INTO projects (
            id, organization_id, name, slug, description, is_active, created_at, updated_at
        )
        SELECT gen_random_uuid(), id, 'All Knowledge', 'all-knowledge',
               'Default project containing the organization''s existing sources.',
               true, now(), now()
        FROM organizations
        ON CONFLICT (organization_id, slug) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO project_sources (
            id, organization_id, project_id, knowledge_base_id, created_at, updated_at
        )
        SELECT gen_random_uuid(), kb.organization_id, p.id, kb.id, now(), now()
        FROM knowledge_bases kb
        JOIN projects p
          ON p.organization_id = kb.organization_id AND p.slug = 'all-knowledge'
        ON CONFLICT (project_id, knowledge_base_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO project_members (
            id, organization_id, project_id, user_id, project_role, created_at, updated_at
        )
        SELECT gen_random_uuid(), u.organization_id, p.id, u.id,
               CASE WHEN u.role = 'admin' THEN 'manager'::project_role
                    ELSE 'member'::project_role END,
               now(), now()
        FROM users u
        JOIN projects p
          ON p.organization_id = u.organization_id AND p.slug = 'all-knowledge'
        ON CONFLICT (project_id, user_id) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE users u
        SET default_project_id = p.id
        FROM projects p
        WHERE p.organization_id = u.organization_id
          AND p.slug = 'all-knowledge'
          AND u.default_project_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE conversations c
        SET project_id = p.id
        FROM projects p
        WHERE p.organization_id = c.organization_id
          AND p.slug = 'all-knowledge'
          AND c.project_id IS NULL
        """
    )

    op.create_foreign_key(
        "fk_users_org_default_project",
        "users",
        "projects",
        ["organization_id", "default_project_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_conversations_org_project",
        "conversations",
        "projects",
        ["organization_id", "project_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )

    op.alter_column("knowledge_bases", "access_scope", server_default=None)
    op.alter_column("projects", "description", server_default=None)
    op.alter_column("projects", "is_active", server_default=None)
    op.alter_column("project_members", "project_role", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_conversations_org_project", "conversations", type_="foreignkey")
    op.drop_constraint("fk_users_org_default_project", "users", type_="foreignkey")
    op.drop_index("ix_conversations_project_id", table_name="conversations")
    op.drop_column("conversations", "project_id")
    op.drop_index("ix_users_default_project_id", table_name="users")
    op.drop_column("users", "default_project_id")

    op.drop_index("ix_source_access_grants_org_user", table_name="source_access_grants")
    op.drop_table("source_access_grants")
    op.drop_index("ix_project_members_org_user", table_name="project_members")
    op.drop_table("project_members")
    op.drop_index("ix_project_sources_knowledge_base_id", table_name="project_sources")
    op.drop_index("ix_project_sources_org_project", table_name="project_sources")
    op.drop_table("project_sources")
    op.drop_index("ix_projects_organization_id", table_name="projects")
    op.drop_table("projects")

    op.drop_constraint("uq_conversations_org_id", "conversations", type_="unique")
    op.drop_constraint("uq_users_org_id", "users", type_="unique")
    op.drop_constraint("uq_kb_org_id", "knowledge_bases", type_="unique")
    op.drop_column("knowledge_bases", "access_scope")

    project_role.drop(op.get_bind(), checkfirst=True)
    access_scope.drop(op.get_bind(), checkfirst=True)
