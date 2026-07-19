import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from core.config import get_settings
from embeddings.fake import FakeEmbeddings
from ingestion.queue import IngestionQueue
from models import Document, SlackEventReceipt, User
from repositories.connectors import ConnectorRepository
from services.document_service import DocumentService
from services.slack_normalizer import SlackMessage, SlackThread
from services.slack_service import SlackConnectorService, SlackSocketEnvelopeReceiver


class CapturingQueue(IngestionQueue):
    def __init__(self, events: list[str] | None = None) -> None:
        self.jobs: list[tuple[Callable[..., Awaitable[None]], dict[str, Any]]] = []
        self.events = events

    def enqueue(self, job: Callable[..., Awaitable[None]], /, **kwargs: Any) -> None:
        self.jobs.append((job, kwargs))
        if self.events is not None:
            self.events.append("queued")


class FakeSlackClient:
    def __init__(self, thread: SlackThread | None) -> None:
        self.thread = thread
        self.fetches: list[tuple[str, str]] = []

    async def list_thread_roots(self, *, channel_id: str, limit: int) -> list[str]:
        return [self.thread.thread_ts] if self.thread else []

    async def fetch_thread(
        self,
        *,
        workspace_id: str,
        channel_id: str,
        channel_name: str,
        thread_ts: str,
    ) -> SlackThread | None:
        self.fetches.append((channel_id, thread_ts))
        return self.thread


