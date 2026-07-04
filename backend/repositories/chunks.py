"""Chunk persistence and search.

The only module that knows chunks live in Postgres. A future vector-DB swap
reimplements ChunkSearchRepository behind the same method signatures.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import Chunk, Document


@dataclass(slots=True)
class SearchHit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    content: str
    chunk_metadata: dict
    score: float  # arm-specific raw score; fusion normalizes


class ChunkRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add_all(self, chunks: list[Chunk]) -> None:
        self.db.add_all(chunks)

    async def deactivate_for_document(self, document_id: uuid.UUID) -> None:
        await self.db.execute(
            update(Chunk).where(Chunk.document_id == document_id).values(is_active=False)
        )

    async def delete_for_document(self, document_id: uuid.UUID) -> None:
        await self.db.execute(delete(Chunk).where(Chunk.document_id == document_id))

    async def count_for_kb(self, kb_id: uuid.UUID) -> int:
        return (
            await self.db.scalar(
                select(func.count())
                .select_from(Chunk)
                .where(Chunk.knowledge_base_id == kb_id, Chunk.is_active.is_(True))
            )
            or 0
        )

    async def get_many(self, chunk_ids: list[uuid.UUID]) -> list[Chunk]:
        rows = await self.db.scalars(select(Chunk).where(Chunk.id.in_(chunk_ids)))
        return list(rows)


class ChunkSearchRepository:
    """Dense + sparse retrieval arms. Each returns raw-scored hits; fusion is a pipeline step."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def dense_search(
        self,
        kb_id: uuid.UUID,
        query_embedding: list[float],
        limit: int,
        collection_id: uuid.UUID | None = None,
    ) -> list[SearchHit]:
        distance = Chunk.embedding.cosine_distance(query_embedding)
        stmt = (
            select(
                Chunk.id,
                Chunk.document_id,
                Document.title,
                Chunk.content,
                Chunk.chunk_metadata,
                (1 - distance).label("score"),
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Chunk.knowledge_base_id == kb_id,
                Chunk.is_active.is_(True),
                Chunk.embedding.is_not(None),
                Document.is_deleted.is_(False),
            )
            .order_by(distance)
            .limit(limit)
        )
        if collection_id:
            stmt = stmt.where(Document.collection_id == collection_id)
        rows = await self.db.execute(stmt)
        return [
            SearchHit(r.id, r.document_id, r.title, r.content, r.chunk_metadata, float(r.score))
            for r in rows
        ]

    async def sparse_search(
        self,
        kb_id: uuid.UUID,
        query: str,
        limit: int,
        collection_id: uuid.UUID | None = None,
    ) -> list[SearchHit]:
        tsquery = func.websearch_to_tsquery("english", query)
        rank = func.ts_rank_cd(Chunk.tsv, tsquery)
        stmt = (
            select(
                Chunk.id,
                Chunk.document_id,
                Document.title,
                Chunk.content,
                Chunk.chunk_metadata,
                rank.label("score"),
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Chunk.knowledge_base_id == kb_id,
                Chunk.is_active.is_(True),
                Chunk.tsv.op("@@")(tsquery),
                Document.is_deleted.is_(False),
            )
            .order_by(rank.desc())
            .limit(limit)
        )
        if collection_id:
            stmt = stmt.where(Document.collection_id == collection_id)
        rows = await self.db.execute(stmt)
        return [
            SearchHit(r.id, r.document_id, r.title, r.content, r.chunk_metadata, float(r.score))
            for r in rows
        ]
