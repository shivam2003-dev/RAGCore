import uuid

from fastapi import APIRouter

from api.deps import CurrentUser, KnowledgeWorkflowDep
from services.knowledge_workflows import (
    ChangeRequest,
    ChangeResponse,
    ExpertRequest,
    ExpertResponse,
    FreshnessResponse,
    IncidentCopilotResponse,
    IncidentRequest,
)

router = APIRouter(prefix="/workflows", tags=["knowledge-workflows"])


@router.post("/incident", response_model=IncidentCopilotResponse)
async def incident_copilot(
    body: IncidentRequest,
    user: CurrentUser,
    service: KnowledgeWorkflowDep,
) -> IncidentCopilotResponse:
    return await service.incident(body=body, user=user)


@router.post("/experts", response_model=ExpertResponse)
async def who_knows(
    body: ExpertRequest,
    user: CurrentUser,
    service: KnowledgeWorkflowDep,
) -> ExpertResponse:
    return await service.experts(body=body, user=user)


@router.post("/changes", response_model=ChangeResponse)
async def what_changed(
    body: ChangeRequest,
    user: CurrentUser,
    service: KnowledgeWorkflowDep,
) -> ChangeResponse:
    return await service.changes(body=body, user=user)


@router.get("/freshness", response_model=FreshnessResponse)
async def freshness_center(
    project_id: uuid.UUID,
    user: CurrentUser,
    service: KnowledgeWorkflowDep,
) -> FreshnessResponse:
    return await service.freshness(project_id=project_id, user=user)
