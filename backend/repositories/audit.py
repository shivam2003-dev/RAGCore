import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.base import utcnow
from models import AuditLog


class AuditLogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        org_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        detail: str | None = None,
        ip_address: str | None = None,
    ) -> None:
        self.db.add(
            AuditLog(
                organization_id=org_id,
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                detail=detail,
                ip_address=ip_address,
                created_at=utcnow(),
            )
        )

    async def list_for_org(
        self, org_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> list[AuditLog]:
        rows = await self.db.scalars(
            select(AuditLog)
            .where(AuditLog.organization_id == org_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows)
