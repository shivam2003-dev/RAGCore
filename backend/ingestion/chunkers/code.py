"""Code-aware chunking: prefer top-level definition boundaries (def/class/
function/exported symbols) so a chunk holds whole constructs, not torn halves."""

import itertools
import re

from ingestion.chunkers.base import TextChunk, count_tokens
from ingestion.chunkers.recursive import RecursiveChunker

_BOUNDARY_RE = re.compile(
    r"^(?:def |class |async def |function |const |export |public |private |fn |func )",
    re.MULTILINE,
)


class CodeChunker:
    def __init__(self) -> None:
        self._fallback = RecursiveChunker()

    def chunk(self, text: str, *, chunk_size: int, overlap: int) -> list[TextChunk]:
        starts = [m.start() for m in _BOUNDARY_RE.finditer(text)]
        if len(starts) < 2:
            return self._fallback.chunk(text, chunk_size=chunk_size, overlap=overlap)
        bounds = [0, *starts[1:], len(text)]
        blocks = [text[a:b] for a, b in itertools.pairwise(bounds) if text[a:b].strip()]

        chunks: list[TextChunk] = []
        current = ""
        for block in blocks:
            if current and count_tokens(current + block) > chunk_size:
                chunks.append(
                    TextChunk(
                        content=current.rstrip(),
                        ordinal=len(chunks),
                        token_count=count_tokens(current),
                        metadata={"kind": "code"},
                    )
                )
                current = block
            else:
                current += block
        if current.strip():
            chunks.append(
                TextChunk(
                    content=current.rstrip(),
                    ordinal=len(chunks),
                    token_count=count_tokens(current),
                    metadata={"kind": "code"},
                )
            )
        # oversized single blocks still need recursive splitting
        final: list[TextChunk] = []
        for chunk in chunks:
            if chunk.token_count > chunk_size * 2:
                for sub in self._fallback.chunk(
                    chunk.content, chunk_size=chunk_size, overlap=overlap
                ):
                    sub.metadata["kind"] = "code"
                    final.append(
                        TextChunk(
                            content=sub.content,
                            ordinal=len(final),
                            token_count=sub.token_count,
                            metadata=sub.metadata,
                        )
                    )
            else:
                chunk.ordinal = len(final)
                final.append(chunk)
        return final
