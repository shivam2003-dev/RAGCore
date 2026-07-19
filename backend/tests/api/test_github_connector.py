import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import delete, update

from core.config import get_settings
from core.exceptions import ConflictError
from database.base import utcnow
from embeddings.fake import FakeEmbeddings
from ingestion.queue import IngestionQueue
from models import AuditLog, Document, DocumentStatus, User
from repositories.connectors import ConnectorRepository
from services.document_service import DocumentService
from services.github_client import (
    GitHubBranchSnapshot,
    GitHubPullRequest,
    GitHubTreeEntry,
)
from services.github_index import GitHubIndexService


class CapturingQueue(IngestionQueue):
    def __init__(self) -> None:
        self.jobs: list[tuple[Callable[..., Awaitable[None]], dict[str, Any]]] = []

    def enqueue(self, job: Callable[..., Awaitable[None]], /, **kwargs: Any) -> None:
        self.jobs.append((job, kwargs))


@dataclass
class FakeGitHubClient:
    snapshot: GitHubBranchSnapshot
    entries: list[GitHubTreeEntry]
    blobs: dict[str, bytes]

    def __post_init__(self) -> None:
        self.blob_calls: list[str] = []

    async def branch(self, *, owner: str, repository: str, branch: str) -> GitHubBranchSnapshot:
        return self.snapshot

    async def tree(self, *, owner: str, repository: str, tree_sha: str) -> list[GitHubTreeEntry]:
        return self.entries

    async def blob(self, *, owner: str, repository: str, blob_sha: str) -> bytes:
        self.blob_calls.append(blob_sha)
        return self.blobs[blob_sha]

    async def contributors(self, *, owner: str, repository: str) -> list[str]:
        return ["alice", "bob"]

    async def recent_pull_requests(
        self,
        *,
        owner: str,
        repository: str,
        limit: int,
    ) -> list[GitHubPullRequest]:
        return [
            GitHubPullRequest(
                number=7,
                title="Improve gateway retries",
                body="Bound retries and preserve errors.",
                state="open",
                author="alice",
                url="https://github.com/acme/service/pull/7",
                base_branch="main",
                head_branch="retry",
                created_at="2026-07-01T00:00:00Z",
                updated_at="2026-07-02T00:00:00Z",
                merged_at=None,
                draft=False,
                labels=["sre"],
            )
        ]


async def _run_jobs(queue: CapturingQueue, start: int = 0) -> None:
    for job, kwargs in queue.jobs[start:]:
        await job(**kwargs)


