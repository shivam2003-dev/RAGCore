"""Run the read-only Slack Socket Mode receiver.

The worker follows Slack's wire protocol directly: open a short-lived WebSocket
URL with the app token, acknowledge each envelope immediately, then deduplicate
and queue a complete-thread refresh. It never calls Slack mutation methods.
"""

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from sqlalchemy import select
from websockets.asyncio.client import connect

from api.deps import get_redis
from core.config import get_settings
from core.logging import configure_logging, get_logger
from database.session import SessionFactory, engine
from embeddings.factory import build_embedding_provider
from ingestion.queue import IngestionQueue
from models import ConnectorState, Role, User
from services.document_service import DocumentService
from services.slack_client import SlackHttpClient
from services.slack_service import SlackConnectorService, SlackSocketEnvelopeReceiver

log = get_logger(__name__)
_tasks: set[asyncio.Task[None]] = set()


class AsyncioTaskQueue(IngestionQueue):
    def enqueue(self, job: Callable[..., Awaitable[None]], /, **kwargs: Any) -> None:
        task = asyncio.create_task(job(**kwargs))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)


async def process_receipt(*, receipt_id: uuid.UUID) -> None:
    settings = get_settings()
    async with SessionFactory() as db:
        state = await db.scalar(select(ConnectorState).where(ConnectorState.kind == "slack"))
        if state is None:
            return
        user = await db.get(User, state.created_by) if state.created_by else None
        if user is None:
            user = await db.scalar(
                select(User).where(
                    User.organization_id == state.organization_id,
                    User.role == Role.ADMIN,
                    User.is_active.is_(True),
                )
            )
        if user is None:
            raise RuntimeError("Slack connector has no active organization admin")
        queue = AsyncioTaskQueue()
        embedder = build_embedding_provider(settings, get_redis())
        documents = DocumentService(db=db, settings=settings, embedder=embedder, queue=queue)
        service = SlackConnectorService(db=db, settings=settings, document_service=documents)
        client = SlackHttpClient(
            bot_token=settings.slack_bot_token,
            timeout_seconds=settings.slack_request_timeout_seconds,
            max_retries=settings.slack_api_max_retries,
            page_limit=settings.slack_history_limit,
        )
        try:
            await service.process_receipt(receipt_id=receipt_id, user=user, client=client)
        finally:
            await client.close()


async def socket_url(app_token: str) -> str:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://slack.com/api/apps.connections.open",
            headers={"Authorization": f"Bearer {app_token}"},
        )
        response.raise_for_status()
        payload = response.json()
    if payload.get("ok") is not True or not isinstance(payload.get("url"), str):
        raise RuntimeError(f"Slack apps.connections.open failed: {payload.get('error', 'unknown_error')}")
    return str(payload["url"])


async def run() -> None:
    configure_logging()
    settings = get_settings()
    if not settings.slack_app_token.strip() or not settings.slack_bot_token.strip():
        raise RuntimeError("SLACK_APP_TOKEN and SLACK_BOT_TOKEN are required")
    queue = AsyncioTaskQueue()
    while True:
        try:
            url = await socket_url(settings.slack_app_token)
            async with connect(url, max_size=2_000_000) as websocket:
                log.info("slack_socket_connected")
                async for raw in websocket:
                    envelope = json.loads(raw)
                    if not isinstance(envelope, dict):
                        continue
                    if envelope.get("type") == "disconnect":
                        break
                    envelope_id = envelope.get("envelope_id")
                    if not isinstance(envelope_id, str):
                        continue
                    # Socket Mode is already authenticated. Slack requires this
                    # acknowledgement promptly, before database validation or work.
                    await websocket.send(json.dumps({"envelope_id": envelope_id}))
                    payload = envelope.get("payload")
                    workspace_id = payload.get("team_id") if isinstance(payload, dict) else None
                    if not isinstance(workspace_id, str):
                        continue
                    async with SessionFactory() as db:
                        state = await db.scalar(
                            select(ConnectorState).where(
                                ConnectorState.kind == "slack",
                                ConnectorState.config["workspace_id"].as_string() == workspace_id,
                            )
                        )
                        if state is None:
                            continue
                        receiver = SlackSocketEnvelopeReceiver(
                            db=db,
                            state=state,
                            queue=queue,
                            processor=process_receipt,
                        )

                        async def acknowledge(_payload: dict[str, str]) -> None:
                            # The worker acknowledged before any database access.
                            return None

                        await receiver.handle(envelope, acknowledge)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("slack_socket_reconnect", error=str(exc)[:500])
            await asyncio.sleep(2)


async def main() -> None:
    try:
        await run()
    finally:
        if _tasks:
            await asyncio.gather(*_tasks, return_exceptions=True)
        await get_redis().aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
