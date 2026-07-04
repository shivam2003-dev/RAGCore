from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol


@dataclass(slots=True)
class TextChunk:
    content: str
    ordinal: int
    token_count: int
    metadata: dict = field(default_factory=dict)
    parent_ordinal: int | None = None  # parent-child linkage (sliding-window children)


class Chunker(Protocol):
    def chunk(self, text: str, *, chunk_size: int, overlap: int) -> list[TextChunk]: ...


@lru_cache
def _encoder():  # type: ignore[no-untyped-def]
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text, disallowed_special=()))
