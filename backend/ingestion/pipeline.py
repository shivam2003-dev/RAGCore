"""Ingestion pipeline: extract → chunk → embed → store. Runs in a background task.

Each run owns its DB session (the request session is gone by the time this
executes). Status transitions and per-stage errors land on the document row.
"""

import uuid
from pathlib import Path

from core.config import Settings, get_settings
from core.logging import get_logger
from database.base import utcnow
from database.session import SessionFactory
from embeddings.base import EmbeddingProvider
from ingestion.chunkers.base import Chunker, count_tokens
from ingestion.chunkers.code import CodeChunker, code_language_for_suffix
from ingestion.chunkers.markdown import MarkdownChunker
from ingestion.chunkers.recursive import RecursiveChunker
from ingestion.extractors.registry import extract_text
from models import Chunk, DocumentStatus
from repositories.chunks import ChunkRepository
from repositories.knowledge import DocumentRepository

log = get_logger(__name__)

_CODE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
}
EMBED_BATCH_SIZE = 64


def select_chunker(suffix: str) -> Chunker:
    if suffix in {".md", ".html", ".htm"}:
        return MarkdownChunker()
    if suffix in _CODE_SUFFIXES:
        return CodeChunker(language=code_language_for_suffix(suffix))
    return RecursiveChunker()


async def ingest_document(
    *,
    document_id: uuid.UUID,
    document_version_id: uuid.UUID,
    kb_id: uuid.UUID,
    file_path: str,
    embedder: EmbeddingProvider,
    embedding_text: str | None = None,
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
            chunk_size, chunk_overlap, chunk_profile = _chunking_profile(
                settings=settings,
                document_metadata=document_metadata,
            )
            text_chunks = chunker.chunk(
                extracted.text,
                chunk_size=chunk_size,
                overlap=chunk_overlap,
            )
            if not text_chunks:
                raise ValueError("Document produced no chunks")

            enriched_chunks = [
                (
                    chunk,
                    _chunk_metadata(
                        chunk_metadata=chunk.metadata,
                        extracted_metadata=extracted.metadata,
                        document_metadata=document_metadata,
                        chunk_profile=chunk_profile,
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap,
                    ),
                )
                for chunk in text_chunks
            ]
            contextual_contents = [
                _contextual_content(chunk.content, chunk_metadata)
                for chunk, chunk_metadata in enriched_chunks
            ]

            embedding_contents = (
                [f"{embedding_text}\n\nSection:\n{content}" for content in contextual_contents]
                if embedding_text and embedding_text.strip()
                else contextual_contents
            )
            embeddings: list[list[float]] = []
            for i in range(0, len(embedding_contents), EMBED_BATCH_SIZE):
                batch = embedding_contents[i : i + EMBED_BATCH_SIZE]
                embeddings.extend(await embedder.embed(batch))

            # replace-then-insert inside one transaction: supersede old version's
            # chunks atomically with the new set
            await chunks_repo.deactivate_for_document(document_id)
            ordinal_to_id: dict[int, uuid.UUID] = {}
            rows: list[Chunk] = []
            for (chunk, chunk_metadata), contextual_content, vector in zip(
                enriched_chunks, contextual_contents, embeddings, strict=True
            ):
                row = Chunk(
                    knowledge_base_id=kb_id,
                    document_id=document_id,
                    document_version_id=document_version_id,
                    ordinal=chunk.ordinal,
                    content=contextual_content,
                    token_count=count_tokens(contextual_content),
                    chunk_metadata=chunk_metadata,
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


def _chunk_metadata(
    *,
    chunk_metadata: dict,
    extracted_metadata: dict,
    document_metadata: dict,
    chunk_profile: str = "default-v1",
    chunk_size: int = 400,
    chunk_overlap: int = 60,
) -> dict:
    merged = dict(document_metadata)
    merged.update(extracted_metadata)
    merged.update(chunk_metadata)

    headings = merged.get("headings")
    if isinstance(headings, list):
        heading_path = " > ".join(str(item).strip() for item in headings if str(item).strip())
    else:
        heading_path = ""

    source_key = (
        merged.get("source_id")
        or merged.get("issue_key")
        or merged.get("page_id")
        or merged.get("jira_issue_key")
        or merged.get("confluence_page_id")
    )
    source_family = str(
        merged.get("source_type")
        or merged.get("source_family")
        or merged.get("source")
        or "upload"
    ).lower()
    merged["chunk_heading_path"] = heading_path
    if heading_path and not merged.get("section_title"):
        merged["section_title"] = heading_path.split(" > ")[-1]
    merged["chunk_source_key"] = str(source_key or "")
    merged["chunk_source_family"] = source_family
    merged["chunk_strategy_version"] = str(merged.get("chunk_strategy_version") or "phase2-structure-v1")
    merged["chunk_profile"] = chunk_profile
    merged["chunk_size_tokens"] = chunk_size
    merged["chunk_overlap_tokens"] = chunk_overlap
    return merged


def _chunking_profile(*, settings: Settings, document_metadata: dict) -> tuple[int, int, str]:
    source_family = str(
        document_metadata.get("source_type")
        or document_metadata.get("source_family")
        or document_metadata.get("source")
        or "upload"
    ).lower()
    if source_family == "jira":
        return (
            settings.jira_chunk_size_tokens,
            settings.jira_chunk_overlap_tokens,
            "jira-relationship-comments-attachments-v5",
        )
    if source_family == "confluence":
        return (
            settings.confluence_chunk_size_tokens,
            settings.confluence_chunk_overlap_tokens,
            "confluence-heading-context-v2",
        )
    return (
        settings.chunk_size_tokens,
        settings.chunk_overlap_tokens,
        "default-v1",
    )


def _contextual_content(content: str, metadata: dict) -> str:
    title = str(metadata.get("source_title") or metadata.get("title") or "").strip()
    source = str(metadata.get("source_type") or metadata.get("source_family") or metadata.get("source") or "").strip()
    space = str(metadata.get("space") or metadata.get("project") or metadata.get("source_space") or "").strip()
    status = str(metadata.get("status") or "").strip()
    updated = str(metadata.get("source_updated_at") or metadata.get("updated_at") or "").strip()
    headings = str(metadata.get("chunk_heading_path") or "").strip()
    kind = str(metadata.get("chunk_kind") or "").strip()
    parent_context = str(metadata.get("parent_context") or "").strip()
    parent_issue = str(metadata.get("jira_parent_issue_key") or "").strip()
    connected_issue_values = metadata.get("jira_child_issue_keys") or metadata.get("jira_related_issue_keys") or []
    connected_issues = (
        ", ".join(str(item) for item in connected_issue_values[:20])
        if isinstance(connected_issue_values, list)
        else ""
    )
    prefix_parts = [
        f"Source type: {source}" if source else "",
        f"Title: {title}" if title else "",
        f"Space/project: {space}" if space else "",
        f"Status: {status}" if status else "",
        f"Updated: {updated}" if updated else "",
        f"Section: {headings}" if headings else "",
        f"Chunk kind: {kind}" if kind else "",
        f"Parent Jira issue: {parent_issue}" if parent_issue else "",
        f"Connected Jira issues: {connected_issues}" if connected_issues else "",
        f"Parent section context: {parent_context}" if parent_context and parent_context not in content else "",
    ]
    prefix = "\n".join(part for part in prefix_parts if part)
    return f"{prefix}\n\n{content.strip()}" if prefix else content.strip()
