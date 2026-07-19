import uuid

from fastapi import APIRouter
from sqlalchemy import select, update

from api.deps import CurrentUser, DbDep
from api.schemas import (
    DefaultProjectUpdate,
    ProjectCreate,
    ProjectMemberOut,
    ProjectMemberUpdate,
    ProjectOut,
    ProjectSourceUpdate,
    ProjectUpdate,
)
from core.exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationError
from models import KnowledgeBase, Project, ProjectRole, Role, User
from repositories.audit import AuditLogRepository
from repositories.projects import (
    DEFAULT_PROJECT_SLUG,
    ProjectAuthorizationRepository,
    ProjectRepository,
    normalize_project_slug,
)

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(user: CurrentUser, db: DbDep) -> list[ProjectOut]:
    repo = ProjectRepository(db)
    projects = await repo.list_for_user(user)
    return [await _project_out(repo, project, user) for project in projects]


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate, user: CurrentUser, db: DbDep) -> ProjectOut:
    if user.role not in {Role.EDITOR, Role.ADMIN}:
        raise AuthorizationError("Editor or admin role required")
    repo = ProjectRepository(db)
    project = await repo.create(
        user=user,
        name=body.name,
        slug=body.slug,
        description=body.description,
    )
    AuditLogRepository(db).record(
        action="project.create",
        resource_type="project",
        resource_id=str(project.id),
        org_id=user.organization_id,
        actor_id=user.id,
        detail=project.slug,
    )
    await db.commit()
    return await _project_out(repo, project, user)


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: uuid.UUID, user: CurrentUser, db: DbDep) -> ProjectOut:
    repo = ProjectRepository(db)
    project = await repo.resolve_for_user(user, project_id)
    return await _project_out(repo, project, user)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    user: CurrentUser,
    db: DbDep,
) -> ProjectOut:
    repo = ProjectRepository(db)
    project = await repo.get_for_org(project_id, user.organization_id)
    if project is None:
        raise NotFoundError("Project not found")
    await ProjectAuthorizationRepository(db).require_manage(user=user, project=project)
    if body.name is not None:
        project.name = body.name.strip()
    if body.description is not None:
        project.description = body.description.strip()
    if body.slug is not None:
        slug = normalize_project_slug(body.slug)
        existing = await repo.get_by_slug(user.organization_id, slug)
        if existing is not None and existing.id != project.id:
            raise ConflictError("Project with this slug already exists")
        project.slug = slug
    if body.is_active is not None:
        if project.slug == DEFAULT_PROJECT_SLUG and not body.is_active:
            raise ValidationError("The default All Knowledge project cannot be deactivated")
        project.is_active = body.is_active
    AuditLogRepository(db).record(
        action="project.update",
        resource_type="project",
        resource_id=str(project.id),
        org_id=user.organization_id,
        actor_id=user.id,
        detail=project.slug,
    )
    await db.commit()
    return await _project_out(repo, project, user)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, user: CurrentUser, db: DbDep) -> None:
    repo = ProjectRepository(db)
    project = await repo.get_for_org(project_id, user.organization_id)
    if project is None:
        raise NotFoundError("Project not found")
    await ProjectAuthorizationRepository(db).require_manage(user=user, project=project)
    if project.slug == DEFAULT_PROJECT_SLUG:
        raise ValidationError("The default All Knowledge project cannot be deleted")
    project.is_active = False
    default_project = await repo.ensure_default(user.organization_id)
    await db.execute(
        update(User)
        .where(
            User.organization_id == user.organization_id,
            User.default_project_id == project.id,
        )
        .values(default_project_id=default_project.id)
    )
    AuditLogRepository(db).record(
        action="project.delete",
        resource_type="project",
        resource_id=str(project.id),
        org_id=user.organization_id,
        actor_id=user.id,
        detail="deactivated",
    )
    await db.commit()


