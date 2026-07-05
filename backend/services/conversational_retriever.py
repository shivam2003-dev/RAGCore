import re
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from models import Conversation, KnowledgeBase, Message, User
from repositories.knowledge import KnowledgeBaseRepository
from retrieval.crag import MIN_ACCEPT_CONFIDENCE
from retrieval.context import RetrievalContext, RetrievedChunk
from retrieval.pipeline import RetrievalPipeline
from services.web_search_service import WebSearchService


JIRA_TERMS = (
    "jira",
    "devo",
    "cvir",
    "board",
    "issue",
    "issues",
    "ticket",
    "tickets",
    "assignee",
    "assigned",
    "sprint",
    "kanban",
    "backlog",
)
CONFLUENCE_TERMS = (
    "confluence",
    "wiki",
    "space",
    "page",
    "docs",
    "documentation",
    "runbook",
    "checklist",
    "broker",
    "install",
    "installation",
    "setup",
    "ssl",
    "sre",
)
COUNT_TERMS = ("count", "how many", "number", "no of", "no. of", "total")


@dataclass(slots=True)
class RetrievalResult:
    chunks: list[RetrievedChunk] = field(default_factory=list)
    timings_ms: dict[str, int] = field(default_factory=dict)
    confidence: float | None = None
    subqueries: list[str] = field(default_factory=list)
    attempts: list[dict[str, object]] = field(default_factory=list)
    quality_notes: list[str] = field(default_factory=list)
    weak_internal_retrieval: bool = False
    fallback_requested: bool = False


class ConversationalRetriever:
    """Runs vector/web retrieval with the standalone question and chat context."""

    def __init__(
        self,
        *,
        db: AsyncSession,
        retrieval: RetrievalPipeline,
        web_search: WebSearchService,
        settings: Settings,
    ) -> None:
        self._db = db
        self._retrieval = retrieval
        self._web_search = web_search
        self._settings = settings
        self._kbs = KnowledgeBaseRepository(db)

    async def retrieve(
        self,
        *,
        user: User,
        conversation: Conversation,
        current_question: str,
        standalone_question: str,
        history: list[Message],
        source_mode: str,
    ) -> RetrievalResult:
        query = standalone_question or current_question
        chunks: list[RetrievedChunk] = []
        timings_ms: dict[str, int] = {}
        confidence: float | None = None
        subqueries: list[str] = []
        attempts: list[dict[str, object]] = []
        quality_notes: list[str] = []
        fallback_requested = False

        if source_mode in {"knowledge", "blended"}:
            kb_scope = await self._knowledge_scope(
                org_id=user.organization_id,
                fallback_kb_id=conversation.knowledge_base_id,
                question=query,
            )
            top_k = self._settings.retrieval_top_k
            if _contains_any(query, COUNT_TERMS):
                top_k = max(top_k, 20)
            subqueries = _decompose_query(query)
            confidences: list[float] = []
            for index, subquery in enumerate(subqueries, start=1):
                ctx = RetrievalContext(
                    kb_id=conversation.knowledge_base_id,
                    kb_ids=kb_scope,
                    query=subquery,
                    top_k=top_k,
                    conversation_context="\n".join(m.content[:500] for m in history[-4:]),
                )
                ctx = await self._retrieval.run(ctx)
                chunks.extend(ctx.chunks)
                for key, value in ctx.timings_ms.items():
                    timings_ms[f"{key}_{index}" if len(subqueries) > 1 else key] = value
                if ctx.confidence is not None:
                    confidences.append(ctx.confidence)
                attempts.extend(
                    {
                        "query": attempt.query,
                        "top_k": attempt.top_k,
                        "result_count": attempt.result_count,
                        "confidence": attempt.confidence,
                    }
                    for attempt in ctx.attempts
                )
                quality_notes.extend(ctx.quality_notes)
                fallback_requested = fallback_requested or ctx.fallback_requested
            if confidences:
                confidence = round(sum(confidences) / len(confidences), 4)

        if source_mode in {"web", "blended"}:
            web_started = time.perf_counter()
            web_chunks = await self._web_search.search(
                user=user,
                query=query,
                max_results=self._settings.web_search_top_k,
            )
            timings_ms["web_search"] = int((time.perf_counter() - web_started) * 1000)
            chunks.extend(web_chunks)
            if confidence is None:
                confidence = _confidence_from_chunks(web_chunks)

        weak_internal = bool(
            source_mode != "web"
            and (confidence is None or confidence < MIN_ACCEPT_CONFIDENCE or fallback_requested)
        )
        return RetrievalResult(
            chunks=_dedupe_chunks(chunks, limit=max(self._settings.retrieval_top_k, 20)),
            timings_ms=timings_ms,
            confidence=confidence,
            subqueries=subqueries or [query],
            attempts=attempts,
            quality_notes=quality_notes,
            weak_internal_retrieval=weak_internal,
            fallback_requested=fallback_requested,
        )

    async def _knowledge_scope(
        self,
        *,
        org_id: uuid.UUID,
        fallback_kb_id: uuid.UUID,
        question: str,
    ) -> list[uuid.UUID]:
        kbs = await self._kbs.list_by_org(org_id)
        if not kbs:
            return [fallback_kb_id]

        normalized = question.lower()
        non_web = [kb for kb in kbs if kb.name != self._settings.web_search_default_kb_name]
        candidates = [kb for kb in non_web if kb.name != "Kimbal Local Runbook"] or non_web or kbs

        named_scope = _named_scope(candidates, normalized)
        if named_scope:
            return [kb.id for kb in named_scope]

        if _contains_any(normalized, JIRA_TERMS):
            jira_kbs = [kb.id for kb in candidates if _kb_source_family(kb) == "jira"]
            if jira_kbs:
                return jira_kbs

        if _contains_any(normalized, CONFLUENCE_TERMS):
            confluence_kbs = [kb.id for kb in candidates if _kb_source_family(kb) == "confluence"]
            if confluence_kbs:
                return confluence_kbs

        return [kb.id for kb in candidates]


