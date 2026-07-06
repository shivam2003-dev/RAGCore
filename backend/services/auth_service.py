from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.exceptions import AuthenticationError, ConflictError, ValidationError
from core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_api_key,
    new_refresh_token,
    verify_password,
)
from database.base import utcnow
from models import ApiKey, Organization, RefreshToken, Role, User
from repositories.audit import AuditLogRepository
from repositories.users import (
    ApiKeyRepository,
    OrganizationRepository,
    RefreshTokenRepository,
    UserRepository,
)


@dataclass(slots=True)
class TokenPair:
    access_token: str
    refresh_token: str


class AuthService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db = db
        self._settings = settings
        self._users = UserRepository(db)
        self._orgs = OrganizationRepository(db)
        self._refresh = RefreshTokenRepository(db)
        self._api_keys = ApiKeyRepository(db)
        self._audit = AuditLogRepository(db)

    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        organization_name: str,
        ip_address: str | None = None,
    ) -> tuple[User, TokenPair]:
        email = self._normalize_email(email)
        self._validate_allowed_email(email)
        if await self._users.get_by_email(email):
            raise ConflictError("Email already registered")

        org = await self._get_or_create_default_org()

        user = User(
            organization_id=org.id,
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=self._initial_role(email),
        )
        self._users.add(user)
        await self._db.flush()
        self._audit.record(
            action="user.register",
            resource_type="user",
            resource_id=str(user.id),
            org_id=org.id,
            actor_id=user.id,
            ip_address=ip_address,
        )
        pair = await self._issue_tokens(user)
        await self._db.commit()
        return user, pair

    async def login(self, *, email: str, password: str, ip_address: str | None = None) -> tuple[User, TokenPair]:
        email = self._normalize_email(email)
        self._validate_allowed_email(email)
        user = await self._users.get_by_email(email)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            # uniform error: no user-existence oracle
            raise AuthenticationError("Invalid email or password")
        self._audit.record(
            action="user.login",
            resource_type="user",
            resource_id=str(user.id),
            org_id=user.organization_id,
            actor_id=user.id,
            ip_address=ip_address,
        )
        pair = await self._issue_tokens(user)
        await self._db.commit()
        return user, pair

    async def create_user(
        self,
        *,
        actor: User,
        email: str,
        password: str,
        full_name: str,
        role: Role = Role.VIEWER,
        ip_address: str | None = None,
    ) -> User:
        email = self._normalize_email(email)
        self._validate_allowed_email(email)
        if await self._users.get_by_email(email):
            raise ConflictError("Email already registered")
        if self._is_super_admin(email):
            role = Role.ADMIN
        org = await self._get_or_create_default_org()
        user = User(
            organization_id=org.id,
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=role,
        )
        self._users.add(user)
        await self._db.flush()
        self._audit.record(
            action="user.create",
            resource_type="user",
            resource_id=str(user.id),
            org_id=org.id,
            actor_id=actor.id,
            ip_address=ip_address,
            detail=role.value,
        )
        await self._db.commit()
        return user

    async def refresh(self, refresh_token: str) -> TokenPair:
        stored = await self._refresh.get_valid(hash_token(refresh_token))
        if stored is None:
            raise AuthenticationError("Invalid refresh token")
        user = await self._users.get(stored.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("User inactive")
        await self._refresh.revoke(stored.id)  # rotation: one-time use
        pair = await self._issue_tokens(user)
        await self._db.commit()
        return pair

    async def logout(self, user: User) -> None:
        await self._refresh.revoke_all_for_user(user.id)
        await self._db.commit()

    async def create_api_key(self, user: User, name: str) -> tuple[ApiKey, str]:
        raw = new_api_key()
        key = ApiKey(
            organization_id=user.organization_id,
            user_id=user.id,
            name=name,
            key_hash=hash_token(raw),
            key_prefix=raw[:12],
        )
        self._api_keys.add(key)
        self._audit.record(
            action="api_key.create",
            resource_type="api_key",
            org_id=user.organization_id,
            actor_id=user.id,
            detail=name,
        )
        await self._db.commit()
        return key, raw  # raw shown exactly once

    async def resolve_api_key(self, raw: str) -> User | None:
        key = await self._api_keys.get_active_by_hash(hash_token(raw))
        if key is None:
            return None
        await self._api_keys.touch(key.id)
        return await self._users.get(key.user_id)

    async def _issue_tokens(self, user: User) -> TokenPair:
        access = create_access_token(
            user_id=user.id, org_id=user.organization_id, role=user.role.value
        )
        raw_refresh = new_refresh_token()
        self._refresh.add(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_token(raw_refresh),
                expires_at=utcnow() + timedelta(seconds=self._settings.jwt_refresh_ttl_seconds),
                created_at=utcnow(),
            )
        )
        return TokenPair(access_token=access, refresh_token=raw_refresh)

    def _normalize_email(self, email: str) -> str:
        return email.strip().lower()

    def _validate_allowed_email(self, email: str) -> None:
        domain = self._settings.auth_allowed_email_domain.strip().lower().lstrip("@")
        if not domain:
            return
        if not email.endswith(f"@{domain}"):
            raise ValidationError(f"Only @{domain} email addresses can access CVUM Knowledge Hub")

    def _is_super_admin(self, email: str) -> bool:
        return email == self._settings.auth_super_admin_email.strip().lower()

    def _initial_role(self, email: str) -> Role:
        return Role.ADMIN if self._is_super_admin(email) else Role.VIEWER

    async def _get_or_create_default_org(self) -> Organization:
        name = self._settings.auth_default_org_name.strip() or "CVUM"
        slug = name.lower().replace(" ", "-")[:80]
        org = await self._orgs.get_by_slug(slug)
        if org is None:
            org = Organization(name=name, slug=slug)
            self._orgs.add(org)
            await self._db.flush()
        return org
