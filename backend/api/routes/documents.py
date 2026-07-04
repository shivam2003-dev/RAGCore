import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from api.deps import CurrentUser, DbDep, DocumentServiceDep, require_role
from api.schemas import DocumentListOut, DocumentOut
from core.exceptions import NotFoundError
from models import Role
from repositories.knowledge import DocumentRepository, KnowledgeBaseRepository

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentOut, status_code=202, dependencies=[require_role(Role.EDITOR)])
async def upload_document(
    user: CurrentUser,
    service: DocumentServiceDep,
    file: Annotated[UploadFile, File()],
    knowledge_base_id: Annotated[uuid.UUID, Form()],
    collection_id: Annotated[uuid.UUID | None, Form()] = None,
    document_id: Annotated[uuid.UUID | None, Form()] = None,  # set → new version
) -> DocumentOut:
    doc = await service.upload(
        user=user,
        kb_id=knowledge_base_id,
        file=file,
        collection_id=collection_id,
        existing_document_id=document_id,
    )
    return DocumentOut.model_validate(doc)


@router.get("", response_model=DocumentListOut)
async def list_documents(
    knowledge_base_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    limit: int = 50,
    offset: int = 0,
) -> DocumentListOut:
    kb = await KnowledgeBaseRepository(db).get(knowledge_base_id, user.organization_id)
    if kb is None:
        raise NotFoundError("Knowledge base not found")
    docs, total = await DocumentRepository(db).list_by_kb(
        knowledge_base_id, limit=min(limit, 200), offset=offset
    )
    return DocumentListOut(items=[DocumentOut.model_validate(d) for d in docs], total=total)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: uuid.UUID, user: CurrentUser, db: DbDep) -> DocumentOut:
    doc = await DocumentRepository(db).get(document_id)
    if doc is None or doc.is_deleted:
        raise NotFoundError("Document not found")
    kb = await KnowledgeBaseRepository(db).get(doc.knowledge_base_id, user.organization_id)
    if kb is None:
        raise NotFoundError("Document not found")
    return DocumentOut.model_validate(doc)


@router.post(
    "/{document_id}/reindex",
    response_model=DocumentOut,
    status_code=202,
    dependencies=[require_role(Role.EDITOR)],
)
async def reindex_document(
    document_id: uuid.UUID, user: CurrentUser, service: DocumentServiceDep
) -> DocumentOut:
    doc = await service.reindex(user=user, document_id=document_id)
    return DocumentOut.model_validate(doc)


@router.delete("/{document_id}", status_code=204, dependencies=[require_role(Role.EDITOR)])
async def delete_document(
    document_id: uuid.UUID, user: CurrentUser, service: DocumentServiceDep
) -> None:
    await service.delete(user=user, document_id=document_id)
