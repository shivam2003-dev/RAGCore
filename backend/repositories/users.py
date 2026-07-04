import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.base import utcnow
from models import ApiKey, Organization, RefreshToken, User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_email(self, email: str) -> User | None:
        return await self.db.scalar(select(User).where(User.email == email.lower()))

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def list_by_org(self, org_id: uuid.UUID, limit: int = 100, offset: int = 0) -> list[User]:
        rows = await self.db.scalars(
            select(User)
            .where(User.organization_id == org_id)
            .order_by(User.created_at)
            .limit(limit)
            .offset(offset)
        )
        return list(rows)

    def add(self, user: User) -> None:
        self.db.add(user)


class OrganizationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_slug(self, slug: str) -> Organization | None:
        return await self.db.scalar(select(Organization).where(Organization.slug == slug))

    def add(self, org: Organization) -> None:
        self.db.add(org)


class RefreshTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add(self, token: RefreshToken) -> None:
        self.db.add(token)

    async def get_valid(self, token_hash: str) -> RefreshToken | None:
        return await self.db.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at > utcnow(),
            )
        )

    async def revoke(self, token_id: uuid.UUID) -> None:
        await self.db.execute(
            update(RefreshToken).where(RefreshToken.id == token_id).values(revoked=True)
        )

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        await self.db.execute(
            update(RefreshToken).where(RefreshToken.user_id == user_id).values(revoked=True)
        )


class ApiKeyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add(self, key: ApiKey) -> None:
        self.db.add(key)

    async def get_active_by_hash(self, key_hash: str) -> ApiKey | None:
        return await self.db.scalar(
            select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
        )

    async def touch(self, key_id: uuid.UUID, when: datetime | None = None) -> None:
        await self.db.execute(
            update(ApiKey).where(ApiKey.id == key_id).values(last_used_at=when or utcnow())
        )

    async def list_by_org(self, org_id: uuid.UUID) -> list[ApiKey]:
        rows = await self.db.scalars(select(ApiKey).where(ApiKey.organization_id == org_id))
        return list(rows)
