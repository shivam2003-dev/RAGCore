"""Read-only evidence primitives with project and source ACL enforcement."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.exceptions import AuthenticationError
from models import Document, User
from repositories.code_search import CodeSearchRepository
from repositories.connectors import ConnectorRepository
from repositories.projects import ProjectAuthorizationRepository
from repositories.users import UserRepository
from retrieval.context import RetrievalContext, RetrievedChunk
from retrieval.pipeline import RetrievalPipeline
from services.evidence_contract import (
    Evidence,
    EvidenceToolName,
    EvidenceToolRequest,
    PermissionContext,
    ToolSelection,
)
from services.evidence_executor import EvidencePrincipal
from services.github_client import GitHubHttpClient, GitHubReadClient

GitHubClientFactory = Callable[[], GitHubReadClient]

_SOURCE_FAMILIES: dict[EvidenceToolName, set[str]] = {
    EvidenceToolName.SEARCH_JIRA: {"jira"},
    EvidenceToolName.SEARCH_CONFLUENCE: {"confluence"},
    EvidenceToolName.SEARCH_SLACK: {"slack"},
}


@dataclass(slots=True)
class _ExpertCandidate:
    count: int
    sources: list[str]
    source: Evidence


class EvidenceToolService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        retrieval: RetrievalPipeline,
        settings: Settings,
        github_client_factory: GitHubClientFactory | None = None,
    ) -> None:
        self._db = db
        self._retrieval = retrieval
        self._settings = settings
        self._authorization = ProjectAuthorizationRepository(db)
        self._github_client_factory = github_client_factory or self._github_client

    async def invoke(
        self,
        *,
        tool: EvidenceToolName,
        request: EvidenceToolRequest,
        user: User,
    ) -> list[Evidence]:
        if tool in _SOURCE_FAMILIES:
            return await self._retrieval_evidence(
                request=request,
                user=user,
                source_families=_SOURCE_FAMILIES[tool],
            )
        if tool is EvidenceToolName.SEARCH_KNOWLEDGE:
            return await self._retrieval_evidence(request=request, user=user)
        if tool is EvidenceToolName.SEARCH_CODE:
            return await self._search_code(request=request, user=user)
        if tool is EvidenceToolName.RECENT_PRS:
            return await self._recent_prs(request=request, user=user)
        if tool is EvidenceToolName.WHO_KNOWS:
            return await self._who_knows(request=request, user=user)
        raise ValueError(f"Unsupported evidence tool: {tool}")

    async def invoke_for_principal(
        self,
        *,
        selection: ToolSelection,
        request: EvidenceToolRequest,
        principal: EvidencePrincipal,
    ) -> list[Evidence]:
        user = await UserRepository(self._db).get(principal.user_id)
        if user is None or not user.is_active or user.organization_id != principal.organization_id:
            raise AuthenticationError("Evidence principal is inactive or unavailable")
        return await self.invoke(tool=selection.tool, request=request, user=user)

    async def _retrieval_evidence(
        self,
        *,
        request: EvidenceToolRequest,
        user: User,
        source_families: set[str] | None = None,
    ) -> list[Evidence]:
        scope = await self._authorization.authorized_scope(user=user, project_id=request.project_id)
        knowledge_base_ids = scope.knowledge_base_ids
        if source_families and knowledge_base_ids:
            rows = await self._db.scalars(
                select(Document.knowledge_base_id)
                .where(
                    Document.knowledge_base_id.in_(knowledge_base_ids),
                    Document.is_deleted.is_(False),
                    or_(
                        Document.doc_metadata["source"].as_string().in_(source_families),
                        Document.doc_metadata["source_type"].as_string().in_(source_families),
                        Document.doc_metadata["source_family"].as_string().in_(source_families),
                    ),
                )
                .distinct()
            )
            knowledge_base_ids = list(rows)
        if not knowledge_base_ids:
            return []
        context = await self._retrieval.run(
            RetrievalContext(
                kb_id=knowledge_base_ids[0],
                kb_ids=knowledge_base_ids,
                query=request.query,
                top_k=request.limit,
            )
        )
        return await self._normalize_chunks(
            chunks=context.chunks[: request.limit],
            user=user,
            project_id=scope.project.id,
        )

    async def _search_code(self, *, request: EvidenceToolRequest, user: User) -> list[Evidence]:
        scope = await self._authorization.authorized_scope(user=user, project_id=request.project_id)
        hits = await CodeSearchRepository(self._db).exact_search(
            query=request.query,
            authorized_knowledge_base_ids=scope.knowledge_base_ids,
            limit=request.limit,
        )
        documents = await self._documents_by_id([hit.document_id for hit in hits])
        evidence: list[Evidence] = []
        for rank, hit in enumerate(hits, start=1):
            document = documents.get(hit.document_id)
            if document is None:
                continue
            metadata = document.doc_metadata or {}
            evidence.append(
                Evidence(
                    source_type="github",
                    source_id=str(metadata.get("source_id") or hit.path),
                    source_url=hit.url or _optional_string(metadata.get("source_url")),
                    project_id=scope.project.id,
                    permission_context=self._permission(
                        user=user,
                        project_id=scope.project.id,
                        knowledge_base_id=document.knowledge_base_id,
                    ),
                    title=hit.path,
                    content=hit.snippet,
                    snippet=hit.snippet[:1000],
                    retrieval_arms=["exact_code"],
                    rank=rank,
                    score=1.0 / rank,
                    freshness=_parse_datetime(metadata.get("source_updated_at")),
                    metadata={
                        **metadata,
                        "symbol": hit.symbol,
                        "language": hit.language,
                        "commit_sha": hit.commit_sha,
                    },
                    citation_identity=f"{scope.project.id}:{hit.document_id}:{hit.chunk_id}",
                    chunk_id=hit.chunk_id,
                    document_id=hit.document_id,
                )
            )
        return evidence

    async def _recent_prs(self, *, request: EvidenceToolRequest, user: User) -> list[Evidence]:
        scope = await self._authorization.authorized_scope(user=user, project_id=request.project_id)
        mappings = [
            mapping
            for mapping in await ConnectorRepository(self._db).list_github_mappings(user.organization_id)
            if mapping.is_enabled
            and mapping.project_id == scope.project.id
            and mapping.knowledge_base_id in scope.knowledge_base_ids
        ]
        if not mappings:
            return []
        client = self._github_client_factory()
        evidence: list[Evidence] = []
        try:
            for mapping in mappings:
                rows = await client.recent_pull_requests(
                    owner=mapping.owner,
                    repository=mapping.repository,
                    limit=min(request.limit, self._settings.github_recent_pr_limit),
                )
                for row in rows:
                    rank = len(evidence) + 1
                    content = (
                        f"PR #{row.number}: {row.title}\nState: {row.state}\nAuthor: {row.author}\n"
                        f"Base: {row.base_branch}\nHead: {row.head_branch}\n{row.body}"
                    ).strip()
                    evidence.append(
                        Evidence(
                            source_type="github_pr",
                            source_id=f"{mapping.owner}/{mapping.repository}#{row.number}",
                            source_url=row.url,
                            project_id=scope.project.id,
                            permission_context=self._permission(
                                user=user,
                                project_id=scope.project.id,
                                knowledge_base_id=mapping.knowledge_base_id,
                            ),
                            title=row.title,
                            content=content,
                            snippet=content[:1000],
                            retrieval_arms=["github_recent_prs"],
                            rank=rank,
                            score=1.0 / rank,
                            freshness=_parse_datetime(row.updated_at),
                            metadata={
                                "repository": f"{mapping.owner}/{mapping.repository}",
                                "number": row.number,
                                "state": row.state,
                                "author": row.author,
                                "labels": row.labels,
                                "draft": row.draft,
                                "created_at": row.created_at,
                                "updated_at": row.updated_at,
                                "merged_at": row.merged_at,
                            },
                            citation_identity=f"github-pr:{mapping.owner}/{mapping.repository}#{row.number}:{row.updated_at}",
                        )
                    )
                    if len(evidence) >= request.limit:
                        return evidence
        finally:
            close = getattr(client, "close", None)
            if close is not None:
                await close()
        return evidence

    async def _who_knows(self, *, request: EvidenceToolRequest, user: User) -> list[Evidence]:
        sources = await self._retrieval_evidence(request=request, user=user)
        candidates: dict[str, _ExpertCandidate] = {}
        for source in sources:
            metadata = source.metadata
            raw_people: list[object] = []
            raw_people.extend(_as_list(metadata.get("github_codeowners")))
            raw_people.extend(_as_list(metadata.get("github_contributors")))
            raw_people.extend(_as_list(metadata.get("participants")))
            raw_people.extend(_as_list(metadata.get("jira_assignee")))
            for raw in raw_people:
                if isinstance(raw, dict):
                    person = str(raw.get("display_name") or raw.get("name") or raw.get("id") or "").strip()
                else:
                    person = str(raw).strip()
                if not person:
                    continue
                entry = candidates.setdefault(
                    person,
                    _ExpertCandidate(count=0, sources=[], source=source),
                )
                entry.count += 1
                if source.source_id not in entry.sources:
                    entry.sources.append(source.source_id)
        ranked = sorted(candidates.items(), key=lambda item: (-item[1].count, item[0].casefold()))
        results: list[Evidence] = []
        for rank, (person, detail) in enumerate(ranked[: request.limit], start=1):
            source = detail.source
            source_ids = detail.sources
            count = detail.count
            content = f"{person} appears in ownership or participation metadata for {count} authorized source(s)."
            results.append(
                Evidence(
                    source_type="expert_signal",
                    source_id=f"expert:{person}",
                    source_url=source.source_url,
                    project_id=source.project_id,
                    permission_context=source.permission_context,
                    title=person,
                    content=content,
                    snippet=content,
                    retrieval_arms=["ownership_metadata"],
                    rank=rank,
                    score=float(count),
                    freshness=source.freshness,
                    metadata={"person": person, "evidence_count": count, "source_ids": source_ids},
                    citation_identity=f"{source.project_id}:expert:{person.casefold()}",
                    chunk_id=source.chunk_id,
                    document_id=source.document_id,
                )
            )
        return results

    async def _normalize_chunks(
        self,
        *,
        chunks: list[RetrievedChunk],
        user: User,
        project_id: uuid.UUID,
    ) -> list[Evidence]:
        documents = await self._documents_by_id([chunk.document_id for chunk in chunks])
        results: list[Evidence] = []
        for fallback_rank, chunk in enumerate(chunks, start=1):
            document = documents.get(chunk.document_id)
            if document is None:
                continue
            metadata = {**(document.doc_metadata or {}), **(chunk.metadata or {})}
            source_type = _source_type(metadata, document.source_type)
            source_id = str(metadata.get("source_id") or document.id)
            results.append(
                Evidence(
                    source_type=source_type,
                    source_id=source_id,
                    source_url=_optional_string(metadata.get("source_url")),
                    project_id=project_id,
                    permission_context=self._permission(
                        user=user,
                        project_id=project_id,
                        knowledge_base_id=document.knowledge_base_id,
                    ),
                    title=chunk.document_title,
                    content=chunk.content,
                    snippet=chunk.content[:1000],
                    retrieval_arms=chunk.retrieval_arms or ["hybrid"],
                    rank=chunk.selected_rank or fallback_rank,
                    score=chunk.score,
                    freshness=_parse_datetime(metadata.get("source_updated_at")) or document.updated_at,
                    metadata=metadata,
                    citation_identity=f"{project_id}:{chunk.document_id}:{chunk.chunk_id}",
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                )
            )
        return results

    async def _documents_by_id(self, document_ids: list[uuid.UUID]) -> dict[uuid.UUID, Document]:
        if not document_ids:
            return {}
        rows = await self._db.scalars(
            select(Document).where(Document.id.in_(set(document_ids)), Document.is_deleted.is_(False))
        )
        return {document.id: document for document in rows}

    @staticmethod
    def _permission(
        *,
        user: User,
        project_id: uuid.UUID,
        knowledge_base_id: uuid.UUID | None,
    ) -> PermissionContext:
        return PermissionContext(
            organization_id=user.organization_id,
            user_id=user.id,
            project_id=project_id,
            knowledge_base_id=knowledge_base_id,
        )

    def _github_client(self) -> GitHubHttpClient:
        return GitHubHttpClient(
            token=self._settings.github_token,
            base_url=self._settings.github_api_base_url,
            api_version=self._settings.github_api_version,
            timeout_seconds=self._settings.github_request_timeout_seconds,
            max_retries=self._settings.github_api_max_retries,
        )


def _source_type(metadata: dict[str, object], fallback: str) -> str:
    return str(
        metadata.get("source_family")
        or metadata.get("source_type")
        or metadata.get("source")
        or fallback
    ).lower()


def _optional_string(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]
