from fastapi import APIRouter

from api.deps import CurrentUser, JiraSyncDep, SettingsDep, require_role
from api.schemas import JiraIssueSyncOut, JiraStatusOut, JiraSyncRequest, JiraSyncResponse
from models import Role
from services.jira_service import jira_config_status

router = APIRouter(prefix="/jira", tags=["jira"])


@router.get("/status", response_model=JiraStatusOut, dependencies=[require_role(Role.ADMIN)])
async def jira_status(_user: CurrentUser, settings: SettingsDep) -> JiraStatusOut:
    return JiraStatusOut.model_validate(jira_config_status(settings))


@router.post(
    "/sync",
    response_model=JiraSyncResponse,
    status_code=202,
    dependencies=[require_role(Role.ADMIN)],
)
async def sync_jira(
    body: JiraSyncRequest,
    user: CurrentUser,
    service: JiraSyncDep,
) -> JiraSyncResponse:
    result = await service.sync_board(
        user=user,
        kb_id=body.knowledge_base_id,
        max_issues=body.max_issues,
    )
    return JiraSyncResponse(
        knowledge_base_id=result.knowledge_base_id,
        knowledge_base_name=result.knowledge_base_name,
        project_key=result.project_key,
        board_id=result.board_id,
        board_name=result.board_name,
        total_issues=result.total_issues,
        created=result.created,
        updated=result.updated,
        skipped=result.skipped,
        documents=[
            JiraIssueSyncOut(
                issue_id=item.issue_id,
                issue_key=item.issue_key,
                title=item.title,
                url=item.url,
                status=item.status,
                updated_at=item.updated_at,
                document_id=item.document_id,
                document_status=item.document_status,
                action=item.action,
            )
            for item in result.documents
        ],
    )
