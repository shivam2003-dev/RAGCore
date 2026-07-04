import uuid

from fastapi import APIRouter

from api.deps import ConfluenceSyncDep, CurrentUser, SettingsDep, require_role
from api.schemas import (
    ConfluencePageSyncOut,
    ConfluenceStatusOut,
    ConfluenceSyncRequest,
    ConfluenceSyncResponse,
)
from models import Role
from services.confluence_service import confluence_config_status

router = APIRouter(prefix="/confluence", tags=["confluence"])


@router.get("/status", response_model=ConfluenceStatusOut)
async def confluence_status(_user: CurrentUser, settings: SettingsDep) -> ConfluenceStatusOut:
    return ConfluenceStatusOut.model_validate(confluence_config_status(settings))


@router.post(
    "/sync",
    response_model=ConfluenceSyncResponse,
    status_code=202,
    dependencies=[require_role(Role.EDITOR)],
)
async def sync_confluence(
    body: ConfluenceSyncRequest,
    user: CurrentUser,
    service: ConfluenceSyncDep,
) -> ConfluenceSyncResponse:
    result = await service.sync_space(
        user=user,
        kb_id=body.knowledge_base_id,
        max_pages=body.max_pages,
    )
    return ConfluenceSyncResponse(
        knowledge_base_id=uuid.UUID(str(result.knowledge_base_id)),
        knowledge_base_name=result.knowledge_base_name,
        space_key=result.space_key,
        space_name=result.space_name,
        total_pages=result.total_pages,
        created=result.created,
        updated=result.updated,
        skipped=result.skipped,
        documents=[
            ConfluencePageSyncOut(
                page_id=item.page_id,
                title=item.title,
                url=item.url,
                version=item.version,
                document_id=item.document_id,
                document_status=item.document_status,
                action=item.action,
            )
            for item in result.documents
        ],
    )
