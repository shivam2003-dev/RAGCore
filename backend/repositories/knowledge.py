import uuid
from typing import cast

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import Chunk, Collection, Document, DocumentStatus, DocumentVersion, KnowledgeBase


class KnowledgeBaseRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add(self, kb: KnowledgeBase) -> None:
        self.db.add(kb)

    async def get(self, kb_id: uuid.UUID, org_id: uuid.UUID) -> KnowledgeBase | None:
        return cast(
            KnowledgeBase | None,
            await self.db.scalar(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == kb_id,
                    KnowledgeBase.organization_id == org_id,
                )
            ),
        )

    async def list_by_org(self, org_id: uuid.UUID) -> list[KnowledgeBase]:
        rows = await self.db.scalars(
            select(KnowledgeBase).where(KnowledgeBase.organization_id == org_id).order_by(KnowledgeBase.created_at)
        )
        return list(rows)

    async def list_by_ids(self, org_id: uuid.UUID, knowledge_base_ids: list[uuid.UUID]) -> list[KnowledgeBase]:
        if not knowledge_base_ids:
            return []
        rows = await self.db.scalars(
            select(KnowledgeBase)
            .where(
                KnowledgeBase.organization_id == org_id,
                KnowledgeBase.id.in_(knowledge_base_ids),
            )
            .order_by(KnowledgeBase.created_at)
        )
        return list(rows)

    async def get_by_name(self, org_id: uuid.UUID, name: str) -> KnowledgeBase | None:
        return cast(
            KnowledgeBase | None,
            await self.db.scalar(
                select(KnowledgeBase).where(
                    KnowledgeBase.organization_id == org_id,
                    KnowledgeBase.name == name,
                )
            ),
        )


class CollectionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add(self, collection: Collection) -> None:
        self.db.add(collection)

    async def get(self, collection_id: uuid.UUID) -> Collection | None:
        return await self.db.get(Collection, collection_id)

    async def list_by_kb(self, kb_id: uuid.UUID) -> list[Collection]:
        rows = await self.db.scalars(select(Collection).where(Collection.knowledge_base_id == kb_id))
        return list(rows)


class DocumentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add(self, doc: Document) -> None:
        self.db.add(doc)

    def add_version(self, version: DocumentVersion) -> None:
        self.db.add(version)

    async def get(self, doc_id: uuid.UUID) -> Document | None:
        return cast(Document | None, await self.db.get(Document, doc_id))

    async def get_by_metadata_value(self, kb_id: uuid.UUID, key: str, value: str) -> Document | None:
        return cast(
            Document | None,
            await self.db.scalar(
                select(Document)
                .where(
                    Document.knowledge_base_id == kb_id,
                    Document.is_deleted.is_(False),
                    Document.doc_metadata[key].as_string() == value,
                )
                .order_by(Document.updated_at.desc(), Document.created_at.desc())
            ),
        )

    async def list_active_by_metadata_key(
        self,
        kb_id: uuid.UUID,
        key: str,
    ) -> list[Document]:
        rows = await self.db.scalars(
            select(Document)
            .where(
                Document.knowledge_base_id == kb_id,
                Document.is_deleted.is_(False),
                Document.doc_metadata[key].as_string().is_not(None),
            )
            .order_by(Document.updated_at.desc(), Document.created_at.desc())
        )
        return list(rows)

    async def update_metadata(self, doc_id: uuid.UUID, metadata: dict[str, object]) -> None:
        await self.db.execute(update(Document).where(Document.id == doc_id).values(doc_metadata=metadata))

    async def soft_delete_metadata_duplicates(
        self,
        kb_id: uuid.UUID,
        key: str,
        value: str,
        keep_doc_id: uuid.UUID,
    ) -> int:
        rows = await self.db.scalars(
            select(Document.id).where(
                Document.knowledge_base_id == kb_id,
                Document.is_deleted.is_(False),
                Document.id != keep_doc_id,
                Document.doc_metadata[key].as_string() == value,
            )
        )
        duplicate_ids = list(rows)
        if not duplicate_ids:
            return 0
        await self.db.execute(update(Document).where(Document.id.in_(duplicate_ids)).values(is_deleted=True))
        await self.db.execute(update(Chunk).where(Chunk.document_id.in_(duplicate_ids)).values(is_active=False))
        return len(duplicate_ids)

    async def soft_delete_metadata_orphans(
        self,
        *,
        kb_id: uuid.UUID,
        key: str,
        tracked_values: list[str],
        tracked_document_ids: list[uuid.UUID],
    ) -> int:
        if not tracked_values:
            return 0
        stmt = select(Document.id).where(
            Document.knowledge_base_id == kb_id,
            Document.is_deleted.is_(False),
            Document.doc_metadata[key].as_string().in_(tracked_values),
        )
        if tracked_document_ids:
            stmt = stmt.where(Document.id.not_in(tracked_document_ids))
        orphan_ids = list(await self.db.scalars(stmt))
        if not orphan_ids:
            return 0
        await self.db.execute(update(Document).where(Document.id.in_(orphan_ids)).values(is_deleted=True))
        await self.db.execute(update(Chunk).where(Chunk.document_id.in_(orphan_ids)).values(is_active=False))
        return len(orphan_ids)

    async def list_by_kb(self, kb_id: uuid.UUID, limit: int = 50, offset: int = 0) -> tuple[list[Document], int]:
        base = select(Document).where(Document.knowledge_base_id == kb_id, Document.is_deleted.is_(False))
        total = await self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = await self.db.scalars(base.order_by(Document.created_at.desc()).limit(limit).offset(offset))
        return list(rows), total

    async def list_by_org(self, org_id: uuid.UUID, limit: int = 50, offset: int = 0) -> tuple[list[Document], int]:
        base = (
            select(Document)
            .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
            .where(KnowledgeBase.organization_id == org_id, Document.is_deleted.is_(False))
        )
        total = await self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = await self.db.scalars(base.order_by(Document.updated_at.desc()).limit(limit).offset(offset))
        return list(rows), total

    async def list_by_kb_ids(
        self,
        knowledge_base_ids: list[uuid.UUID],
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Document], int]:
        if not knowledge_base_ids:
            return [], 0
        base = select(Document).where(
            Document.knowledge_base_id.in_(knowledge_base_ids),
            Document.is_deleted.is_(False),
        )
        total = await self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = await self.db.scalars(base.order_by(Document.updated_at.desc()).limit(limit).offset(offset))
        return list(rows), total

    async def set_status(self, doc_id: uuid.UUID, status: DocumentStatus, error: str | None = None) -> None:
        await self.db.execute(update(Document).where(Document.id == doc_id).values(status=status, error=error))

    async def soft_delete(self, doc_id: uuid.UUID) -> None:
        await self.db.execute(update(Document).where(Document.id == doc_id).values(is_deleted=True))
        await self.db.execute(update(Chunk).where(Chunk.document_id == doc_id).values(is_active=False))

    async def latest_version(self, doc_id: uuid.UUID) -> DocumentVersion | None:
        return cast(
            DocumentVersion | None,
            await self.db.scalar(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == doc_id)
                .order_by(DocumentVersion.version.desc())
                .limit(1)
            ),
        )
