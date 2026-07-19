import uuid

from fastapi import APIRouter

from api.deps import CurrentUser, DbDep, SettingsDep, require_role
from api.schemas import (
    CollectionCreate,
    CollectionOut,
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    SourcePermissionOut,
    SourcePermissionUpdate,
)
from core.exceptions import ConflictError, NotFoundError
from models import AccessScope, Collection, KnowledgeBase, Role
from repositories.audit import AuditLogRepository
from repositories.knowledge import CollectionRepository, KnowledgeBaseRepository
from repositories.projects import ProjectAuthorizationRepository, ProjectRepository

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


@router.post("", response_model=KnowledgeBaseOut, status_code=201, dependencies=[require_role(Role.ADMIN)])
async def create_kb(body: KnowledgeBaseCreate, user: CurrentUser, db: DbDep, settings: SettingsDep) -> KnowledgeBaseOut:
    repo = KnowledgeBaseRepository(db)
    existing = [kb for kb in await repo.list_by_org(user.organization_id) if kb.name == body.name]
    if existing:
        raise ConflictError("Knowledge base with this name exists")
    kb = KnowledgeBase(
        organization_id=user.organization_id,
        name=body.name,
        description=body.description,
        embedding_model=settings.embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
    )
    repo.add(kb)
    await db.flush()
    default_project = await ProjectRepository(db).ensure_default(user.organization_id)
    await ProjectRepository(db).add_source(
        project=default_project,
        knowledge_base_id=kb.id,
    )
    await db.commit()
    return KnowledgeBaseOut.model_validate(kb)


@router.get("", response_model=list[KnowledgeBaseOut])
async def list_kbs(user: CurrentUser, db: DbDep) -> list[KnowledgeBaseOut]:
    repo = KnowledgeBaseRepository(db)
    if user.role is Role.ADMIN:
        kbs = await repo.list_by_org(user.organization_id)
    else:
        authorized_ids = await ProjectAuthorizationRepository(db).authorized_source_ids_any_project(user)
        kbs = await repo.list_by_ids(user.organization_id, authorized_ids)
    return [KnowledgeBaseOut.model_validate(kb) for kb in kbs]


@router.get("/{kb_id}/permissions", response_model=SourcePermissionOut)
async def get_source_permissions(
    kb_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
) -> SourcePermissionOut:
    if user.role is not Role.ADMIN:
        from core.exceptions import AuthorizationError

        raise AuthorizationError("Admin role required")
    kb = await KnowledgeBaseRepository(db).get(kb_id, user.organization_id)
    if kb is None:
        raise NotFoundError("Knowledge base not found")
    authz = ProjectAuthorizationRepository(db)
    return SourcePermissionOut(
        knowledge_base_id=kb.id,
        access_scope=kb.access_scope.value,
        user_ids=await authz.source_grant_user_ids(kb.id),
    )


@router.put("/{kb_id}/permissions", response_model=SourcePermissionOut)
async def update_source_permissions(
    kb_id: uuid.UUID,
    body: SourcePermissionUpdate,
    user: CurrentUser,
    db: DbDep,
) -> SourcePermissionOut:
    if user.role is not Role.ADMIN:
        from core.exceptions import AuthorizationError

        raise AuthorizationError("Admin role required")
    kb = await KnowledgeBaseRepository(db).get(kb_id, user.organization_id)
    if kb is None:
        raise NotFoundError("Knowledge base not found")
    kb.access_scope = AccessScope(body.access_scope)
    authz = ProjectAuthorizationRepository(db)
    await authz.replace_source_grants(
        actor=user,
        knowledge_base=kb,
        user_ids=list(dict.fromkeys(body.user_ids)),
    )
    AuditLogRepository(db).record(
        action="source.permission.update",
        resource_type="knowledge_base",
        resource_id=str(kb.id),
        org_id=user.organization_id,
        actor_id=user.id,
        detail=f"scope={kb.access_scope.value} grants={len(set(body.user_ids))}",
    )
    await db.commit()
    return SourcePermissionOut(
        knowledge_base_id=kb.id,
        access_scope=kb.access_scope.value,
        user_ids=await authz.source_grant_user_ids(kb.id),
    )


@router.get("/{kb_id}", response_model=KnowledgeBaseOut)
async def get_kb(kb_id: uuid.UUID, user: CurrentUser, db: DbDep) -> KnowledgeBaseOut:
    kb = await KnowledgeBaseRepository(db).get(kb_id, user.organization_id)
    if kb is None:
        raise NotFoundError("Knowledge base not found")
    if user.role is not Role.ADMIN:
        await ProjectAuthorizationRepository(db).require_source_any_project(
            user=user,
            knowledge_base_id=kb_id,
        )
    return KnowledgeBaseOut.model_validate(kb)


@router.post(
    "/{kb_id}/collections",
    response_model=CollectionOut,
    status_code=201,
    dependencies=[require_role(Role.ADMIN)],
)
async def create_collection(kb_id: uuid.UUID, body: CollectionCreate, user: CurrentUser, db: DbDep) -> CollectionOut:
    kb = await KnowledgeBaseRepository(db).get(kb_id, user.organization_id)
    if kb is None:
        raise NotFoundError("Knowledge base not found")
    if user.role is not Role.ADMIN:
        await ProjectAuthorizationRepository(db).require_source_any_project(
            user=user,
            knowledge_base_id=kb_id,
        )
    collection = Collection(knowledge_base_id=kb_id, name=body.name, description=body.description)
    CollectionRepository(db).add(collection)
    await db.commit()
    return CollectionOut.model_validate(collection)


@router.get("/{kb_id}/collections", response_model=list[CollectionOut])
async def list_collections(kb_id: uuid.UUID, user: CurrentUser, db: DbDep) -> list[CollectionOut]:
    kb = await KnowledgeBaseRepository(db).get(kb_id, user.organization_id)
    if kb is None:
        raise NotFoundError("Knowledge base not found")
    if user.role is not Role.ADMIN:
        await ProjectAuthorizationRepository(db).require_source_any_project(
            user=user,
            knowledge_base_id=kb_id,
        )
    collections = await CollectionRepository(db).list_by_kb(kb_id)
    return [CollectionOut.model_validate(c) for c in collections]
