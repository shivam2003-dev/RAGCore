import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.ids import uuid7
from database.base import utcnow
from models import (
    ConnectorState,
    GitHubFileState,
    GitHubRepositoryMapping,
    SlackChannelMapping,
    SlackEventReceipt,
)


class ConnectorRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_state(self, organization_id: uuid.UUID, kind: str) -> ConnectorState | None:
        return await self.db.scalar(
            select(ConnectorState).where(
                ConnectorState.organization_id == organization_id,
                ConnectorState.kind == kind,
            )
        )

    async def ensure_state(
        self,
        *,
        organization_id: uuid.UUID,
        kind: str,
        created_by: uuid.UUID | None,
    ) -> ConnectorState:
        state = await self.get_state(organization_id, kind)
        if state is not None:
            return state
        state = ConnectorState(
            organization_id=organization_id,
            created_by=created_by,
            kind=kind,
            status="disabled",
            config={},
        )
        self.db.add(state)
        await self.db.flush()
        return state

    async def list_slack_mappings(self, organization_id: uuid.UUID) -> list[SlackChannelMapping]:
        rows = await self.db.scalars(
            select(SlackChannelMapping)
            .where(SlackChannelMapping.organization_id == organization_id)
            .order_by(SlackChannelMapping.channel_name, SlackChannelMapping.channel_id)
        )
        return list(rows)

    async def get_slack_mapping(
        self,
        *,
        organization_id: uuid.UUID,
        workspace_id: str,
        channel_id: str,
        enabled_only: bool = True,
    ) -> SlackChannelMapping | None:
        stmt = select(SlackChannelMapping).where(
            SlackChannelMapping.organization_id == organization_id,
            SlackChannelMapping.workspace_id == workspace_id,
            SlackChannelMapping.channel_id == channel_id,
        )
        if enabled_only:
            stmt = stmt.where(SlackChannelMapping.is_enabled.is_(True))
        return await self.db.scalar(stmt)

    async def get_slack_mapping_for_state(
        self,
        *,
        connector_state_id: uuid.UUID,
        channel_id: str,
    ) -> SlackChannelMapping | None:
        return await self.db.scalar(
            select(SlackChannelMapping).where(
                SlackChannelMapping.connector_state_id == connector_state_id,
                SlackChannelMapping.channel_id == channel_id,
                SlackChannelMapping.is_enabled.is_(True),
            )
        )

    async def claim_slack_event(
        self,
        *,
        organization_id: uuid.UUID,
        connector_state_id: uuid.UUID,
        event_id: str,
        channel_id: str,
        thread_ts: str,
        event_type: str,
        payload_hash: str,
    ) -> uuid.UUID | None:
        receipt_id = uuid7()
        claimed = await self.db.scalar(
            insert(SlackEventReceipt)
            .values(
                id=receipt_id,
                organization_id=organization_id,
                connector_state_id=connector_state_id,
                event_id=event_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
                event_type=event_type,
                status="queued",
                attempts=0,
                payload_hash=payload_hash,
                received_at=utcnow(),
            )
            .on_conflict_do_nothing(constraint="uq_slack_event_receipts_event")
            .returning(SlackEventReceipt.id)
        )
        return claimed

    async def get_slack_receipt(self, receipt_id: uuid.UUID) -> SlackEventReceipt | None:
        return await self.db.get(SlackEventReceipt, receipt_id)

    async def mark_slack_receipt(
        self,
        *,
        receipt_id: uuid.UUID,
        status: str,
        error: str | None = None,
    ) -> None:
        values: dict[str, object] = {
            "status": status,
            "last_error": error[:1000] if error else None,
        }
        if status in {"processed", "ignored", "failed"}:
            values["processed_at"] = utcnow()
        if status == "processing":
            values["attempts"] = SlackEventReceipt.attempts + 1
        await self.db.execute(
            update(SlackEventReceipt).where(SlackEventReceipt.id == receipt_id).values(**values)
        )

    async def record_connector_success(
        self,
        state: ConnectorState,
        *,
        source_activity_at: datetime | None,
    ) -> None:
        now = utcnow()
        state.status = "connected"
        state.last_success_at = now
        state.last_event_at = source_activity_at or now
        state.last_error_at = None
        state.error_detail = None
        state.failure_count = 0
        state.lag_seconds = (
            max(0, int((now - source_activity_at).total_seconds()))
            if source_activity_at is not None
            else None
        )

    def record_connector_failure(self, state: ConnectorState, error: str) -> None:
        state.status = "degraded"
        state.last_error_at = utcnow()
        state.failure_count += 1
        state.error_detail = error[:1000]

    async def list_github_mappings(self, organization_id: uuid.UUID) -> list[GitHubRepositoryMapping]:
        rows = await self.db.scalars(
            select(GitHubRepositoryMapping)
            .where(GitHubRepositoryMapping.organization_id == organization_id)
            .order_by(
                GitHubRepositoryMapping.owner,
                GitHubRepositoryMapping.repository,
                GitHubRepositoryMapping.branch,
            )
        )
        return list(rows)

    async def get_github_mapping(
        self,
        *,
        mapping_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> GitHubRepositoryMapping | None:
        return await self.db.scalar(
            select(GitHubRepositoryMapping).where(
                GitHubRepositoryMapping.id == mapping_id,
                GitHubRepositoryMapping.organization_id == organization_id,
            )
        )

    async def get_github_mapping_by_repo(
        self,
        *,
        organization_id: uuid.UUID,
        owner: str,
        repository: str,
        branch: str,
    ) -> GitHubRepositoryMapping | None:
        return await self.db.scalar(
            select(GitHubRepositoryMapping).where(
                GitHubRepositoryMapping.organization_id == organization_id,
                GitHubRepositoryMapping.owner == owner,
                GitHubRepositoryMapping.repository == repository,
                GitHubRepositoryMapping.branch == branch,
            )
        )

    async def github_file_states(self, mapping_id: uuid.UUID) -> list[GitHubFileState]:
        rows = await self.db.scalars(
            select(GitHubFileState)
            .where(GitHubFileState.repository_mapping_id == mapping_id)
            .order_by(GitHubFileState.path)
        )
        return list(rows)
