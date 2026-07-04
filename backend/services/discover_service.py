import hashlib
import html
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from xml.etree.ElementTree import Element

import httpx
from bs4 import BeautifulSoup
from defusedxml import ElementTree
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from database.base import utcnow
from models import Document, KnowledgeBase, User

QueryParam = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class DiscoverDepartment:
    id: str
    label: str
    description: str
    query: str


@dataclass(frozen=True, slots=True)
class DiscoverArticle:
    id: str
    title: str
    url: str
    source: str
    summary: str
    section: str
    department: str
    published_at: str | None
    score: float


@dataclass(frozen=True, slots=True)
class DiscoverBoardItem:
    title: str
    url: str | None
    source_type: str
    status: str
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DiscoverBoardPulse:
    jira_documents: int
    confluence_documents: int
    upload_documents: int
    web_documents: int
    latest_items: list[DiscoverBoardItem]


@dataclass(frozen=True, slots=True)
class DiscoverFeed:
    generated_at: datetime
    provider: str
    configured: bool
    department: str
    departments: list[DiscoverDepartment]
    lead: DiscoverArticle | None
    articles: list[DiscoverArticle]
    alerts: list[DiscoverArticle]
    research: list[DiscoverArticle]
    board_pulse: DiscoverBoardPulse
    warnings: list[str]


_DEFAULT_DEPARTMENTS: tuple[DiscoverDepartment, ...] = (
    DiscoverDepartment(
        id="for-you",
        label="For You",
        description="Enterprise technology, operations, security, and product updates.",
        query="enterprise technology DevOps SRE cybersecurity software engineering AI product management news",
    ),
    DiscoverDepartment(
        id="devops",
        label="DevOps",
        description="Kubernetes, GitOps, CI/CD, platform engineering, and release operations.",
        query="DevOps Kubernetes GitOps Argo CD platform engineering CI CD production operations",
    ),
    DiscoverDepartment(
        id="sre",
        label="SRE",
        description="Reliability, incident response, observability, SLOs, and postmortems.",
        query="site reliability engineering SRE observability incident response SLO postmortem outage",
    ),
    DiscoverDepartment(
        id="development",
        label="Development",
        description="Developer productivity, frameworks, testing, architecture, and AI coding.",
        query="software engineering developer productivity architecture testing AI coding release notes",
    ),
    DiscoverDepartment(
        id="security",
        label="Security",
        description="Zero-days, CVEs, exploits, advisories, conferences, and hardening guidance.",
        query="cybersecurity zero day CVE vulnerability exploit advisory patch conference research",
    ),
    DiscoverDepartment(
        id="hr",
        label="HR",
        description="People operations, compliance, policy, hiring, and employee experience.",
        query="human resources people operations workplace compliance employee experience HR technology",
    ),
    DiscoverDepartment(
        id="finance",
        label="Finance",
        description="Markets, budgeting, cost optimization, procurement, and financial operations.",
        query="finance market outlook IT cost optimization procurement budgeting business technology",
    ),
    DiscoverDepartment(
        id="product",
        label="Product",
        description="Product strategy, user research, SaaS trends, analytics, and roadmap signals.",
        query="product management SaaS user research roadmap analytics AI product strategy",
    ),
)

_CACHE: dict[str, tuple[datetime, list[DiscoverArticle]]] = {}


