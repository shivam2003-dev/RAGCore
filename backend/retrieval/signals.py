import math
import re
from collections.abc import Iterable

EXACT_IDENTIFIER_RE = re.compile(
    r"(?:\b[A-Z][A-Z0-9]{1,9}-\d+\b|"
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b|"
    r"\b[a-zA-Z0-9][a-zA-Z0-9.-]{2,}\.[a-zA-Z]{2,}\b|"
    r"(?<!\w)--?[a-zA-Z][a-zA-Z0-9_-]{2,}\b|"
    r"\b[A-Z][A-Z0-9_]{2,}\d[A-Z0-9_]*\b)"
)
RARE_TOKEN_RE = re.compile(r"--?[A-Za-z][A-Za-z0-9_-]{2,}|[A-Za-z0-9][A-Za-z0-9_.:/-]{3,}")
COMMON_TOKENS = {
    "about",
    "after",
    "before",
    "could",
    "error",
    "from",
    "have",
    "please",
    "show",
    "that",
    "their",
    "there",
    "these",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
}


def exact_identifiers(query: str, *, limit: int = 8) -> list[str]:
    return _dedupe(match.group(0) for match in EXACT_IDENTIFIER_RE.finditer(query))[:limit]


def rare_tokens(query: str, *, limit: int = 8) -> list[str]:
    candidates: list[str] = []
    exact = {item.lower() for item in exact_identifiers(query, limit=limit)}
    for match in RARE_TOKEN_RE.finditer(query):
        token = match.group(0)
        normalized = token.lower().strip(".,:;!?()[]{}")
        if normalized in COMMON_TOKENS or len(normalized) < 4:
            continue
        has_rare_shape = bool(
            normalized in exact
            or token.startswith("-")
            or any(character.isdigit() for character in token)
            or any(character in "_./:" for character in token)
            or (token.isupper() and len(token) >= 4)
        )
        if has_rare_shape:
            candidates.append(normalized)
    return _dedupe(candidates)[:limit]


def inverse_document_frequency(total_documents: int, document_frequency: int) -> float:
    total = max(total_documents, 0)
    frequency = max(min(document_frequency, total), 0)
    return math.log((1 + total) / (1 + frequency)) + 1.0


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result
