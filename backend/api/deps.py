"""Request-scoped dependency wiring."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import BackgroundTasks, Depends, Security
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from redis.asyncio import Redis, from_url
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.exceptions import AuthenticationError, AuthorizationError
from core.security import decode_access_token
from database.session import get_db
from embeddings.base import EmbeddingProvider
from embeddings.factory import build_embedding_provider
from ingestion.queue import BackgroundTasksQueue
from llm.base import LLMProvider
from llm.factory import build_llm_provider
from models import Role, User
from repositories.chunks import ChunkSearchRepository
from repositories.users import UserRepository
from retrieval.pipeline import RetrievalPipeline
from services.auth_service import AuthService
from services.chat_service import ChatService
from services.confluence_service import ConfluenceSyncService
from services.document_service import DocumentService
from services.jira_service import JiraSyncService
from services.web_search_service import WebSearchService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
api_key_scheme = APIKeyHeader(name="x-api-key", auto_error=False)

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = from_url(get_settings().redis_url, decode_responses=True)
    return _redis


async def get_redis_dep() -> AsyncIterator[Redis]:
    yield get_redis()


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[Redis, Depends(get_redis_dep)]


async def get_current_user(
    db: DbDep,
    settings: SettingsDep,
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
    api_key: Annotated[str | None, Security(api_key_scheme)] = None,
) -> User:
    if token:
        payload = decode_access_token(token)
        user = await UserRepository(db).get(uuid.UUID(payload["sub"]))
        if user is None or not user.is_active:
            raise AuthenticationError("User not found or inactive")
        return user
    if api_key:
        user = await AuthService(db, settings).resolve_api_key(api_key)
        if user is None or not user.is_active:
            raise AuthenticationError("Invalid API key")
        return user
    raise AuthenticationError("Not authenticated")


CurrentUser = Annotated[User, Depends(get_current_user)]

_ROLE_ORDER = {Role.VIEWER: 0, Role.EDITOR: 1, Role.ADMIN: 2}


def require_role(minimum: Role):  # type: ignore[no-untyped-def]
    async def checker(user: CurrentUser) -> User:
        if _ROLE_ORDER[user.role] < _ROLE_ORDER[minimum]:
            raise AuthorizationError(f"Requires {minimum.value} role")
        return user

    return Depends(checker)


def get_embedder(settings: SettingsDep, redis: RedisDep) -> EmbeddingProvider:
    return build_embedding_provider(settings, redis)


def get_llm(settings: SettingsDep) -> LLMProvider:
    return build_llm_provider(settings)


EmbedderDep = Annotated[EmbeddingProvider, Depends(get_embedder)]
LLMDep = Annotated[LLMProvider, Depends(get_llm)]


def get_auth_service(db: DbDep, settings: SettingsDep) -> AuthService:
    return AuthService(db, settings)


def get_document_service(
    db: DbDep, settings: SettingsDep, embedder: EmbedderDep, background: BackgroundTasks
) -> DocumentService:
    return DocumentService(
        db=db, settings=settings, embedder=embedder, queue=BackgroundTasksQueue(background)
    )


def get_confluence_sync_service(
    db: DbDep, settings: SettingsDep, embedder: EmbedderDep, background: BackgroundTasks
) -> ConfluenceSyncService:
    return ConfluenceSyncService(
        db=db, settings=settings, embedder=embedder, queue=BackgroundTasksQueue(background)
    )


def get_jira_sync_service(
    db: DbDep, settings: SettingsDep, embedder: EmbedderDep, background: BackgroundTasks
) -> JiraSyncService:
    return JiraSyncService(
        db=db, settings=settings, embedder=embedder, queue=BackgroundTasksQueue(background)
    )


def get_web_search_service(db: DbDep, settings: SettingsDep, embedder: EmbedderDep) -> WebSearchService:
    return WebSearchService(db=db, settings=settings, embedder=embedder)


def get_retrieval_pipeline(
    db: DbDep, settings: SettingsDep, embedder: EmbedderDep
) -> RetrievalPipeline:
    return RetrievalPipeline(
        search_repo=ChunkSearchRepository(db), embedder=embedder, settings=settings
    )


def get_chat_service(
    db: DbDep,
    settings: SettingsDep,
    llm: LLMDep,
    web_search: Annotated[WebSearchService, Depends(get_web_search_service)],
    retrieval: Annotated[RetrievalPipeline, Depends(get_retrieval_pipeline)],
) -> ChatService:
    return ChatService(db=db, retrieval=retrieval, llm=llm, web_search=web_search, settings=settings)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]
ConfluenceSyncDep = Annotated[ConfluenceSyncService, Depends(get_confluence_sync_service)]
JiraSyncDep = Annotated[JiraSyncService, Depends(get_jira_sync_service)]
WebSearchDep = Annotated[WebSearchService, Depends(get_web_search_service)]
RetrievalDep = Annotated[RetrievalPipeline, Depends(get_retrieval_pipeline)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
