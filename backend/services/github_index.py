import fnmatch
import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from urllib.parse import quote

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.exceptions import ConflictError, NotFoundError, ValidationError
from database.base import utcnow
from ingestion.extractors.registry import SUPPORTED_SUFFIXES
from models import (
    AccessScope,
    ConnectorState,
    Document,
    DocumentStatus,
    GitHubFileState,
    GitHubRepositoryMapping,
    KnowledgeBase,
    ProjectSource,
    User,
)
from repositories.audit import AuditLogRepository
from repositories.connectors import ConnectorRepository
from repositories.knowledge import DocumentRepository, KnowledgeBaseRepository
from repositories.projects import ProjectAuthorizationRepository, ProjectRepository
from services.document_service import DocumentService
from services.github_client import GitHubPullRequest, GitHubReadClient, GitHubTreeEntry

_REPO_PART_RE = re.compile(r"^[A-Za-z0-9_.-]{1,255}$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
_CODE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
}
_TEXT_SUFFIXES = _CODE_SUFFIXES | {
    ".graphql",
    ".json",
    ".md",
    ".proto",
    ".rst",
    ".sql",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
_SPECIAL_TEXT_FILES = {"codeowners", "dockerfile", "makefile"}
_UPLOADED_REINDEX_AFTER = timedelta(seconds=30)
_PROCESSING_REINDEX_AFTER = timedelta(minutes=15)


@dataclass(slots=True, frozen=True)
class GitHubRepositoryConfig:
    owner: str
    repository: str
    branch: str
    project_id: uuid.UUID
    path_allowlist: list[str]
    path_denylist: list[str]


@dataclass(slots=True, frozen=True)
class CodeownersRule:
    pattern: str
    owners: list[str]


class GitHubIndexService:
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
        self._document_rows = DocumentRepository(db)
        self._projects = ProjectRepository(db)
        self._authorization = ProjectAuthorizationRepository(db)
        self._audit = AuditLogRepository(db)

    async def status(self, user: User) -> dict[str, object]:
        state = await self._connectors.get_state(user.organization_id, "github")
        mappings = await self._connectors.list_github_mappings(user.organization_id)
        enabled = [mapping for mapping in mappings if mapping.is_enabled]
        return {
            "configured": bool(self._settings.github_token.strip() and enabled),
            "credentials_configured": bool(self._settings.github_token.strip()),
            "read_only": True,
            "preferred_auth": "github_app",
            "status": state.status if state else "disabled",
            "repositories": [self._mapping_out(mapping) for mapping in mappings],
            "last_success_at": state.last_success_at if state else None,
            "last_error_at": state.last_error_at if state else None,
            "lag_seconds": state.lag_seconds if state else None,
            "failure_count": state.failure_count if state else 0,
            "error_detail": state.error_detail if state else None,
        }

    async def configure(
        self,
        *,
        user: User,
        config: GitHubRepositoryConfig,
    ) -> GitHubRepositoryMapping:
        owner = config.owner.strip()
        repository = config.repository.strip()
        branch = config.branch.strip()
        _validate_repository_identity(owner, repository, branch)
        project = await self._projects.get_for_org(config.project_id, user.organization_id)
        if project is None or not project.is_active:
            raise NotFoundError("Project not found")
        allowlist = validate_path_patterns(config.path_allowlist)
        denylist = validate_path_patterns(config.path_denylist)
        state = await self._connectors.ensure_state(
            organization_id=user.organization_id,
            kind="github",
            created_by=user.id,
        )
        mapping = await self._connectors.get_github_mapping_by_repo(
            organization_id=user.organization_id,
            owner=owner,
            repository=repository,
            branch=branch,
        )
        if mapping is None:
            kb = KnowledgeBase(
                organization_id=user.organization_id,
                name=f"GitHub {owner}/{repository}@{branch}"[:255],
                description=f"Read-only code index for {owner}/{repository}, branch {branch}.",
                embedding_model=self._settings.embedding_model,
                embedding_dimensions=self._settings.embedding_dimensions,
                access_scope=AccessScope.ORGANIZATION,
            )
            self._kbs.add(kb)
            await self._db.flush()
            mapping = GitHubRepositoryMapping(
                organization_id=user.organization_id,
                connector_state_id=state.id,
                project_id=project.id,
                knowledge_base_id=kb.id,
                owner=owner,
                repository=repository,
                branch=branch,
                path_allowlist=allowlist,
                path_denylist=denylist,
                is_enabled=True,
                status="configured",
            )
            self._db.add(mapping)
        else:
            if mapping.project_id != project.id:
                await self._db.execute(
                    delete(ProjectSource).where(
                        ProjectSource.project_id == mapping.project_id,
                        ProjectSource.knowledge_base_id == mapping.knowledge_base_id,
                    )
                )
            mapping.project_id = project.id
            mapping.path_allowlist = allowlist
            mapping.path_denylist = denylist
            mapping.is_enabled = True
            mapping.status = "configured"
            mapping.error_detail = None
        await self._projects.add_source(project=project, knowledge_base_id=mapping.knowledge_base_id)
        state.status = "configured"
        await self._db.flush()
        state.config = {
            "repository_count": len(
                await self._connectors.list_github_mappings(user.organization_id)
            )
        }
        self._audit.record(
            action="github.configure",
            resource_type="connector",
            resource_id=str(mapping.id),
            org_id=user.organization_id,
            actor_id=user.id,
            detail=f"repository={owner}/{repository}; branch={branch}; project={project.id}",
        )
        await self._db.commit()
        return mapping

    async def sync_repository(
        self,
        *,
        user: User,
        mapping_id: uuid.UUID,
        client: GitHubReadClient,
    ) -> dict[str, object]:
        organization_id = user.organization_id
        mapping = await self._connectors.get_github_mapping(
            mapping_id=mapping_id,
            organization_id=organization_id,
        )
        if mapping is None or not mapping.is_enabled:
            raise NotFoundError("GitHub repository mapping not found")
        await self._authorization.require_source(
            user=user,
            project_id=mapping.project_id,
            knowledge_base_id=mapping.knowledge_base_id,
        )
        state = await self._connectors.get_state(organization_id, "github")
        if state is None:
            raise ValidationError("GitHub connector is not configured")
        acquired = await self._connectors.acquire_github_sync(
            mapping_id=mapping_id,
            organization_id=organization_id,
        )
        if not acquired:
            raise ConflictError("GitHub repository sync is already running")
        await self._db.commit()
        counts: dict[str, int] = {
            "created": 0,
            "updated": 0,
            "renamed": 0,
            "deleted": 0,
            "skipped": 0,
            "denied": 0,
            "oversized": 0,
            "binary": 0,
        }
        try:
            snapshot = await client.branch(
                owner=mapping.owner,
                repository=mapping.repository,
                branch=mapping.branch,
            )
            _validate_sha(snapshot.commit_sha)
            _validate_sha(snapshot.tree_sha)
            states = await self._connectors.github_file_states(mapping.id)
            tracked_states = [
                item
                for item in states
                if item.status == "active" and item.document_id is not None
            ]
            tracked_document_ids = [
                document_id
                for item in tracked_states
                if (document_id := item.document_id) is not None
            ]
            await self._document_rows.soft_delete_metadata_orphans(
                kb_id=mapping.knowledge_base_id,
                key="github_path",
                tracked_values=[item.path for item in tracked_states],
                tracked_document_ids=tracked_document_ids,
            )
            documents = {
                document.id: document
                for document in await self._db.scalars(
                    select(Document).where(Document.id.in_(tracked_document_ids))
                )
            }
            if mapping.head_tree_sha == snapshot.tree_sha and all(
                item.document_id is not None
                and (document := documents.get(item.document_id)) is not None
                and document.status == DocumentStatus.READY
                and not document.is_deleted
                for item in states
                if item.status == "active"
            ):
                counts["skipped"] = sum(item.status == "active" for item in states)
                await self._record_success(state, mapping, snapshot.commit_sha, snapshot.tree_sha)
                await self._db.commit()
                return {**counts, "commit_sha": snapshot.commit_sha, "tree_sha": snapshot.tree_sha}

            tree = await client.tree(
                owner=mapping.owner,
                repository=mapping.repository,
                tree_sha=snapshot.tree_sha,
            )
            entries = tree[: self._settings.github_max_files_per_sync + 1]
            if len(entries) > self._settings.github_max_files_per_sync:
                raise ValidationError("GitHub tree exceeds GITHUB_MAX_FILES_PER_SYNC")
            allowed_entries: list[GitHubTreeEntry] = []
            for entry in entries:
                decision = path_policy(
                    entry.path,
                    size=entry.size,
                    allowlist=[str(item) for item in mapping.path_allowlist],
                    denylist=[
                        *_split_patterns(self._settings.github_default_path_denylist),
                        *[str(item) for item in mapping.path_denylist],
                    ],
                    max_bytes=self._settings.github_max_blob_bytes,
                )
                if decision == "allowed":
                    allowed_entries.append(entry)
                else:
                    counts[decision] += 1

            owners = await self._load_codeowners(mapping, allowed_entries, client)
            contributors = await client.contributors(owner=mapping.owner, repository=mapping.repository)
            active_by_path = {item.path: item for item in states if item.status == "active"}
            allowed_paths = {entry.path for entry in allowed_entries}
            missing_states = [item for item in states if item.status == "active" and item.path not in allowed_paths]
            missing_by_blob = {item.blob_sha: item for item in missing_states}
            now = utcnow()

            for entry in allowed_entries:
                current = active_by_path.get(entry.path)
                if current is not None and current.blob_sha == entry.blob_sha:
                    document = documents.get(current.document_id) if current.document_id else None
                    if document is not None and not document.is_deleted:
                        if document.status == DocumentStatus.READY or _document_job_is_recent(
                            document,
                            now=now,
                        ):
                            counts["skipped"] += 1
                            continue
                        await self._documents.reindex(user=user, document_id=document.id)
                        counts["updated"] += 1
                        continue
                    current.document_id = None
                rename = current is None and entry.blob_sha in missing_by_blob
                file_state = missing_by_blob.pop(entry.blob_sha) if rename else current
                content = await client.blob(
                    owner=mapping.owner,
                    repository=mapping.repository,
                    blob_sha=entry.blob_sha,
                )
                if not is_text_content(content):
                    counts["binary"] += 1
                    if file_state is not None:
                        if file_state.document_id:
                            await self._documents.delete(user=user, document_id=file_state.document_id)
                        file_state.status = "deleted"
                        file_state.last_commit_sha = snapshot.commit_sha
                        counts["deleted"] += 1
                    continue
                existing_document_id = file_state.document_id if file_state else None
                if existing_document_id is None:
                    orphan = await self._document_rows.get_by_metadata_value(
                        mapping.knowledge_base_id,
                        "github_path",
                        entry.path,
                    )
                    if orphan is not None:
                        existing_document_id = orphan.id
                metadata = github_file_metadata(
                    mapping=mapping,
                    path=entry.path,
                    blob_sha=entry.blob_sha,
                    commit_sha=snapshot.commit_sha,
                    codeowners=owners_for_path(entry.path, owners),
                    contributors=contributors,
                    content=content,
                )
                document = await self._documents.create_from_bytes(
                    user=user,
                    kb_id=mapping.knowledge_base_id,
                    filename=_ingestion_filename(entry.path),
                    content=content,
                    existing_document_id=existing_document_id,
                    title=f"{mapping.owner}/{mapping.repository}:{entry.path}"[:500],
                    metadata=metadata,
                    audit_action="github.file.ingest",
                )
                await self._document_rows.soft_delete_metadata_duplicates(
                    mapping.knowledge_base_id,
                    "github_path",
                    entry.path,
                    document.id,
                )
                if file_state is None:
                    file_state = GitHubFileState(
                        repository_mapping_id=mapping.id,
                        document_id=document.id,
                        path=entry.path,
                        blob_sha=entry.blob_sha,
                        language=language_for_path(entry.path),
                        status="active",
                        last_commit_sha=snapshot.commit_sha,
                    )
                    self._db.add(file_state)
                    counts["created"] += 1
                else:
                    file_state.path = entry.path
                    file_state.blob_sha = entry.blob_sha
                    file_state.language = language_for_path(entry.path)
                    file_state.status = "active"
                    file_state.last_commit_sha = snapshot.commit_sha
                    file_state.document_id = document.id
                    counts["renamed" if rename else "updated"] += 1

            for file_state in missing_states:
                if file_state.blob_sha not in missing_by_blob:
                    continue
                if file_state.document_id:
                    await self._documents.delete(user=user, document_id=file_state.document_id)
                file_state.status = "deleted"
                file_state.last_commit_sha = snapshot.commit_sha
                counts["deleted"] += 1

            await self._record_success(state, mapping, snapshot.commit_sha, snapshot.tree_sha)
            self._audit.record(
                action="github.sync",
                resource_type="connector",
                resource_id=str(mapping.id),
                org_id=user.organization_id,
                actor_id=user.id,
                detail="; ".join(f"{key}={value}" for key, value in counts.items()),
            )
            await self._db.commit()
            return {**counts, "commit_sha": snapshot.commit_sha, "tree_sha": snapshot.tree_sha}
        except Exception as exc:
            await self._db.rollback()
            state = await self._connectors.get_state(organization_id, "github")
            mapping = await self._connectors.get_github_mapping(
                mapping_id=mapping_id,
                organization_id=organization_id,
            )
            if state is not None:
                self._connectors.record_connector_failure(state, str(exc))
            if mapping is not None:
                mapping.status = "failed"
                mapping.last_error_at = utcnow()
                mapping.error_detail = str(exc)[:1000]
            await self._db.commit()
            raise

    async def recent_pull_requests(
        self,
        *,
        user: User,
        mapping_id: uuid.UUID,
        client: GitHubReadClient,
    ) -> list[GitHubPullRequest]:
        mapping = await self._connectors.get_github_mapping(
            mapping_id=mapping_id,
            organization_id=user.organization_id,
        )
        if mapping is None or not mapping.is_enabled:
            raise NotFoundError("GitHub repository mapping not found")
        await self._authorization.require_source(
            user=user,
            project_id=mapping.project_id,
            knowledge_base_id=mapping.knowledge_base_id,
        )
        return await client.recent_pull_requests(
            owner=mapping.owner,
            repository=mapping.repository,
            limit=self._settings.github_recent_pr_limit,
        )

    async def _load_codeowners(
        self,
        mapping: GitHubRepositoryMapping,
        entries: list[GitHubTreeEntry],
        client: GitHubReadClient,
    ) -> list[CodeownersRule]:
        candidates = {"codeowners", ".github/codeowners", "docs/codeowners"}
        entry = next((item for item in entries if item.path.lower() in candidates), None)
        if entry is None:
            return []
        content = await client.blob(
            owner=mapping.owner,
            repository=mapping.repository,
            blob_sha=entry.blob_sha,
        )
        if not is_text_content(content):
            return []
        return parse_codeowners(content.decode("utf-8"))

    async def _record_success(
        self,
        state: ConnectorState,
        mapping: GitHubRepositoryMapping,
        commit_sha: str,
        tree_sha: str,
    ) -> None:
        mapping.head_commit_sha = commit_sha
        mapping.head_tree_sha = tree_sha
        mapping.status = "connected"
        mapping.last_indexed_at = utcnow()
        mapping.last_error_at = None
        mapping.error_detail = None
        await self._connectors.record_connector_success(state, source_activity_at=utcnow())

    @staticmethod
    def _mapping_out(mapping: GitHubRepositoryMapping) -> dict[str, object]:
        return {
            "id": mapping.id,
            "owner": mapping.owner,
            "repository": mapping.repository,
            "branch": mapping.branch,
            "project_id": mapping.project_id,
            "knowledge_base_id": mapping.knowledge_base_id,
            "path_allowlist": mapping.path_allowlist,
            "path_denylist": mapping.path_denylist,
            "is_enabled": mapping.is_enabled,
            "status": mapping.status,
            "head_commit_sha": mapping.head_commit_sha,
            "head_tree_sha": mapping.head_tree_sha,
            "last_indexed_at": mapping.last_indexed_at,
            "last_error_at": mapping.last_error_at,
            "error_detail": mapping.error_detail,
        }


def validate_path_patterns(patterns: list[str]) -> list[str]:
    result: list[str] = []
    for raw in patterns:
        pattern = raw.strip().replace("\\", "/")
        if not pattern or pattern.startswith("/") or ".." in PurePosixPath(pattern).parts:
            raise ValidationError("GitHub path patterns must be relative and cannot contain '..'")
        if any(ord(character) < 32 for character in pattern):
            raise ValidationError("GitHub path patterns cannot contain control characters")
        if pattern not in result:
            result.append(pattern)
    return result


def path_policy(
    path: str,
    *,
    size: int,
    allowlist: list[str],
    denylist: list[str],
    max_bytes: int,
) -> str:
    normalized = path.strip().replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if (
        not normalized
        or normalized.startswith("/")
        or ".." in parts
        or any(ord(character) < 32 for character in normalized)
    ):
        return "denied"
    if size <= 0:
        return "denied"
    if size > max_bytes:
        return "oversized"
    name = PurePosixPath(normalized).name.lower()
    suffix = PurePosixPath(normalized).suffix.lower()
    if suffix not in _TEXT_SUFFIXES and name not in _SPECIAL_TEXT_FILES:
        return "denied"
    if allowlist and not any(_path_match(normalized, pattern) for pattern in allowlist):
        return "denied"
    if any(_path_match(normalized, pattern) for pattern in denylist):
        return "denied"
    return "allowed"


def parse_codeowners(content: str) -> list[CodeownersRule]:
    rules: list[CodeownersRule] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        owners = [owner for owner in parts[1:] if owner.startswith("@") and len(owner) > 1]
        if len(parts) >= 2 and owners:
            rules.append(CodeownersRule(pattern=parts[0], owners=owners))
    return rules


def owners_for_path(path: str, rules: list[CodeownersRule]) -> list[str]:
    owners: list[str] = []
    for rule in rules:
        if _path_match(path, rule.pattern):
            owners = rule.owners
    return owners


def is_text_content(content: bytes) -> bool:
    if b"\x00" in content[:8192]:
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _document_job_is_recent(document: Document, *, now: datetime) -> bool:
    age = now - document.updated_at
    if document.status == DocumentStatus.UPLOADED:
        return age < _UPLOADED_REINDEX_AFTER
    if document.status == DocumentStatus.PROCESSING:
        return age < _PROCESSING_REINDEX_AFTER
    return False


def language_for_path(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    mapping = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".cs": "csharp",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".c": "c",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
        ".sh": "shell",
    }
    return mapping.get(suffix, suffix.lstrip(".") or "text")


def github_file_metadata(
    *,
    mapping: GitHubRepositoryMapping,
    path: str,
    blob_sha: str,
    commit_sha: str,
    codeowners: list[str],
    contributors: list[str],
    content: bytes,
) -> dict[str, object]:
    source_url = (
        f"https://github.com/{quote(mapping.owner, safe='')}/{quote(mapping.repository, safe='')}"
        f"/blob/{quote(commit_sha, safe='')}/{quote(path, safe='/')}"
    )
    source_id = f"{mapping.owner}/{mapping.repository}:{mapping.branch}:{path}"
    return {
        "source": "github",
        "source_type": "github",
        "source_family": "github",
        "source_system": "github",
        "source_id": source_id,
        "source_title": path,
        "source_url": source_url,
        "source_space": f"{mapping.owner}/{mapping.repository}",
        "source_version": commit_sha,
        "source_updated_at": utcnow().isoformat(),
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "connector": "github",
        "connector_scope": f"{mapping.owner}/{mapping.repository}@{mapping.branch}",
        "connector_sync_id": f"github:{source_id}:{blob_sha}",
        "acl": "repository-allowlist",
        "permission_state": "visible",
        "github_owner": mapping.owner,
        "github_repository": mapping.repository,
        "github_branch": mapping.branch,
        "github_path": path,
        "github_blob_sha": blob_sha,
        "github_commit_sha": commit_sha,
        "github_language": language_for_path(path),
        "github_codeowners": codeowners,
        "github_contributors": contributors,
        "project_id": str(mapping.project_id),
    }


def _path_match(path: str, raw_pattern: str) -> bool:
    pattern = raw_pattern.strip().replace("\\", "/").lstrip("/")
    if pattern.endswith("/"):
        pattern += "**"
    if pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:]):
        return True
    if "/" not in pattern:
        return fnmatch.fnmatchcase(PurePosixPath(path).name, pattern)
    return fnmatch.fnmatchcase(path, pattern)


def _split_patterns(value: str) -> list[str]:
    return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]


def _validate_repository_identity(owner: str, repository: str, branch: str) -> None:
    if not _REPO_PART_RE.fullmatch(owner) or not _REPO_PART_RE.fullmatch(repository):
        raise ValidationError("GitHub owner and repository names are invalid")
    if (
        not branch
        or len(branch) > 255
        or branch.startswith("/")
        or branch.endswith("/")
        or ".." in branch
        or any(character in branch for character in "~^:?*[\\")
        or any(ord(character) < 32 for character in branch)
    ):
        raise ValidationError("GitHub branch name is invalid")


def _validate_sha(value: str) -> None:
    if not _SHA_RE.fullmatch(value):
        raise ValidationError("GitHub returned an invalid object SHA")


def _ingestion_filename(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    return (
        PurePosixPath(path).name
        if suffix in SUPPORTED_SUFFIXES
        else f"{PurePosixPath(path).name}.txt"
    )
