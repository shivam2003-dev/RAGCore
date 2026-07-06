from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Self, cast
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.exceptions import AuthorizationError, NotFoundError, ProviderError, ValidationError
from embeddings.base import EmbeddingProvider
from ingestion.queue import IngestionQueue
from models import Document, DocumentStatus, KnowledgeBase, User
from repositories.audit import AuditLogRepository
from repositories.knowledge import DocumentRepository, KnowledgeBaseRepository
from services.document_service import DocumentService

JsonDict = dict[str, object]
JIRA_FIELDS = (
    "summary,status,issuetype,priority,labels,components,assignee,reporter,"
    "updated,created,description,project"
)


@dataclass(frozen=True, slots=True)
class JiraBoard:
    id: int
    name: str
    type: str
    url: str


@dataclass(frozen=True, slots=True)
class JiraIssue:
    id: str
    key: str
    title: str
    url: str
    issue_type: str | None
    status: str | None
    status_category: str | None
    status_category_key: str | None
    priority: str | None
    labels: list[str]
    components: list[str]
    assignee: str | None
    assignee_email: str | None
    assignee_account_id: str | None
    reporter: str | None
    reporter_email: str | None
    reporter_account_id: str | None
    created_at: str | None
    updated_at: str | None
    description: str
    project_key: str | None
    project_name: str | None


@dataclass(frozen=True, slots=True)
class SyncedJiraDocument:
    issue_id: str
    issue_key: str
    title: str
    url: str
    status: str | None
    updated_at: str | None
    document_id: uuid.UUID
    document_status: str
    action: str


@dataclass(frozen=True, slots=True)
class JiraSyncResult:
    knowledge_base_id: uuid.UUID
    knowledge_base_name: str
    project_key: str
    board_id: int
    board_name: str
    total_issues: int
    created: int
    updated: int
    skipped: int
    documents: list[SyncedJiraDocument]


class JiraClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = normalize_jira_base_url(settings.jira_base_url)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        token = jira_token(self._settings)
        if not token:
            raise ValidationError("Jira API token is not configured")

        mode = self._settings.jira_auth_mode.strip().lower()
        if mode not in {"auto", "basic", "bearer"}:
            raise ValidationError("JIRA_AUTH_MODE must be auto, basic, or bearer")

        auth: httpx.Auth | None = None
        headers = {"Accept": "application/json", "User-Agent": "kimbal-knowledge-hub/0.1"}
        email = jira_email(self._settings)
        if mode == "basic" or (mode == "auto" and email):
            if not email:
                raise ValidationError("JIRA_EMAIL or CONFLUENCE_EMAIL is required for Jira basic auth")
            auth = httpx.BasicAuth(email, token)
        else:
            headers["Authorization"] = f"Bearer {token}"

        self._client = httpx.AsyncClient(
            base_url=f"{self._base_url}/",
            auth=auth,
            headers=headers,
            timeout=self._settings.jira_request_timeout_seconds,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def get_board(self, board_id: int) -> JiraBoard:
        payload = await self._get(f"rest/agile/1.0/board/{board_id}")
        board_id_value = _int(payload.get("id"))
        if board_id_value is None:
            raise ProviderError("Jira board response is missing id")
        return JiraBoard(
            id=board_id_value,
            name=_str(payload.get("name")) or f"Board {board_id_value}",
            type=_str(payload.get("type")) or "unknown",
            url=f"{self._base_url}/jira/software/c/projects/{self._settings.jira_project_key}/boards/{board_id_value}",
        )

    async def iter_board_issues(self, board_id: int, max_issues: int | None = None) -> AsyncIterator[JiraIssue]:
        limit = max(1, min(self._settings.jira_issue_limit, 100))
        if max_issues is not None:
            limit = min(limit, max(1, max_issues))
        path = f"rest/software/1.0/board/{board_id}/issue"
        params: dict[str, str | int] = {
            "maxResults": limit,
            "fields": JIRA_FIELDS,
        }
        if self._settings.jira_project_key.strip():
            params["jql"] = f"project = {self._settings.jira_project_key.strip()}"
        fetched = 0

        while max_issues is None or fetched < max_issues:
            payload = await self._get(path, params=params)
            issues = _list_of_dicts(payload.get("issues"))
            for row in issues:
                yield self._parse_issue(row)
                fetched += 1
                if max_issues is not None and fetched >= max_issues:
                    return

            token = _str(payload.get("nextPageToken"))
            if token:
                params = {
                    "maxResults": limit,
                    "nextPageToken": token,
                    "fields": JIRA_FIELDS,
                }
                if self._settings.jira_project_key.strip():
                    params["jql"] = f"project = {self._settings.jira_project_key.strip()}"
                continue

            start = _int(payload.get("startAt"))
            total = _int(payload.get("total"))
            max_results = _int(payload.get("maxResults")) or limit
            if start is not None and total is not None and start + max_results < total:
                params = {
                    "maxResults": limit,
                    "startAt": start + max_results,
                    "fields": JIRA_FIELDS,
                }
                if self._settings.jira_project_key.strip():
                    params["jql"] = f"project = {self._settings.jira_project_key.strip()}"
                continue
            return

    async def iter_project_issues(self, project_key: str, max_issues: int | None = None) -> AsyncIterator[JiraIssue]:
        key = project_key.strip()
        if not key:
            raise ValidationError("JIRA_PROJECT_KEY is required for project issue sync")
        limit = max(1, min(self._settings.jira_issue_limit, 100))
        if max_issues is not None:
            limit = min(limit, max(1, max_issues))
        params: dict[str, str | int] = {
            "jql": f"project = {key} ORDER BY updated DESC",
            "maxResults": limit,
            "fields": JIRA_FIELDS,
        }
        fetched = 0
        start_at = 0
        use_legacy_search = False

        while max_issues is None or fetched < max_issues:
            if use_legacy_search:
                payload = await self._get("rest/api/3/search", params={**params, "startAt": start_at})
            else:
                try:
                    payload = await self._get("rest/api/3/search/jql", params=params)
                except NotFoundError:
                    use_legacy_search = True
                    payload = await self._get("rest/api/3/search", params={**params, "startAt": start_at})

            issues = _list_of_dicts(payload.get("issues"))
            for row in issues:
                yield self._parse_issue(row)
                fetched += 1
                if max_issues is not None and fetched >= max_issues:
                    return

            token = _str(payload.get("nextPageToken"))
            if token and not use_legacy_search:
                params = {
                    "jql": f"project = {key} ORDER BY updated DESC",
                    "maxResults": limit,
                    "nextPageToken": token,
                    "fields": JIRA_FIELDS,
                }
                continue

            start = _int(payload.get("startAt"))
            total = _int(payload.get("total"))
            max_results = _int(payload.get("maxResults")) or limit
            if start is not None and total is not None and start + max_results < total:
                start_at = start + max_results
                continue
            return

    async def _get(self, path: str, params: dict[str, str | int] | None = None) -> JsonDict:
        if self._client is None:
            raise RuntimeError("JiraClient must be used as an async context manager")
        try:
            response = await self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise ProviderError("Jira read request failed") from exc

        if response.status_code == 401:
            raise ProviderError("Jira authentication failed")
        if response.status_code == 403:
            raise AuthorizationError("Jira token does not have permission to view this board")
        if response.status_code == 404:
            raise NotFoundError("Jira board or issue resource was not found")
        if response.status_code >= 400:
            raise ProviderError(f"Jira read request failed with HTTP {response.status_code}")

        payload = response.json()
        if not isinstance(payload, dict):
            raise ProviderError("Jira returned an unexpected response shape")
        return cast(JsonDict, payload)

    def _parse_issue(self, row: JsonDict) -> JiraIssue:
        fields = _dict(row.get("fields"))
        project = _dict(fields.get("project"))
        status = _dict(fields.get("status"))
        status_category = _dict(status.get("statusCategory"))
        issue_type = _dict(fields.get("issuetype"))
        priority = _dict(fields.get("priority"))
        components = _list_of_dicts(fields.get("components"))
        assignee = _dict(fields.get("assignee"))
        reporter = _dict(fields.get("reporter"))
        key = _required_str(row, "key")
        issue_id = _required_str(row, "id")
        return JiraIssue(
            id=issue_id,
            key=key,
            title=_str(fields.get("summary")) or key,
            url=f"{self._base_url}/browse/{key}",
            issue_type=_str(issue_type.get("name")),
            status=_str(status.get("name")),
            status_category=_str(status_category.get("name")),
            status_category_key=_str(status_category.get("key")),
            priority=_str(priority.get("name")),
            labels=[str(label) for label in _list(fields.get("labels")) if isinstance(label, str)],
            components=[name for item in components if (name := _str(item.get("name")))],
            assignee=_str(assignee.get("displayName")),
            assignee_email=_str(assignee.get("emailAddress")),
            assignee_account_id=_str(assignee.get("accountId")),
            reporter=_str(reporter.get("displayName")),
            reporter_email=_str(reporter.get("emailAddress")),
            reporter_account_id=_str(reporter.get("accountId")),
            created_at=_str(fields.get("created")),
            updated_at=_str(fields.get("updated")),
            description=adf_to_text(fields.get("description")),
            project_key=_str(project.get("key")),
            project_name=_str(project.get("name")),
        )


class JiraSyncService:
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

    async def sync_board(
        self,
        *,
        user: User,
        kb_id: uuid.UUID | None = None,
        max_issues: int | None = None,
    ) -> JiraSyncResult:
        kb: KnowledgeBase | None = None
        try:
            self._validate_config()
            kb = await self._resolve_kb(user=user, kb_id=kb_id)
            limit = _sync_limit(max_issues, self._settings.jira_sync_max_issues)
            documents: list[SyncedJiraDocument] = []

            async with JiraClient(self._settings) as client:
                if self._settings.jira_board_id:
                    board = await client.get_board(self._settings.jira_board_id)
                    issues = client.iter_board_issues(board.id, max_issues=limit)
                else:
                    board = JiraBoard(
                        id=0,
                        name=f"{self._settings.jira_project_key.strip()} Project",
                        type="project",
                        url=f"{normalize_jira_base_url(self._settings.jira_base_url)}/jira/core/projects/{self._settings.jira_project_key.strip()}/board",
                    )
                    issues = client.iter_project_issues(self._settings.jira_project_key, max_issues=limit)

                async for issue in issues:
                    if not _jira_issue_allowed(issue, self._settings):
                        continue
                    documents.append(await self._sync_issue(user=user, kb=kb, board=board, issue=issue))
        except Exception as exc:
            await self._db.rollback()
            self._audit.record(
                action="jira.sync",
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
            action="jira.sync",
            resource_type="knowledge_base",
            resource_id=str(kb.id),
            org_id=user.organization_id,
            actor_id=user.id,
            detail=f"{created} created, {updated} updated, {skipped} skipped from {board.name}",
        )
        await self._db.commit()
        return JiraSyncResult(
            knowledge_base_id=kb.id,
            knowledge_base_name=kb.name,
            project_key=self._settings.jira_project_key,
            board_id=board.id,
            board_name=board.name,
            total_issues=len(documents),
            created=created,
            updated=updated,
            skipped=skipped,
            documents=documents,
        )

    async def _sync_issue(
        self,
        *,
        user: User,
        kb: KnowledgeBase,
        board: JiraBoard,
        issue: JiraIssue,
    ) -> SyncedJiraDocument:
        existing = await self._docs.get_by_metadata_value(kb.id, "jira_issue_id", issue.id)
        metadata = _issue_metadata(board=board, issue=issue)
        if existing is not None and _is_current(existing, metadata):
            if (existing.doc_metadata or {}) != metadata:
                await self._docs.update_metadata(existing.id, metadata)
            await self._docs.soft_delete_metadata_duplicates(
                kb.id, "jira_issue_id", issue.id, existing.id
            )
            return SyncedJiraDocument(
                issue_id=issue.id,
                issue_key=issue.key,
                title=issue.title,
                url=issue.url,
                status=issue.status,
                updated_at=issue.updated_at,
                document_id=existing.id,
                document_status=existing.status.value,
                action="skipped",
            )

        content = _render_issue_markdown(board=board, issue=issue).encode("utf-8")
        doc = await self._document_service.create_from_bytes(
            user=user,
            kb_id=kb.id,
            filename=_issue_filename(issue),
            content=content,
            existing_document_id=existing.id if existing else None,
            title=f"{issue.key}: {issue.title}",
            metadata=metadata,
            audit_action="jira.issue.sync",
        )
        await self._docs.soft_delete_metadata_duplicates(kb.id, "jira_issue_id", issue.id, doc.id)
        return SyncedJiraDocument(
            issue_id=issue.id,
            issue_key=issue.key,
            title=issue.title,
            url=issue.url,
            status=issue.status,
            updated_at=issue.updated_at,
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
            if kb.name == self._settings.jira_default_kb_name
        ]
        if existing:
            return existing[0]

        kb = KnowledgeBase(
            organization_id=user.organization_id,
            name=self._settings.jira_default_kb_name,
            description=f"Read-only Jira sync for board {self._settings.jira_board_id}.",
            embedding_model=self._settings.embedding_model,
            embedding_dimensions=self._settings.embedding_dimensions,
        )
        self._kbs.add(kb)
        await self._db.commit()
        return kb

    def _validate_config(self) -> None:
        if not self._settings.jira_base_url.strip():
            raise ValidationError("JIRA_BASE_URL is not configured")
        if not self._settings.jira_board_id and not self._settings.jira_project_key.strip():
            raise ValidationError("JIRA_BOARD_ID or JIRA_PROJECT_KEY is not configured")
        if not jira_token(self._settings):
            raise ValidationError("JIRA_API_TOKEN or CONFLUENCE_API_TOKEN is not configured")
        if self._settings.jira_auth_mode.strip().lower() == "basic" and not jira_email(self._settings):
            raise ValidationError("JIRA_EMAIL or CONFLUENCE_EMAIL is required when JIRA_AUTH_MODE=basic")


def jira_config_status(settings: Settings) -> JsonDict:
    base_url = settings.jira_base_url.strip()
    token = jira_token(settings)
    email = jira_email(settings)
    mode = settings.jira_auth_mode.strip().lower()
    using_fallback = bool(token and not settings.jira_api_token.strip())
    return {
        "configured": bool(
            base_url
            and (settings.jira_board_id or settings.jira_project_key.strip())
            and token
            and (email or mode != "basic")
        ),
        "read_only": True,
        "base_url": normalize_jira_base_url(base_url) if base_url else None,
        "project_key": settings.jira_project_key,
        "board_id": settings.jira_board_id,
        "default_kb_name": settings.jira_default_kb_name,
        "auth_mode": mode,
        "email_configured": bool(email),
        "token_configured": bool(token),
        "using_atlassian_fallback_credentials": using_fallback,
        "requires_email": mode == "basic" or (mode == "auto" and bool(token) and not email),
    }


def _sync_limit(requested: int | None, configured: int) -> int | None:
    if requested is not None:
        return requested
    return configured if configured > 0 else None


def normalize_jira_base_url(raw_url: str) -> str:
    raw = raw_url.strip().rstrip("/")
    if not raw:
        raise ValidationError("JIRA_BASE_URL is not configured")
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        raise ValidationError("JIRA_BASE_URL must be an absolute URL")
    return f"{parsed.scheme}://{parsed.netloc}"


def jira_token(settings: Settings) -> str:
    return settings.jira_api_token.strip() or settings.confluence_api_token.strip()


def jira_email(settings: Settings) -> str:
    return settings.jira_email.strip() or settings.confluence_email.strip()


def adf_to_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        node_type = value.get("type")
        if node_type == "text":
            return _str(value.get("text")) or ""
        pieces = [adf_to_text(child) for child in _list(value.get("content"))]
        text = "".join(pieces) if node_type in {"paragraph", "heading"} else "\n".join(p for p in pieces if p)
        if node_type in {"paragraph", "heading", "listItem"} and text:
            return f"{text}\n"
        return text
    if isinstance(value, list):
        return "\n".join(adf_to_text(item) for item in value)
    return ""


def _render_issue_markdown(*, board: JiraBoard, issue: JiraIssue) -> str:
    fields = [
        ("Issue key", issue.key),
        ("URL", issue.url),
        ("Board", f"{board.name} ({board.id})"),
        ("Project", f"{issue.project_name or 'Unknown'} ({issue.project_key or 'unknown'})"),
        ("Type", issue.issue_type),
        ("Status", issue.status),
        ("Status category", issue.status_category),
        ("Priority", issue.priority),
        ("Labels", ", ".join(issue.labels) if issue.labels else None),
        ("Components", ", ".join(issue.components) if issue.components else None),
        ("Assignee", issue.assignee),
        ("Assignee email", issue.assignee_email),
        ("Assignee account id", issue.assignee_account_id),
        ("Reporter", issue.reporter),
        ("Reporter email", issue.reporter_email),
        ("Created", issue.created_at),
        ("Updated", issue.updated_at),
    ]
    lines = [f"# {issue.key}: {issue.title}", ""]
    lines.extend(f"- **{label}:** {value}" for label, value in fields if value)
    lines.extend(["", "## Description", "", issue.description.strip() or "No description."])
    return "\n".join(lines).strip() + "\n"


def _issue_metadata(*, board: JiraBoard, issue: JiraIssue) -> dict[str, object]:
    rendered = _render_issue_markdown(board=board, issue=issue).encode("utf-8")
    project = issue.project_key or ""
    owner = issue.assignee_email or issue.assignee or issue.assignee_account_id
    return {
        "source": "jira",
        "source_type": "jira",
        "source_family": "jira",
        "source_system": "jira",
        "source_id": issue.key,
        "source_title": f"{issue.key}: {issue.title}",
        "source_url": issue.url,
        "source_space": project,
        "source_version": issue.updated_at,
        "source_updated_at": issue.updated_at,
        "project": project,
        "project_key": issue.project_key,
        "project_name": issue.project_name,
        "issue_id": issue.id,
        "issue_key": issue.key,
        "title": f"{issue.key}: {issue.title}",
        "url": issue.url,
        "created_at": issue.created_at,
        "updated_at": issue.updated_at,
        "status": issue.status,
        "labels": issue.labels,
        "components": issue.components,
        "owner": owner,
        "acl": "connector-visible",
        "connector": "jira",
        "connector_scope": project or str(board.id),
        "connector_sync_id": f"jira:{project or 'unknown'}:{issue.key}:{issue.updated_at or issue.id}",
        "permission_state": "visible",
        "priority": issue.priority,
        "issue_type": issue.issue_type,
        "jira_board_id": board.id,
        "jira_board_name": board.name,
        "jira_project_key": issue.project_key,
        "jira_project_name": issue.project_name,
        "jira_issue_id": issue.id,
        "jira_issue_key": issue.key,
        "jira_issue_url": issue.url,
        "jira_issue_status": issue.status,
        "jira_issue_status_category": issue.status_category,
        "jira_issue_status_category_key": issue.status_category_key,
        "jira_issue_type": issue.issue_type,
        "jira_labels": issue.labels,
        "jira_components": issue.components,
        "jira_assignee": issue.assignee,
        "jira_assignee_email": issue.assignee_email,
        "jira_assignee_account_id": issue.assignee_account_id,
        "jira_reporter": issue.reporter,
        "jira_reporter_email": issue.reporter_email,
        "jira_reporter_account_id": issue.reporter_account_id,
        "jira_issue_updated_at": issue.updated_at,
        "source_sha256": hashlib.sha256(rendered).hexdigest(),
    }


def _jira_issue_allowed(issue: JiraIssue, settings: Settings) -> bool:
    status = (issue.status or "").lower()
    labels = {label.lower() for label in issue.labels}
    include_statuses = _csv_set(settings.jira_include_statuses)
    exclude_statuses = _csv_set(settings.jira_exclude_statuses)
    include_labels = _csv_set(settings.jira_include_labels)
    exclude_labels = _csv_set(settings.jira_exclude_labels)
    if include_statuses and status not in include_statuses:
        return False
    if exclude_statuses and status in exclude_statuses:
        return False
    if include_labels and not (labels & include_labels):
        return False
    if exclude_labels and labels & exclude_labels:
        return False
    return True


def _csv_set(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _issue_filename(issue: JiraIssue) -> str:
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "-", f"{issue.key}-{issue.title}").strip(" .-")
    stem = re.sub(r"\s+", "-", stem)[:100] or issue.key
    return f"{stem}.md"


def _is_current(existing: Document | None, metadata: dict[str, object]) -> bool:
    if existing is None or existing.status != DocumentStatus.READY:
        return False
    existing_metadata = existing.doc_metadata or {}
    return existing_metadata.get("source_sha256") == metadata.get("source_sha256")


def _dict(value: object) -> JsonDict:
    return cast(JsonDict, value) if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _list_of_dicts(value: object) -> list[JsonDict]:
    if not isinstance(value, list):
        return []
    return [cast(JsonDict, item) for item in value if isinstance(item, dict)]


def _required_str(row: JsonDict, key: str) -> str:
    value = _str(row.get(key))
    if not value:
        raise ProviderError(f"Jira response is missing {key}")
    return value


def _str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int(value: object) -> int | None:
    return value if isinstance(value, int) else None
