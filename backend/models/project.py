import enum
import uuid

from sqlalchemy import Enum, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin, UUIDPKMixin


class ProjectRole(enum.StrEnum):
    MEMBER = "member"
    MANAGER = "manager"


class Project(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_projects_org_slug"),
        UniqueConstraint("organization_id", "id", name="uq_projects_org_id"),
        Index("ix_projects_organization_id", "organization_id"),
    )


class ProjectSource(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "project_sources"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
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
        UniqueConstraint("project_id", "knowledge_base_id", name="uq_project_sources_pair"),
        Index("ix_project_sources_org_project", "organization_id", "project_id"),
        Index("ix_project_sources_knowledge_base_id", "knowledge_base_id"),
    )


class ProjectMember(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "project_members"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    project_role: Mapped[ProjectRole] = mapped_column(
        Enum(ProjectRole, name="project_role", values_callable=lambda values: [item.value for item in values]),
        default=ProjectRole.MEMBER,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("project_id", "user_id", name="uq_project_members_pair"),
        Index("ix_project_members_org_user", "organization_id", "user_id"),
    )


class SourceAccessGrant(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "source_access_grants"

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    granted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "knowledge_base_id"],
            ["knowledge_bases.organization_id", "knowledge_bases.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("knowledge_base_id", "user_id", name="uq_source_access_grants_pair"),
        Index("ix_source_access_grants_org_user", "organization_id", "user_id"),
    )
