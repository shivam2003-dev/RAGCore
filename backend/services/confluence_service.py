from __future__ import annotations

import hashlib
import html
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Self, cast
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.exceptions import AuthorizationError, NotFoundError, ProviderError, ValidationError
from embeddings.base import EmbeddingProvider
from ingestion.queue import IngestionQueue
from knowledgebase.source_metadata import normalize_source_metadata
from models import Document, DocumentStatus, KnowledgeBase, User
from repositories.audit import AuditLogRepository
from repositories.knowledge import DocumentRepository, KnowledgeBaseRepository
from services.document_service import DocumentService


@dataclass(frozen=True, slots=True)
class ConfluenceSpace:
    id: str
    key: str
    name: str
    url: str


@dataclass(frozen=True, slots=True)
class ConfluencePage:
    id: str
    title: str
    url: str
    storage_html: str
    version_number: int | None
    version_created_at: str | None


@dataclass(frozen=True, slots=True)
class SyncedConfluenceDocument:
    page_id: str
    title: str
    url: str
    version: int | None
    document_id: uuid.UUID
    document_status: str
    action: str


@dataclass(frozen=True, slots=True)
class ConfluenceSyncResult:
    knowledge_base_id: uuid.UUID
    knowledge_base_name: str
    space_key: str
    space_name: str
    total_pages: int
    created: int
    updated: int
    skipped: int
    documents: list[SyncedConfluenceDocument]


JsonDict = dict[str, object]
CHUNK_STRATEGY_VERSION = "confluence-heading-context-v2"


class ConfluenceClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._wiki_root = normalize_confluence_wiki_root(settings.confluence_base_url)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        token = self._settings.confluence_api_token.strip()
        if not token:
            raise ValidationError("Confluence API token is not configured")

        mode = self._settings.confluence_auth_mode.strip().lower()
        if mode not in {"auto", "basic", "bearer"}:
            raise ValidationError("CONFLUENCE_AUTH_MODE must be auto, basic, or bearer")

        auth: httpx.Auth | None = None
        headers = {
            "Accept": "application/json",
            "User-Agent": "cvum-knowledge-hub/0.1",
        }
        email = self._settings.confluence_email.strip()
        if mode == "basic" or (mode == "auto" and email):
            if not email:
                raise ValidationError("CONFLUENCE_EMAIL is required for Confluence basic auth")
            auth = httpx.BasicAuth(email, token)
        else:
            headers["Authorization"] = f"Bearer {token}"

        self._client = httpx.AsyncClient(
            base_url=f"{self._wiki_root}/",
            auth=auth,
            headers=headers,
            timeout=self._settings.confluence_request_timeout_seconds,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def get_space_by_key(self, space_key: str) -> ConfluenceSpace:
        try:
            return await self._get_space_by_key_v2(space_key)
        except NotFoundError:
            return await self._get_space_by_key_v1(space_key)

    async def _get_space_by_key_v2(self, space_key: str) -> ConfluenceSpace:
        payload = await self._get("api/v2/spaces", params={"keys": space_key, "limit": 1})
        rows = _list_of_dicts(payload.get("results"))
        if not rows:
            raise NotFoundError(f"Confluence space {space_key} was not found by Cloud v2 API")
        row = rows[0]
        links = _dict(row.get("_links"))
        return ConfluenceSpace(
            id=_required_str(row, "id"),
            key=_required_str(row, "key"),
            name=_str(row.get("name")) or space_key,
            url=self._absolute_url(_str(links.get("webui")) or f"/spaces/{space_key}/overview"),
        )

    async def _get_space_by_key_v1(self, space_key: str) -> ConfluenceSpace:
        payload = await self._get(f"rest/api/space/{space_key}")
        links = _dict(payload.get("_links"))
        return ConfluenceSpace(
            id=str(_required_str_or_int(payload, "id")),
            key=_required_str(payload, "key"),
            name=_str(payload.get("name")) or space_key,
            url=self._absolute_url(_str(links.get("webui")) or f"/spaces/{space_key}/overview"),
        )

    async def iter_pages(self, space: ConfluenceSpace, max_pages: int | None = None) -> AsyncIterator[ConfluencePage]:
        seen: set[str] = set()
        yielded = 0
        try:
            async for page in self._iter_pages_v2(space, max_pages=max_pages):
                if page.id in seen:
                    continue
                seen.add(page.id)
                yield page
                yielded += 1
                if max_pages is not None and yielded >= max_pages:
                    return
        except NotFoundError:
            async for page in self._iter_pages_v1(space, max_pages=max_pages):
                if page.id in seen:
                    continue
                seen.add(page.id)
                yield page
                yielded += 1
                if max_pages is not None and yielded >= max_pages:
                    return

    async def _iter_pages_v2(
        self, space: ConfluenceSpace, max_pages: int | None = None
    ) -> AsyncIterator[ConfluencePage]:
        page_limit = max(1, min(self._settings.confluence_page_limit, 100))
        if max_pages is not None:
            page_limit = min(page_limit, max(1, max_pages))
        path_or_url = f"api/v2/spaces/{space.id}/pages"
        params: dict[str, str | int] | None = {
            "limit": page_limit,
            "body-format": "storage",
            "status": "current",
        }
        fetched = 0

        while max_pages is None or fetched < max_pages:
            payload = await self._get(path_or_url, params=params)
            rows = _list_of_dicts(payload.get("results"))
            for row in rows:
                page = self._parse_page(row)
                if not page.storage_html:
                    page = await self.get_page_by_id(page.id)
                yield page
                fetched += 1
                if max_pages is not None and fetched >= max_pages:
                    return

            next_url = _next_link(payload)
            if next_url:
                path_or_url = next_url
                params = None
                continue

            cursor = _next_cursor(payload)
            if cursor:
                path_or_url = f"api/v2/spaces/{space.id}/pages"
                params = {
                    "limit": page_limit,
                    "body-format": "storage",
                    "status": "current",
                    "cursor": cursor,
                }
                continue
            return

    async def _iter_pages_v1(
        self, space: ConfluenceSpace, max_pages: int | None = None
    ) -> AsyncIterator[ConfluencePage]:
        page_limit = max(1, min(self._settings.confluence_page_limit, 100))
        if max_pages is not None:
            page_limit = min(page_limit, max(1, max_pages))
        path_or_url = "rest/api/content"
        params: dict[str, str | int] | None = {
            "spaceKey": space.key,
            "type": "page",
            "status": "current",
            "limit": page_limit,
            "expand": "body.storage,version",
        }
        fetched = 0

        while max_pages is None or fetched < max_pages:
            payload = await self._get(path_or_url, params=params)
            rows = _list_of_dicts(payload.get("results"))
            for row in rows:
                yield self._parse_v1_page(row)
                fetched += 1
                if max_pages is not None and fetched >= max_pages:
                    return

            next_url = _next_link(payload)
            if not next_url:
                return
            path_or_url = next_url
            params = None

    async def get_page_by_id(self, page_id: str) -> ConfluencePage:
        try:
            payload = await self._get(f"api/v2/pages/{page_id}", params={"body-format": "storage"})
            return self._parse_page(payload)
        except NotFoundError:
            payload = await self._get(f"rest/api/content/{page_id}", params={"expand": "body.storage,version"})
            return self._parse_v1_page(payload)

    async def _get(self, path_or_url: str, params: dict[str, str | int] | None = None) -> JsonDict:
        if self._client is None:
            raise RuntimeError("ConfluenceClient must be used as an async context manager")
        try:
            response = await self._client.get(path_or_url, params=params)
        except httpx.HTTPError as exc:
            raise ProviderError("Confluence read request failed") from exc

        if response.status_code == 401:
            raise ProviderError(
                "Confluence authentication failed. Atlassian Cloud API tokens usually require "
                "CONFLUENCE_EMAIL plus CONFLUENCE_API_TOKEN."
            )
        if response.status_code == 403:
            raise AuthorizationError("Confluence token does not have permission to view this space")
        if response.status_code == 404:
            raise NotFoundError("Confluence resource was not found")
        if response.status_code >= 400:
            raise ProviderError(f"Confluence read request failed with HTTP {response.status_code}")

        payload = response.json()
        if not isinstance(payload, dict):
            raise ProviderError("Confluence returned an unexpected response shape")
        return cast(JsonDict, payload)

    def _parse_page(self, row: JsonDict) -> ConfluencePage:
        links = _dict(row.get("_links"))
        body = _dict(row.get("body"))
        storage = _dict(body.get("storage"))
        version = _dict(row.get("version"))
        return ConfluencePage(
            id=_required_str(row, "id"),
            title=_str(row.get("title")) or "Untitled Confluence page",
            url=self._absolute_url(_str(links.get("webui")) or f"/pages/{_required_str(row, 'id')}"),
            storage_html=_str(storage.get("value")) or "",
            version_number=_int(version.get("number")),
            version_created_at=_str(version.get("createdAt")),
        )

    def _parse_v1_page(self, row: JsonDict) -> ConfluencePage:
        links = _dict(row.get("_links"))
        body = _dict(row.get("body"))
        storage = _dict(body.get("storage"))
        version = _dict(row.get("version"))
        return ConfluencePage(
            id=_required_str(row, "id"),
            title=_str(row.get("title")) or "Untitled Confluence page",
            url=self._absolute_url(_str(links.get("webui")) or f"/pages/{_required_str(row, 'id')}"),
            storage_html=_str(storage.get("value")) or "",
            version_number=_int(version.get("number")),
            version_created_at=_str(version.get("createdAt")) or _str(version.get("when")),
        )

    def _absolute_url(self, link: str) -> str:
        if link.startswith("http://") or link.startswith("https://"):
            return link
        parsed = urlparse(self._wiki_root)
        if link.startswith("/wiki"):
            return f"{parsed.scheme}://{parsed.netloc}{link}"
        if link.startswith("/"):
            return f"{self._wiki_root}{link}"
        return urljoin(f"{self._wiki_root}/", link)


class ConfluenceSyncService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        settings: Settings,
        embedder: EmbeddingProvider,
        queue: IngestionQueue,
    ) -> None:
        self._db = db
        self._settings = settings
        self._docs = DocumentRepository(db)
        self._kbs = KnowledgeBaseRepository(db)
        self._audit = AuditLogRepository(db)
        self._document_service = DocumentService(
            db=db, settings=settings, embedder=embedder, queue=queue
        )

    async def sync_space(
        self,
        *,
        user: User,
        kb_id: uuid.UUID | None = None,
        max_pages: int | None = None,
    ) -> ConfluenceSyncResult:
        kb: KnowledgeBase | None = None
        try:
            self._validate_config()
            kb = await self._resolve_kb(user=user, kb_id=kb_id)
            limit = _sync_limit(max_pages, self._settings.confluence_sync_max_pages)
            documents: list[SyncedConfluenceDocument] = []

            async with ConfluenceClient(self._settings) as client:
                space = await client.get_space_by_key(self._settings.confluence_space_key)
                async for page in client.iter_pages(space, max_pages=limit):
                    if not _confluence_page_allowed(page, self._settings):
                        continue
                    documents.append(await self._sync_page(user=user, kb=kb, space=space, page=page))
        except Exception as exc:
            await self._db.rollback()
            self._audit.record(
                action="confluence.sync",
                resource_type="knowledge_base",
                resource_id=str(kb.id) if kb else None,
                org_id=user.organization_id,
                actor_id=user.id,
                detail=f"0 created, 0 updated, 0 skipped, 1 failed: {type(exc).__name__}: {str(exc)[:180]}",
            )
            await self._db.commit()
            raise

        created = sum(1 for doc in documents if doc.action == "created")
        updated = sum(1 for doc in documents if doc.action == "updated")
        skipped = sum(1 for doc in documents if doc.action == "skipped")
        self._audit.record(
            action="confluence.sync",
            resource_type="knowledge_base",
            resource_id=str(kb.id),
            org_id=user.organization_id,
            actor_id=user.id,
            detail=f"{created} created, {updated} updated, {skipped} skipped from {space.key}",
        )
        await self._db.commit()
        return ConfluenceSyncResult(
            knowledge_base_id=kb.id,
            knowledge_base_name=kb.name,
            space_key=space.key,
            space_name=space.name,
            total_pages=len(documents),
            created=created,
            updated=updated,
            skipped=skipped,
            documents=documents,
        )

    async def _sync_page(
        self,
        *,
        user: User,
        kb: KnowledgeBase,
        space: ConfluenceSpace,
        page: ConfluencePage,
    ) -> SyncedConfluenceDocument:
        existing = await self._docs.get_by_metadata_value(kb.id, "confluence_page_id", page.id)
        metadata = _page_metadata(space=space, page=page)

        if existing is not None and _is_current(existing, page):
            if (existing.doc_metadata or {}) != metadata:
                await self._docs.update_metadata(existing.id, metadata)
            await self._docs.soft_delete_metadata_duplicates(
                kb.id, "confluence_page_id", page.id, existing.id
            )
            return SyncedConfluenceDocument(
                page_id=page.id,
                title=page.title,
                url=page.url,
                version=page.version_number,
                document_id=existing.id,
                document_status=existing.status.value,
                action="skipped",
            )

        content = _render_page_html(space=space, page=page).encode("utf-8")
        filename = _page_filename(page)
        doc = await self._document_service.create_from_bytes(
            user=user,
            kb_id=kb.id,
            filename=filename,
            content=content,
            existing_document_id=existing.id if existing else None,
            title=page.title,
            metadata=metadata,
            audit_action="confluence.page.sync",
        )
        await self._docs.soft_delete_metadata_duplicates(kb.id, "confluence_page_id", page.id, doc.id)
        return SyncedConfluenceDocument(
            page_id=page.id,
            title=page.title,
            url=page.url,
            version=page.version_number,
            document_id=doc.id,
            document_status=doc.status.value,
            action="updated" if existing else "created",
        )

    async def _resolve_kb(self, *, user: User, kb_id: uuid.UUID | None) -> KnowledgeBase:
        if kb_id is not None:
            kb = await self._kbs.get(kb_id, user.organization_id)
            if kb is None:
                raise NotFoundError("Knowledge base not found")
            return kb

        existing = [
            kb
            for kb in await self._kbs.list_by_org(user.organization_id)
            if kb.name == self._settings.confluence_default_kb_name
        ]
        if existing:
            return existing[0]

        kb = KnowledgeBase(
            organization_id=user.organization_id,
            name=self._settings.confluence_default_kb_name,
            description=f"Read-only Confluence sync for {self._settings.confluence_space_key}.",
            embedding_model=self._settings.embedding_model,
            embedding_dimensions=self._settings.embedding_dimensions,
        )
        self._kbs.add(kb)
        await self._db.commit()
        return kb

    def _validate_config(self) -> None:
        if not self._settings.confluence_base_url.strip():
            raise ValidationError("CONFLUENCE_BASE_URL is not configured")
        if not self._settings.confluence_space_key.strip():
            raise ValidationError("CONFLUENCE_SPACE_KEY is not configured")
        if not self._settings.confluence_api_token.strip():
            raise ValidationError("CONFLUENCE_API_TOKEN is not configured")
        if (
            self._settings.confluence_auth_mode.strip().lower() == "basic"
            and not self._settings.confluence_email.strip()
        ):
            raise ValidationError("CONFLUENCE_EMAIL is required when CONFLUENCE_AUTH_MODE=basic")


