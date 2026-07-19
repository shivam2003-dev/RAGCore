import copy
import re
import time
import uuid
from collections.abc import Sequence

from core.config import Settings
from embeddings.base import EmbeddingProvider
from repositories.chunks import ChunkSearchRepository, SearchHit
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
from retrieval.expansion import expand_ranked_neighbors
from retrieval.fusion import fuse, fuse_weighted, reciprocal_rank_fusion
from retrieval.recency import apply_source_recency_decay, parse_half_lives
from retrieval.signals import exact_identifiers, rare_tokens

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
    "and",
    "confluence",
    "documentation",
    "docs",
    "document",
    "documents",
    "does",
    "epic",
    "explain",
    "find",
    "from",
    "give",
    "me",
    "no",
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
        best_chunks: list[RetrievedChunk] = []
        best_confidence = -1.0
        best_query: str | None = None
        best_trace: dict[str, object] = {}

        for _ in range(MAX_ATTEMPTS):
            await self._retrieve_once(ctx)
            ctx.confidence = await self._evaluator.evaluate(ctx)
            confidence = ctx.confidence or 0.0
            if confidence > best_confidence or (confidence == best_confidence and len(ctx.chunks) > len(best_chunks)):
                best_chunks = list(ctx.chunks)
                best_confidence = confidence
                best_query = ctx.effective_query
                best_trace = copy.deepcopy(ctx.trace)
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
                break

        if best_chunks:
            ctx.chunks = best_chunks
            ctx.confidence = best_confidence
            ctx.rewritten_query = best_query if best_query and best_query != ctx.query else None
            ctx.trace = best_trace
            ctx.trace["policy_attempt_count"] = len(ctx.attempts)
            if len(ctx.attempts) > 1:
                ctx.quality_notes.append(f"selected_best_attempt={best_query[:140] if best_query else ctx.query[:140]}")

        ctx.time_stage("retrieval", started)
        return ctx

    async def jira_relationship_context(
        self,
        *,
        kb_scope: uuid.UUID | Sequence[uuid.UUID],
        issue_key: str,
        query: str,
        limit: int,
    ) -> list[RetrievedChunk]:
        hits = await self._search.jira_relationship_search(
            kb_scope,
            issue_key=issue_key,
            query=query,
            limit=limit,
        )
        return fuse(
            [],
            hits,
            dense_weight=0.0,
            sparse_weight=1.0,
            top_k=limit,
        )

    async def _retrieve_once(self, ctx: RetrievalContext) -> None:
        retrieval_query = retrieval_search_query(ctx.effective_query)
        if retrieval_query != ctx.effective_query:
            ctx.quality_notes.append(f"retrieval_query={retrieval_query[:140]}")
        embed_started = time.perf_counter()
        query_vec = (await self._embedder.embed([retrieval_query]))[0]
        ctx.time_stage("embedding", embed_started)

        candidates = max(self._settings.retrieval_candidate_k, ctx.top_k)
        kb_scope = ctx.kb_ids or ctx.kb_id
        arms: dict[str, list[SearchHit]] = {}
        arm_trace: list[dict[str, object]] = []

        dense_started = time.perf_counter()
        dense = await self._search.dense_search(kb_scope, query_vec, candidates, ctx.collection_id)
        arms["dense"] = dense
        arm_trace.append(
            {
                "arm": "dense",
                "result_count": len(dense),
                "latency_ms": int((time.perf_counter() - dense_started) * 1000),
            }
        )

        sparse_started = time.perf_counter()
        sparse = await self._search.sparse_search(kb_scope, retrieval_query, candidates, ctx.collection_id)
        arms["sparse"] = sparse
        arm_trace.append(
            {
                "arm": "sparse",
                "result_count": len(sparse),
                "latency_ms": int((time.perf_counter() - sparse_started) * 1000),
            }
        )

        identifiers = exact_identifiers(retrieval_query)
        if self._settings.retrieval_exact_identifier_enabled and identifiers:
            exact_started = time.perf_counter()
            exact = await self._search.exact_identifier_search(
                kb_scope,
                identifiers,
                candidates,
                ctx.collection_id,
            )
            arms["exact_identifier"] = exact
            arm_trace.append(
                {
                    "arm": "exact_identifier",
                    "result_count": len(exact),
                    "latency_ms": int((time.perf_counter() - exact_started) * 1000),
                    "identifier_count": len(identifiers),
                }
            )

        measured_tokens = rare_tokens(retrieval_query)
        rare_trace: dict[str, object] = {}
        if self._settings.retrieval_rare_token_enabled and measured_tokens:
            rare_started = time.perf_counter()
            rare = await self._search.rare_token_search(
                kb_scope,
                measured_tokens,
                candidates,
                ctx.collection_id,
            )
            arms["rare_token"] = rare.hits
            rare_trace = {
                "document_frequencies": rare.document_frequencies,
                "total_documents": rare.total_documents,
            }
            arm_trace.append(
                {
                    "arm": "rare_token",
                    "result_count": len(rare.hits),
                    "latency_ms": int((time.perf_counter() - rare_started) * 1000),
                    "token_count": len(measured_tokens),
                }
            )

        dense_weight = self._settings.retrieval_dense_weight
        sparse_weight = self._settings.retrieval_sparse_weight
        if self._embedder.name == "fake":
            dense_weight, sparse_weight = 0.45, 0.55
            if "lexical_fusion_for_local_embeddings" not in ctx.quality_notes:
                ctx.quality_notes.append("lexical_fusion_for_local_embeddings")
        weights = {
            "dense": dense_weight,
            "sparse": sparse_weight,
            "exact_identifier": self._settings.retrieval_exact_identifier_weight,
            "rare_token": self._settings.retrieval_rare_token_weight,
        }
        active_weight_total = sum(max(weights.get(name, 0.0), 0.0) for name in arms) or 1.0
        active_weights = {name: max(weights.get(name, 0.0), 0.0) / active_weight_total for name in arms}
        fusion_started = time.perf_counter()
        fusion_mode = self._settings.retrieval_fusion_mode.lower().strip()
        if fusion_mode == "rrf":
            fused = reciprocal_rank_fusion(
                arms,
                weights=active_weights,
                smoothing_k=self._settings.retrieval_rrf_smoothing_k,
                top_k=min(candidates, 50),
            )
        else:
            if fusion_mode != "weighted":
                ctx.quality_notes.append(f"unknown_fusion_mode={fusion_mode};using=weighted")
            fusion_mode = "weighted"
            fused = fuse_weighted(
                arms,
                weights=active_weights,
                top_k=min(candidates, 50),
            )
        fusion_ms = int((time.perf_counter() - fusion_started) * 1000)
        if self._settings.retrieval_recency_decay_enabled:
            fused = apply_source_recency_decay(
                fused,
                half_lives=parse_half_lives(self._settings.retrieval_recency_half_lives),
                floor=self._settings.retrieval_recency_floor,
            )
        reranked = await self._reranker.rerank(ctx, fused)
        reranker_name = str(ctx.trace.get("reranker") or "heuristic")
        selected = select_final_context(ctx, reranked, top_k=ctx.top_k)
        for rank, chunk in enumerate(selected, start=1):
            chunk.selected_rank = rank

        expanded = selected
        neighbor_ms = 0
        if self._settings.retrieval_neighbor_expansion_enabled and selected:
            neighbor_started = time.perf_counter()
            neighbors = await self._search.neighboring_chunks(
                kb_scope,
                anchor_chunk_ids=[chunk.chunk_id for chunk in selected],
                window=self._settings.retrieval_neighbor_window,
            )
            expanded = expand_ranked_neighbors(
                selected,
                neighbors,
                token_budget=self._settings.retrieval_neighbor_token_budget,
                max_neighbors=self._settings.retrieval_neighbor_max_chunks,
            )
            neighbor_ms = int((time.perf_counter() - neighbor_started) * 1000)
        ctx.chunks = expanded
        ctx.trace = {
            "fusion_mode": fusion_mode,
            "reranker": reranker_name,
            "fusion_latency_ms": fusion_ms,
            "arms": arm_trace,
            "candidate_count": len(fused),
            "selected_count": len(selected),
            "expanded_count": len(expanded) - len(selected),
            "discarded_candidate_count": max(0, len(fused) - len(selected)),
            "neighbor_expansion_latency_ms": neighbor_ms,
            "rare_token_signal": rare_trace,
            "selected": [
                {
                    "chunk_id": str(chunk.chunk_id),
                    "retrieval_arms": list(chunk.retrieval_arms),
                    "arm_ranks": dict(chunk.arm_ranks),
                    "selected_rank": chunk.selected_rank,
                    "expanded_from_chunk_id": (
                        str(chunk.expanded_from_chunk_id) if chunk.expanded_from_chunk_id else None
                    ),
                }
                for chunk in expanded
            ],
        }


