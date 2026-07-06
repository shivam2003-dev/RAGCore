"""Corrective RAG policies used by the retrieval pipeline.

The implementation is deliberately provider-free: it uses retrieval scores,
lexical agreement, source-family hints, and freshness metadata so search can
self-correct without adding another LLM call to every Ask request.
"""

import enum
import math
import re
from datetime import UTC, datetime
from typing import Protocol

from retrieval.context import RetrievalContext, RetrievedChunk

MIN_ACCEPT_CONFIDENCE = 0.22
MIN_STRONG_CONFIDENCE = 0.34
TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_+-]{2,}")
STOPWORDS = {
    "and",
    "are",
    "can",
    "for",
    "from",
    "how",
    "into",
    "only",
    "please",
    "should",
    "that",
    "the",
    "then",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
}
JIRA_HINTS = {"jira", "devo", "cvir", "issue", "issues", "ticket", "tickets", "assignee", "sprint"}
CONFLUENCE_HINTS = {
    "confluence",
    "wiki",
    "space",
    "page",
    "docs",
    "documentation",
    "runbook",
    "procedure",
    "process",
    "checklist",
    "architecture",
    "architectural",
    "design",
    "diagram",
    "diagrams",
    "overview",
    "topology",
    "flow",
    "flows",
    "hld",
    "lld",
    "sop",
    "guide",
    "deployment",
    "release",
    "configuration",
    "implementation",
}


class PolicyDecision(enum.StrEnum):
    ACCEPT = "accept"
    REWRITE = "rewrite"
    WIDEN_K = "widen_k"
    FALLBACK = "fallback"


class QueryRewriter(Protocol):
    async def rewrite(self, ctx: RetrievalContext) -> str | None:
        """Return a rewritten query, or None to keep the original."""
        ...


class RetrievalEvaluator(Protocol):
    async def evaluate(self, ctx: RetrievalContext) -> float:
        """Score retrieved-set quality in [0, 1]."""
        ...


