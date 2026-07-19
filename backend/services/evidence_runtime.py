"""Production wiring for independently sessioned evidence tool calls."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from core.config import Settings
from database.session import SessionFactory
from embeddings.base import EmbeddingProvider
from llm.base import LLMProvider
from repositories.chunks import ChunkSearchRepository
from retrieval.pipeline import RetrievalPipeline
from services.evidence_tools import EvidenceToolService


@asynccontextmanager
async def independent_evidence_tool_context(
    *,
    settings: Settings,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
) -> AsyncIterator[EvidenceToolService]:
    """Open a distinct database session for one concurrent evidence tool."""

    async with SessionFactory() as session:
        reranker = None
        if settings.retrieval_model_reranker_enabled:
            from retrieval.rerankers import ModelReranker

            reranker = ModelReranker(
                llm=llm,
                timeout_seconds=settings.retrieval_model_reranker_timeout_seconds,
                candidate_limit=settings.retrieval_model_reranker_candidate_k,
            )
        retrieval = RetrievalPipeline(
            search_repo=ChunkSearchRepository(session),
            embedder=embedder,
            settings=settings,
            reranker=reranker,
        )
        yield EvidenceToolService(db=session, retrieval=retrieval, settings=settings)
