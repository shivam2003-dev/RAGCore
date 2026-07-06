import uuid

from retrieval.context import RetrievedChunk
from services.conversational_retriever import _dedupe_chunks


def _chunk(source_key: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title=f"{source_key} title",
        content="content",
        metadata={"chunk_source_key": source_key},
        score=score,
    )


def test_final_retrieval_limits_repeated_chunks_per_source():
    chunks = [
        _chunk("page-a", 0.90),
        _chunk("page-a", 0.89),
        _chunk("page-a", 0.88),
        _chunk("page-b", 0.50),
        _chunk("page-c", 0.40),
    ]

    result = _dedupe_chunks(chunks)

    assert [chunk.metadata["chunk_source_key"] for chunk in result] == [
        "page-a",
        "page-a",
        "page-b",
        "page-c",
    ]
