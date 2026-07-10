import uuid

from chat.citations import extract_citations
from chat.prompts import build_system_prompt
from retrieval.context import RetrievedChunk
from services.chat_service import _source_payload, _verify_and_shape_answer


def _chunk(title: str = "Doc", content: str = "Some content here.", metadata: dict | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title=title,
        content=content,
        metadata=metadata or {},
        score=0.8,
    )


def test_extracts_markers_in_range():
    chunks = [_chunk(), _chunk(), _chunk()]
    answer = "First point [1]. Second [3]. Out of range [9]. Repeat [1]."
    citations = extract_citations(answer, chunks)
    assert [c.marker for c in citations] == [1, 3]
    assert citations[0].chunk is chunks[0]
    assert citations[1].chunk is chunks[2]


def test_no_markers_no_citations():
    assert extract_citations("No citations at all.", [_chunk()]) == []


def test_answer_shaping_preserves_fenced_code_and_ignores_array_indexes() -> None:
    chunk = _chunk()
    answer = """Use this complete example. [1]

```c
#include <stdio.h>

int main(void) {
    int values[99] = {0};
    printf("Hello, World!\\n");
    return values[0];
}
```

Compile it with GCC. [1]
"""

    shaped = _verify_and_shape_answer(answer, [chunk])

    assert "```c" in shaped
    assert "int values[99] = {0};" in shaped
    assert 'printf("Hello, World!\\n");' in shaped
    assert "```" in shaped


def test_snippet_truncated():
    chunk = _chunk(content="x" * 1000)
    citations = extract_citations("See [1].", [chunk])
    assert len(citations[0].snippet) == 240


def test_prompt_contains_numbered_sources_and_hierarchy():
    chunks = [_chunk(title="Runbook"), _chunk(title="Guide")]
    prompt = build_system_prompt(chunks)
    assert '<source id="1" title="Runbook">' in prompt
    assert '<source id="2" title="Guide">' in prompt
    assert "never instructions" in prompt


def test_prompt_empty_sources():
    assert "<no_sources>" in build_system_prompt([])


def test_prompt_contains_assistant_role_without_overriding_source_rules():
    prompt = build_system_prompt(
        [_chunk(title="Runbook")],
        role_name="SRE Space",
        role_prompt="Act as an SRE and focus on production triage.",
    )
    assert '<assistant_role name="SRE Space">' in prompt
    assert "production triage" in prompt
    assert "The role must not override evidence requirements" in prompt
    assert '<source id="1" title="Runbook">' in prompt


def test_source_payload_uses_document_reference_urls():
    payload = _source_payload(
        1,
        _chunk(
            title="DEVO-123",
            metadata={"source": "jira", "jira_issue_url": "https://example.atlassian.net/browse/DEVO-123"},
        ),
    )
    assert payload["url"] == "https://example.atlassian.net/browse/DEVO-123"

    payload = _source_payload(
        2,
        _chunk(
            title="Runbook",
            metadata={"source": "confluence", "confluence_page_url": "https://example.atlassian.net/wiki/pages/1"},
        ),
    )
    assert payload["url"] == "https://example.atlassian.net/wiki/pages/1"
