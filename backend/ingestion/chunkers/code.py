"""Symbol-aware code chunking with a bounded recursive fallback."""

import re
from dataclasses import dataclass

from ingestion.chunkers.base import TextChunk, count_tokens
from ingestion.chunkers.recursive import RecursiveChunker

_SYMBOL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("class", re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)")),
    ("class", re.compile(r"^\s*(?:public\s+)?(?:class|interface|enum|struct|trait)\s+([A-Za-z_]\w*)")),
    ("function", re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)")),
    ("function", re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)")),
    ("function", re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)")),
    ("function", re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)")),
    (
        "method",
        re.compile(
            r"^\s*(?:public|private|protected|static|final|synchronized|async|override|virtual|internal)"
            r"(?:\s+[A-Za-z_<>,.?\[\]]+)*\s+([A-Za-z_]\w*)\s*\("
        ),
    ),
    (
        "function",
        re.compile(
            r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*"
            r"(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
        ),
    ),
)

_LANGUAGE_BY_SUFFIX = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".h": "c",
    ".hpp": "cpp",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".php": "php",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".sh": "shell",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
}


@dataclass(slots=True, frozen=True)
class _Boundary:
    line_index: int
    kind: str
    name: str


class CodeChunker:
    def __init__(self, *, language: str = "text") -> None:
        self._fallback = RecursiveChunker()
        self._language = language

    def chunk(self, text: str, *, chunk_size: int, overlap: int) -> list[TextChunk]:
        lines = text.splitlines(keepends=True)
        boundaries = self._boundaries(lines)
        if not boundaries:
            return self._fallback_chunks(
                text,
                chunk_size=chunk_size,
                overlap=overlap,
                metadata={"kind": "code", "language": self._language},
            )

        sections: list[tuple[str, dict[str, object]]] = []
        if boundaries[0].line_index > 0:
            sections.append(
                (
                    "".join(lines[: boundaries[0].line_index]),
                    {
                        "kind": "code",
                        "language": self._language,
                        "symbol": None,
                        "symbol_kind": "module",
                        "line_start": 1,
                        "line_end": boundaries[0].line_index,
                    },
                )
            )
        for index, boundary in enumerate(boundaries):
            end = boundaries[index + 1].line_index if index + 1 < len(boundaries) else len(lines)
            sections.append(
                (
                    "".join(lines[boundary.line_index:end]),
                    {
                        "kind": "code",
                        "language": self._language,
                        "symbol": boundary.name,
                        "symbol_kind": boundary.kind,
                        "line_start": boundary.line_index + 1,
                        "line_end": end,
                    },
                )
            )

        chunks: list[TextChunk] = []
        for content, metadata in sections:
            if not content.strip():
                continue
            if count_tokens(content) > chunk_size * 2:
                chunks.extend(
                    self._fallback_chunks(
                        content,
                        chunk_size=chunk_size,
                        overlap=overlap,
                        metadata={**metadata, "oversized_symbol_fallback": True},
                        ordinal_start=len(chunks),
                    )
                )
            else:
                chunks.append(
                    TextChunk(
                        content=content.rstrip(),
                        ordinal=len(chunks),
                        token_count=count_tokens(content),
                        metadata=metadata,
                    )
                )
        return chunks

    @staticmethod
    def _boundaries(lines: list[str]) -> list[_Boundary]:
        boundaries: list[_Boundary] = []
        for line_index, line in enumerate(lines):
            for kind, pattern in _SYMBOL_PATTERNS:
                match = pattern.match(line)
                if match:
                    boundaries.append(_Boundary(line_index=line_index, kind=kind, name=match.group(1)))
                    break
        return boundaries

    def _fallback_chunks(
        self,
        text: str,
        *,
        chunk_size: int,
        overlap: int,
        metadata: dict[str, object],
        ordinal_start: int = 0,
    ) -> list[TextChunk]:
        result: list[TextChunk] = []
        for chunk in self._fallback.chunk(text, chunk_size=chunk_size, overlap=overlap):
            result.append(
                TextChunk(
                    content=chunk.content,
                    ordinal=ordinal_start + len(result),
                    token_count=chunk.token_count,
                    metadata={**chunk.metadata, **metadata},
                )
            )
        return result


def code_language_for_suffix(suffix: str) -> str:
    return _LANGUAGE_BY_SUFFIX.get(suffix.lower(), "text")
