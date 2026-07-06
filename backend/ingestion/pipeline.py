"""Ingestion pipeline: extract → chunk → embed → store. Runs in a background task.

Each run owns its DB session (the request session is gone by the time this
executes). Status transitions and per-stage errors land on the document row.
"""

import uuid
from pathlib import Path

from core.config import get_settings
from core.logging import get_logger
from database.base import utcnow
from database.session import SessionFactory
from embeddings.base import EmbeddingProvider
from ingestion.chunkers.base import Chunker
from ingestion.chunkers.code import CodeChunker
from ingestion.chunkers.markdown import MarkdownChunker
from ingestion.chunkers.recursive import RecursiveChunker
from ingestion.extractors.registry import extract_text
from models import Chunk, DocumentStatus
from repositories.chunks import ChunkRepository
from repositories.knowledge import DocumentRepository

log = get_logger(__name__)

_CODE_SUFFIXES = {".py", ".ts", ".js", ".go", ".java", ".rs"}
EMBED_BATCH_SIZE = 64


def select_chunker(suffix: str) -> Chunker:
    if suffix == ".md":
        return MarkdownChunker()
    if suffix in _CODE_SUFFIXES:
        return CodeChunker()
    return RecursiveChunker()


async def ingest_document(
    *,
    document_id: uuid.UUID,
    document_version_id: uuid.UUID,
    kb_id: uuid.UUID,
    file_path: str,
    embedder: EmbeddingProvider,
) -> None:
    settings = get_settings()
    async with SessionFactory() as db:
        docs = DocumentRepository(db)
        chunks_repo = ChunkRepository(db)
        try:
            await docs.set_status(document_id, DocumentStatus.PROCESSING)
            await db.commit()

            doc = await docs.get(document_id)
            if doc is None:
                raise ValueError("Document not found")
            document_metadata = dict(doc.doc_metadata or {})
            path = Path(file_path)
            extracted = extract_text(path)
            chunker = select_chunker(path.suffix.lower())
            text_chunks = chunker.chunk(
                extracted.text,
                chunk_size=settings.chunk_size_tokens,
                overlap=settings.chunk_overlap_tokens,
            )
            if not text_chunks:
                raise ValueError("Document produced no chunks")

            embeddings: list[list[float]] = []
            for i in range(0, len(text_chunks), EMBED_BATCH_SIZE):
                batch = text_chunks[i : i + EMBED_BATCH_SIZE]
                embeddings.extend(await embedder.embed([c.content for c in batch]))

            # replace-then-insert inside one transaction: supersede old version's
            # chunks atomically with the new set
            await chunks_repo.deactivate_for_document(document_id)
            ordinal_to_id: dict[int, uuid.UUID] = {}
            rows: list[Chunk] = []
            for chunk, vector in zip(text_chunks, embeddings, strict=True):
                row = Chunk(
                    knowledge_base_id=kb_id,
                    document_id=document_id,
                    document_version_id=document_version_id,
                    ordinal=chunk.ordinal,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    chunk_metadata=chunk.metadata | extracted.metadata | document_metadata,
                    embedding=vector,
                    parent_id=(
                        ordinal_to_id.get(chunk.parent_ordinal)
                        if chunk.parent_ordinal is not None
                        else None
                    ),
                    created_at=utcnow(),
                )
                ordinal_to_id[chunk.ordinal] = row.id
                rows.append(row)
            chunks_repo.add_all(rows)
            await docs.set_status(document_id, DocumentStatus.READY)
            await db.commit()
            log.info("document_ingested", document_id=str(document_id), chunks=len(rows))
        except Exception as exc:
            await db.rollback()
            await docs.set_status(document_id, DocumentStatus.FAILED, error=str(exc)[:2000])
            await db.commit()
            log.error("document_ingestion_failed", document_id=str(document_id), error=str(exc))