def _named_scope(kbs: list[KnowledgeBase], normalized_question: str) -> list[KnowledgeBase]:
    rules = [
        ("cvir", ("cvir",)),
        ("devo", ("devo", "devops1", "devops")),
        ("devops", ("devo", "devops1", "devops")),
        ("sre", ("sre", "cvir", " confluence as", " as")),
    ]
    selected: list[KnowledgeBase] = []
    for term, needles in rules:
        if not re.search(rf"\b{re.escape(term)}\b", normalized_question):
            continue
        for kb in kbs:
            name = f" {kb.name.lower()} "
            if any(needle in name for needle in needles):
                selected.append(kb)
    return _dedupe_kbs(selected)


def _kb_source_family(kb: KnowledgeBase) -> str:
    name = kb.name.lower()
    if "jira" in name or "devo" in name or "cvir" in name:
        return "jira"
    if "confluence" in name or "devops1" in name or "sre" in name:
        return "confluence"
    if "web" in name:
        return "web"
    return "knowledge"


def _dedupe_kbs(kbs: list[KnowledgeBase]) -> list[KnowledgeBase]:
    seen: set[uuid.UUID] = set()
    result: list[KnowledgeBase] = []
    for kb in kbs:
        if kb.id in seen:
            continue
        seen.add(kb.id)
        result.append(kb)
    return result


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    normalized = value.lower()
    return any(needle in normalized for needle in needles)


def _decompose_query(query: str) -> list[str]:
    normalized = query.strip()
    if not normalized:
        return [query]
    lower = f" {normalized.lower()} "
    has_multi_signal = (
        " and " in lower
        or " also " in lower
        or " plus " in lower
        or ";" in normalized
        or "?" in normalized.rstrip("?")
    )
    if not has_multi_signal:
        return [normalized]

    parts = [
        part.strip(" .?\n\t")
        for part in re.split(r"\s+(?:and|also|plus)\s+|;", normalized, flags=re.IGNORECASE)
        if len(part.strip(" .?\n\t")) >= 8
    ]
    if len(parts) < 2:
        return [normalized]

    source_signals = sum(
        1
        for part in parts
        if _contains_any(part, JIRA_TERMS)
        or _contains_any(part, CONFLUENCE_TERMS)
        or _contains_any(part, COUNT_TERMS)
    )
    if source_signals < 2:
        return [normalized]
    return _dedupe_strings([*parts, normalized])[:3]


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _dedupe_chunks(chunks: list[RetrievedChunk], *, limit: int | None = None) -> list[RetrievedChunk]:
    seen: set[uuid.UUID] = set()
    deduped: list[RetrievedChunk] = []
    for chunk in sorted(chunks, key=lambda item: item.score, reverse=True):
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        deduped.append(chunk)
        if limit is not None and len(deduped) >= limit:
            break
    return deduped


def _confidence_from_chunks(chunks: list[RetrievedChunk]) -> float | None:
    if not chunks:
        return None
    score = sum(chunk.score for chunk in chunks) / len(chunks)
    return round(max(0.0, min(score, 1.0)), 4)