def confluence_config_status(settings: Settings) -> JsonDict:
    base_url = settings.confluence_base_url.strip()
    token = settings.confluence_api_token.strip()
    email = settings.confluence_email.strip()
    mode = settings.confluence_auth_mode.strip().lower()
    return {
        "configured": bool(base_url and settings.confluence_space_key.strip() and token and (email or mode != "basic")),
        "read_only": True,
        "base_url": normalize_confluence_wiki_root(base_url) if base_url else None,
        "space_key": settings.confluence_space_key,
        "default_kb_name": settings.confluence_default_kb_name,
        "auth_mode": mode,
        "email_configured": bool(email),
        "token_configured": bool(token),
        "requires_email": mode == "basic" or (mode == "auto" and bool(token) and not email),
    }


def _sync_limit(requested: int | None, configured: int) -> int | None:
    if requested is not None:
        return requested
    return configured if configured > 0 else None


def normalize_confluence_wiki_root(raw_url: str) -> str:
    raw = raw_url.strip().rstrip("/")
    if not raw:
        raise ValidationError("CONFLUENCE_BASE_URL is not configured")
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        raise ValidationError("CONFLUENCE_BASE_URL must be an absolute URL")
    parts = [part for part in parsed.path.split("/") if part]
    wiki_path = "/" + "/".join(parts[: parts.index("wiki") + 1]) if "wiki" in parts else "/wiki"
    return f"{parsed.scheme}://{parsed.netloc}{wiki_path}"


