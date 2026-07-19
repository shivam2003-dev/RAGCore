import uuid

from fastapi import APIRouter

from api.deps import CurrentUser, DbDep, GitHubIndexDep, SettingsDep, require_role
from api.schemas import (
    ExactCodeHitOut,
    ExactCodeSearchIn,
    ExactCodeSearchOut,
    GitHubPullRequestOut,
    GitHubRepositoryConfigIn,
    GitHubRepositoryOut,
    GitHubStatusOut,
    GitHubSyncOut,
)
from models import Role
from repositories.code_search import CodeSearchRepository
from repositories.projects import ProjectAuthorizationRepository
from services.github_client import GitHubHttpClient
from services.github_index import GitHubRepositoryConfig

router = APIRouter(prefix="/github", tags=["github"])


@router.get("/status", response_model=GitHubStatusOut, dependencies=[require_role(Role.ADMIN)])
async def github_status(user: CurrentUser, service: GitHubIndexDep) -> GitHubStatusOut:
    return GitHubStatusOut.model_validate(await service.status(user))


@router.post(
    "/repositories",
    response_model=GitHubRepositoryOut,
    status_code=201,
    dependencies=[require_role(Role.ADMIN)],
)
async def configure_repository(
    body: GitHubRepositoryConfigIn,
    user: CurrentUser,
    service: GitHubIndexDep,
) -> GitHubRepositoryOut:
    mapping = await service.configure(
        user=user,
        config=GitHubRepositoryConfig(
            owner=body.owner,
            repository=body.repository,
            branch=body.branch,
            project_id=body.project_id,
            path_allowlist=body.path_allowlist,
            path_denylist=body.path_denylist,
        ),
    )
    status = await service.status(user)
    row = next(item for item in status["repositories"] if item["id"] == mapping.id)
    return GitHubRepositoryOut.model_validate(row)


@router.post(
    "/repositories/{mapping_id}/sync",
    response_model=GitHubSyncOut,
    status_code=202,
    dependencies=[require_role(Role.ADMIN)],
)
async def sync_repository(
    mapping_id: uuid.UUID,
    user: CurrentUser,
    service: GitHubIndexDep,
    settings: SettingsDep,
) -> GitHubSyncOut:
    client = _client(settings)
    try:
        result = await service.sync_repository(user=user, mapping_id=mapping_id, client=client)
    finally:
        await client.close()
    return GitHubSyncOut.model_validate(result)


@router.get(
    "/repositories/{mapping_id}/recent-prs",
    response_model=list[GitHubPullRequestOut],
)
async def recent_pull_requests(
    mapping_id: uuid.UUID,
    user: CurrentUser,
    service: GitHubIndexDep,
    settings: SettingsDep,
) -> list[GitHubPullRequestOut]:
    client = _client(settings)
    try:
        rows = await service.recent_pull_requests(user=user, mapping_id=mapping_id, client=client)
    finally:
        await client.close()
    return [GitHubPullRequestOut.model_validate(row, from_attributes=True) for row in rows]


@router.post("/code-search", response_model=ExactCodeSearchOut)
async def exact_code_search(
    body: ExactCodeSearchIn,
    user: CurrentUser,
    db: DbDep,
) -> ExactCodeSearchOut:
    scope = await ProjectAuthorizationRepository(db).authorized_scope(
        user=user,
        project_id=body.project_id,
    )
    rows = await CodeSearchRepository(db).exact_search(
        query=body.query,
        authorized_knowledge_base_ids=scope.knowledge_base_ids,
        limit=body.limit,
    )
    return ExactCodeSearchOut(
        hits=[ExactCodeHitOut.model_validate(row, from_attributes=True) for row in rows]
    )


def _client(settings: SettingsDep) -> GitHubHttpClient:
    return GitHubHttpClient(
        token=settings.github_token,
        base_url=settings.github_api_base_url,
        api_version=settings.github_api_version,
        timeout_seconds=settings.github_request_timeout_seconds,
        max_retries=settings.github_api_max_retries,
    )
