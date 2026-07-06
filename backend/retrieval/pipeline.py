import re
import time

from core.config import Settings
from embeddings.base import EmbeddingProvider
from repositories.chunks import ChunkSearchRepository
from retrieval.context import RetrievalAttempt, RetrievalContext, RetrievedChunk
from retrieval.crag import (
    ChunkReranker,
    CorrectiveQueryRewriter,
    HeuristicEvaluator,
    HeuristicReranker,
    PolicyDecision,
    QueryRewriter,
    RetrievalEvaluator,
    RetrievalPolicy,
    ThresholdRetrievalPolicy,
)
from retrieval.fusion import fuse

MAX_ATTEMPTS = 3  # hard stop for future retrying policies
DOC_INTENT_TERMS = {
    "architecture",
    "architectural",
    "design",
    "diagram",
    "diagrams",
    "overview",
    "topology",
    "hld",
    "lld",
    "documentation",
    "docs",
    "runbook",
    "sop",
    "guide",
    "procedure",
    "process",
}
QUERY_NOISE_TERMS = {
    "about",
    "confluence",
    "documentation",
    "docs",
    "document",
    "documents",
    "does",
    "explain",
    "give",
    "say",
    "says",
    "tell",
    "the",
    "what",
    "which",
}


class RetrievalPipeline:
    """rewrite → embed → hybrid search → fuse → rerank → evaluate → policy loop."""

    def __init__(
        self,
        *,
        search_repo: ChunkSearchRepository,
        embedder: EmbeddingProvider,
        settings: Settings,
        rewriter: QueryRewriter | None = None,
        evaluator: RetrievalEvaluator | None = None,
        reranker: ChunkReranker | None = None,
        policy: RetrievalPolicy | None = None,
    ) -> None:
        self._search = search_repo
        self._embedder = embedder
        self._settings = settings
        self._rewriter = rewriter or CorrectiveQueryRewriter()
        self._evaluator = evaluator or HeuristicEvaluator()
        self._reranker = reranker or HeuristicReranker()
        self._policy = policy or ThresholdRetrievalPolicy()

    async def run(self, ctx: RetrievalContext) -> RetrievalContext:
        started = time.perf_counter()
        ctx.rewritten_query = await self._rewriter.rewrite(ctx)

        for _ in range(MAX_ATTEMPTS):
            await self._retrieve_once(ctx)
            ctx.confidence = await self._evaluator.evaluate(ctx)
            ctx.attempts.append(
                RetrievalAttempt(
                    query=ctx.effective_query,
                    top_k=ctx.top_k,
                    result_count=len(ctx.chunks),
                    confidence=ctx.confidence,
                )
            )
            decision = self._policy.decide(ctx)
            if decision == PolicyDecision.ACCEPT:
                break
            if decision == PolicyDecision.WIDEN_K:
                ctx.top_k = min(ctx.top_k * 2, 50)
            elif decision == PolicyDecision.REWRITE:
                ctx.rewritten_query = await self._rewriter.rewrite(ctx) or ctx.rewritten_query
            elif decision == PolicyDecision.FALLBACK:
                ctx.fallback_requested = True
                break  # future: web/external fallback search

        ctx.time_stage("retrieval", started)
        return ctx

    async def _retrieve_once(self, ctx: RetrievalContext) -> None:
        retrieval_query = retrieval_search_query(ctx.effective_query)
        if retrieval_query != ctx.effective_query:
            ctx.quality_notes.append(f"retrieval_query={retrieval_query[:140]}")
        embed_started = time.perf_counter()
        query_vec = (await self._embedder.embed([retrieval_query]))[0]
        ctx.time_stage("embedding", embed_started)

        candidates = max(self._settings.retrieval_candidate_k, ctx.top_k)
        kb_scope = ctx.kb_ids or ctx.kb_id
        dense = await self._search.dense_search(
            kb_scope, query_vec, candidates, ctx.collection_id
        )
        sparse = await self._search.sparse_search(
            kb_scope, retrieval_query, candidates, ctx.collection_id
        )
        fused = fuse(
            dense,
            sparse,
            dense_weight=self._settings.retrieval_dense_weight,
            sparse_weight=self._settings.retrieval_sparse_weight,
            top_k=min(candidates, 50),
        )
        reranked = await self._reranker.rerank(ctx, fused)
        ctx.chunks = select_final_context(ctx, reranked, top_k=ctx.top_k)


