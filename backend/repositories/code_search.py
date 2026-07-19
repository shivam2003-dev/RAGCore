import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ValidationError
from models import Chunk, Document


@dataclass(slots=True, frozen=True)
class ExactCodeHit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    path: str
    symbol: str | None
    language: str
    commit_sha: str
    url: str
    snippet: str


class CodeSearchRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def exact_search(
        self,
        *,
        query: str,
        authorized_knowledge_base_ids: list[uuid.UUID],
        limit: int = 20,
    ) -> list[ExactCodeHit]:
        needle = validate_exact_code_query(query)
        if not authorized_knowledge_base_ids:
            return []
        rows = await self._db.execute(
            select(Chunk, Document)
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Chunk.knowledge_base_id.in_(authorized_knowledge_base_ids),
                Chunk.is_active.is_(True),
                Document.is_deleted.is_(False),
                Document.doc_metadata["source"].as_string() == "github",
                func.strpos(func.lower(Chunk.content), needle.lower()) > 0,
            )
            .order_by(Document.updated_at.desc(), Chunk.ordinal)
            .limit(max(1, min(limit, 100)))
        )
        hits: list[ExactCodeHit] = []
        for chunk, document in rows:
            metadata = {**(document.doc_metadata or {}), **(chunk.chunk_metadata or {})}
            hits.append(
                ExactCodeHit(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    path=str(metadata.get("github_path") or document.title),
                    symbol=str(metadata["symbol"]) if metadata.get("symbol") else None,
                    language=str(metadata.get("github_language") or metadata.get("language") or "text"),
                    commit_sha=str(metadata.get("github_commit_sha") or ""),
                    url=str(metadata.get("source_url") or ""),
                    snippet=_snippet(chunk.content, needle),
                )
            )
        return hits


def validate_exact_code_query(query: str) -> str:
    value = query.strip()
    if len(value) < 2 or len(value) > 256:
        raise ValidationError("Exact code query must contain 2 to 256 characters")
    if any(ord(character) < 32 for character in value):
        raise ValidationError("Exact code query cannot contain control characters")
    return value


def _snippet(content: str, query: str, radius: int = 240) -> str:
    index = content.lower().find(query.lower())
    if index < 0:
        return content[: radius * 2]
    start = max(0, index - radius)
    end = min(len(content), index + len(query) + radius)
    return content[start:end]
