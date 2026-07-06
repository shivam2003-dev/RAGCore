import uuid

from retrieval.context import RetrievalContext, RetrievedChunk
from retrieval.crag import HeuristicReranker


def _chunk(title: str, source: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title=title,
        content=f"{title}\nOperational knowledge source.",
        metadata={"source": source},
        score=score,
    )


async def test_architecture_queries_prefer_confluence_over_high_volume_jira() -> None:
    ranked = await HeuristicReranker().rerank(
        RetrievalContext(kb_id=uuid.uuid4(), query="HES Architecture", top_k=2),
        [
            _chunk("DEVO-10001 HES Architecture follow-up ticket", "jira", 0.82),
            _chunk("HES Architecture Overview", "confluence", 0.72),
        ],
    )

    assert ranked[0].metadata["source"] == "confluence"

