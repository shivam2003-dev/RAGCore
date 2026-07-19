from fastapi import APIRouter

from api.deps import CurrentUser, SettingsDep, SlackConnectorDep, require_role
from api.schemas import SlackConfigurationIn, SlackStatusOut, SlackSyncOut, SlackSyncRequest
from models import Role
from services.slack_client import SlackHttpClient
from services.slack_service import SlackChannelConfig

router = APIRouter(prefix="/slack", tags=["slack"])


@router.get("/status", response_model=SlackStatusOut, dependencies=[require_role(Role.ADMIN)])
async def slack_status(user: CurrentUser, service: SlackConnectorDep) -> SlackStatusOut:
    return SlackStatusOut.model_validate(await service.status(user))


@router.put("/configuration", response_model=SlackStatusOut, dependencies=[require_role(Role.ADMIN)])
async def configure_slack(
    body: SlackConfigurationIn,
    user: CurrentUser,
    service: SlackConnectorDep,
) -> SlackStatusOut:
    result = await service.configure(
        user=user,
        workspace_id=body.workspace_id,
        channels=[
            SlackChannelConfig(
                channel_id=channel.channel_id,
                channel_name=channel.channel_name,
                project_id=channel.project_id,
                visibility=channel.visibility,
            )
            for channel in body.channels
        ],
    )
    return SlackStatusOut.model_validate(result)


@router.post(
    "/sync",
    response_model=SlackSyncOut,
    status_code=202,
    dependencies=[require_role(Role.ADMIN)],
)
async def sync_slack(
    body: SlackSyncRequest,
    user: CurrentUser,
    service: SlackConnectorDep,
    settings: SettingsDep,
) -> SlackSyncOut:
    client = SlackHttpClient(
        bot_token=settings.slack_bot_token,
        timeout_seconds=settings.slack_request_timeout_seconds,
        max_retries=settings.slack_api_max_retries,
        page_limit=settings.slack_history_limit,
    )
    try:
        result = await service.sync_allowlisted_channels(
            user=user,
            client=client,
            channel_id=body.channel_id,
        )
    finally:
        await client.close()
    return SlackSyncOut.model_validate(result)
