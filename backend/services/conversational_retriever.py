import re
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.exceptions import AuthorizationError, NotFoundError, ProviderError, ValidationError
from models import Chunk, Conversation, Document, KnowledgeBase, Message, User
from repositories.knowledge import KnowledgeBaseRepository
from retrieval.context import RetrievalContext, RetrievedChunk
from retrieval.crag import MIN_ACCEPT_CONFIDENCE
from retrieval.pipeline import RetrievalPipeline
from services.jira_service import retrieve_live_jira_relationships
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
    "procedure",
    "process",
    "architecture",
    "architectural",
    "design",
    "diagram",
    "diagrams",
    "overview",
    "topology",
    "flow",
    "flows",
    "hld",
    "lld",
    "sop",
    "guide",
    "deployment",
    "release",
    "configuration",
    "implementation",
    "broker",
    "install",
    "installation",
    "setup",
    "ssl",
    "sre",
)
COUNT_TERMS = ("count", "how many", "number", "no of", "no. of", "total")
DOC_INTENT_TERMS = (
    "architecture",
    "architectural",
    "design",
    "diagram",
    "diagrams",
    "overview",
    "topology",
    "hld",
    "lld",
    "documentation",
    "docs",
    "runbook",
    "sop",
    "guide",
    "procedure",
    "process",
)
JIRA_ISSUE_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b", re.IGNORECASE)