class ChunkReranker(Protocol):
    async def rerank(self, ctx: RetrievalContext, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Return chunks ordered for answer generation."""
        ...


class RetrievalPolicy(Protocol):
    def decide(self, ctx: RetrievalContext) -> PolicyDecision: ...


class GroundingVerifier(Protocol):
    async def verify(self, answer: str, ctx: RetrievalContext) -> bool:
        """Post-generation: is the answer supported by retrieved sources?"""
        ...


class NoopRewriter:
    async def rewrite(self, ctx: RetrievalContext) -> str | None:
        return None


class CorrectiveQueryRewriter:
    """Low-risk corrective rewrite for weak retrieval attempts."""

    async def rewrite(self, ctx: RetrievalContext) -> str | None:
        if not ctx.attempts:
            return None

        query = ctx.effective_query
        tokens = _tokens(query)
        if not tokens:
            return None

        additions: list[str] = []
        normalized = query.lower()
        if tokens & JIRA_HINTS:
            additions.append("jira issue status assignee project board")
        if tokens & CONFLUENCE_HINTS:
            additions.append("confluence runbook procedure documentation")
        if "sre" in tokens:
            additions.append("sre incident service alert")
        if "devops" in tokens or "deployment" in tokens:
            additions.append("devops deployment release checklist")

        title_tokens = _top_title_tokens(ctx.chunks)
        if title_tokens:
            additions.append(" ".join(title_tokens[:6]))

        compact = " ".join(token for token in TOKEN_RE.findall(query) if token.lower() not in STOPWORDS)
        rewritten = " ".join(part for part in [compact, *additions] if part).strip()
        if not rewritten or rewritten.lower() == normalized:
            return None
        ctx.quality_notes.append(f"corrective_query={rewritten[:140]}")
        return rewritten


class HeuristicEvaluator:
    """Provider-free retrieval quality evaluator.

    The score blends fused retrieval confidence, query/context lexical overlap,
    source-family fit, and result diversity. A very low score means the answer
    should either retry with a corrective query or refuse from internal sources.
    """

    async def evaluate(self, ctx: RetrievalContext) -> float:
        if not ctx.chunks:
            ctx.quality_notes.append("no_chunks")
            return 0.0

        query_tokens = _tokens(ctx.effective_query)
        top = ctx.chunks[: min(6, len(ctx.chunks))]
        top_score = _clamp01(max(chunk.score for chunk in top))
        mean_score = _clamp01(sum(_clamp01(chunk.score) for chunk in top) / len(top))
        lexical = _mean([_overlap(query_tokens, _chunk_tokens(chunk)) for chunk in top])
        source_fit = _mean([_source_fit(query_tokens, chunk) for chunk in top])
        diversity = len({chunk.document_id for chunk in top}) / len(top)

        score = (
            (0.36 * top_score)
            + (0.20 * mean_score)
            + (0.26 * lexical)
            + (0.12 * source_fit)
            + (0.06 * diversity)
        )
        confidence = round(_clamp01(score), 4)
        ctx.quality_notes.append(
            f"retrieval_quality={confidence} lexical={round(lexical, 3)} source_fit={round(source_fit, 3)}"
        )
        return confidence


class HeuristicReranker:
    """Rerank fused hits using query fit, source fit, and freshness metadata."""

    async def rerank(self, ctx: RetrievalContext, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not chunks:
            return []

        query_tokens = _tokens(ctx.effective_query)
        rescored: list[RetrievedChunk] = []
        for rank, chunk in enumerate(chunks):
            lexical = _overlap(query_tokens, _chunk_tokens(chunk))
            source_fit = _source_fit(query_tokens, chunk)
            freshness = _freshness(chunk.metadata)
            position = 1 / math.sqrt(rank + 1)
            chunk.score = round(
                _clamp01(
                    (0.58 * _clamp01(chunk.score))
                    + (0.24 * lexical)
                    + (0.10 * source_fit)
                    + (0.04 * freshness)
                    + (0.04 * position)
                ),
                6,
            )
            rescored.append(chunk)
        return sorted(rescored, key=lambda item: item.score, reverse=True)


class ThresholdRetrievalPolicy:
    def decide(self, ctx: RetrievalContext) -> PolicyDecision:
        attempts = len(ctx.attempts)
        confidence = ctx.confidence or 0.0
        if confidence >= MIN_ACCEPT_CONFIDENCE:
            return PolicyDecision.ACCEPT
        if not ctx.chunks and attempts == 1:
            return PolicyDecision.WIDEN_K
        if attempts == 1:
            return PolicyDecision.REWRITE
        if attempts == 2 and confidence < MIN_STRONG_CONFIDENCE:
            return PolicyDecision.WIDEN_K
        ctx.fallback_requested = True
        ctx.quality_notes.append("fallback_requested")
        return PolicyDecision.ACCEPT


class AlwaysAcceptPolicy:
    def decide(self, ctx: RetrievalContext) -> PolicyDecision:
        return PolicyDecision.ACCEPT


class NoopGroundingVerifier:
    async def verify(self, answer: str, ctx: RetrievalContext) -> bool:
        return True


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text) if token.lower() not in STOPWORDS}


def _top_title_tokens(chunks: list[RetrievedChunk]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for chunk in chunks[:5]:
        for token in TOKEN_RE.findall(chunk.document_title):
            normalized = token.lower()
            if normalized in STOPWORDS or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
    return result


def _chunk_tokens(chunk: RetrievedChunk) -> set[str]:
    metadata = chunk.metadata or {}
    values = [
        chunk.document_title,
        chunk.content[:1800],
        str(metadata.get("source") or ""),
        str(metadata.get("jira_issue_key") or ""),
        str(metadata.get("jira_issue_status") or ""),
        str(metadata.get("confluence_space_key") or ""),
    ]
    return _tokens(" ".join(values))


def _source_fit(query_tokens: set[str], chunk: RetrievedChunk) -> float:
    if not query_tokens:
        return 0.0
    metadata = chunk.metadata or {}
    source = str(metadata.get("source") or metadata.get("source_type") or "").lower()
    title = chunk.document_title.lower()
    score = 0.0
    if query_tokens & JIRA_HINTS and ("jira" in source or "jira" in title or "devo" in title or "cvir" in title):
        score += 0.6
    if query_tokens & CONFLUENCE_HINTS and _is_confluence_source(source, title, metadata):
        score += 0.6
    architecture_terms = {
        "architecture",
        "architectural",
        "design",
        "diagram",
        "diagrams",
        "overview",
        "topology",
        "hld",
        "lld",
    }
    if query_tokens & architecture_terms:
        if _is_confluence_source(source, title, metadata):
            score += 0.25
        if any(term in title for term in ("architecture", "design", "diagram", "overview", "hld", "lld")):
            score += 0.15
    if "sre" in query_tokens and (
        "sre" in title or "cvir" in title or metadata.get("confluence_space_key") in {"SRE", "AS"}
    ):
        score += 0.3
    if ("devops" in query_tokens or "devo" in query_tokens) and ("devo" in title or "devops" in title):
        score += 0.3
    return _clamp01(score)


def _is_confluence_source(source: str, title: str, metadata: dict) -> bool:
    return bool(
        "confluence" in source
        or "confluence" in title
        or metadata.get("confluence_space_key")
        or metadata.get("confluence-page-id")
        or metadata.get("confluence_page_id")
    )


def _freshness(metadata: dict) -> float:
    raw = (
        metadata.get("source_updated_at")
        or metadata.get("jira_issue_updated_at")
        or metadata.get("jira_updated_at")
        or metadata.get("confluence_version_created_at")
        or metadata.get("updated_at")
    )
    if not raw:
        return 0.4
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return 0.4
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    age_days = max(0, (datetime.now(UTC) - parsed).days)
    if age_days <= 30:
        return 1.0
    if age_days >= 365:
        return 0.2
    return _clamp01(1 - ((age_days - 30) / 335))


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return _clamp01(len(left & right) / len(left))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