def select_final_context(ctx: RetrievalContext, chunks: list[RetrievedChunk], *, top_k: int) -> list[RetrievedChunk]:
    """Choose final contexts after reranking with source and document diversity.

    Enterprise corpora are imbalanced: Jira often has far more chunks than Confluence.
    This keeps high-volume sources from crowding out distinct docs that match the query intent.
    """

    if not chunks or top_k <= 0:
        return []

    query_tokens = {token.strip(".,:;!?()[]{}").lower() for token in ctx.effective_query.split()}
    doc_intent = bool(query_tokens & DOC_INTENT_TERMS)
    architecture_intent = bool(
        query_tokens
        & {"architecture", "architectural", "components", "design", "diagram", "hld", "lld", "overview", "topology"}
    )
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
        if per_document.get(chunk.document_id, 0) >= (1 if architecture_intent else 2):
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
        meaningful_terms = [
            token
            for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", query)
            if token.lower() not in QUERY_NOISE_TERMS and token.upper() not in identifiers
        ]
        return " ".join([*identifiers, *meaningful_terms[:8]])

    raw_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", query)
    normalized = [token.lower() for token in raw_tokens]
    doc_intent = bool(set(normalized) & DOC_INTENT_TERMS) or "confluence" in normalized
    if not doc_intent:
        return query

    kept = [token for token in raw_tokens if token.lower() not in QUERY_NOISE_TERMS and len(token) > 2]
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
