"""Citation extraction: map [n] markers in the generated answer back to the
retrieved chunks that were numbered 1..K in the prompt."""

import re
from dataclasses import dataclass

from retrieval.context import RetrievedChunk

_MARKER_RE = re.compile(r"\[(\d{1,2})\]")

SNIPPET_LEN = 240


@dataclass(slots=True)
class ExtractedCitation:
    marker: int
    chunk: RetrievedChunk
    snippet: str


def extract_citations(answer: str, chunks: list[RetrievedChunk]) -> list[ExtractedCitation]:
    seen: set[int] = set()
    citations: list[ExtractedCitation] = []
    for match in _MARKER_RE.finditer(answer):
        marker = int(match.group(1))
        if marker in seen or not (1 <= marker <= len(chunks)):
            continue
        seen.add(marker)
        chunk = chunks[marker - 1]
        citations.append(
            ExtractedCitation(
                marker=marker,
                chunk=chunk,
                snippet=chunk.content[:SNIPPET_LEN],
            )
        )
    return citations
