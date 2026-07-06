import uuid

from models import KnowledgeBase
from retrieval.context import RetrievedChunk
from services.conversational_retriever import _classify_query, _dedupe_chunks, _kb_source_family, _role_scope


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


def _kb(name: str) -> KnowledgeBase:
    return KnowledgeBase(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        name=name,
        description="",
        embedding_model="fake",
        embedding_dimensions=8,
    )


def test_devops_role_scope_prefers_devo_and_devops1_sources():
    kbs = [
        _kb("Jira DEVO"),
        _kb("Jira CVIR"),
        _kb("Confluence DevOps1"),
        _kb("Confluence SRE"),
        _kb("Confluence AS"),
    ]

    scoped = _role_scope(kbs, "DevOps Space")

    assert [kb.name for kb in scoped] == ["Jira DEVO", "Confluence DevOps1"]


def test_devops1_confluence_is_not_misclassified_as_jira():
    assert _kb_source_family(_kb("Confluence DevOps1")) == "confluence"
    assert _kb_source_family(_kb("Jira DEVO")) == "jira"


def test_sre_role_scope_prefers_cvir_sre_and_as_sources():
    kbs = [
        _kb("Jira DEVO"),
        _kb("Jira CVIR"),
        _kb("Confluence DevOps1"),
        _kb("Confluence SRE"),
        _kb("Confluence AS"),
    ]

    scoped = _role_scope(kbs, "SRE Space")

    assert [kb.name for kb in scoped] == ["Jira CVIR", "Confluence SRE", "Confluence AS"]


def test_query_classifier_identifies_architecture_and_jira_analytics():
    assert _classify_query("How many Jira issues are open in CVIR?") == "jira_count_stat"
    assert _classify_query("Explain HES Architecture") == "architecture_docs"
    assert _classify_query("What is the restart runbook for broker?") == "procedure_runbook"
