import asyncio
import uuid
from collections.abc import AsyncIterator

from llm.base import LLMDelta, LLMRequest
from retrieval.context import RetrievalContext, RetrievedChunk
from retrieval.rerankers import ModelReranker


class RankingLLM:
    name = "test"
    model = "ranking-test"

    async def stream(self, _request: LLMRequest) -> AsyncIterator[LLMDelta]:
        yield LLMDelta(text='{"ranking":["C2","C1"]}')
        yield LLMDelta(done=True)


class SlowLLM:
    name = "test"
    model = "slow-test"

    async def stream(self, _request: LLMRequest) -> AsyncIterator[LLMDelta]:
        await asyncio.sleep(0.05)
        yield LLMDelta(text='{"ranking":["C1"]}')


def _chunk(title: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title=title,
        content=f"{title} operational architecture details",
        metadata={"source": "confluence"},
        score=score,
    )


async def test_model_reranker_uses_bounded_model_order():
    first = _chunk("First architecture", 0.9)
    second = _chunk("Second architecture", 0.8)
    ctx = RetrievalContext(
        kb_id=uuid.uuid4(),
        query="Compare the service architecture design options",
        top_k=2,
    )

    ranked = await ModelReranker(
        llm=RankingLLM(),
        timeout_seconds=1,
        candidate_limit=2,
    ).rerank(ctx, [first, second])

    assert ranked[0].document_title == "Second architecture"
    assert ctx.trace["reranker"] == "model:ranking-test"


async def test_model_reranker_timeout_falls_back_to_heuristics():
    chunks = [_chunk("Architecture overview", 0.8), _chunk("Deployment notes", 0.7)]
    ctx = RetrievalContext(
        kb_id=uuid.uuid4(),
        query="Explain the service architecture and deployment flow",
        top_k=2,
    )

    ranked = await ModelReranker(
        llm=SlowLLM(),
        timeout_seconds=0.001,
        candidate_limit=2,
    ).rerank(ctx, chunks)

    assert len(ranked) == 2
    assert ctx.trace["reranker"] == "heuristic_fallback"
    assert any(note.startswith("model_reranker_fallback=") for note in ctx.quality_notes)
