import uuid

from retrieval.context import RetrievedChunk
from services.chat_service import _source_payload
from services.web_search_service import _freshness_aware_query, _score_duckduckgo_result


def test_duckduckgo_ranking_boosts_answer_bearing_result_snippets() -> None:
    vague_top_result = _score_duckduckgo_result(
        query="who won fifa world cup 2022",
        title="2022 FIFA World Cup final - Wikipedia",
        snippet=(
            "The 2022 FIFA World Cup final was contested by Argentina and France "
            "at Lusail Stadium."
        ),
        rank=1,
    )
    answer_result = _score_duckduckgo_result(
        query="who won fifa world cup 2022",
        title="2022 FIFA World Cup winner and final result",
        snippet="Argentina defeated France in the final match to win its third World Cup title.",
        rank=7,
    )

    assert answer_result > vague_top_result


def test_web_source_payload_uses_display_snippet_not_rendered_chunk() -> None:
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="2022 FIFA World Cup",
        content="# 2022 FIFA World Cup\nURL: https://example.test\n\nRendered internal chunk body",
        metadata={
            "source": "web",
            "source_url": "https://example.test",
            "web_snippet": "Argentina defeated France in the final match.",
        },
        score=0.92,
    )

    payload = _source_payload(1, chunk)

    assert payload["snippet"] == "Argentina defeated France in the final match."
    assert payload["url"] == "https://example.test"


def test_current_web_queries_include_date_and_primary_source_hint() -> None:
    rewritten = _freshness_aware_query("What is the current stable Argo CD release?")

    assert "2026" in rewritten
    assert "GitHub Releases" in rewritten
    assert _freshness_aware_query("Explain Kubernetes RBAC") == "Explain Kubernetes RBAC"
