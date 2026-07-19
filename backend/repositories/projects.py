import re
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationError
from models import (
    AccessScope,
    KnowledgeBase,
    Project,
    ProjectMember,
    ProjectRole,
    ProjectSource,
    Role,
    SourceAccessGrant,
    User,
)

DEFAULT_PROJECT_NAME = "All Knowledge"
DEFAULT_PROJECT_SLUG = "all-knowledge"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(slots=True)
class AuthorizedProjectScope:
    project: Project
    knowledge_base_ids: list[uuid.UUID]


class ProjectRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_for_org(self, project_id: uuid.UUID, org_id: uuid.UUID) -> Project | None:
        return await self.db.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.organization_id == org_id,
            )
        )

    async def get_by_slug(self, org_id: uuid.UUID, slug: str) -> Project | None:
        return await self.db.scalar(
            select(Project).where(
                Project.organization_id == org_id,
                Project.slug == slug,
            )
        )

    async def ensure_default(self, org_id: uuid.UUID) -> Project:
        project = await self.get_by_slug(org_id, DEFAULT_PROJECT_SLUG)
        if project is not None:
            return project
        project = Project(
            organization_id=org_id,
            name=DEFAULT_PROJECT_NAME,
            slug=DEFAULT_PROJECT_SLUG,
            description="Default project containing the organization's available sources.",
        )
        self.db.add(project)
        await self.db.flush()
        return project

    async def list_for_user(self, user: User, *, include_inactive: bool = False) -> list[Project]:
        stmt = select(Project).where(Project.organization_id == user.organization_id)
        if user.role is not Role.ADMIN:
            stmt = stmt.join(
                ProjectMember,
                (ProjectMember.project_id == Project.id) & (ProjectMember.organization_id == Project.organization_id),
            ).where(ProjectMember.user_id == user.id)
        if not include_inactive:
            stmt = stmt.where(Project.is_active.is_(True))
        rows = await self.db.scalars(stmt.order_by(Project.name, Project.id))
        return list(rows.unique())

    async def resolve_for_user(
        self,
        user: User,
        project_id: uuid.UUID | None = None,
    ) -> Project:
        candidates = await self.list_for_user(user)
        target_id = project_id or user.default_project_id
        if target_id is not None:
            project = next((candidate for candidate in candidates if candidate.id == target_id), None)
            if project is not None:
                return project
            if project_id is not None:
                raise NotFoundError("Project not found")
        if candidates:
            return candidates[0]
        raise AuthorizationError("No active project is available for this user")

    async def add_member(
        self,
        *,
        project: Project,
        user: User,
        project_role: ProjectRole = ProjectRole.MEMBER,
    ) -> ProjectMember:
        existing = await self.db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == user.id,
            )
        )
        if existing is not None:
            existing.project_role = project_role
            return existing
        member = ProjectMember(
            organization_id=project.organization_id,
            project_id=project.id,
            user_id=user.id,
            project_role=project_role,
        )
        self.db.add(member)
        return member

    async def add_source(self, *, project: Project, knowledge_base_id: uuid.UUID) -> ProjectSource:
        existing = await self.db.scalar(
            select(ProjectSource).where(
                ProjectSource.project_id == project.id,
                ProjectSource.knowledge_base_id == knowledge_base_id,
            )
        )
        if existing is not None:
            return existing
        source = ProjectSource(
            organization_id=project.organization_id,
            project_id=project.id,
            knowledge_base_id=knowledge_base_id,
        )
        self.db.add(source)
        return source

    async def source_ids(self, project_id: uuid.UUID) -> list[uuid.UUID]:
        rows = await self.db.scalars(
            select(ProjectSource.knowledge_base_id)
            .where(ProjectSource.project_id == project_id)
            .order_by(ProjectSource.knowledge_base_id)
        )
        return list(rows)

    async def member_rows(self, project_id: uuid.UUID) -> list[ProjectMember]:
        rows = await self.db.scalars(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .order_by(ProjectMember.created_at, ProjectMember.user_id)
        )
        return list(rows)

    async def manager_role(self, project_id: uuid.UUID, user_id: uuid.UUID) -> ProjectRole | None:
        return await self.db.scalar(
            select(ProjectMember.project_role).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )

    async def replace_sources(
        self,
        *,
        project: Project,
        knowledge_base_ids: list[uuid.UUID],
    ) -> None:
        await self.db.execute(delete(ProjectSource).where(ProjectSource.project_id == project.id))
        self.db.add_all(
            ProjectSource(
                organization_id=project.organization_id,
                project_id=project.id,
                knowledge_base_id=knowledge_base_id,
            )
            for knowledge_base_id in knowledge_base_ids
        )

    async def replace_members(
        self,
        *,
        project: Project,
        members: list[tuple[uuid.UUID, ProjectRole]],
    ) -> None:
        await self.db.execute(delete(ProjectMember).where(ProjectMember.project_id == project.id))
        self.db.add_all(
            ProjectMember(
                organization_id=project.organization_id,
                project_id=project.id,
                user_id=user_id,
                project_role=project_role,
            )
            for user_id, project_role in members
        )

    async def create(
        self,
        *,
        user: User,
        name: str,
        description: str,
        slug: str | None = None,
    ) -> Project:
        normalized_slug = normalize_project_slug(slug or name)
        if await self.get_by_slug(user.organization_id, normalized_slug):
            raise ConflictError("Project with this slug already exists")
        project = Project(
            organization_id=user.organization_id,
            name=name.strip(),
            slug=normalized_slug,
            description=description.strip(),
        )
        self.db.add(project)
        await self.db.flush()
        await self.add_member(project=project, user=user, project_role=ProjectRole.MANAGER)
        return project

    async def count_members(self, project_id: uuid.UUID) -> int:
        return int(
            await self.db.scalar(
                select(func.count()).select_from(ProjectMember).where(ProjectMember.project_id == project_id)
            )
            or 0
        )


class ProjectAuthorizationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.projects = ProjectRepository(db)

    async def authorized_scope(
        self,
        *,
        user: User,
        project_id: uuid.UUID | None = None,
    ) -> AuthorizedProjectScope:
        project = await self.projects.resolve_for_user(user, project_id)
        grant_exists = exists(
            select(SourceAccessGrant.id).where(
                SourceAccessGrant.organization_id == user.organization_id,
                SourceAccessGrant.knowledge_base_id == KnowledgeBase.id,
                SourceAccessGrant.user_id == user.id,
            )
        )
        rows = await self.db.scalars(
            select(KnowledgeBase.id)
            .join(
                ProjectSource,
                (ProjectSource.knowledge_base_id == KnowledgeBase.id)
                & (ProjectSource.organization_id == KnowledgeBase.organization_id),
            )
            .where(
                ProjectSource.project_id == project.id,
                KnowledgeBase.organization_id == user.organization_id,
                or_(
                    KnowledgeBase.access_scope == AccessScope.ORGANIZATION,
                    grant_exists,
                ),
            )
            .order_by(KnowledgeBase.id)
        )
        return AuthorizedProjectScope(project=project, knowledge_base_ids=list(rows))

    async def require_source(
        self,
        *,
        user: User,
        knowledge_base_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
    ) -> AuthorizedProjectScope:
        scope = await self.authorized_scope(user=user, project_id=project_id)
        if knowledge_base_id not in scope.knowledge_base_ids:
            raise NotFoundError("Knowledge base not found")
        return scope

    async def require_source_any_project(
        self,
        *,
        user: User,
        knowledge_base_id: uuid.UUID,
    ) -> None:
        if knowledge_base_id not in await self.authorized_source_ids_any_project(user):
            raise NotFoundError("Knowledge base not found")

    async def authorized_source_ids_any_project(self, user: User) -> list[uuid.UUID]:
        projects = await self.projects.list_for_user(user)
        source_ids: set[uuid.UUID] = set()
        for project in projects:
            scope = await self.authorized_scope(user=user, project_id=project.id)
            source_ids.update(scope.knowledge_base_ids)
        return sorted(source_ids, key=str)

    async def can_manage(self, *, user: User, project: Project) -> bool:
        if project.organization_id != user.organization_id:
            return False
        if user.role is Role.ADMIN:
            return True
        if user.role is not Role.EDITOR:
            return False
        return (await self.projects.manager_role(project.id, user.id)) is ProjectRole.MANAGER

    async def require_manage(self, *, user: User, project: Project) -> None:
        if not await self.can_manage(user=user, project=project):
            raise AuthorizationError("Project manager or admin role required")

    async def replace_source_grants(
        self,
        *,
        actor: User,
        knowledge_base: KnowledgeBase,
        user_ids: list[uuid.UUID],
    ) -> None:
        if knowledge_base.organization_id != actor.organization_id:
            raise NotFoundError("Knowledge base not found")
        if actor.role is not Role.ADMIN:
            raise AuthorizationError("Admin role required")
        valid_user_ids = set(
            await self.db.scalars(
                select(User.id).where(
                    User.organization_id == actor.organization_id,
                    User.id.in_(user_ids),
                )
            )
        )
        if valid_user_ids != set(user_ids):
            raise ValidationError("Every source grant user must belong to the organization")
        await self.db.execute(delete(SourceAccessGrant).where(SourceAccessGrant.knowledge_base_id == knowledge_base.id))
        self.db.add_all(
            SourceAccessGrant(
                organization_id=actor.organization_id,
                knowledge_base_id=knowledge_base.id,
                user_id=user_id,
                granted_by=actor.id,
            )
            for user_id in user_ids
        )

    async def source_grant_user_ids(self, knowledge_base_id: uuid.UUID) -> list[uuid.UUID]:
        rows = await self.db.scalars(
            select(SourceAccessGrant.user_id)
            .where(SourceAccessGrant.knowledge_base_id == knowledge_base_id)
            .order_by(SourceAccessGrant.user_id)
        )
        return list(rows)


def normalize_project_slug(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.strip().lower()).strip("-")[:100]
    if not slug:
        raise ValidationError("Project slug must contain a letter or number")
    return slug
