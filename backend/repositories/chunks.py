"""Chunk persistence and search.

The only module that knows chunks live in Postgres. A future vector-DB swap
reimplements ChunkSearchRepository behind the same method signatures.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from models import Chunk, Document

_LEXICAL_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_]{1,}")
_ISSUE_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b", re.IGNORECASE)
_LEXICAL_STOPWORDS = {
    "about",
    "also",
    "and",
    "are",
    "can",
    "does",
    "explain",
    "for",
    "from",
    "give",
    "how",
    "into",
    "its",
    "please",
    "say",
    "says",
    "tell",
    "that",
    "the",
    "their",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
}


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
        kb_id: uuid.UUID | Sequence[uuid.UUID],
        query_embedding: list[float],
        limit: int,
        collection_id: uuid.UUID | None = None,
    ) -> list[SearchHit]:
        kb_filter = _knowledge_base_filter(kb_id)
        distance = Chunk.embedding.cosine_distance(query_embedding)
        stmt = (
            select(
                Chunk.id,
                Chunk.document_id,
                Document.title,
                Chunk.content,
                Chunk.chunk_metadata,
                Document.doc_metadata,
                (1 - distance).label("score"),
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(
                kb_filter,
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
            SearchHit(
                r.id,
                r.document_id,
                r.title,
                r.content,
                _merged_metadata(r.chunk_metadata, r.doc_metadata),
                float(r.score),
            )
            for r in rows
        ]

    async def sparse_search(
        self,
        kb_id: uuid.UUID | Sequence[uuid.UUID],
        query: str,
        limit: int,
        collection_id: uuid.UUID | None = None,
    ) -> list[SearchHit]:
        kb_filter = _knowledge_base_filter(kb_id)
        strict_query = func.websearch_to_tsquery("english", query)
        terms = _lexical_query_terms(query)
        broad_query = func.to_tsquery("english", " | ".join(terms)) if terms else strict_query
        title_tsv = func.to_tsvector("english", func.coalesce(Document.title, ""))
        content_rank = (
            0.5 * func.ts_rank_cd(Chunk.tsv, broad_query, 32)
            + 0.3 * func.ts_rank_cd(Chunk.tsv, strict_query, 32)
        )
        title_rank = 1.5 * func.ts_rank_cd(title_tsv, broad_query, 32)
        issue_key = _issue_key(query)
        exact_rank = 0.0
        if issue_key:
            normalized_issue_key = issue_key.lower()
            exact_rank = (
                2.0 * case((func.lower(Document.title).contains(normalized_issue_key), 1.0), else_=0.0)
                + 1.2 * case((func.lower(Chunk.content).contains(normalized_issue_key), 1.0), else_=0.0)
            )
        rank = (content_rank + title_rank + exact_rank).label("score")
        stmt = (
            select(
                Chunk.id,
                Chunk.document_id,
                Document.title,
                Chunk.content,
                Chunk.chunk_metadata,
                Document.doc_metadata,
                rank,
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(
                kb_filter,
                Chunk.is_active.is_(True),
                or_(Chunk.tsv.op("@@")(broad_query), title_tsv.op("@@")(broad_query)),
                Document.is_deleted.is_(False),
            )
            .order_by(rank.desc())
            .limit(limit)
        )
        if collection_id:
            stmt = stmt.where(Document.collection_id == collection_id)
        rows = await self.db.execute(stmt)
        return [
            SearchHit(
                r.id,
                r.document_id,
                r.title,
                r.content,
                _merged_metadata(r.chunk_metadata, r.doc_metadata),
                float(r.score),
            )
            for r in rows
        ]

    async def jira_relationship_search(
        self,
        kb_id: uuid.UUID | Sequence[uuid.UUID],
        *,
        issue_key: str,
        query: str,
        limit: int,
    ) -> list[SearchHit]:
        """Fetch an issue plus child/linked Jira evidence using connector metadata."""

        normalized_key = issue_key.upper()
        kb_filter = _knowledge_base_filter(kb_id)
        issue_key_field = Document.doc_metadata["jira_issue_key"].astext
        parent_key_field = Document.doc_metadata["jira_parent_issue_key"].astext
        child_keys_field = Document.doc_metadata["jira_child_issue_keys"]
        related_keys_field = Document.doc_metadata["jira_related_issue_keys"]
        exact_filter = func.upper(issue_key_field) == normalized_key
        relationship_filter = or_(
            func.upper(parent_key_field) == normalized_key,
            child_keys_field.contains([normalized_key]),
            related_keys_field.contains([normalized_key]),
        )

        query_without_key = _ISSUE_KEY_RE.sub(" ", query)
        terms = _lexical_query_terms(query_without_key)
        if terms:
            broad_query = func.to_tsquery("english", " | ".join(terms))
            relevance = (
                1.4 * func.ts_rank_cd(Chunk.tsv, broad_query, 32)
                + 1.0
                * func.ts_rank_cd(
                    func.to_tsvector("english", func.coalesce(Document.title, "")),
                    broad_query,
                    32,
                )
            )
        else:
            relevance = 0.0

        async def fetch(where: ColumnElement[bool], row_limit: int, relationship_score: float) -> list[SearchHit]:
            score = (relevance + relationship_score).label("score")
            stmt = (
                select(
                    Chunk.id,
                    Chunk.document_id,
                    Document.title,
                    Chunk.content,
                    Chunk.chunk_metadata,
                    Document.doc_metadata,
                    score,
                )
                .join(Document, Document.id == Chunk.document_id)
                .where(
                    kb_filter,
                    where,
                    Chunk.is_active.is_(True),
                    Document.is_deleted.is_(False),
                )
                .order_by(score.desc(), Document.updated_at.desc())
                .limit(row_limit)
            )
            rows = await self.db.execute(stmt)
            return [
                SearchHit(
                    row.id,
                    row.document_id,
                    row.title,
                    row.content,
                    _merged_metadata(row.chunk_metadata, row.doc_metadata),
                    float(row.score),
                )
                for row in rows
            ]

        own_limit = min(4, max(1, limit // 4))
        own = await fetch(exact_filter, own_limit, 1.0)
        connected = await fetch(relationship_filter, max(1, limit - len(own)), 0.8)
        return [*own, *connected]


def _knowledge_base_filter(kb_id: uuid.UUID | Sequence[uuid.UUID]) -> ColumnElement[bool]:
    if isinstance(kb_id, uuid.UUID):
        return Chunk.knowledge_base_id == kb_id
    return Chunk.knowledge_base_id.in_(list(kb_id))


def _merged_metadata(chunk_metadata: dict | None, document_metadata: dict | None) -> dict:
    merged = dict(document_metadata or {})
    merged.update(chunk_metadata or {})
    return merged


def _lexical_query_terms(query: str) -> list[str]:
    """Build a safe relaxed tsquery without letting filler words require a match."""

    terms: list[str] = []
    seen: set[str] = set()
    for token in _LEXICAL_TOKEN_RE.findall(query):
        normalized = token.lower()
        if normalized in _LEXICAL_STOPWORDS or normalized in seen:
            continue
        seen.add(normalized)
        terms.append(normalized)
        if len(terms) >= 12:
            break
    return terms


def _issue_key(query: str) -> str:
    match = _ISSUE_KEY_RE.search(query)
    return match.group(0) if match else ""