def _render_page_html(*, space: ConfluenceSpace, page: ConfluencePage) -> str:
    title = html.escape(page.title)
    source_url = html.escape(page.url)
    return (
        "<!doctype html><html><head>"
        f"<meta charset=\"utf-8\"><title>{title}</title>"
        f"<meta name=\"confluence-page-id\" content=\"{html.escape(page.id)}\">"
        f"<meta name=\"confluence-space-key\" content=\"{html.escape(space.key)}\">"
        f"<meta name=\"source-url\" content=\"{source_url}\">"
        "</head><body>"
        f"<h1>{title}</h1>"
        f"<p>Source: <a href=\"{source_url}\">{source_url}</a></p>"
        f"<p>Confluence space: {html.escape(space.name)} ({html.escape(space.key)})</p>"
        f"<main>{page.storage_html}</main>"
        "</body></html>"
    )


def _page_metadata(*, space: ConfluenceSpace, page: ConfluencePage) -> dict[str, object]:
    rendered = _render_page_html(space=space, page=page).encode("utf-8")
    updated_at = page.version_created_at
    metadata: dict[str, object] = {
        "source": "confluence",
        "source_type": "confluence",
        "source_family": "confluence",
        "source_system": "confluence",
        "source_id": page.id,
        "source_title": page.title,
        "source_url": page.url,
        "source_space": space.key,
        "source_version": page.version_number,
        "source_updated_at": updated_at,
        "space": space.key,
        "space_key": space.key,
        "space_name": space.name,
        "page_id": page.id,
        "title": page.title,
        "url": page.url,
        "updated_at": updated_at,
        "status": "current",
        "labels": [],
        "owner": space.name,
        "acl": "connector-visible",
        "connector": "confluence",
        "connector_scope": space.key,
        "connector_sync_id": f"confluence:{space.key}:{page.id}:{page.version_number or 'unknown'}",
        "chunk_strategy_version": CHUNK_STRATEGY_VERSION,
        "permission_state": "visible",
        "confluence_space_id": space.id,
        "confluence_space_key": space.key,
        "confluence_space_name": space.name,
        "confluence_page_id": page.id,
        "confluence_page_url": page.url,
        "confluence_page_title": page.title,
        "confluence_version": page.version_number,
        "confluence_version_created_at": page.version_created_at,
        "source_sha256": hashlib.sha256(rendered).hexdigest(),
    }
    return normalize_source_metadata(
        metadata,
        source_type="confluence",
        title=page.title,
        source_id=page.id,
        source_url=page.url,
        source_space=space.key,
        source_version=page.version_number,
        updated_at=updated_at,
        status="current",
        owner=space.name,
        acl="connector-visible",
        connector="confluence",
        connector_scope=space.key,
        source_sha256=str(metadata["source_sha256"]),
    )


