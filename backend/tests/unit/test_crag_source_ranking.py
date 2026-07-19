import uuid

from retrieval.context import RetrievalAttempt, RetrievalContext, RetrievedChunk
from retrieval.crag import HeuristicEvaluator, HeuristicReranker, PolicyDecision, ThresholdRetrievalPolicy


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


async def test_exact_jira_key_beats_generic_high_score_chunk() -> None:
    ranked = await HeuristicReranker().rerank(
        RetrievalContext(kb_id=uuid.uuid4(), query="What happened in CVIR-6360?", top_k=2),
        [
            _chunk("Generic CVIR incident summary", "jira", 0.92),
            RetrievedChunk(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                document_title="CVIR-6360: RF Communication Down",
                content="Issue key CVIR-6360 reports RF communication down.",
                metadata={"source": "jira", "jira_issue_key": "CVIR-6360", "source_id": "CVIR-6360"},
                score=0.70,
            ),
        ],
    )

    assert ranked[0].metadata["jira_issue_key"] == "CVIR-6360"


async def test_architecture_hld_beats_incident_page_that_only_mentions_hes() -> None:
    ranked = await HeuristicReranker().rerank(
        RetrievalContext(kb_id=uuid.uuid4(), query="Explain HES architecture and components", top_k=2),
        [
            _chunk("RCA: HES Web Not Accessible", "confluence", 0.88),
            _chunk("CVUM HES HLD", "confluence", 0.68),
        ],
    )

    assert ranked[0].document_title == "CVUM HES HLD"


async def test_generic_query_words_are_not_treated_as_exact_identifiers() -> None:
    ctx = RetrievalContext(kb_id=uuid.uuid4(), query="Explain the deployment process", top_k=4)
    ctx.chunks = [_chunk("Unrelated deployment note", "confluence", 0.55)]

    confidence = await HeuristicEvaluator().evaluate(ctx)

    assert confidence < 0.6
    assert "identifier_fit=0.0" in ctx.quality_notes[-1]


def test_broad_questions_require_more_than_one_document_before_accepting() -> None:
    ctx = RetrievalContext(kb_id=uuid.uuid4(), query="Explain HES architecture and components", top_k=8)
    ctx.chunks = [_chunk("HES Architecture", "confluence", 0.9)]
    ctx.confidence = 0.9
    ctx.attempts.append(
        RetrievalAttempt(query=ctx.query, top_k=ctx.top_k, result_count=1, confidence=ctx.confidence)
    )

    assert ThresholdRetrievalPolicy().decide(ctx) == PolicyDecision.WIDEN_K


def test_exact_issue_lookup_can_accept_one_strong_document() -> None:
    ctx = RetrievalContext(kb_id=uuid.uuid4(), query="What happened in CVIR-6360?", top_k=8)
    ctx.chunks = [_chunk("CVIR-6360 incident", "jira", 0.9)]
    ctx.confidence = 0.9
    ctx.attempts.append(
        RetrievalAttempt(query=ctx.query, top_k=ctx.top_k, result_count=1, confidence=ctx.confidence)
    )

    assert ThresholdRetrievalPolicy().decide(ctx) == PolicyDecision.ACCEPT
