import hashlib
import json
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.exceptions import NotFoundError, ValidationError
from ingestion.queue import IngestionQueue
from models import (
    AccessScope,
    ConnectorState,
    KnowledgeBase,
    ProjectSource,
    SlackChannelMapping,
    User,
)
from repositories.audit import AuditLogRepository
from repositories.connectors import ConnectorRepository
from repositories.knowledge import DocumentRepository, KnowledgeBaseRepository
from repositories.projects import ProjectRepository
from services.document_service import DocumentService
from services.slack_client import SlackReadClient
from services.slack_normalizer import NormalizedSlackThread, SlackThreadNormalizer

_PUBLIC_CHANNEL_ID = re.compile(r"^C[A-Z0-9]{2,63}$")
_SUPPORTED_MESSAGE_SUBTYPES = {
    None,
    "message_changed",
    "message_deleted",
    "message_replied",
    "thread_broadcast",
}


@dataclass(slots=True, frozen=True)
class SlackChannelConfig:
    channel_id: str
    channel_name: str
    project_id: uuid.UUID
    visibility: str = "public"


@dataclass(slots=True, frozen=True)
class SlackIngestResult:
    action: str
    document_id: uuid.UUID | None
    thread_ts: str


class SlackConnectorService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        settings: Settings,
        document_service: DocumentService,
    ) -> None:
        self._db = db
        self._settings = settings
        self._documents = document_service
        self._connectors = ConnectorRepository(db)
        self._kbs = KnowledgeBaseRepository(db)
        self._projects = ProjectRepository(db)
        self._document_repo = DocumentRepository(db)
        self._audit = AuditLogRepository(db)

    async def status(self, user: User) -> dict[str, object]:
        state = await self._connectors.get_state(user.organization_id, "slack")
        mappings = await self._connectors.list_slack_mappings(user.organization_id)
        enabled = [mapping for mapping in mappings if mapping.is_enabled]
        credentials = bool(self._settings.slack_app_token.strip() and self._settings.slack_bot_token.strip())
        return {
            "configured": bool(credentials and enabled),
            "credentials_configured": credentials,
            "socket_mode_configured": bool(self._settings.slack_app_token.strip()),
            "read_only": True,
            "workspace_id": (state.config or {}).get("workspace_id") if state else None,
            "status": state.status if state else "disabled",
            "allowlisted_channels": len(enabled),
            "last_event_at": state.last_event_at if state else None,
            "last_success_at": state.last_success_at if state else None,
            "last_error_at": state.last_error_at if state else None,
            "lag_seconds": state.lag_seconds if state else None,
            "failure_count": state.failure_count if state else 0,
            "error_detail": state.error_detail if state else None,
            "channels": [self._mapping_out(mapping) for mapping in mappings],
        }

    async def configure(
        self,
        *,
        user: User,
        workspace_id: str,
        channels: list[SlackChannelConfig],
    ) -> dict[str, object]:
        workspace = workspace_id.strip()
        if not workspace or len(workspace) > 64:
            raise ValidationError("A valid Slack workspace ID is required")
        seen: set[str] = set()
        for channel in channels:
            self._validate_public_channel(channel)
            if channel.channel_id in seen:
                raise ValidationError("Slack channel IDs must be unique")
            seen.add(channel.channel_id)
            project = await self._projects.get_for_org(channel.project_id, user.organization_id)
            if project is None or not project.is_active:
                raise NotFoundError("Project not found")

        state = await self._connectors.ensure_state(
            organization_id=user.organization_id,
            kind="slack",
            created_by=user.id,
        )
        existing = await self._connectors.list_slack_mappings(user.organization_id)
        existing_by_channel = {mapping.channel_id: mapping for mapping in existing}
        for mapping in existing:
            mapping.is_enabled = False
            await self._db.execute(
                delete(ProjectSource).where(
                    ProjectSource.project_id == mapping.project_id,
                    ProjectSource.knowledge_base_id == mapping.knowledge_base_id,
                )
            )

        for channel in channels:
            mapping = existing_by_channel.get(channel.channel_id)
            if mapping is None:
                kb = KnowledgeBase(
                    organization_id=user.organization_id,
                    name=self._knowledge_base_name(channel),
                    description=f"Read-only Slack knowledge from allowlisted public channel #{channel.channel_name}.",
                    embedding_model=self._settings.embedding_model,
                    embedding_dimensions=self._settings.embedding_dimensions,
                    access_scope=AccessScope.ORGANIZATION,
                )
                self._kbs.add(kb)
                await self._db.flush()
                mapping = SlackChannelMapping(
                    organization_id=user.organization_id,
                    connector_state_id=state.id,
                    project_id=channel.project_id,
                    knowledge_base_id=kb.id,
                    workspace_id=workspace,
                    channel_id=channel.channel_id,
                    channel_name=channel.channel_name.strip(),
                    visibility="public",
                    is_enabled=True,
                )
                self._db.add(mapping)
            else:
                mapping.connector_state_id = state.id
                mapping.project_id = channel.project_id
                mapping.workspace_id = workspace
                mapping.channel_name = channel.channel_name.strip()
                mapping.visibility = "public"
                mapping.is_enabled = True
            project = await self._projects.get_for_org(channel.project_id, user.organization_id)
            assert project is not None
            await self._projects.add_source(project=project, knowledge_base_id=mapping.knowledge_base_id)

        state.config = {"workspace_id": workspace, "channel_count": len(channels)}
        state.status = "configured" if channels else "disabled"
        state.error_detail = None
        self._audit.record(
            action="slack.configure",
            resource_type="connector",
            resource_id=str(state.id),
            org_id=user.organization_id,
            actor_id=user.id,
            detail=f"workspace={workspace}; allowlisted_channels={len(channels)}",
        )
        await self._db.commit()
        return await self.status(user)

    async def sync_allowlisted_channels(
        self,
        *,
        user: User,
        client: SlackReadClient,
        channel_id: str | None = None,
    ) -> dict[str, int]:
        if not self._settings.slack_bot_token.strip():
            raise ValidationError("SLACK_BOT_TOKEN is not configured")
        state = await self._connectors.get_state(user.organization_id, "slack")
        if state is None:
            raise ValidationError("Slack connector is not configured")
        mappings = [
            mapping
            for mapping in await self._connectors.list_slack_mappings(user.organization_id)
            if mapping.is_enabled and (channel_id is None or mapping.channel_id == channel_id)
        ]
        if channel_id and not mappings:
            raise NotFoundError("Allowlisted Slack channel not found")

        counts = {"created": 0, "updated": 0, "skipped": 0, "deleted": 0, "failed": 0}
        for mapping in mappings:
            roots = await client.list_thread_roots(
                channel_id=mapping.channel_id,
                limit=self._settings.slack_history_limit,
            )
            for thread_ts in roots:
                try:
                    result = await self._ingest_thread(
                        user=user,
                        state=state,
                        mapping=mapping,
                        thread_ts=thread_ts,
                        event_id=None,
                        client=client,
                    )
                    counts[result.action] += 1
                except Exception as exc:
                    counts["failed"] += 1
                    self._connectors.record_connector_failure(state, str(exc))
        self._audit.record(
            action="slack.sync",
            resource_type="connector",
            resource_id=str(state.id),
            org_id=user.organization_id,
            actor_id=user.id,
            detail="; ".join(f"{key}={value}" for key, value in counts.items()),
        )
        await self._db.commit()
        return counts

    async def process_receipt(
        self,
        *,
        receipt_id: uuid.UUID,
        user: User,
        client: SlackReadClient,
    ) -> SlackIngestResult:
        receipt = await self._connectors.get_slack_receipt(receipt_id)
        if receipt is None or receipt.organization_id != user.organization_id:
            raise NotFoundError("Slack event receipt not found")
        state = await self._db.get(ConnectorState, receipt.connector_state_id)
        mapping = await self._connectors.get_slack_mapping_for_state(
            connector_state_id=receipt.connector_state_id,
            channel_id=receipt.channel_id,
        )
        if state is None or mapping is None:
            await self._connectors.mark_slack_receipt(receipt_id=receipt_id, status="ignored")
            await self._db.commit()
            return SlackIngestResult(action="skipped", document_id=None, thread_ts=receipt.thread_ts)
        await self._connectors.mark_slack_receipt(receipt_id=receipt_id, status="processing")
        await self._db.commit()
        try:
            result = await self._ingest_thread(
                user=user,
                state=state,
                mapping=mapping,
                thread_ts=receipt.thread_ts,
                event_id=receipt.event_id,
                client=client,
            )
            await self._connectors.mark_slack_receipt(receipt_id=receipt_id, status="processed")
            await self._db.commit()
            return result
        except Exception as exc:
            await self._db.rollback()
            state = await self._db.get(ConnectorState, receipt.connector_state_id)
            if state is not None:
                self._connectors.record_connector_failure(state, str(exc))
            await self._connectors.mark_slack_receipt(
                receipt_id=receipt_id,
                status="failed",
                error=str(exc),
            )
            await self._db.commit()
            raise

    async def _ingest_thread(
        self,
        *,
        user: User,
        state: ConnectorState,
        mapping: SlackChannelMapping,
        thread_ts: str,
        event_id: str | None,
        client: SlackReadClient,
    ) -> SlackIngestResult:
        thread = await client.fetch_thread(
            workspace_id=mapping.workspace_id,
            channel_id=mapping.channel_id,
            channel_name=mapping.channel_name,
            thread_ts=thread_ts,
        )
        thread_key = f"{mapping.workspace_id}:{mapping.channel_id}:{thread_ts}"
        existing = await self._document_repo.get_by_metadata_value(
            mapping.knowledge_base_id,
            "slack_thread_key",
            thread_key,
        )
        if thread is None:
            if existing is None:
                await self._connectors.record_connector_success(state, source_activity_at=None)
                return SlackIngestResult(action="skipped", document_id=None, thread_ts=thread_ts)
            await self._documents.delete(user=user, document_id=existing.id)
            await self._connectors.record_connector_success(state, source_activity_at=None)
            return SlackIngestResult(action="deleted", document_id=existing.id, thread_ts=thread_ts)

        normalizer = SlackThreadNormalizer(
            summary_max_chars=self._settings.slack_summary_max_chars,
            burst_min_messages=self._settings.slack_burst_min_messages,
            burst_rare_token_threshold=self._settings.slack_burst_rare_token_threshold,
            burst_reaction_threshold=self._settings.slack_burst_reaction_threshold,
        )
        normalized = await normalizer.normalize(thread)
        rendered = normalized.render_markdown().encode("utf-8")
        content_hash = hashlib.sha256(rendered).hexdigest()
        if existing is not None and (existing.doc_metadata or {}).get("source_sha256") == content_hash:
            activity = _parse_datetime(normalized.last_activity_at)
            await self._connectors.record_connector_success(state, source_activity_at=activity)
            return SlackIngestResult(action="skipped", document_id=existing.id, thread_ts=thread_ts)

        previous_event_ids = list((existing.doc_metadata or {}).get("slack_event_ids") or []) if existing else []
        event_ids = (
            [*previous_event_ids, event_id]
            if event_id and event_id not in previous_event_ids
            else previous_event_ids
        )
        metadata = self._metadata(
            normalized=normalized,
            mapping=mapping,
            event_ids=event_ids[-100:],
            source_sha256=content_hash,
        )
        document = await self._documents.create_from_bytes(
            user=user,
            kb_id=mapping.knowledge_base_id,
            filename=f"slack-{mapping.channel_id}-{thread_ts.replace('.', '-')}.md",
            content=rendered,
            existing_document_id=existing.id if existing else None,
            title=normalized.searchable_question[:500],
            metadata=metadata,
            audit_action="slack.thread.ingest",
            embedding_text=normalized.embedding_text(),
        )
        activity = _parse_datetime(normalized.last_activity_at)
        await self._connectors.record_connector_success(state, source_activity_at=activity)
        mapping.last_thread_ts = thread_ts
        await self._db.commit()
        return SlackIngestResult(
            action="updated" if existing else "created",
            document_id=document.id,
            thread_ts=thread_ts,
        )

    def _metadata(
        self,
        *,
        normalized: NormalizedSlackThread,
        mapping: SlackChannelMapping,
        event_ids: list[str],
        source_sha256: str,
    ) -> dict[str, object]:
        return {
            "source": "slack",
            "source_type": "slack",
            "source_family": "slack",
            "source_system": "slack",
            "source_id": normalized.source_id,
            "source_title": normalized.searchable_question[:500],
            "source_url": normalized.thread_url,
            "source_space": mapping.channel_id,
            "source_version": normalized.last_activity_at,
            "source_updated_at": normalized.last_activity_at,
            "source_sha256": source_sha256,
            "connector": "slack",
            "connector_scope": mapping.channel_id,
            "connector_sync_id": f"slack:{normalized.source_id}:{normalized.last_activity_at}",
            "acl": "channel-allowlist",
            "permission_state": "visible",
            "workspace_id": normalized.workspace_id,
            "channel_id": normalized.channel_id,
            "channel_name": normalized.channel_name,
            "thread_ts": normalized.thread_ts,
            "thread_url": normalized.thread_url,
            "slack_thread_key": normalized.source_id,
            "slack_event_ids": event_ids,
            "searchable_question": normalized.searchable_question,
            "summary": normalized.summary,
            "resolution": normalized.resolution,
            "systems": normalized.systems,
            "code_references": normalized.code_references,
            "participants": normalized.participants,
            "created_at": normalized.created_at,
            "last_activity_at": normalized.last_activity_at,
            "summary_fallback": normalized.summary_fallback,
            "burst_count": len(normalized.bursts),
            "project_id": str(mapping.project_id),
        }

    @staticmethod
    def _validate_public_channel(channel: SlackChannelConfig) -> None:
        if channel.visibility != "public":
            raise ValidationError("Only public Slack channels can be allowlisted")
        if not _PUBLIC_CHANNEL_ID.fullmatch(channel.channel_id.strip()):
            raise ValidationError("DMs, group DMs, and private Slack channels are not allowed")
        if not channel.channel_name.strip() or len(channel.channel_name.strip()) > 255:
            raise ValidationError("A valid Slack channel name is required")

    def _knowledge_base_name(self, channel: SlackChannelConfig) -> str:
        prefix = self._settings.slack_default_kb_name_prefix.strip() or "Slack"
        return f"{prefix} #{channel.channel_name.strip()} ({channel.channel_id})"[:255]

    @staticmethod
    def _mapping_out(mapping: SlackChannelMapping) -> dict[str, object]:
        return {
            "id": mapping.id,
            "workspace_id": mapping.workspace_id,
            "channel_id": mapping.channel_id,
            "channel_name": mapping.channel_name,
            "visibility": mapping.visibility,
            "is_enabled": mapping.is_enabled,
            "project_id": mapping.project_id,
            "knowledge_base_id": mapping.knowledge_base_id,
            "last_thread_ts": mapping.last_thread_ts,
        }