class DiscoverService:
    def __init__(self, *, db: AsyncSession, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    async def feed(self, *, user: User, department_id: str = "for-you") -> DiscoverFeed:
        departments = department_catalog(self._settings.discover_department_queries)
        department = next((item for item in departments if item.id == department_id), departments[0])
        board_pulse = await self._board_pulse(user)
        warnings: list[str] = []
        articles: list[DiscoverArticle] = []
        configured = self._settings.discover_enabled
        provider = self._settings.discover_provider.strip().lower()

        if not configured:
            warnings.append("Discover is disabled. Set DISCOVER_ENABLED=true to fetch external updates.")
        else:
            status_warning = self._provider_warning(provider)
            if status_warning:
                configured = False
                warnings.append(status_warning)
            else:
                try:
                    articles = await self._cached_external_articles(department)
                except (httpx.HTTPError, ElementTree.ParseError) as exc:
                    configured = False
                    warnings.append(f"Discover provider request failed: {type(exc).__name__}")

        alerts = [item for item in articles if item.section == "alerts"]
        research = [item for item in articles if item.section == "research"]
        normal_articles = [item for item in articles if item.section == "articles"]
        lead = articles[0] if articles else None

        return DiscoverFeed(
            generated_at=utcnow(),
            provider=provider,
            configured=configured,
            department=department.id,
            departments=departments,
            lead=lead,
            articles=normal_articles,
            alerts=alerts,
            research=research,
            board_pulse=board_pulse,
            warnings=warnings,
        )

    async def _cached_external_articles(self, department: DiscoverDepartment) -> list[DiscoverArticle]:
        provider = self._settings.discover_provider.strip().lower()
        ttl = max(60, self._settings.discover_cache_ttl_seconds)
        count = max(4, min(self._settings.discover_items_per_department, 20))
        key = f"{provider}:{department.id}:{department.query}:{count}"
        cached = _CACHE.get(key)
        now = datetime.now(UTC)
        if cached is not None and (now - cached[0]).total_seconds() < ttl:
            return cached[1]

        rows = await self._fetch_external(query=department.query, max_results=count)
        articles = _dedupe_articles(
            _row_to_article(row, department=department.id, rank=rank)
            for rank, row in enumerate(rows, start=1)
        )
        _CACHE[key] = (now, articles)
        return articles

    async def _fetch_external(self, *, query: str, max_results: int) -> list[dict[str, object]]:
        provider = self._settings.discover_provider.strip().lower()
        if provider == "fake":
            return _fake_rows(query, max_results)
        if provider == "google_news_rss":
            return await self._google_news_rss(query=query, max_results=max_results)
        if provider == "duckduckgo":
            return await self._duckduckgo(query=query, max_results=max_results)
        if provider == "brave":
            return await self._brave(query=query, max_results=max_results)
        if provider == "tavily":
            return await self._tavily(query=query, max_results=max_results)
        if provider == "searxng":
            return await self._searxng(query=query, max_results=max_results)
        return []

    async def _google_news_rss(self, *, query: str, max_results: int) -> list[dict[str, object]]:
        base_url = self._settings.discover_base_url or "https://news.google.com/rss/search"
        language = self._settings.discover_locale.split("-", 1)[0] or "en"
        region = self._settings.discover_region or "US"
        params = {
            "q": query,
            "hl": self._settings.discover_locale,
            "gl": region,
            "ceid": f"{region}:{language}",
        }
        text = await self._get_text(base_url, params=params)
        return _parse_google_news_rss(text, max_results=max_results)

    async def _duckduckgo(self, *, query: str, max_results: int) -> list[dict[str, object]]:
        base_url = self._settings.discover_base_url or "https://html.duckduckgo.com/html/"
        html_text = await self._get_text(base_url, params={"q": query})
        soup = BeautifulSoup(html_text, "html.parser")
        rows: list[dict[str, object]] = []
        for rank, result in enumerate(soup.select(".result"), start=1):
            link = result.select_one(".result__a")
            if link is None:
                continue
            title = link.get_text(" ", strip=True)
            url = _normalize_duckduckgo_url(str(link.get("href") or ""))
            snippet_node = result.select_one(".result__snippet")
            summary = snippet_node.get_text(" ", strip=True) if snippet_node is not None else title
            if title and url:
                rows.append(
                    {
                        "title": title,
                        "url": url,
                        "summary": summary,
                        "source": _source_from_url(url),
                        "score": max(0.05, 1.0 - (rank - 1) * 0.07),
                    }
                )
            if len(rows) >= max_results:
                break
        return rows

    async def _brave(self, *, query: str, max_results: int) -> list[dict[str, object]]:
        base_url = self._settings.discover_base_url or "https://api.search.brave.com/res/v1/web/search"
        payload = await self._get_json(
            base_url,
            headers={"Accept": "application/json", "X-Subscription-Token": self._settings.discover_api_key},
            params={"q": query, "count": max_results, "safesearch": "moderate"},
        )
        web = payload.get("web") if isinstance(payload, dict) else {}
        rows = web.get("results") if isinstance(web, dict) else []
        return _normalize_search_rows(rows if isinstance(rows, list) else [], max_results=max_results)

    async def _tavily(self, *, query: str, max_results: int) -> list[dict[str, object]]:
        base_url = self._settings.discover_base_url or "https://api.tavily.com/search"
        payload = await self._post_json(
            base_url,
            headers={"Authorization": f"Bearer {self._settings.discover_api_key}", "Content-Type": "application/json"},
            json={"query": query, "max_results": max_results, "include_answer": False, "search_depth": "basic"},
        )
        rows = payload.get("results") if isinstance(payload, dict) else []
        return _normalize_search_rows(rows if isinstance(rows, list) else [], max_results=max_results)

    async def _searxng(self, *, query: str, max_results: int) -> list[dict[str, object]]:
        base_url = (
            self._settings.discover_base_url.rstrip("/") + "/search"
            if self._settings.discover_base_url
            else ""
        )
        payload = await self._get_json(
            base_url,
            headers={"Accept": "application/json"},
            params={"q": query, "format": "json", "safesearch": "1"},
        )
        rows = payload.get("results") if isinstance(payload, dict) else []
        return _normalize_search_rows(rows if isinstance(rows, list) else [], max_results=max_results)

    async def _get_text(self, url: str, *, params: Mapping[str, QueryParam]) -> str:
        async with httpx.AsyncClient(timeout=self._settings.web_search_request_timeout_seconds) as client:
            response = await client.get(
                url,
                headers={"Accept": "text/html,application/rss+xml,application/xml", "User-Agent": "KimbalDiscover/1.0"},
                params=params,
                follow_redirects=True,
            )
            response.raise_for_status()
            return response.text

    async def _get_json(
        self, url: str, *, headers: dict[str, str], params: Mapping[str, QueryParam]
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._settings.web_search_request_timeout_seconds) as client:
            response = await client.get(url, headers=headers, params=params, follow_redirects=True)
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {}

    async def _post_json(
        self, url: str, *, headers: dict[str, str], json: dict[str, object]
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._settings.web_search_request_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=json, follow_redirects=True)
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {}

    async def _board_pulse(self, user: User) -> DiscoverBoardPulse:
        source_expr = func.coalesce(Document.doc_metadata["source"].as_string(), Document.source_type)
        count_rows = await self._db.execute(
            select(source_expr, func.count(Document.id))
            .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
            .where(KnowledgeBase.organization_id == user.organization_id, Document.is_deleted.is_(False))
            .group_by(source_expr)
        )
        counts = {str(row[0] or "upload").lower(): int(row[1] or 0) for row in count_rows}
        latest_docs = await self._db.scalars(
            select(Document)
            .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
            .where(KnowledgeBase.organization_id == user.organization_id, Document.is_deleted.is_(False))
            .order_by(desc(Document.updated_at))
            .limit(8)
        )
        latest_items = [
            DiscoverBoardItem(
                title=doc.title,
                url=_source_url(doc.doc_metadata),
                source_type=str(doc.doc_metadata.get("source") or doc.source_type),
                status=doc.status.value,
                updated_at=doc.updated_at,
            )
            for doc in latest_docs
        ]
        known = counts.get("jira", 0) + counts.get("confluence", 0) + counts.get("web", 0)
        total = sum(counts.values())
        return DiscoverBoardPulse(
            jira_documents=counts.get("jira", 0),
            confluence_documents=counts.get("confluence", 0),
            upload_documents=max(0, total - known),
            web_documents=counts.get("web", 0),
            latest_items=latest_items,
        )

    def _provider_warning(self, provider: str) -> str | None:
        if provider == "disabled":
            return (
                "Discover is disabled. Set DISCOVER_PROVIDER to google_news_rss, "
                "duckduckgo, brave, tavily, or searxng."
            )
        if provider in {"brave", "tavily"} and not self._settings.discover_api_key:
            return f"DISCOVER_API_KEY is required for {provider}."
        if provider == "searxng" and not self._settings.discover_base_url:
            return "DISCOVER_BASE_URL is required for searxng."
        if provider not in {"google_news_rss", "duckduckgo", "brave", "tavily", "searxng", "fake"}:
            return f"Unsupported DISCOVER_PROVIDER: {provider}."
        return None


def department_catalog(overrides: str = "") -> list[DiscoverDepartment]:
    by_id = {item.id: item for item in _DEFAULT_DEPARTMENTS}
    for key, query in _parse_department_query_overrides(overrides).items():
        item = by_id.get(key)
        if item is not None:
            by_id[key] = DiscoverDepartment(id=item.id, label=item.label, description=item.description, query=query)
    return [by_id[item.id] for item in _DEFAULT_DEPARTMENTS]


def _parse_department_query_overrides(raw: str) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for part in re.split(r"[;\n]", raw):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if key and value:
            overrides[key] = value
    return overrides


def _parse_google_news_rss(text: str, *, max_results: int) -> list[dict[str, object]]:
    root = ElementTree.fromstring(text)
    rows: list[dict[str, object]] = []
    for item in root.findall(".//item"):
        title = _xml_text(item, "title")
        url = _xml_text(item, "link")
        source = _xml_text(item, "source") or _source_from_url(url)
        summary = _clean_html(_xml_text(item, "description")) or title
        published_at = _parse_date(_xml_text(item, "pubDate"))
        if title and url:
            rows.append(
                {
                    "title": title,
                    "url": url,
                    "source": source,
                    "summary": summary,
                    "published_at": published_at,
                    "score": max(0.05, 1.0 - len(rows) * 0.07),
                }
            )
        if len(rows) >= max_results:
            break
    return rows


def _normalize_search_rows(rows: Sequence[object], *, max_results: int) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for rank, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        url = str(row.get("url") or "").strip()
        summary = str(row.get("description") or row.get("content") or "").strip()
        if not title or not url:
            continue
        normalized.append(
            {
                "title": title,
                "url": url,
                "source": str(row.get("source") or _source_from_url(url)),
                "summary": summary or title,
                "published_at": str(row.get("age") or row.get("published_date") or "") or None,
                "score": (
                    float(row.get("score"))
                    if isinstance(row.get("score"), (int, float))
                    else max(0.05, 1.0 - (rank - 1) * 0.07)
                ),
            }
        )
        if len(normalized) >= max_results:
            break
    return normalized


def _row_to_article(row: dict[str, object], *, department: str, rank: int) -> DiscoverArticle:
    title = str(row.get("title") or "").strip()
    url = str(row.get("url") or "").strip()
    summary = str(row.get("summary") or "").strip() or title
    source = str(row.get("source") or _source_from_url(url))
    section = _classify_section(title, summary)
    score_raw = row.get("score")
    score = float(score_raw) if isinstance(score_raw, (int, float)) else max(0.05, 1.0 - (rank - 1) * 0.07)
    return DiscoverArticle(
        id=hashlib.sha256(f"{department}:{url}:{title}".encode()).hexdigest()[:16],
        title=title[:300],
        url=url,
        source=source[:120],
        summary=summary[:500],
        section=section,
        department=department,
        published_at=str(row.get("published_at") or "") or None,
        score=max(0.0, min(score, 1.0)),
    )


def _dedupe_articles(items: Iterable[DiscoverArticle]) -> list[DiscoverArticle]:
    seen: set[str] = set()
    deduped: list[DiscoverArticle] = []
    for item in items:
        if not item.url or item.url in seen:
            continue
        seen.add(item.url)
        deduped.append(item)
    return deduped


def _fake_rows(query: str, max_results: int) -> list[dict[str, object]]:
    seed = [
        (
            "Kubernetes incident review patterns for production teams",
            "https://example.com/kubernetes-incident-review",
            "A field update on SLOs, rollout guardrails, and production incident review habits.",
        ),
        (
            "Critical CVE patch advisory for platform services",
            "https://example.com/platform-cve-advisory",
            "Security teams are tracking a critical vulnerability and prioritizing patch windows.",
        ),
        (
            "New research report on developer productivity and AI coding workflows",
            "https://example.com/dev-productivity-research",
            "A research summary covering productivity metrics, review quality, and AI-assisted delivery.",
        ),
    ]
    return [
        {
            "title": title,
            "url": url,
            "source": _source_from_url(url),
            "summary": f"{summary} Query: {query}",
            "score": max(0.05, 1.0 - rank * 0.08),
        }
        for rank, (title, url, summary) in enumerate(seed[:max_results])
    ]


def _classify_section(title: str, summary: str) -> str:
    text = f"{title} {summary}".lower()
    alert_words = (
        "cve",
        "zero-day",
        "zero day",
        "vulnerability",
        "exploit",
        "breach",
        "outage",
        "incident",
        "advisory",
        "critical",
    )
    research_words = (
        "research",
        "paper",
        "conference",
        "book",
        "report",
        "study",
        "benchmark",
        "whitepaper",
        "guide",
    )
    if any(word in text for word in alert_words):
        return "alerts"
    if any(word in text for word in research_words):
        return "research"
    return "articles"


def _source_url(metadata: dict[str, object]) -> str | None:
    for key in ("source_url", "web_url", "jira_issue_url", "confluence_page_url", "confluence_url", "jira_url"):
        value = metadata.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return None


def _xml_text(item: Element, tag: str) -> str:
    child = item.find(tag)
    return html.unescape(child.text or "").strip() if child is not None else ""


def _clean_html(value: str) -> str:
    if not value:
        return ""
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


def _parse_date(value: str) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(UTC).isoformat()
    except (TypeError, ValueError):
        return value


def _source_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host or "web"


def _normalize_duckduckgo_url(href: str) -> str:
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urlparse(href)
    params = parse_qs(parsed.query)
    uddg = params.get("uddg")
    if uddg and uddg[0]:
        return uddg[0]
    if parsed.scheme or parsed.netloc:
        return href
    if href.startswith("/l/?"):
        params = parse_qs(href.split("?", 1)[1])
        uddg = params.get("uddg")
        if uddg and uddg[0]:
            return uddg[0]
    if href and not href.startswith("http"):
        return f"https://duckduckgo.com/?{urlencode({'q': href})}"
    return href
