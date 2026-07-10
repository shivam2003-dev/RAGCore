"""Recursive character chunking: split on the strongest separator that keeps
pieces under the token budget, merging small neighbors back together."""

from ingestion.chunkers.base import TextChunk, count_tokens, split_token_windows

_SEPARATORS = ["\n\n", "\n", ". ", " "]


def _split(text: str, chunk_size: int, separators: list[str]) -> list[str]:
    if count_tokens(text) <= chunk_size:
        return [text]
    if not separators:
        return split_token_windows(text, chunk_size)
    sep, rest = separators[0], separators[1:]
    parts = [p for p in text.split(sep) if p.strip()]
    if len(parts) == 1:
        return _split(text, chunk_size, rest)
    out: list[str] = []
    for part in parts:
        piece = part + (sep if sep != " " else " ")
        if count_tokens(piece) > chunk_size:
            out.extend(_split(piece, chunk_size, rest))
        else:
            out.append(piece)
    return out


def _merge(pieces: list[str], chunk_size: int, overlap: int) -> list[str]:
    merged: list[str] = []
    current = ""
    for piece in pieces:
        if current and count_tokens(current + piece) > chunk_size:
            merged.append(current.strip())
            # carry tail of previous chunk forward as overlap
            tail_words = current.split()
            carry = " ".join(tail_words[-max(overlap // 4, 1):]) if overlap else ""
            candidate = (carry + " " if carry else "") + piece
            current = piece if count_tokens(candidate) > chunk_size else candidate
        else:
            current += piece
    if current.strip():
        merged.append(current.strip())
    return merged


class RecursiveChunker:
    def chunk(self, text: str, *, chunk_size: int, overlap: int) -> list[TextChunk]:
        pieces = _split(text, chunk_size, _SEPARATORS)
        merged = _merge(pieces, chunk_size, overlap)
        return [
            TextChunk(content=c, ordinal=i, token_count=count_tokens(c))
            for i, c in enumerate(merged)
        ]