@router.put("/projects/{project_id}/sources", response_model=ProjectOut)
async def replace_project_sources(
    project_id: uuid.UUID,
    body: ProjectSourceUpdate,
    user: CurrentUser,
    db: DbDep,
) -> ProjectOut:
    repo = ProjectRepository(db)
    project = await repo.get_for_org(project_id, user.organization_id)
    if project is None:
        raise NotFoundError("Project not found")
    await ProjectAuthorizationRepository(db).require_manage(user=user, project=project)
    source_ids = list(dict.fromkeys(body.knowledge_base_ids))
    valid_ids = set(
        await db.scalars(
            select(KnowledgeBase.id).where(
                KnowledgeBase.organization_id == user.organization_id,
                KnowledgeBase.id.in_(source_ids),
            )
        )
    )
    if valid_ids != set(source_ids):
        raise ValidationError("Every project source must belong to the organization")
    await repo.replace_sources(project=project, knowledge_base_ids=source_ids)
    AuditLogRepository(db).record(
        action="project.source.update",
        resource_type="project",
        resource_id=str(project.id),
        org_id=user.organization_id,
        actor_id=user.id,
        detail=f"source_count={len(source_ids)}",
    )
    await db.commit()
    return await _project_out(repo, project, user)


@router.get("/projects/{project_id}/members", response_model=list[ProjectMemberOut])
async def list_project_members(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> list[ProjectMemberOut]:
    repo = ProjectRepository(db)
    project = await repo.resolve_for_user(user, project_id)
    members = await repo.member_rows(project.id)
    users = {
        row.id: row
        for row in await db.scalars(
            select(User).where(
                User.organization_id == user.organization_id,
                User.id.in_([member.user_id for member in members]),
            )
        )
    }
    return [
        ProjectMemberOut(
            user_id=member.user_id,
            full_name=users[member.user_id].full_name,
            email=users[member.user_id].email,
            project_role=member.project_role.value,
        )
        for member in members
        if member.user_id in users
    ]


@router.put("/projects/{project_id}/members", response_model=list[ProjectMemberOut])
async def replace_project_members(
    project_id: uuid.UUID,
    body: ProjectMemberUpdate,
    user: CurrentUser,
    db: DbDep,
) -> list[ProjectMemberOut]:
    if user.role is not Role.ADMIN:
        raise AuthorizationError("Admin role required")
    repo = ProjectRepository(db)
    project = await repo.get_for_org(project_id, user.organization_id)
    if project is None:
        raise NotFoundError("Project not found")
    unique_members = {member.user_id: ProjectRole(member.project_role) for member in body.members}
    valid_ids = set(
        await db.scalars(
            select(User.id).where(
                User.organization_id == user.organization_id,
                User.id.in_(unique_members),
            )
        )
    )
    if valid_ids != set(unique_members):
        raise ValidationError("Every project member must belong to the organization")
    await repo.replace_members(project=project, members=list(unique_members.items()))
    AuditLogRepository(db).record(
        action="project.member.update",
        resource_type="project",
        resource_id=str(project.id),
        org_id=user.organization_id,
        actor_id=user.id,
        detail=f"member_count={len(unique_members)}",
    )
    await db.commit()
    return await list_project_members(project_id, user, db)


@router.put("/users/me/default-project", response_model=ProjectOut)
async def set_default_project(
    body: DefaultProjectUpdate,
    user: CurrentUser,
    db: DbDep,
) -> ProjectOut:
    repo = ProjectRepository(db)
    project = await repo.resolve_for_user(user, body.project_id)
    user.default_project_id = project.id
    AuditLogRepository(db).record(
        action="user.default_project.update",
        resource_type="user",
        resource_id=str(user.id),
        org_id=user.organization_id,
        actor_id=user.id,
        detail=str(project.id),
    )
    await db.commit()
    return await _project_out(repo, project, user)


async def _project_out(repo: ProjectRepository, project: Project, user: User) -> ProjectOut:
    project_role = await repo.manager_role(project.id, user.id)
    authz = ProjectAuthorizationRepository(repo.db)
    authorized_source_ids = (await authz.authorized_scope(user=user, project_id=project.id)).knowledge_base_ids
    if await authz.can_manage(user=user, project=project):
        source_ids = await repo.source_ids(project.id)
    else:
        source_ids = authorized_source_ids
    return ProjectOut(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description,
        is_active=project.is_active,
        source_ids=source_ids,
        authorized_source_ids=authorized_source_ids,
        member_count=await repo.count_members(project.id),
        user_project_role=project_role.value if project_role else None,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )
