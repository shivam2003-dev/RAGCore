import hashlib
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.exceptions import ProviderError, ValidationError
from database.base import utcnow
from embeddings.base import EmbeddingProvider
from knowledgebase.source_metadata import normalize_source_metadata
from models import Chunk, Document, DocumentStatus, DocumentVersion, KnowledgeBase, User
from repositories.chunks import ChunkRepository
from repositories.knowledge import DocumentRepository, KnowledgeBaseRepository
from retrieval.context import RetrievedChunk

type QueryParam = str | int | float | bool | None


@dataclass(slots=True)
class WebSearchStatus:
    configured: bool
    provider: str
    default_kb_name: str
    top_k: int
    reason: str


@dataclass(slots=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str
    score: float
    published_at: str | None = None


class WebSearchService:
    def __init__(self, *, db: AsyncSession, settings: Settings, embedder: EmbeddingProvider) -> None:
        self._db = db
        self._settings = settings
        self._embedder = embedder
        self._kbs = KnowledgeBaseRepository(db)
        self._docs = DocumentRepository(db)

    def status(self) -> WebSearchStatus:
        provider = self._settings.web_search_provider.lower()
        if provider == "disabled":
            return WebSearchStatus(
                configured=False,
                provider=provider,
                default_kb_name=self._settings.web_search_default_kb_name,
                top_k=self._settings.web_search_top_k,
                reason="Set WEB_SEARCH_PROVIDER to duckduckgo, brave, tavily, or searxng.",
            )
        if provider in {"brave", "tavily"} and not self._settings.web_search_api_key:
            return WebSearchStatus(
                configured=False,
                provider=provider,
                default_kb_name=self._settings.web_search_default_kb_name,
                top_k=self._settings.web_search_top_k,
                reason="Set WEB_SEARCH_API_KEY for the selected provider.",
            )
        if provider == "searxng" and not self._settings.web_search_base_url:
            return WebSearchStatus(
                configured=False,
                provider=provider,
                default_kb_name=self._settings.web_search_default_kb_name,
                top_k=self._settings.web_search_top_k,
                reason="Set WEB_SEARCH_BASE_URL to a SearXNG instance with JSON output enabled.",
            )
        if provider not in {"duckduckgo", "brave", "tavily", "searxng", "fake"}:
            return WebSearchStatus(
                configured=False,
                provider=provider,
                default_kb_name=self._settings.web_search_default_kb_name,
                top_k=self._settings.web_search_top_k,
                reason=f"Unsupported WEB_SEARCH_PROVIDER: {provider}",
            )
        return WebSearchStatus(
            configured=True,
            provider=provider,
            default_kb_name=self._settings.web_search_default_kb_name,
            top_k=self._settings.web_search_top_k,
            reason="configured",
        )

    async def search(self, *, user: User, query: str, max_results: int | None = None) -> list[RetrievedChunk]:
        status = self.status()
        if not status.configured:
            raise ValidationError(f"Web search is not configured. {status.reason}")

        top_k = max(1, min(max_results or self._settings.web_search_top_k, 10))
        results = await self._provider_search(query=query, max_results=top_k)
        if not results:
            return []

        kb = await self._ensure_web_kb(user)
        chunks: list[RetrievedChunk] = []
        for rank, result in enumerate(results[:top_k], start=1):
            chunk = await self._upsert_result(user=user, kb=kb, result=result, rank=rank)
            chunks.append(chunk)
        await self._db.flush()
        return chunks

    async def _provider_search(self, *, query: str, max_results: int) -> list[WebSearchResult]:
        provider = self._settings.web_search_provider.lower()
        if provider == "fake":
            return [
                WebSearchResult(
                    title="CVUM web search result",
                    url="https://example.com/cvum-web-search",
                    snippet=f"Live web-search style result for query: {query}",
                    score=1.0,
                )
            ][:max_results]
        if provider == "duckduckgo":
            return await self._search_duckduckgo(query=query, max_results=max_results)
        if provider == "brave":
            return await self._search_brave(query=query, max_results=max_results)
        if provider == "tavily":
            return await self._search_tavily(query=query, max_results=max_results)
        if provider == "searxng":
            return await self._search_searxng(query=query, max_results=max_results)
        raise ValidationError(f"Unsupported web search provider: {provider}")

    async def _search_duckduckgo(self, *, query: str, max_results: int) -> list[WebSearchResult]:
        base_url = self._settings.web_search_base_url or "https://html.duckduckgo.com/html/"
        params: dict[str, QueryParam] = {"q": query}
        html = await self._get_text(
            base_url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "Mozilla/5.0 CVUMKnowledgeHub/1.0",
            },
            params=params,
        )
        soup = BeautifulSoup(html, "html.parser")
        rows: list[dict[str, object]] = []
        collect_limit = max(12, max_results * 3)
        for rank, result in enumerate(soup.select(".result"), start=1):
            link = result.select_one(".result__a")
            if link is None:
                continue
            href = str(link.get("href") or "")
            title = link.get_text(" ", strip=True)
            snippet_node = result.select_one(".result__snippet")
            snippet = snippet_node.get_text(" ", strip=True) if snippet_node is not None else title
            url = _normalize_duckduckgo_url(href)
            if not title or not url:
                continue
            rows.append(
                {
                    "title": title,
                    "url": url,
                    "description": snippet,
                    "score": _score_duckduckgo_result(query=query, title=title, snippet=snippet, rank=rank),
                }
            )
            if len(rows) >= collect_limit:
                break
        rows.sort(key=_row_score, reverse=True)
        return _normalize_result_rows(rows, max_results=max_results)

    async def _search_brave(self, *, query: str, max_results: int) -> list[WebSearchResult]:
        base_url = self._settings.web_search_base_url or "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self._settings.web_search_api_key,
        }
        params: dict[str, QueryParam] = {"q": query, "count": max_results, "safesearch": "moderate"}
        payload = await self._get_json(base_url, headers=headers, params=params)
        web = payload.get("web") if isinstance(payload, dict) else {}
        rows = web.get("results") if isinstance(web, dict) else []
        return _normalize_result_rows(rows if isinstance(rows, list) else [], max_results=max_results)

    async def _search_tavily(self, *, query: str, max_results: int) -> list[WebSearchResult]:
        base_url = self._settings.web_search_base_url or "https://api.tavily.com/search"
        headers = {
            "Authorization": f"Bearer {self._settings.web_search_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "query": query,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
            "search_depth": "basic",
        }
        payload = await self._post_json(base_url, headers=headers, json=body)
        rows = payload.get("results") if isinstance(payload, dict) else []
        return _normalize_result_rows(rows if isinstance(rows, list) else [], max_results=max_results)

    async def _search_searxng(self, *, query: str, max_results: int) -> list[WebSearchResult]:
        base_url = urljoin(self._settings.web_search_base_url.rstrip("/") + "/", "search")
        params = {"q": query, "format": "json", "safesearch": "1"}
        payload = await self._get_json(base_url, headers={"Accept": "application/json"}, params=params)
        rows = payload.get("results") if isinstance(payload, dict) else []
        return _normalize_result_rows(rows if isinstance(rows, list) else [], max_results=max_results)

    async def _get_json(
        self, url: str, *, headers: dict[str, str], params: Mapping[str, QueryParam]
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self._settings.web_search_request_timeout_seconds) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPError as exc:
            raise ProviderError(f"Web search provider request failed: {exc}") from exc

    async def _get_text(
        self, url: str, *, headers: dict[str, str], params: Mapping[str, QueryParam]
    ) -> str:
        try:
            async with httpx.AsyncClient(timeout=self._settings.web_search_request_timeout_seconds) as client:
                response = await client.get(url, headers=headers, params=params, follow_redirects=True)
                response.raise_for_status()
                return response.text
        except httpx.HTTPError as exc:
            raise ProviderError(f"Web search provider request failed: {exc}") from exc

    async def _post_json(
        self, url: str, *, headers: dict[str, str], json: dict[str, object]
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self._settings.web_search_request_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=json)
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPError as exc:
            raise ProviderError(f"Web search provider request failed: {exc}") from exc

    async def _ensure_web_kb(self, user: User) -> KnowledgeBase:
        existing = await self._kbs.get_by_name(
            org_id=user.organization_id,
            name=self._settings.web_search_default_kb_name,
        )
        if existing is not None:
            return existing
        kb = KnowledgeBase(
            organization_id=user.organization_id,
            name=self._settings.web_search_default_kb_name,
            description="Web search snippets captured from configured external search providers.",
            embedding_model=self._embedder.model,
            embedding_dimensions=self._embedder.dimensions,
        )
        self._kbs.add(kb)
        await self._db.flush()
        return kb

    async def _upsert_result(
        self, *, user: User, kb: KnowledgeBase, result: WebSearchResult, rank: int
    ) -> RetrievedChunk:
        content = _render_web_result(result)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        metadata: dict[str, object] = {
            "source": "web",
            "web_provider": self._settings.web_search_provider.lower(),
            "web_url": result.url,
            "source_url": result.url,
            "web_snippet": result.snippet,
            "web_rank": rank,
            "web_source_sha256": content_hash,
        }
        if result.published_at:
            metadata["web_published_at"] = result.published_at
        metadata = normalize_source_metadata(
            metadata,
            source_type="web",
            title=result.title,
            source_id=result.url,
            source_url=result.url,
            source_space=self._settings.web_search_provider.lower(),
            updated_at=result.published_at,
            status="current",
            acl="public-web",
            connector="web",
            connector_scope=self._settings.web_search_provider.lower(),
            source_sha256=content_hash,
        )

        doc = await self._docs.get_by_metadata_value(kb.id, "web_url", result.url)
        if doc is not None and doc.doc_metadata.get("web_source_sha256") == content_hash:
            chunk = await self._first_active_chunk(doc.id)
            if chunk is not None:
                return _chunk_to_retrieved(chunk=chunk, title=doc.title, score=result.score)

        if doc is None:
            doc = Document(
                knowledge_base_id=kb.id,
                uploaded_by=user.id,
                title=_trim_title(result.title),
                source_type="web",
                status=DocumentStatus.READY,
                doc_metadata=metadata,
            )
            self._docs.add(doc)
            version_number = 1
        else:
            doc.current_version += 1
            doc.title = _trim_title(result.title)
            doc.status = DocumentStatus.READY
            doc.error = None
            doc.doc_metadata = metadata
            version_number = doc.current_version
            await self._db.execute(update(Chunk).where(Chunk.document_id == doc.id).values(is_active=False))
        await self._db.flush()

        version = DocumentVersion(
            document_id=doc.id,
            version=version_number,
            file_path=result.url,
            file_sha256=content_hash,
            file_size_bytes=len(content.encode("utf-8")),
            created_at=utcnow(),
        )
        self._docs.add_version(version)
        await self._db.flush()

        embedding = (await self._embedder.embed([content]))[0]
        chunk = Chunk(
            knowledge_base_id=kb.id,
            document_id=doc.id,
            document_version_id=version.id,
            ordinal=0,
            content=content,
            token_count=max(1, len(content.split())),
            chunk_metadata=metadata,
            embedding=embedding,
            created_at=utcnow(),
        )
        ChunkRepository(self._db).add_all([chunk])
        await self._db.flush()
        return _chunk_to_retrieved(chunk=chunk, title=doc.title, score=result.score)

    async def _first_active_chunk(self, document_id: uuid.UUID) -> Chunk | None:
        return cast(
            Chunk | None,
            await self._db.scalar(
                select(Chunk)
                .where(Chunk.document_id == document_id, Chunk.is_active.is_(True))
                .order_by(Chunk.ordinal)
                .limit(1)
            ),
        )


def _normalize_result_rows(rows: Sequence[object], *, max_results: int) -> list[WebSearchResult]:
    results: list[WebSearchResult] = []
    for rank, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        url = str(row.get("url") or "").strip()
        snippet = str(row.get("description") or row.get("content") or "").strip()
        if not title or not url:
            continue
        score_raw = row.get("score")
        score = (
            float(score_raw)
            if isinstance(score_raw, (int, float))
            else max(0.05, 1.0 - (rank - 1) * 0.08)
        )
        results.append(
            WebSearchResult(
                title=title,
                url=url,
                snippet=snippet or title,
                score=max(0.0, min(score, 1.0)),
                published_at=str(row.get("age") or row.get("published_date") or "") or None,
            )
        )
        if len(results) >= max_results:
            break
    return results


def _row_score(row: dict[str, object]) -> float:
    score = row.get("score")
    return float(score) if isinstance(score, (int, float)) else 0.0


def _normalize_duckduckgo_url(href: str) -> str:
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urlparse(href)
    params = parse_qs(parsed.query)
    uddg = params.get("uddg")
    if uddg and uddg[0]:
        return uddg[0]
    return href


def _score_duckduckgo_result(*, query: str, title: str, snippet: str, rank: int) -> float:
    normalized_query = query.lower()
    text = f"{title} {snippet}".lower()
    query_tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", normalized_query)
        if len(token) > 2 and token not in {"the", "and", "for", "with"}
    }
    covered = sum(1 for token in query_tokens if token in text)
    coverage = covered / max(len(query_tokens), 1)
    score = max(0.05, 1.0 - (rank - 1) * 0.06) + coverage * 0.18

    asks_for_result = any(phrase in normalized_query for phrase in ("who won", "winner", "result", "score"))
    if asks_for_result and any(
        cue in text for cue in (" won ", " win ", "winner", "defeat", "defeated", "beat ", "champion", "title")
    ):
        score += 0.42
    if asks_for_result and any(cue in text for cue in ("who won", "result", "winner")):
        score += 0.1
    return min(score, 1.5)


def _render_web_result(result: WebSearchResult) -> str:
    lines = [f"# {result.title}", f"URL: {result.url}"]
    if result.published_at:
        lines.append(f"Published: {result.published_at}")
    lines.extend(["", result.snippet])
    return "\n".join(lines)


def _trim_title(title: str) -> str:
    return title[:500] or "Web result"


def _chunk_to_retrieved(*, chunk: Chunk, title: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        document_title=title,
        content=chunk.content,
        metadata=chunk.chunk_metadata,
        score=score,
    )
