"""Markdown-aware chunking: split at headings first so sections stay intact,
carry the heading path into chunk metadata, delegate oversized sections to
the recursive chunker."""

import re

from ingestion.chunkers.base import TextChunk, count_tokens
from ingestion.chunkers.recursive import RecursiveChunker

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


class MarkdownChunker:
    def __init__(self) -> None:
        self._fallback = RecursiveChunker()

    def chunk(self, text: str, *, chunk_size: int, overlap: int) -> list[TextChunk]:
        sections: list[tuple[list[str], int, str]] = []  # (heading_path, level, body)
        path: list[str] = []
        last_end = 0
        matches = list(_HEADING_RE.finditer(text))
        if not matches:
            return self._fallback.chunk(text, chunk_size=chunk_size, overlap=overlap)

        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.append(([], 0, preamble))
        for i, m in enumerate(matches):
            level = len(m.group(1))
            path = [*path[:level - 1], m.group(2).strip()]
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[m.end():end].strip()
            sections.append((list(path), level, f"{m.group(0)}\n{body}"))
            last_end = end
        _ = last_end

        chunks: list[TextChunk] = []
        for heading_path, level, body in sections:
            meta = _section_metadata(heading_path, level, body)
            if count_tokens(body) <= chunk_size:
                if body.strip():
                    chunks.append(
                        TextChunk(
                            content=body,
                            ordinal=len(chunks),
                            token_count=count_tokens(body),
                            metadata=meta,
                        )
                    )
            else:
                for sub in self._fallback.chunk(body, chunk_size=chunk_size, overlap=overlap):
                    child_meta = dict(meta)
                    child_meta["role"] = "child"
                    child_meta["parent_context"] = _parent_context(body)
                    chunks.append(
                        TextChunk(
                            content=sub.content,
                            ordinal=len(chunks),
                            token_count=sub.token_count,
                            metadata=child_meta,
                        )
                    )
        return chunks


def _section_metadata(heading_path: list[str], level: int, body: str) -> dict[str, object]:
    section_title = heading_path[-1] if heading_path else ""
    metadata: dict[str, object] = {
        "role": "section",
        "chunk_kind": "section",
        "heading_level": level,
        "section_title": section_title,
        "section_depth": len(heading_path),
        "parent_context": _parent_context(body),
    }
    if heading_path:
        metadata["headings"] = heading_path
        metadata["heading_path"] = " > ".join(heading_path)
    if _looks_like_table(body):
        metadata["contains_table"] = True
        metadata["chunk_kind"] = "table_or_section"
    if "```" in body:
        metadata["contains_code"] = True
        metadata["chunk_kind"] = "code_or_section"
    if _looks_like_procedure(body):
        metadata["contains_procedure"] = True
        metadata["chunk_kind"] = "procedure"
    return metadata


def _parent_context(body: str, *, max_chars: int = 900) -> str:
    cleaned = re.sub(r"\s+", " ", body).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rsplit(" ", 1)[0].strip()


def _looks_like_table(body: str) -> bool:
    lines = [line for line in body.splitlines() if "|" in line]
    return len(lines) >= 2


def _looks_like_procedure(body: str) -> bool:
    return bool(re.search(r"(^|\n)\s*(?:\d+\.|[-*])\s+", body)) or any(
        term in body.lower()
        for term in ("step", "runbook", "procedure", "checklist", "execute", "verify", "rollback")
    )