@dataclass(slots=True)
class RetrievalResult:
    chunks: list[RetrievedChunk] = field(default_factory=list)
    timings_ms: dict[str, int] = field(default_factory=dict)
    confidence: float | None = None
    query_classification: str = "factual_lookup"
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
        assistant_role: str | None = None,
        assistant_role_prompt: str | None = None,
    ) -> RetrievalResult:
        query = standalone_question or current_question
        current_issue_keys = JIRA_ISSUE_KEY_RE.findall(current_question)
        if current_issue_keys:
            prior_user_intent = " ".join(
                message.content[:500]
                for message in history[-6:]
                if message.role == "user"
            ).strip()
            if prior_user_intent:
                query = f"{query}\nPrior user intent: {prior_user_intent[-900:]}"
        query_classification = _classify_query(query)
        chunks: list[RetrievedChunk] = []
        timings_ms: dict[str, int] = {}
        confidence: float | None = None
        subqueries: list[str] = []
        attempts: list[dict[str, object]] = []
        quality_notes: list[str] = []
        fallback_requested = False
        live_jira_chunks: list[RetrievedChunk] = []

        if source_mode in {"knowledge", "blended"}:
            kb_scope = await self._knowledge_scope(
                org_id=user.organization_id,
                fallback_kb_id=conversation.knowledge_base_id,
                question=query,
                role_context=" ".join(part for part in (assistant_role, assistant_role_prompt) if part),
            )
            top_k = self._settings.retrieval_top_k
            if _contains_any(query, COUNT_TERMS):
                top_k = max(top_k, 20)
            issue_keys = list(dict.fromkeys(match.upper() for match in JIRA_ISSUE_KEY_RE.findall(query)))
            exact_jira_scope = bool(issue_keys) and not _contains_any(query, CONFLUENCE_TERMS)
            subqueries = [] if exact_jira_scope else _decompose_query(query)
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

            for issue_key in issue_keys[:3]:
                relationship_started = time.perf_counter()
                relationship_chunks = await self._retrieval.jira_relationship_context(
                    kb_scope=kb_scope,
                    issue_key=issue_key,
                    query=query,
                    limit=max(self._settings.retrieval_candidate_k, 24),
                )
                timings_ms[f"jira_relationship_{issue_key.lower()}"] = int(
                    (time.perf_counter() - relationship_started) * 1000
                )
                chunks.extend(relationship_chunks)
                if relationship_chunks:
                    quality_notes.append(
                        f"expanded_jira_relationship={issue_key} chunks={len(relationship_chunks)}"
                    )
                live_started = time.perf_counter()
                try:
                    live_chunks = await retrieve_live_jira_relationships(
                        settings=self._settings,
                        issue_key=issue_key,
                        query=query,
                        limit=max(self._settings.retrieval_top_k, 12),
                    )
                    live_chunks = await self._map_live_jira_chunks(
                        chunks=live_chunks,
                        kb_scope=kb_scope,
                    )
                except (AuthorizationError, NotFoundError, ProviderError, ValidationError):
                    live_chunks = []
                    quality_notes.append(f"live_jira_relationship_failed={issue_key}")
                timings_ms[f"live_jira_{issue_key.lower()}"] = int(
                    (time.perf_counter() - live_started) * 1000
                )
                chunks.extend(live_chunks)
                if live_chunks:
                    live_jira_chunks.extend(live_chunks)
                    quality_notes.append(
                        f"live_jira_relationship={issue_key} chunks={len(live_chunks)}"
                    )

            if live_jira_chunks:
                confidence = max(confidence or 0.0, 0.8)
                fallback_requested = False
                if not _contains_any(query, CONFLUENCE_TERMS):
                    chunks = live_jira_chunks
                    quality_notes.append("exact_jira_scope=live_issue_family")

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
            query_classification=query_classification,
            subqueries=subqueries or [query],
            attempts=attempts,
            quality_notes=quality_notes,
            weak_internal_retrieval=weak_internal,
            fallback_requested=fallback_requested,
        )

    async def _map_live_jira_chunks(
        self,
        *,
        chunks: list[RetrievedChunk],
        kb_scope: list[uuid.UUID],
    ) -> list[RetrievedChunk]:
        """Use persisted IDs for live Jira text so stored citations retain valid foreign keys."""

        issue_keys = {
            str(chunk.metadata.get("jira_issue_key") or "").upper()
            for chunk in chunks
            if chunk.metadata.get("jira_issue_key")
        }
        if not issue_keys:
            return []
        issue_key_field = Document.doc_metadata["jira_issue_key"].astext
        rows = (
            await self._db.execute(
                select(Document.id, Document.title, Document.doc_metadata, Chunk.id)
                .join(Chunk, Chunk.document_id == Document.id)
                .where(
                    Document.knowledge_base_id.in_(kb_scope),
                    Document.is_deleted.is_(False),
                    Chunk.is_active.is_(True),
                    func.upper(issue_key_field).in_(issue_keys),
                )
                .order_by(Document.updated_at.desc(), Chunk.ordinal)
            )
        ).all()
        by_issue: dict[str, list[tuple[uuid.UUID, uuid.UUID, str]]] = {}
        chosen_document: dict[str, uuid.UUID] = {}
        for document_id, title, metadata, chunk_id in rows:
            key = str((metadata or {}).get("jira_issue_key") or "").upper()
            if not key:
                continue
            chosen_document.setdefault(key, document_id)
            if chosen_document[key] != document_id:
                continue
            by_issue.setdefault(key, []).append((document_id, chunk_id, title))

        mapped: list[RetrievedChunk] = []
        ordinal_by_issue: dict[str, int] = {}
        for chunk in chunks:
            key = str(chunk.metadata.get("jira_issue_key") or "").upper()
            persisted = by_issue.get(key) or []
            if not persisted:
                continue
            ordinal = ordinal_by_issue.get(key, 0)
            document_id, chunk_id, title = persisted[min(ordinal, len(persisted) - 1)]
            ordinal_by_issue[key] = ordinal + 1
            mapped.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    document_title=title,
                    content=chunk.content,
                    metadata=chunk.metadata,
                    dense_score=chunk.dense_score,
                    sparse_score=chunk.sparse_score,
                    score=chunk.score,
                )
            )
        return mapped

    async def _knowledge_scope(
        self,
        *,
        org_id: uuid.UUID,
        fallback_kb_id: uuid.UUID,
        question: str,
        role_context: str = "",
    ) -> list[uuid.UUID]:
        kbs = await self._kbs.list_by_org(org_id)
        if not kbs:
            return [fallback_kb_id]

        normalized = question.lower()
        non_web = [kb for kb in kbs if kb.name != self._settings.web_search_default_kb_name]
        candidates = [kb for kb in non_web if kb.name != "CVUM Local Runbook"] or non_web or kbs

        named_scope = _named_scope(candidates, normalized)
        if named_scope:
            if _contains_any(normalized, DOC_INTENT_TERMS) and not _contains_any(normalized, JIRA_TERMS):
                confluence_named_scope = [kb for kb in named_scope if _kb_source_family(kb) == "confluence"]
                if confluence_named_scope:
                    return [kb.id for kb in confluence_named_scope]
            return [kb.id for kb in named_scope]

        role_scope = _role_scope(candidates, role_context)
        if role_scope:
            if _contains_any(normalized, DOC_INTENT_TERMS) and not _contains_any(normalized, JIRA_TERMS):
                # A persona can prioritize response framing, but it must not hide a relevant
                # architecture/runbook page owned by another internal Confluence space.
                confluence_scope = [kb for kb in candidates if _kb_source_family(kb) == "confluence"]
                if confluence_scope:
                    return [kb.id for kb in confluence_scope]
            return [kb.id for kb in role_scope]

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