def _confluence_page_allowed(page: ConfluencePage, settings: Settings) -> bool:
    title = page.title
    include = settings.confluence_include_title_pattern.strip()
    exclude = settings.confluence_exclude_title_pattern.strip()
    if include and not re.search(include, title, flags=re.IGNORECASE):
        return False
    return not (exclude and re.search(exclude, title, flags=re.IGNORECASE))


def _page_filename(page: ConfluencePage) -> str:
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "-", page.title).strip(" .-")
    stem = re.sub(r"\s+", "-", stem)[:90] or "confluence-page"
    return f"{stem}-{page.id}.html"


def _is_current(existing: Document | None, page: ConfluencePage) -> bool:
    if existing is None or existing.status != DocumentStatus.READY:
        return False
    metadata = existing.doc_metadata or {}
    return (
        metadata.get("confluence_version") == page.version_number
        and metadata.get("chunk_strategy_version") == CHUNK_STRATEGY_VERSION
    )


def _dict(value: object) -> JsonDict:
    return cast(JsonDict, value) if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[JsonDict]:
    if not isinstance(value, list):
        return []
    return [cast(JsonDict, item) for item in value if isinstance(item, dict)]


def _required_str(row: JsonDict, key: str) -> str:
    value = _str(row.get(key))
    if not value:
        raise ProviderError(f"Confluence response is missing {key}")
    return value


def _required_str_or_int(row: JsonDict, key: str) -> str | int:
    value = row.get(key)
    if isinstance(value, str) and value:
        return value
    if isinstance(value, int):
        return value
    raise ProviderError(f"Confluence response is missing {key}")


def _str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _next_link(payload: JsonDict) -> str | None:
    links = _dict(payload.get("_links"))
    return _str(links.get("next"))


def _next_cursor(payload: JsonDict) -> str | None:
    meta = _dict(payload.get("meta"))
    if meta.get("hasMore") is True:
        return _str(meta.get("cursor"))
    return None
