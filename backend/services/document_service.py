import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.exceptions import NotFoundError, ValidationError
from database.base import utcnow
from embeddings.base import EmbeddingProvider
from ingestion.extractors.base import MAGIC_BYTES
from ingestion.extractors.registry import SUPPORTED_SUFFIXES
from ingestion.pipeline import ingest_document
from ingestion.queue import IngestionQueue
from models import Document, DocumentStatus, DocumentVersion, User
from repositories.audit import AuditLogRepository
from repositories.knowledge import DocumentRepository, KnowledgeBaseRepository


class DocumentService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        settings: Settings,
        embedder: EmbeddingProvider,
        queue: IngestionQueue,
    ) -> None:
        self._db = db
        self._settings = settings
        self._embedder = embedder
        self._queue = queue
        self._docs = DocumentRepository(db)
        self._kbs = KnowledgeBaseRepository(db)
        self._audit = AuditLogRepository(db)

    async def upload(
        self,
        *,
        user: User,
        kb_id: uuid.UUID,
        file: UploadFile,
        collection_id: uuid.UUID | None = None,
        existing_document_id: uuid.UUID | None = None,
    ) -> Document:
        filename = file.filename or "untitled"
        content = await file.read()
        return await self.create_from_bytes(
            user=user,
            kb_id=kb_id,
            filename=filename,
            content=content,
            collection_id=collection_id,
            existing_document_id=existing_document_id,
            audit_action="document.upload",
        )

    async def create_from_bytes(
        self,
        *,
        user: User,
        kb_id: uuid.UUID,
        filename: str,
        content: bytes,
        collection_id: uuid.UUID | None = None,
        existing_document_id: uuid.UUID | None = None,
        title: str | None = None,
        metadata: dict[str, object] | None = None,
        audit_action: str = "document.upload",
    ) -> Document:
        kb = await self._kbs.get(kb_id, user.organization_id)
        if kb is None:
            raise NotFoundError("Knowledge base not found")

        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise ValidationError(f"Unsupported file type: {suffix or 'unknown'}")

        if len(content) > self._settings.upload_max_bytes:
            raise ValidationError("File exceeds size limit")
        if not content:
            raise ValidationError("Empty file")
        self._validate_magic(suffix, content)

        if existing_document_id:  # new version of an existing document
            doc = await self._docs.get(existing_document_id)
            if doc is None or doc.knowledge_base_id != kb_id or doc.is_deleted:
                raise NotFoundError("Document not found")
            doc.current_version += 1
            doc.status = DocumentStatus.UPLOADED
            doc.error = None
            doc.title = title or doc.title
            if metadata is not None:
                doc.doc_metadata = metadata
            version_number = doc.current_version
        else:
            doc = Document(
                knowledge_base_id=kb_id,
                collection_id=collection_id,
                uploaded_by=user.id,
                title=title or Path(filename or "untitled").name,
                source_type=suffix.lstrip("."),
                status=DocumentStatus.UPLOADED,
                doc_metadata=metadata or {},
            )
            self._docs.add(doc)
            version_number = 1
        await self._db.flush()

        stored_path = self._store_file(doc.id, version_number, suffix, content)
        version = DocumentVersion(
            document_id=doc.id,
            version=version_number,
            file_path=str(stored_path),
            file_sha256=hashlib.sha256(content).hexdigest(),
            file_size_bytes=len(content),
            created_at=utcnow(),
        )
        self._docs.add_version(version)
        self._audit.record(
            action=audit_action,
            resource_type="document",
            resource_id=str(doc.id),
            org_id=user.organization_id,
            actor_id=user.id,
            detail=f"{doc.title} v{version_number}",
        )
        await self._db.commit()

        self._queue.enqueue(
            ingest_document,
            document_id=doc.id,
            document_version_id=version.id,
            kb_id=kb_id,
            file_path=str(stored_path),
            embedder=self._embedder,
        )
        return doc

    async def reindex(self, *, user: User, document_id: uuid.UUID) -> Document:
        doc = await self._docs.get(document_id)
        if doc is None or doc.is_deleted:
            raise NotFoundError("Document not found")
        kb = await self._kbs.get(doc.knowledge_base_id, user.organization_id)
        if kb is None:
            raise NotFoundError("Document not found")
        version = await self._docs.latest_version(document_id)
        if version is None:
            raise NotFoundError("No stored file for document")
        await self._docs.set_status(document_id, DocumentStatus.UPLOADED)
        await self._db.commit()
        self._queue.enqueue(
            ingest_document,
            document_id=document_id,
            document_version_id=version.id,
            kb_id=doc.knowledge_base_id,
            file_path=version.file_path,
            embedder=self._embedder,
        )
        return doc

    async def delete(self, *, user: User, document_id: uuid.UUID) -> None:
        doc = await self._docs.get(document_id)
        if doc is None or doc.is_deleted:
            raise NotFoundError("Document not found")
        kb = await self._kbs.get(doc.knowledge_base_id, user.organization_id)
        if kb is None:
            raise NotFoundError("Document not found")
        await self._docs.soft_delete(document_id)
        self._audit.record(
            action="document.delete",
            resource_type="document",
            resource_id=str(document_id),
            org_id=user.organization_id,
            actor_id=user.id,
        )
        await self._db.commit()

    def _validate_magic(self, suffix: str, content: bytes) -> None:
        signatures = MAGIC_BYTES.get(suffix, ())
        if signatures:
            if not any(content.startswith(sig) for sig in signatures):
                raise ValidationError("File content does not match its extension")
        else:  # text formats: must decode
            try:
                content[:65536].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValidationError("File is not valid UTF-8 text") from exc

    def _store_file(self, doc_id: uuid.UUID, version: int, suffix: str, content: bytes) -> Path:
        base = Path(self._settings.upload_dir)
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{doc_id}_v{version}{suffix}"
        path.write_bytes(content)
        return path
