"""Sliding-window chunking with parent-child linkage: large parent windows for
context expansion, overlapping child windows as the retrieval unit."""

from ingestion.chunkers.base import TextChunk, _encoder


class SlidingWindowChunker:
    def __init__(self, parent_multiple: int = 4) -> None:
        self.parent_multiple = parent_multiple

    def chunk(self, text: str, *, chunk_size: int, overlap: int) -> list[TextChunk]:
        enc = _encoder()
        tokens = enc.encode(text, disallowed_special=())
        if not tokens:
            return []

        parent_size = chunk_size * self.parent_multiple
        chunks: list[TextChunk] = []
        parent_ordinals: list[int] = []

        for start in range(0, len(tokens), parent_size):
            window = tokens[start : start + parent_size]
            ordinal = len(chunks)
            parent_ordinals.append(ordinal)
            chunks.append(
                TextChunk(
                    content=enc.decode(window),
                    ordinal=ordinal,
                    token_count=len(window),
                    metadata={"role": "parent"},
                )
            )

        step = max(chunk_size - overlap, 1)
        for start in range(0, len(tokens), step):
            window = tokens[start : start + chunk_size]
            if not window:
                break
            parent_idx = min(start // parent_size, len(parent_ordinals) - 1)
            chunks.append(
                TextChunk(
                    content=enc.decode(window),
                    ordinal=len(chunks),
                    token_count=len(window),
                    metadata={"role": "child"},
                    parent_ordinal=parent_ordinals[parent_idx],
                )
            )
            if start + chunk_size >= len(tokens):
                break
        return chunks