def select_final_context(ctx: RetrievalContext, chunks: list[RetrievedChunk], *, top_k: int) -> list[RetrievedChunk]:
    """Choose final contexts after reranking with source and document diversity.

    Enterprise corpora are imbalanced: Jira often has far more chunks than Confluence.
    This keeps high-volume sources from crowding out distinct docs that match the query intent.
    """

    if not chunks or top_k <= 0:
        return []

    query_tokens = {token.strip(".,:;!?()[]{}").lower() for token in ctx.effective_query.split()}
    doc_intent = bool(query_tokens & DOC_INTENT_TERMS)
    confluence_chunks = [chunk for chunk in chunks if _source_family(chunk) == "confluence"]
    selected: list[RetrievedChunk] = []
    seen_chunks: set[object] = set()
    per_document: dict[object, int] = {}
    per_source_key: dict[str, int] = {}
    per_family: dict[str, int] = {}

    def add(chunk: RetrievedChunk, *, family_cap: int | None = None) -> bool:
        family = _source_family(chunk)
        source_key = _source_key(chunk)
        if chunk.chunk_id in seen_chunks:
            return False
        if per_document.get(chunk.document_id, 0) >= 2:
            return False
        if per_source_key.get(source_key, 0) >= 2:
            return False
        if family_cap is not None and per_family.get(family, 0) >= family_cap:
            return False
        seen_chunks.add(chunk.chunk_id)
        per_document[chunk.document_id] = per_document.get(chunk.document_id, 0) + 1
        per_source_key[source_key] = per_source_key.get(source_key, 0) + 1
        per_family[family] = per_family.get(family, 0) + 1
        selected.append(chunk)
        return True

    if doc_intent and confluence_chunks:
        minimum_confluence = min(max(2, top_k // 2), len(confluence_chunks), top_k)
        for chunk in confluence_chunks:
            add(chunk)
            if per_family.get("confluence", 0) >= minimum_confluence:
                break

    jira_cap = max(2, top_k // 3) if doc_intent and confluence_chunks else None
    for chunk in chunks:
        family_cap = jira_cap if _source_family(chunk) == "jira" else None
        add(chunk, family_cap=family_cap)
        if len(selected) >= top_k:
            break

    if len(selected) < top_k:
        for chunk in chunks:
            add(chunk)
            if len(selected) >= top_k:
                break
    return selected[:top_k]


def retrieval_search_query(query: str) -> str:
    identifiers = re.findall(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b", query.upper())
    if identifiers:
        return " ".join(identifiers)

    raw_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", query)
    normalized = [token.lower() for token in raw_tokens]
    doc_intent = bool(set(normalized) & DOC_INTENT_TERMS) or "confluence" in normalized
    if not doc_intent:
        return query

    kept = [
        token
        for token in raw_tokens
        if token.lower() not in QUERY_NOISE_TERMS and len(token) > 2
    ]
    if len(kept) >= 2:
        return " ".join(kept)
    return query


def _source_family(chunk: RetrievedChunk) -> str:
    metadata = chunk.metadata or {}
    value = str(
        metadata.get("source")
        or metadata.get("source_type")
        or metadata.get("source_family")
        or metadata.get("connector")
        or ""
    ).lower()
    title = chunk.document_title.lower()
    if "confluence" in value or metadata.get("confluence_page_id") or "confluence" in title:
        return "confluence"
    if "jira" in value or metadata.get("jira_issue_key") or "devo-" in title or "cvir-" in title:
        return "jira"
    if "web" in value:
        return "web"
    if "upload" in value:
        return "upload"
    return value or "knowledge"


def _source_key(chunk: RetrievedChunk) -> str:
    metadata = chunk.metadata or {}
    for key in ("source_inventory_key", "chunk_source_key", "source_id", "jira_issue_key", "confluence_page_id"):
        value = metadata.get(key)
        if isinstance(value, (str, int)) and str(value):
            return str(value)
    return str(chunk.document_id)
