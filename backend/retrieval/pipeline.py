import time

from core.config import Settings
from embeddings.base import EmbeddingProvider
from repositories.chunks import ChunkSearchRepository
from retrieval.context import RetrievalAttempt, RetrievalContext
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
        embed_started = time.perf_counter()
        query_vec = (await self._embedder.embed([ctx.effective_query]))[0]
        ctx.time_stage("embedding", embed_started)

        candidates = max(self._settings.retrieval_candidate_k, ctx.top_k)
        kb_scope = ctx.kb_ids or ctx.kb_id
        dense = await self._search.dense_search(
            kb_scope, query_vec, candidates, ctx.collection_id
        )
        sparse = await self._search.sparse_search(
            kb_scope, ctx.effective_query, candidates, ctx.collection_id
        )
        fused = fuse(
            dense,
            sparse,
            dense_weight=self._settings.retrieval_dense_weight,
            sparse_weight=self._settings.retrieval_sparse_weight,
            top_k=min(candidates, 50),
        )
        reranked = await self._reranker.rerank(ctx, fused)
        ctx.chunks = reranked[: ctx.top_k]
