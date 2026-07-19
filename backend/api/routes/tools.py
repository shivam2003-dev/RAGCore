"""Authenticated read-only evidence primitives used by REST, chat, and MCP."""

import time

from fastapi import APIRouter

from api.deps import (
    CurrentUser,
    EvidenceOrchestratorDep,
    EvidenceToolDep,
    LLMDep,
    SettingsDep,
)
from services.evidence_contract import (
    TOOL_CAPABILITIES,
    EvidenceExecutionResult,
    EvidencePlan,
    EvidenceToolName,
    EvidenceToolRequest,
    ToolInvocationResult,
)
from services.evidence_planner import EvidencePlanner

router = APIRouter(prefix="/tools", tags=["evidence-tools"])


@router.get("/capabilities")
async def tool_capabilities(_user: CurrentUser) -> dict[str, object]:
    return {
        "read_only": True,
        "tools": [
            {"name": name.value, "description": description}
            for name, description in TOOL_CAPABILITIES.items()
        ],
    }


@router.post("/plan", response_model=EvidencePlan)
async def plan_tools(
    body: EvidenceToolRequest,
    _user: CurrentUser,
    settings: SettingsDep,
    llm: LLMDep,
) -> EvidencePlan:
    planner = EvidencePlanner(
        llm=llm,
        model_enabled=settings.knowledge_planner_model_enabled,
        max_tools=settings.knowledge_planner_max_tools,
    )
    return await planner.plan(question=body.query, project_id=body.project_id)


@router.post("/execute", response_model=EvidenceExecutionResult)
async def execute_tools(
    body: EvidenceToolRequest,
    user: CurrentUser,
    orchestrator: EvidenceOrchestratorDep,
) -> EvidenceExecutionResult:
    result = await orchestrator.retrieve(
        question=body.query,
        project_id=body.project_id,
        user=user,
    )
    return result.execution


@router.post("/{tool_name}", response_model=ToolInvocationResult)
async def invoke_tool(
    tool_name: EvidenceToolName,
    body: EvidenceToolRequest,
    user: CurrentUser,
    service: EvidenceToolDep,
) -> ToolInvocationResult:
    started = time.perf_counter()
    evidence = await service.invoke(tool=tool_name, request=body, user=user)
    return ToolInvocationResult(
        tool=tool_name,
        project_id=body.project_id,
        evidence=evidence,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