async def test_github_incremental_indexing_code_search_prs_and_acl(client, auth_headers, db):
    project = await client.post(
        "/api/v1/projects",
        json={"name": "Code Project", "slug": "code-project"},
        headers=auth_headers,
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    configured = await client.post(
        "/api/v1/github/repositories",
        json={
            "owner": "acme",
            "repository": "service",
            "branch": "main",
            "project_id": project_id,
            "path_allowlist": ["src/**", "CODEOWNERS"],
            "path_denylist": ["secrets/**"],
        },
        headers=auth_headers,
    )
    assert configured.status_code == 201, configured.text
    mapping = configured.json()

    status = await client.get("/api/v1/github/status", headers=auth_headers)
    assert status.status_code == 200, status.text
    assert status.json()["read_only"] is True
    assert status.json()["credentials_configured"] is False
    assert "token" not in str(status.json()).lower()

    projects = (await client.get("/api/v1/projects", headers=auth_headers)).json()
    target = next(item for item in projects if item["id"] == project_id)
    default = next(item for item in projects if item["slug"] == "all-knowledge")
    assert mapping["knowledge_base_id"] in target["authorized_source_ids"]
    assert mapping["knowledge_base_id"] not in default["authorized_source_ids"]

    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    user = await db.get(User, uuid.UUID(me.json()["id"]))
    settings = get_settings().model_copy(
        update={
            "github_token": "fixture-token",
            "github_max_blob_bytes": 500,
            "github_default_path_denylist": "node_modules/**,**/.env*,**/*secret*",
        }
    )
    queue = CapturingQueue()
    documents = DocumentService(
        db=db,
        settings=settings,
        embedder=FakeEmbeddings(dimensions=settings.embedding_dimensions),
        queue=queue,
    )
    service = GitHubIndexService(db=db, settings=settings, document_service=documents)

    app_v1 = b"def target_symbol():\n    return 'v1'\n"
    util = b"export function helper() { return 'ok'; }\n"
    old = b"def removed_later():\n    return True\n"
    codeowners = b"* @platform\nsrc/*.py @python-team\n"
    fixture = FakeGitHubClient(
        snapshot=GitHubBranchSnapshot(commit_sha="a" * 40, tree_sha="b" * 40),
        entries=[
            GitHubTreeEntry("src/app.py", "1" * 40, len(app_v1)),
            GitHubTreeEntry("src/util.ts", "2" * 40, len(util)),
            GitHubTreeEntry("src/old.py", "3" * 40, len(old)),
            GitHubTreeEntry("CODEOWNERS", "4" * 40, len(codeowners)),
            GitHubTreeEntry("node_modules/pkg.js", "5" * 40, 10),
            GitHubTreeEntry("src/large.py", "6" * 40, 501),
            GitHubTreeEntry("assets/logo.png", "7" * 40, 20),
        ],
        blobs={"1" * 40: app_v1, "2" * 40: util, "3" * 40: old, "4" * 40: codeowners},
    )
    first = await service.sync_repository(
        user=user,
        mapping_id=uuid.UUID(mapping["id"]),
        client=fixture,
    )
    assert first["created"] == 4
    assert first["denied"] == 2
    assert first["oversized"] == 1
    assert len(queue.jobs) == 4
    await _run_jobs(queue)

    exact = await client.post(
        "/api/v1/github/code-search",
        json={"query": "target_symbol", "project_id": project_id},
        headers=auth_headers,
    )
    assert exact.status_code == 200, exact.text
    assert exact.json()["hits"][0]["path"] == "src/app.py"
    assert exact.json()["hits"][0]["symbol"] == "target_symbol"
    assert exact.json()["hits"][0]["url"].endswith(f"/{'a' * 40}/src/app.py")
    indexed_document = await db.get(Document, uuid.UUID(exact.json()["hits"][0]["document_id"]))
    assert indexed_document.doc_metadata["github_codeowners"] == ["@python-team"]
    assert indexed_document.doc_metadata["github_contributors"] == ["alice", "bob"]
    assert indexed_document.doc_metadata["github_commit_sha"] == "a" * 40

    connector_repository = ConnectorRepository(db)
    organization_id = user.organization_id
    assert await connector_repository.acquire_github_sync(
        mapping_id=uuid.UUID(mapping["id"]),
        organization_id=organization_id,
    )
    await db.commit()
    assert not await connector_repository.acquire_github_sync(
        mapping_id=uuid.UUID(mapping["id"]),
        organization_id=organization_id,
    )
    await db.commit()
    with pytest.raises(ConflictError, match="already running"):
        await service.sync_repository(
            user=user,
            mapping_id=uuid.UUID(mapping["id"]),
            client=fixture,
        )
    locked_mapping = await connector_repository.get_github_mapping(
        mapping_id=uuid.UUID(mapping["id"]),
        organization_id=organization_id,
    )
    assert locked_mapping is not None
    locked_mapping.status = "connected"
    await db.commit()

    semantic = await client.post(
        "/api/v1/search",
        json={
            "query": "Which function returns version v1?",
            "knowledge_base_id": mapping["knowledge_base_id"],
            "project_id": project_id,
            "top_k": 5,
        },
        headers=auth_headers,
    )
    assert semantic.status_code == 200, semantic.text
    assert any("target_symbol" in hit["content"] for hit in semantic.json()["hits"])

    default_scope = await client.post(
        "/api/v1/github/code-search",
        json={"query": "target_symbol"},
        headers=auth_headers,
    )
    assert default_scope.status_code == 200
    assert default_scope.json()["hits"] == []

    injection = await client.post(
        "/api/v1/github/code-search",
        json={"query": "target_symbol; rm -rf /", "project_id": project_id},
        headers=auth_headers,
    )
    assert injection.status_code == 200
    assert injection.json()["hits"] == []
    control = await client.post(
        "/api/v1/github/code-search",
        json={"query": "target\ncommand", "project_id": project_id},
        headers=auth_headers,
    )
    assert control.status_code == 422

    duplicate_start = len(queue.jobs)
    orphan = await documents.create_from_bytes(
        user=user,
        kb_id=uuid.UUID(mapping["knowledge_base_id"]),
        filename="duplicate-app.py",
        content=app_v1,
        title="orphaned retry document",
        metadata=dict(indexed_document.doc_metadata),
        audit_action="github.file.ingest",
    )
    await _run_jobs(queue, duplicate_start)

    initial_blob_calls = list(fixture.blob_calls)
    initial_job_count = len(queue.jobs)
    unchanged = await service.sync_repository(
        user=user,
        mapping_id=uuid.UUID(mapping["id"]),
        client=fixture,
    )
    assert unchanged["skipped"] == 4
    assert fixture.blob_calls == initial_blob_calls
    assert len(queue.jobs) == initial_job_count
    await db.refresh(orphan)
    assert orphan.is_deleted is True

    app_v2 = b"def target_symbol():\n    return 'v2'\n"
    fixture.snapshot = GitHubBranchSnapshot(commit_sha="c" * 40, tree_sha="d" * 40)
    fixture.entries = [
        GitHubTreeEntry("src/app.py", "8" * 40, len(app_v2)),
        GitHubTreeEntry("src/helper.ts", "2" * 40, len(util)),
        GitHubTreeEntry("CODEOWNERS", "4" * 40, len(codeowners)),
        GitHubTreeEntry("secrets/credentials.py", "9" * 40, 20),
    ]
    fixture.blobs["8" * 40] = app_v2
    fixture.blobs["9" * 40] = b"TOKEN = 'never-index'\n"
    second_start = len(queue.jobs)
    changed = await service.sync_repository(
        user=user,
        mapping_id=uuid.UUID(mapping["id"]),
        client=fixture,
    )
    assert changed["updated"] == 1
    assert changed["renamed"] == 1
    assert changed["deleted"] == 1
    assert changed["skipped"] == 1
    assert changed["denied"] == 1
    await _run_jobs(queue, second_start)

    states = await ConnectorRepository(db).github_file_states(uuid.UUID(mapping["id"]))
    active_paths = {item.path for item in states if item.status == "active"}
    assert active_paths == {"CODEOWNERS", "src/app.py", "src/helper.ts"}
    assert "9" * 40 not in fixture.blob_calls
    old_state = next(item for item in states if item.path == "src/old.py")
    old_document = await db.get(Document, old_state.document_id)
    assert old_document.is_deleted is True

    prs = await service.recent_pull_requests(
        user=user,
        mapping_id=uuid.UUID(mapping["id"]),
        client=fixture,
    )
    assert prs[0].url.endswith("/pull/7")
    assert prs[0].author == "alice"

    # Recover a file whose metadata committed before a failed request but whose
    # queued background ingestion never ran.
    recovery_start = len(queue.jobs)
    await db.execute(
        update(Document)
        .where(Document.id == indexed_document.id)
        .values(
            status=DocumentStatus.UPLOADED,
            updated_at=utcnow() - timedelta(minutes=5),
        )
    )
    await db.commit()
    recovered = await service.sync_repository(
        user=user,
        mapping_id=uuid.UUID(mapping["id"]),
        client=fixture,
    )
    assert recovered["updated"] == 1
    assert len(queue.jobs) == recovery_start + 1
    await _run_jobs(queue, recovery_start)

    # Keep this session-scoped database fixture isolated for older metrics
    # tests that intentionally assert an empty starting inventory.
    for file_state in states:
        if file_state.status == "active" and file_state.document_id:
            await documents.delete(user=user, document_id=file_state.document_id)
    await db.execute(
        delete(AuditLog).where(
            AuditLog.organization_id == user.organization_id,
            AuditLog.action.like("github.%"),
        )
    )
    await db.commit()

    # A provider failure must remain the surfaced error after rollback. In
    # particular, error-state recording cannot lazy-load the expired user and
    # replace the original failure with SQLAlchemy MissingGreenlet.
    organization_id = user.organization_id
    fixture.snapshot = GitHubBranchSnapshot(commit_sha="e" * 40, tree_sha="f" * 40)
    fixture.entries = [GitHubTreeEntry("src/broken.py", "0" * 40, 10)]
    with pytest.raises(KeyError):
        await service.sync_repository(
            user=user,
            mapping_id=uuid.UUID(mapping["id"]),
            client=fixture,
        )
    failed_mapping = await ConnectorRepository(db).get_github_mapping(
        mapping_id=uuid.UUID(mapping["id"]),
        organization_id=organization_id,
    )
    assert failed_mapping is not None
    assert failed_mapping.status == "failed"


async def test_github_configuration_rejects_unsafe_repository_inputs(client, auth_headers):
    projects = (await client.get("/api/v1/projects", headers=auth_headers)).json()
    project_id = next(item["id"] for item in projects if item["slug"] == "all-knowledge")
    response = await client.post(
        "/api/v1/github/repositories",
        json={
            "owner": "acme;touch /tmp/pwned",
            "repository": "service",
            "branch": "../main",
            "project_id": project_id,
            "path_allowlist": ["../secrets/**"],
        },
        headers=auth_headers,
    )
    assert response.status_code == 422