class SlackSocketEnvelopeReceiver:
    """Acknowledges Socket Mode envelopes before validation and queueing."""

    def __init__(
        self,
        *,
        db: AsyncSession,
        state: ConnectorState,
        queue: IngestionQueue,
        processor: Callable[..., Awaitable[None]],
    ) -> None:
        self._db = db
        self._state = state
        self._queue = queue
        self._processor = processor
        self._connectors = ConnectorRepository(db)

    async def handle(
        self,
        envelope: dict[str, object],
        acknowledge: Callable[[dict[str, str]], Awaitable[None]],
    ) -> str:
        envelope_id = _string(envelope.get("envelope_id"))
        if not envelope_id:
            raise ValidationError("Slack Socket Mode envelope_id is missing")
        await acknowledge({"envelope_id": envelope_id})

        parsed = _parse_event(envelope)
        if parsed is None:
            return "ignored"
        workspace_id, event_id, channel_id, thread_ts, event_type, channel_type, event_payload = parsed
        if channel_type in {"im", "mpim", "private"} or not _PUBLIC_CHANNEL_ID.fullmatch(channel_id):
            return "ignored"
        mapping = await self._connectors.get_slack_mapping(
            organization_id=self._state.organization_id,
            workspace_id=workspace_id,
            channel_id=channel_id,
        )
        if mapping is None:
            return "ignored"
        payload_hash = hashlib.sha256(
            json.dumps(event_payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        receipt_id = await self._connectors.claim_slack_event(
            organization_id=self._state.organization_id,
            connector_state_id=self._state.id,
            event_id=event_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            event_type=event_type,
            payload_hash=payload_hash,
        )
        await self._db.commit()
        if receipt_id is None:
            return "duplicate"
        self._queue.enqueue(self._processor, receipt_id=receipt_id)
        return "queued"


def slack_config_status(settings: Settings) -> dict[str, object]:
    return {
        "credentials_configured": bool(settings.slack_app_token.strip() and settings.slack_bot_token.strip()),
        "socket_mode_configured": bool(settings.slack_app_token.strip()),
        "read_only": True,
    }


def _parse_event(
    envelope: dict[str, object],
) -> tuple[str, str, str, str, str, str | None, dict[str, object]] | None:
    if envelope.get("type") != "events_api":
        return None
    payload = envelope.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "event_callback":
        return None
    event = payload.get("event")
    if not isinstance(event, dict) or event.get("type") != "message":
        return None
    subtype = _string(event.get("subtype")) or None
    if subtype not in _SUPPORTED_MESSAGE_SUBTYPES:
        return None
    workspace_id = _string(payload.get("team_id")) or _string(event.get("team"))
    event_id = _string(payload.get("event_id"))
    channel_id = _string(event.get("channel"))
    channel_type = _string(event.get("channel_type"))
    message = event.get("message") if isinstance(event.get("message"), dict) else event
    previous = event.get("previous_message") if isinstance(event.get("previous_message"), dict) else {}
    if subtype == "message_deleted":
        thread_ts = (
            _string(previous.get("thread_ts"))
            or _string(previous.get("ts"))
            or _string(event.get("deleted_ts"))
        )
    else:
        thread_ts = _string(message.get("thread_ts")) or _string(message.get("ts"))
    if not all([workspace_id, event_id, channel_id, thread_ts]):
        return None
    return (
        workspace_id,
        event_id,
        channel_id,
        thread_ts,
        f"message.{subtype or 'created'}",
        channel_type,
        event,
    )


def _string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
