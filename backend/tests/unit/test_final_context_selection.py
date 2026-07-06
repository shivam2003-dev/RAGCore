import uuid

from retrieval.context import RetrievalContext, RetrievedChunk
from retrieval.pipeline import retrieval_search_query, select_final_context


def _chunk(title: str, source: str, score: float, document_id: uuid.UUID | None = None) -> RetrievedChunk:
    doc_id = document_id or uuid.uuid4()
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=doc_id,
        document_title=title,
        content=f"{title}\ncontent",
        metadata={"source": source, "source_id": str(doc_id)},
        score=score,
    )


def test_doc_intent_context_keeps_confluence_when_jira_volume_is_high() -> None:
    jira_chunks = [_chunk(f"DEVO-{index} HES Architecture ticket", "jira", 0.95 - (index * 0.01)) for index in range(8)]
    confluence_chunks = [
        _chunk("HES Architecture Overview", "confluence", 0.72),
        _chunk("HES Architecture Components", "confluence", 0.70),
    ]
    ctx = RetrievalContext(kb_id=uuid.uuid4(), query="HES Architecture", top_k=5)

    selected = select_final_context(ctx, [*jira_chunks, *confluence_chunks], top_k=5)

    assert [chunk.metadata["source"] for chunk in selected].count("confluence") >= 2
    assert [chunk.metadata["source"] for chunk in selected].count("jira") <= 3


def test_final_context_limits_repeated_chunks_from_same_document() -> None:
    document_id = uuid.uuid4()
    chunks = [_chunk(f"Runbook section {index}", "confluence", 0.9 - (index * 0.01), document_id) for index in range(5)]
    chunks.append(_chunk("Second runbook", "confluence", 0.5))
    ctx = RetrievalContext(kb_id=uuid.uuid4(), query="runbook procedure", top_k=4)

    selected = select_final_context(ctx, chunks, top_k=4)

    assert sum(1 for chunk in selected if chunk.document_id == document_id) == 2


def test_retrieval_search_query_removes_doc_question_noise() -> None:
    assert retrieval_search_query("What does the Confluence documentation say about HES Architecture?") == "HES Architecture"
    assert retrieval_search_query("Tell me about CVIR-6360") == "CVIR-6360"
