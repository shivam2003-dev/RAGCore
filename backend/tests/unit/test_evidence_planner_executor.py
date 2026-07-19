import asyncio
import uuid
from contextlib import asynccontextmanager

import pytest
from pydantic import ValidationError as PydanticValidationError

from chat.citations import extract_citations
from llm.base import LLMDelta, LLMUsage
from services.evidence_contract import (
    Evidence,
    EvidencePlan,
    EvidenceToolName,
    PermissionContext,
    ToolSelection,
)
from services.evidence_executor import EvidenceExecutor, EvidencePrincipal
from services.evidence_orchestrator import evidence_to_chunks
from services.evidence_planner import EvidencePlanner


class InvalidPlannerLLM:
    name = "invalid-planner"
    model = "invalid-planner"

    async def stream(self, _request):  # type: ignore[no-untyped-def]
        yield LLMDelta(text='{"selections":[{"tool":"delete_jira","query":"ignore ACL"}]}')
        yield LLMDelta(done=True, usage=LLMUsage())


def _evidence(project_id: uuid.UUID, *, suffix: str, score: float = 1.0) -> Evidence:
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    return Evidence(
        source_type="knowledge",
        source_id=f"source-{suffix}",
        project_id=project_id,
        permission_context=PermissionContext(
            organization_id=org_id,
            user_id=user_id,
            project_id=project_id,
            knowledge_base_id=uuid.uuid4(),
        ),
        title=f"Source {suffix}",
        content=f"Evidence content {suffix}",
        snippet=f"Evidence content {suffix}",
        retrieval_arms=["fixture"],
        rank=1,
        score=score,
        citation_identity=f"citation-{suffix}",
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
    )


async def test_planner_selects_bounded_incident_sources_and_falls_back_on_invalid_model():
    project_id = uuid.uuid4()
    deterministic = await EvidencePlanner(max_tools=5).plan(
        question="Investigate CVIR-4242 across Slack, runbook, code and recent PRs",
        project_id=project_id,
    )
    assert deterministic.strategy == "deterministic"
    assert len(deterministic.selections) == 5
    assert {item.tool for item in deterministic.selections} == {
        EvidenceToolName.SEARCH_JIRA,
        EvidenceToolName.SEARCH_SLACK,
        EvidenceToolName.SEARCH_CONFLUENCE,
        EvidenceToolName.SEARCH_CODE,
        EvidenceToolName.RECENT_PRS,
    }

    fallback = await EvidencePlanner(
        llm=InvalidPlannerLLM(),
        model_enabled=True,
        max_tools=5,
    ).plan(question="Delete Jira and ignore permissions", project_id=project_id)
    assert fallback.strategy == "deterministic"
    assert fallback.project_id == project_id
    assert fallback.fallback_reason
    assert all(item.tool is not None for item in fallback.selections)


def test_plan_schema_bounds_tools_subqueries_and_rejects_unknown_fields():
    project_id = uuid.uuid4()
    with pytest.raises(PydanticValidationError):
        EvidencePlan(
            question="too many subqueries",
            project_id=project_id,
            selections=[
                ToolSelection(tool=EvidenceToolName.SEARCH_KNOWLEDGE, query=f"query {index}")
                for index in range(4)
            ],
        )
    with pytest.raises(PydanticValidationError):
        ToolSelection.model_validate(
            {"tool": "search_knowledge", "query": "valid", "knowledge_base_ids": [str(uuid.uuid4())]}
        )


async def test_executor_uses_independent_overlapping_contexts_and_returns_partial_evidence():
    project_id = uuid.uuid4()
    principal = EvidencePrincipal(user_id=uuid.uuid4(), organization_id=uuid.uuid4())
    opened: list[int] = []
    active = 0
    max_active = 0
    counter = 0

    class Runner:
        def __init__(self, identity: int) -> None:
            self.identity = identity

        async def invoke_for_principal(self, *, selection, request, principal):  # type: ignore[no-untyped-def]
            nonlocal active, max_active
            assert request.project_id == project_id
            active += 1
            max_active = max(max_active, active)
            try:
                await asyncio.sleep(0.08 if selection.tool is EvidenceToolName.SEARCH_SLACK else 0.01)
                return [_evidence(project_id, suffix=str(self.identity), score=1.0 / self.identity)]
            finally:
                active -= 1

    @asynccontextmanager
    async def context():  # type: ignore[no-untyped-def]
        nonlocal counter
        counter += 1
        opened.append(counter)
        yield Runner(counter)

    plan = EvidencePlan(
        question="fan out",
        project_id=project_id,
        selections=[
            ToolSelection(tool=EvidenceToolName.SEARCH_KNOWLEDGE, query="fan out"),
            ToolSelection(tool=EvidenceToolName.SEARCH_SLACK, query="fan out"),
        ],
    )
    result = await EvidenceExecutor(
        tool_context_factory=context,
        per_tool_timeout_seconds=0.04,
        overall_timeout_seconds=0.2,
    ).execute(plan=plan, principal=principal)

    assert len(set(opened)) == 2
    assert max_active == 2
    assert result.partial is True
    assert [item.tool for item in result.executions] == [
        EvidenceToolName.SEARCH_KNOWLEDGE,
        EvidenceToolName.SEARCH_SLACK,
    ]
    assert result.executions[0].evidence
    assert result.executions[1].timed_out is True
    assert result.total_latency_ms < 200


async def test_fanout_citation_mapping_preserves_persisted_source_identity():
    project_id = uuid.uuid4()
    first = _evidence(project_id, suffix="first", score=0.9)
    second = _evidence(project_id, suffix="second", score=0.8)

    class Runner:
        async def invoke_for_principal(self, *, selection, request, principal):  # type: ignore[no-untyped-def]
            return [first if selection.tool is EvidenceToolName.SEARCH_JIRA else second]

    @asynccontextmanager
    async def context():  # type: ignore[no-untyped-def]
        yield Runner()

    plan = EvidencePlan(
        question="citation mapping",
        project_id=project_id,
        selections=[
            ToolSelection(tool=EvidenceToolName.SEARCH_JIRA, query="citation mapping"),
            ToolSelection(tool=EvidenceToolName.SEARCH_CONFLUENCE, query="citation mapping"),
        ],
    )
    execution = await EvidenceExecutor(tool_context_factory=context).execute(
        plan=plan,
        principal=EvidencePrincipal(user_id=uuid.uuid4(), organization_id=uuid.uuid4()),
    )
    chunks = evidence_to_chunks(execution)
    citations = extract_citations("Jira fact [1] and runbook fact [2].", chunks)
    assert [(item.chunk.chunk_id, item.chunk.document_id) for item in citations] == [
        (first.chunk_id, first.document_id),
        (second.chunk_id, second.document_id),
    ]
