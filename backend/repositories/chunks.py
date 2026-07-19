"""Chunk persistence and search.

The only module that knows chunks live in Postgres. A future vector-DB swap
reimplements ChunkSearchRepository behind the same method signatures.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Text, case, cast, delete, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from models import Chunk, Document
from retrieval.signals import inverse_document_frequency

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
    chunk_metadata: dict[str, object]
    score: float  # arm-specific raw score; fusion normalizes


@dataclass(slots=True)
class RareTokenSearchResult:
    hits: list[SearchHit]
    document_frequencies: dict[str, int]
    total_documents: int


@dataclass(slots=True)
class NeighborSearchHit:
    anchor_chunk_id: uuid.UUID
    distance: int
    ordinal: int
    token_count: int
    hit: SearchHit


class ChunkRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add_all(self, chunks: list[Chunk]) -> None:
        self.db.add_all(chunks)

    async def deactivate_for_document(self, document_id: uuid.UUID) -> None:
        await self.db.execute(update(Chunk).where(Chunk.document_id == document_id).values(is_active=False))

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
        content_rank = 0.5 * func.ts_rank_cd(Chunk.tsv, broad_query, 32) + 0.3 * func.ts_rank_cd(
            Chunk.tsv, strict_query, 32
        )
        title_rank = 1.5 * func.ts_rank_cd(title_tsv, broad_query, 32)
        issue_key = _issue_key(query)
        exact_rank = 0.0
        if issue_key:
            normalized_issue_key = issue_key.lower()
            exact_rank = 2.0 * case(
                (func.lower(Document.title).contains(normalized_issue_key), 1.0), else_=0.0
            ) + 1.2 * case((func.lower(Chunk.content).contains(normalized_issue_key), 1.0), else_=0.0)
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

    async def exact_identifier_search(
        self,
        kb_id: uuid.UUID | Sequence[uuid.UUID],
        identifiers: list[str],
        limit: int,
        collection_id: uuid.UUID | None = None,
    ) -> list[SearchHit]:
        normalized = [identifier.lower() for identifier in identifiers if identifier.strip()]
        if not normalized:
            return []
        kb_filter = _knowledge_base_filter(kb_id)
        metadata_text = func.lower(cast(Document.doc_metadata, Text))
        match_filters: list[ColumnElement[bool]] = []
        score: ColumnElement[float] = literal(0.0)
        for identifier in normalized:
            title_match = func.lower(Document.title).contains(identifier)
            content_match = func.lower(Chunk.content).contains(identifier)
            metadata_match = metadata_text.contains(identifier)
            match_filters.append(or_(title_match, content_match, metadata_match))
            score += (
                3.0 * case((title_match, 1.0), else_=0.0)
                + 2.0 * case((metadata_match, 1.0), else_=0.0)
                + 1.0 * case((content_match, 1.0), else_=0.0)
            )
        ranked_score = score.label("score")
        stmt = (
            select(
                Chunk.id,
                Chunk.document_id,
                Document.title,
                Chunk.content,
                Chunk.chunk_metadata,
                Document.doc_metadata,
                ranked_score,
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(
                kb_filter,
                Chunk.is_active.is_(True),
                Document.is_deleted.is_(False),
                or_(*match_filters),
            )
            .order_by(ranked_score.desc(), Document.updated_at.desc(), Chunk.ordinal)
            .limit(limit)
        )
        if collection_id:
            stmt = stmt.where(Document.collection_id == collection_id)
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

    async def rare_token_search(
        self,
        kb_id: uuid.UUID | Sequence[uuid.UUID],
        tokens: list[str],
        limit: int,
        collection_id: uuid.UUID | None = None,
    ) -> RareTokenSearchResult:
        normalized = [token.lower() for token in tokens if token.strip()]
        if not normalized:
            return RareTokenSearchResult([], {}, 0)
        kb_filter = _knowledge_base_filter(kb_id)
        document_scope = _document_knowledge_base_filter(kb_id)
        total_stmt = select(func.count(func.distinct(Document.id))).where(
            document_scope,
            Document.is_deleted.is_(False),
        )
        if collection_id:
            total_stmt = total_stmt.where(Document.collection_id == collection_id)
        total_documents = int(await self.db.scalar(total_stmt) or 0)

        frequencies: dict[str, int] = {}
        score: ColumnElement[float] = literal(0.0)
        match_filters: list[ColumnElement[bool]] = []
        for token in normalized:
            token_match = or_(
                func.lower(Document.title).contains(token),
                func.lower(Chunk.content).contains(token),
                func.lower(cast(Document.doc_metadata, Text)).contains(token),
            )
            frequency_stmt = (
                select(func.count(func.distinct(Document.id)))
                .join(Chunk, Chunk.document_id == Document.id)
                .where(
                    document_scope,
                    Document.is_deleted.is_(False),
                    Chunk.is_active.is_(True),
                    token_match,
                )
            )
            if collection_id:
                frequency_stmt = frequency_stmt.where(Document.collection_id == collection_id)
            frequency = int(await self.db.scalar(frequency_stmt) or 0)
            frequencies[token] = frequency
            weight = inverse_document_frequency(total_documents, frequency)
            score += weight * case((token_match, 1.0), else_=0.0)
            match_filters.append(token_match)

        ranked_score = score.label("score")
        stmt = (
            select(
                Chunk.id,
                Chunk.document_id,
                Document.title,
                Chunk.content,
                Chunk.chunk_metadata,
                Document.doc_metadata,
                ranked_score,
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(
                kb_filter,
                Chunk.is_active.is_(True),
                Document.is_deleted.is_(False),
                or_(*match_filters),
            )
            .order_by(ranked_score.desc(), Document.updated_at.desc(), Chunk.ordinal)
            .limit(limit)
        )
        if collection_id:
            stmt = stmt.where(Document.collection_id == collection_id)
        rows = await self.db.execute(stmt)
        return RareTokenSearchResult(
            hits=[
                SearchHit(
                    row.id,
                    row.document_id,
                    row.title,
                    row.content,
                    _merged_metadata(row.chunk_metadata, row.doc_metadata),
                    float(row.score),
                )
                for row in rows
            ],
            document_frequencies=frequencies,
            total_documents=total_documents,
        )

    async def neighboring_chunks(
        self,
        kb_id: uuid.UUID | Sequence[uuid.UUID],
        *,
        anchor_chunk_ids: list[uuid.UUID],
        window: int,
    ) -> list[NeighborSearchHit]:
        if not anchor_chunk_ids or window <= 0:
            return []
        anchor = aliased(Chunk)
        neighbor = aliased(Chunk)
        distance = func.abs(neighbor.ordinal - anchor.ordinal)
        if isinstance(kb_id, uuid.UUID):
            kb_filter = neighbor.knowledge_base_id == kb_id
        else:
            kb_filter = neighbor.knowledge_base_id.in_(list(kb_id))
        rows = await self.db.execute(
            select(
                anchor.id.label("anchor_chunk_id"),
                distance.label("distance"),
                neighbor.id,
                neighbor.document_id,
                Document.title,
                neighbor.content,
                neighbor.ordinal,
                neighbor.token_count,
                neighbor.chunk_metadata,
                Document.doc_metadata,
            )
            .join(
                neighbor,
                (neighbor.document_version_id == anchor.document_version_id) & (distance.between(1, window)),
            )
            .join(Document, Document.id == neighbor.document_id)
            .where(
                anchor.id.in_(anchor_chunk_ids),
                anchor.is_active.is_(True),
                neighbor.is_active.is_(True),
                Document.is_deleted.is_(False),
                kb_filter,
            )
            .order_by(anchor.id, distance, neighbor.ordinal)
        )
        return [
            NeighborSearchHit(
                anchor_chunk_id=row.anchor_chunk_id,
                distance=int(row.distance),
                ordinal=int(row.ordinal),
                token_count=int(row.token_count),
                hit=SearchHit(
                    row.id,
                    row.document_id,
                    row.title,
                    row.content,
                    _merged_metadata(row.chunk_metadata, row.doc_metadata),
                    0.0,
                ),
            )
            for row in rows
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
            relevance = 1.4 * func.ts_rank_cd(Chunk.tsv, broad_query, 32) + 1.0 * func.ts_rank_cd(
                func.to_tsvector("english", func.coalesce(Document.title, "")),
                broad_query,
                32,
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


def _document_knowledge_base_filter(
    kb_id: uuid.UUID | Sequence[uuid.UUID],
) -> ColumnElement[bool]:
    if isinstance(kb_id, uuid.UUID):
        return Document.knowledge_base_id == kb_id
    return Document.knowledge_base_id.in_(list(kb_id))


def _merged_metadata(
    chunk_metadata: dict[str, object] | None,
    document_metadata: dict[str, object] | None,
) -> dict[str, object]:
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
