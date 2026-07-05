import uuid

from fastapi import APIRouter

from api.deps import CurrentUser, DbDep, SettingsDep, require_role
from api.schemas import (
    CollectionCreate,
    CollectionOut,
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
)
from core.exceptions import ConflictError, NotFoundError
from models import Collection, KnowledgeBase, Role
from repositories.knowledge import CollectionRepository, KnowledgeBaseRepository

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
    await db.commit()
    return KnowledgeBaseOut.model_validate(kb)


@router.get("", response_model=list[KnowledgeBaseOut])
async def list_kbs(user: CurrentUser, db: DbDep) -> list[KnowledgeBaseOut]:
    kbs = await KnowledgeBaseRepository(db).list_by_org(user.organization_id)
    return [KnowledgeBaseOut.model_validate(kb) for kb in kbs]


@router.get("/{kb_id}", response_model=KnowledgeBaseOut)
async def get_kb(kb_id: uuid.UUID, user: CurrentUser, db: DbDep) -> KnowledgeBaseOut:
    kb = await KnowledgeBaseRepository(db).get(kb_id, user.organization_id)
    if kb is None:
        raise NotFoundError("Knowledge base not found")
    return KnowledgeBaseOut.model_validate(kb)


@router.post(
    "/{kb_id}/collections",
    response_model=CollectionOut,
    status_code=201,
    dependencies=[require_role(Role.ADMIN)],
)
async def create_collection(
    kb_id: uuid.UUID, body: CollectionCreate, user: CurrentUser, db: DbDep
) -> CollectionOut:
    kb = await KnowledgeBaseRepository(db).get(kb_id, user.organization_id)
    if kb is None:
        raise NotFoundError("Knowledge base not found")
    collection = Collection(knowledge_base_id=kb_id, name=body.name, description=body.description)
    CollectionRepository(db).add(collection)
    await db.commit()
    return CollectionOut.model_validate(collection)


@router.get("/{kb_id}/collections", response_model=list[CollectionOut])
async def list_collections(kb_id: uuid.UUID, user: CurrentUser, db: DbDep) -> list[CollectionOut]:
    kb = await KnowledgeBaseRepository(db).get(kb_id, user.organization_id)
    if kb is None:
        raise NotFoundError("Knowledge base not found")
    collections = await CollectionRepository(db).list_by_kb(kb_id)
    return [CollectionOut.model_validate(c) for c in collections]