def _role_scope(kbs: list[KnowledgeBase], role_context: str) -> list[KnowledgeBase]:
    normalized = role_context.lower()
    if not normalized:
        return []
    if "devops" in normalized or "devops space" in normalized:
        return _dedupe_kbs(
            [
                kb
                for kb in kbs
                if _kb_name_contains(kb, ("jira devo", "devo", "confluence devops1", "devops1", "devops"))
            ]
        )
    if "sre" in normalized or "sre space" in normalized:
        return _dedupe_kbs(
            [
                kb
                for kb in kbs
                if _kb_name_contains(kb, ("jira cvir", "cvir", "confluence sre", "sre", "confluence as", " as"))
            ]
        )
    if "hr" in normalized:
        return _dedupe_kbs([kb for kb in kbs if _kb_name_contains(kb, ("hr", "people"))])
    if "developer" in normalized or "dev space" in normalized:
        return _dedupe_kbs(
            [
                kb
                for kb in kbs
                if _kb_name_contains(kb, ("developer", "engineering", "confluence dev", "dev docs"))
            ]
        )
    return []


def _kb_name_contains(kb: KnowledgeBase, needles: tuple[str, ...]) -> bool:
    name = f" {kb.name.lower()} "
    return any(needle in name for needle in needles)


def _kb_source_family(kb: KnowledgeBase) -> str:
    name = kb.name.lower()
    if "confluence" in name or "devops1" in name or "sre" in name:
        return "confluence"
    if "jira" in name or "devo" in name or "cvir" in name:
        return "jira"
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


def _classify_query(query: str) -> str:
    normalized = query.lower()
    if _contains_any(normalized, COUNT_TERMS):
        return "jira_count_stat" if _contains_any(normalized, JIRA_TERMS) else "count_stat"
    if _contains_any(normalized, DOC_INTENT_TERMS):
        if any(term in normalized for term in ("architecture", "design", "diagram", "topology", "hld", "lld")):
            return "architecture_docs"
        return "procedure_runbook"
    if any(term in normalized for term in ("rca", "root cause", "incident", "outage", "alarm", "failure")):
        return "multi_hop_rca"
    if any(term in normalized for term in ("compare", "difference", "versus", " vs ")):
        return "comparison"
    if any(term in normalized for term in ("summarize", "summary", "overview", "all ", "common", "trend")):
        return "global_summary"
    return "factual_lookup"


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
    per_source: dict[str, int] = {}
    deduped: list[RetrievedChunk] = []
    for chunk in sorted(chunks, key=lambda item: item.score, reverse=True):
        if chunk.chunk_id in seen:
            continue
        source_key = _source_dedupe_key(chunk)
        if per_source.get(source_key, 0) >= 2:
            continue
        seen.add(chunk.chunk_id)
        per_source[source_key] = per_source.get(source_key, 0) + 1
        deduped.append(chunk)
        if limit is not None and len(deduped) >= limit:
            break
    return deduped


def _source_dedupe_key(chunk: RetrievedChunk) -> str:
    metadata = chunk.metadata or {}
    for key in ("chunk_source_key", "source_id", "issue_key", "page_id", "jira_issue_key", "confluence_page_id"):
        value = metadata.get(key)
        if isinstance(value, (str, int)) and str(value):
            return str(value)
    return str(chunk.document_id)


def _confidence_from_chunks(chunks: list[RetrievedChunk]) -> float | None:
    if not chunks:
        return None
    score = sum(chunk.score for chunk in chunks) / len(chunks)
    return round(max(0.0, min(score, 1.0)), 4)
