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
        sections: list[tuple[list[str], str]] = []  # (heading_path, body)
        path: list[str] = []
        last_end = 0
        matches = list(_HEADING_RE.finditer(text))
        if not matches:
            return self._fallback.chunk(text, chunk_size=chunk_size, overlap=overlap)

        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.append(([], preamble))
        for i, m in enumerate(matches):
            level = len(m.group(1))
            path = [*path[:level - 1], m.group(2).strip()]
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[m.end():end].strip()
            sections.append((list(path), f"{m.group(0)}\n{body}"))
            last_end = end
        _ = last_end

        chunks: list[TextChunk] = []
        for heading_path, body in sections:
            meta = {"headings": heading_path} if heading_path else {}
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
                    chunks.append(
                        TextChunk(
                            content=sub.content,
                            ordinal=len(chunks),
                            token_count=sub.token_count,
                            metadata=meta,
                        )
                    )
        return chunks