async def _configure_channel(client, auth_headers, suffix: str = "SLACK") -> tuple[dict, dict]:
    project = await client.post(
        "/api/v1/projects",
        json={"name": f"Slack Project {suffix}", "slug": f"slack-project-{suffix.lower()}"},
        headers=auth_headers,
    )
    assert project.status_code == 201, project.text
    channel_id = f"C{suffix}123"
    response = await client.put(
        "/api/v1/slack/configuration",
        json={
            "workspace_id": "TTEST123",
            "channels": [
                {
                    "channel_id": channel_id,
                    "channel_name": f"sre-{suffix.lower()}",
                    "project_id": project.json()["id"],
                    "visibility": "public",
                }
            ],
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    body["channels"] = [item for item in body["channels"] if item["is_enabled"]]
    return project.json(), body


async def test_slack_status_configuration_project_mapping_and_denials(client, auth_headers):
    before = await client.get("/api/v1/slack/status", headers=auth_headers)
    assert before.status_code == 200, before.text
    assert before.json()["read_only"] is True
    assert before.json()["credentials_configured"] is False
    assert "token" not in str(before.json()).lower()

    project, body = await _configure_channel(client, auth_headers, "CONFIG")
    assert body["configured"] is False
    assert body["allowlisted_channels"] == 1
    assert body["channels"][0]["project_id"] == project["id"]
    slack_kb_id = body["channels"][0]["knowledge_base_id"]

    projects = (await client.get("/api/v1/projects", headers=auth_headers)).json()
    target = next(item for item in projects if item["id"] == project["id"])
    default = next(item for item in projects if item["slug"] == "all-knowledge")
    assert slack_kb_id in target["authorized_source_ids"]
    assert slack_kb_id not in default["authorized_source_ids"]

    private = await client.put(
        "/api/v1/slack/configuration",
        json={
            "workspace_id": "TTEST123",
            "channels": [
                {
                    "channel_id": "GPRIVATE123",
                    "channel_name": "private-help",
                    "project_id": project["id"],
                    "visibility": "public",
                }
            ],
        },
        headers=auth_headers,
    )
    assert private.status_code == 422

    dm = await client.put(
        "/api/v1/slack/configuration",
        json={
            "workspace_id": "TTEST123",
            "channels": [
                {
                    "channel_id": "DUSER123",
                    "channel_name": "direct-message",
                    "project_id": project["id"],
                    "visibility": "public",
                }
            ],
        },
        headers=auth_headers,
    )
    assert dm.status_code == 422


async def test_socket_ack_dedupe_refresh_idempotency_edit_and_delete(client, auth_headers, db):
    project, status = await _configure_channel(client, auth_headers, "EVENT")
    channel = status["channels"][0]
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    user = await db.get(User, uuid.UUID(me.json()["id"]))
    state = await ConnectorRepository(db).get_state(user.organization_id, "slack")
    assert user is not None and state is not None

    order: list[str] = []
    receipt_queue = CapturingQueue(order)

    async def processor(**_kwargs: Any) -> None:
        return None

    receiver = SlackSocketEnvelopeReceiver(
        db=db,
        state=state,
        queue=receipt_queue,
        processor=processor,
    )

    async def acknowledge(_payload: dict[str, str]) -> None:
        order.append("ack")

    envelope = _message_envelope(
        event_id="Ev-1",
        channel_id=channel["channel_id"],
        ts="1750000000.000001",
        thread_ts="1750000000.000001",
    )
    assert await receiver.handle(envelope, acknowledge) == "queued"
    assert order == ["ack", "queued"]
    assert await receiver.handle(envelope, acknowledge) == "duplicate"
    assert len(receipt_queue.jobs) == 1

    receipt_id = receipt_queue.jobs[0][1]["receipt_id"]
    ingest_queue = CapturingQueue()
    settings = get_settings().model_copy(update={"slack_bot_token": "fixture-token"})
    documents = DocumentService(
        db=db,
        settings=settings,
        embedder=FakeEmbeddings(dimensions=settings.embedding_dimensions),
        queue=ingest_queue,
    )
    service = SlackConnectorService(db=db, settings=settings, document_service=documents)
    fake = FakeSlackClient(_thread(channel["channel_id"]))

    created = await service.process_receipt(receipt_id=receipt_id, user=user, client=fake)
    assert created.action == "created"
    assert len(ingest_queue.jobs) == 1
    document = await db.get(Document, created.document_id)
    assert document is not None
    assert document.doc_metadata["project_id"] == project["id"]
    assert document.doc_metadata["thread_url"].endswith("thread_ts=1750000000.000001")
    assert document.doc_metadata["slack_event_ids"] == ["Ev-1"]

    unchanged_envelope = _message_envelope(
        event_id="Ev-2",
        channel_id=channel["channel_id"],
        ts="1750000010.000002",
        thread_ts="1750000000.000001",
    )
    assert await receiver.handle(unchanged_envelope, acknowledge) == "queued"
    unchanged_id = receipt_queue.jobs[-1][1]["receipt_id"]
    unchanged = await service.process_receipt(receipt_id=unchanged_id, user=user, client=fake)
    assert unchanged.action == "skipped"
    assert len(ingest_queue.jobs) == 1

    original_thread = _thread(channel["channel_id"])
    fake.thread = SlackThread(
        workspace_id=original_thread.workspace_id,
        channel_id=original_thread.channel_id,
        channel_name=original_thread.channel_name,
        thread_ts=original_thread.thread_ts,
        thread_url=original_thread.thread_url,
        messages=[
            *original_thread.messages,
            SlackMessage(
                ts="1750000020.000003",
                user_id="U3",
                text="Edited resolution: restart gateway with --safe-mode.",
            ),
        ],
    )
    edited_envelope = _message_changed_envelope(channel["channel_id"])
    assert await receiver.handle(edited_envelope, acknowledge) == "queued"
    edited_id = receipt_queue.jobs[-1][1]["receipt_id"]
    updated = await service.process_receipt(receipt_id=edited_id, user=user, client=fake)
    assert updated.action == "updated"
    assert updated.document_id == created.document_id
    assert len(ingest_queue.jobs) == 2
    document = await db.get(Document, created.document_id)
    await db.refresh(document)
    assert document.current_version == 2

    fake.thread = None
    deleted_envelope = _message_deleted_envelope(channel["channel_id"])
    assert await receiver.handle(deleted_envelope, acknowledge) == "queued"
    deleted_id = receipt_queue.jobs[-1][1]["receipt_id"]
    deleted = await service.process_receipt(receipt_id=deleted_id, user=user, client=fake)
    assert deleted.action == "deleted"
    document = await db.get(Document, created.document_id)
    await db.refresh(document)
    assert document.is_deleted is True
    assert fake.fetches == [(channel["channel_id"], "1750000000.000001")] * 4

    receipts = [
        await db.get(SlackEventReceipt, job[1]["receipt_id"])
        for job in receipt_queue.jobs
    ]
    assert all(receipt is not None and receipt.status == "processed" for receipt in receipts)


async def test_socket_receiver_denies_unallowlisted_and_dm_events(client, auth_headers, db):
    await _configure_channel(client, auth_headers, "DENY")
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    user = await db.get(User, uuid.UUID(me.json()["id"]))
    state = await ConnectorRepository(db).get_state(user.organization_id, "slack")
    queue = CapturingQueue()

    async def processor(**_kwargs: Any) -> None:
        return None

    receiver = SlackSocketEnvelopeReceiver(db=db, state=state, queue=queue, processor=processor)
    acks: list[dict[str, str]] = []

    async def acknowledge(payload: dict[str, str]) -> None:
        acks.append(payload)

    unallowlisted = _message_envelope(
        event_id="Ev-denied-1",
        channel_id="CNOTALLOWED",
        ts="1.0",
        thread_ts="1.0",
    )
    assert await receiver.handle(unallowlisted, acknowledge) == "ignored"
    dm = _message_envelope(
        event_id="Ev-denied-2",
        channel_id="DUSER123",
        ts="2.0",
        thread_ts="2.0",
        channel_type="im",
    )
    assert await receiver.handle(dm, acknowledge) == "ignored"
    assert len(acks) == 2
    assert queue.jobs == []


def _thread(channel_id: str) -> SlackThread:
    return SlackThread(
        workspace_id="TTEST123",
        channel_id=channel_id,
        channel_name="sre-event",
        thread_ts="1750000000.000001",
        thread_url=(
            f"https://example.slack.com/archives/{channel_id}/p1750000000000001"
            "?thread_ts=1750000000.000001"
        ),
        messages=[
            SlackMessage(
                ts="1750000000.000001",
                user_id="U1",
                text="Why is gateway.prod.example.com returning ERR5029?",
            ),
            SlackMessage(
                ts="1750000010.000002",
                user_id="U2",
                text="Restart gateway with --safe-mode and validate the logs.",
                reactions=3,
            ),
        ],
    )


def _message_envelope(
    *,
    event_id: str,
    channel_id: str,
    ts: str,
    thread_ts: str,
    channel_type: str = "channel",
) -> dict[str, object]:
    return {
        "type": "events_api",
        "envelope_id": f"envelope-{event_id}",
        "payload": {
            "type": "event_callback",
            "team_id": "TTEST123",
            "event_id": event_id,
            "event": {
                "type": "message",
                "channel": channel_id,
                "channel_type": channel_type,
                "ts": ts,
                "thread_ts": thread_ts,
                "text": "fixture",
            },
        },
    }


def _message_changed_envelope(channel_id: str) -> dict[str, object]:
    return {
        "type": "events_api",
        "envelope_id": "envelope-Ev-edit",
        "payload": {
            "type": "event_callback",
            "team_id": "TTEST123",
            "event_id": "Ev-edit",
            "event": {
                "type": "message",
                "subtype": "message_changed",
                "channel": channel_id,
                "channel_type": "channel",
                "message": {"ts": "1750000010.000002", "thread_ts": "1750000000.000001"},
            },
        },
    }


def _message_deleted_envelope(channel_id: str) -> dict[str, object]:
    return {
        "type": "events_api",
        "envelope_id": "envelope-Ev-delete",
        "payload": {
            "type": "event_callback",
            "team_id": "TTEST123",
            "event_id": "Ev-delete",
            "event": {
                "type": "message",
                "subtype": "message_deleted",
                "channel": channel_id,
                "channel_type": "channel",
                "deleted_ts": "1750000000.000001",
                "previous_message": {"ts": "1750000000.000001", "thread_ts": "1750000000.000001"},
                "ts": "1750000090.000009",
            },
        },
    }
