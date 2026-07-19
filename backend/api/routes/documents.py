import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from sqlalchemy import func, select

from api.deps import CurrentUser, DbDep, DocumentServiceDep, require_role
from api.schemas import DocumentLineageOut, DocumentListOut, DocumentOut, DocumentVersionLineageOut
from core.exceptions import NotFoundError
from models import Chunk, DocumentVersion, Role
from repositories.knowledge import DocumentRepository, KnowledgeBaseRepository
from repositories.projects import ProjectAuthorizationRepository

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentOut, status_code=202, dependencies=[require_role(Role.ADMIN)])
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


@router.get("", response_model=DocumentListOut, dependencies=[require_role(Role.ADMIN)])
async def list_documents(
    user: CurrentUser,
    db: DbDep,
    knowledge_base_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> DocumentListOut:
    repo = DocumentRepository(db)
    bounded_limit = min(max(limit, 1), 1000)
    authorized_ids = await ProjectAuthorizationRepository(db).authorized_source_ids_any_project(user)
    kb_names = {
        kb.id: kb.name
        for kb in await KnowledgeBaseRepository(db).list_by_ids(
            user.organization_id,
            authorized_ids,
        )
    }
    if knowledge_base_id is not None:
        if knowledge_base_id not in authorized_ids:
            raise NotFoundError("Knowledge base not found")
        docs, total = await repo.list_by_kb(knowledge_base_id, limit=bounded_limit, offset=offset)
    else:
        docs, total = await repo.list_by_kb_ids(
            authorized_ids,
            limit=bounded_limit,
            offset=offset,
        )
    return DocumentListOut(
        items=[
            DocumentOut.model_validate(d).model_copy(update={"knowledge_base_name": kb_names.get(d.knowledge_base_id)})
            for d in docs
        ],
        total=total,
    )


@router.get("/{document_id}", response_model=DocumentOut, dependencies=[require_role(Role.ADMIN)])
async def get_document(document_id: uuid.UUID, user: CurrentUser, db: DbDep) -> DocumentOut:
    doc = await DocumentRepository(db).get(document_id)
    if doc is None or doc.is_deleted:
        raise NotFoundError("Document not found")
    kb = await KnowledgeBaseRepository(db).get(doc.knowledge_base_id, user.organization_id)
    if kb is None:
        raise NotFoundError("Document not found")
    await ProjectAuthorizationRepository(db).require_source_any_project(
        user=user,
        knowledge_base_id=doc.knowledge_base_id,
    )
    return DocumentOut.model_validate(doc)


@router.get("/{document_id}/lineage", response_model=DocumentLineageOut, dependencies=[require_role(Role.ADMIN)])
async def get_document_lineage(document_id: uuid.UUID, user: CurrentUser, db: DbDep) -> DocumentLineageOut:
    doc = await DocumentRepository(db).get(document_id)
    if doc is None or doc.is_deleted:
        raise NotFoundError("Document not found")
    kb = await KnowledgeBaseRepository(db).get(doc.knowledge_base_id, user.organization_id)
    if kb is None:
        raise NotFoundError("Document not found")
    await ProjectAuthorizationRepository(db).require_source_any_project(
        user=user,
        knowledge_base_id=doc.knowledge_base_id,
    )

    chunk_counts = (
        await db.execute(
            select(
                func.count(Chunk.id),
                func.count(Chunk.id).filter(Chunk.is_active.is_(True)),
            ).where(Chunk.document_id == document_id)
        )
    ).one()
    versions = await db.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version.desc())
    )
    metadata = doc.doc_metadata or {}
    source_system = str(metadata.get("source") or doc.source_type or "unknown")
    return DocumentLineageOut(
        id=doc.id,
        knowledge_base_id=doc.knowledge_base_id,
        knowledge_base_name=kb.name,
        title=doc.title,
        source_type=doc.source_type,
        source_system=source_system,
        source_id=_source_id(metadata, source_system),
        source_url=_source_url(metadata),
        source_version=(
            metadata.get("source_version")
            or metadata.get("confluence_version")
            or metadata.get("jira_issue_updated_at")
            or metadata.get("jira_updated_at")
        ),
        source_updated_at=_source_updated_at(metadata, source_system),
        source_sha256=metadata.get("source_sha256") if isinstance(metadata.get("source_sha256"), str) else None,
        status=doc.status.value,
        current_version=doc.current_version,
        chunk_count=int(chunk_counts[0] or 0),
        active_chunk_count=int(chunk_counts[1] or 0),
        embedding_model=kb.embedding_model,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        metadata=metadata,
        versions=[
            DocumentVersionLineageOut(
                version=version.version,
                file_sha256=version.file_sha256,
                file_size_bytes=version.file_size_bytes,
                created_at=version.created_at,
            )
            for version in versions
        ],
    )


@router.post(
    "/{document_id}/reindex",
    response_model=DocumentOut,
    status_code=202,
    dependencies=[require_role(Role.ADMIN)],
)
async def reindex_document(document_id: uuid.UUID, user: CurrentUser, service: DocumentServiceDep) -> DocumentOut:
    doc = await service.reindex(user=user, document_id=document_id)
    return DocumentOut.model_validate(doc)


@router.delete("/{document_id}", status_code=204, dependencies=[require_role(Role.ADMIN)])
async def delete_document(document_id: uuid.UUID, user: CurrentUser, service: DocumentServiceDep) -> None:
    await service.delete(user=user, document_id=document_id)


def _source_url(metadata: dict) -> str | None:
    for key in ("source_url", "source-url", "confluence_page_url", "jira_issue_url", "url"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _source_id(metadata: dict, source_system: str) -> str | None:
    keys = {
        "confluence": ("source_id", "confluence_page_id", "page_id"),
        "jira": ("source_id", "jira_issue_key", "jira_issue_id", "issue_key", "issue_id"),
    }.get(source_system.lower(), ("source_id", "id"))
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, (str, int)) and str(value):
            return str(value)
    return None


def _source_updated_at(metadata: dict, source_system: str) -> str | None:
    keys = {
        "confluence": ("source_updated_at", "updated_at", "confluence_version_created_at"),
        "jira": ("source_updated_at", "updated_at", "jira_issue_updated_at", "jira_updated_at"),
    }.get(source_system.lower(), ("source_updated_at", "updated_at"))
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    return None
