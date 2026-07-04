"""Chat orchestration: retrieval → prompt → streamed generation → persistence.

Yields typed SSE events; the router only serializes them.
"""

import re
import time
import uuid
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chat.citations import extract_citations
from chat.prompts import build_system_prompt
from core.config import Settings
from core.exceptions import NotFoundError, ProviderError, ValidationError
from database.base import utcnow
from llm.base import ChatMessage, LLMProvider, LLMRequest, LLMUsage
from llm.openai_compat import OpenAICompatLLM
from models import Chunk, Citation, Conversation, Document, KnowledgeBase, Message, User
from repositories.conversations import ConversationRepository, MessageRepository
from repositories.knowledge import KnowledgeBaseRepository
from retrieval.context import RetrievalContext, RetrievedChunk
from retrieval.pipeline import RetrievalPipeline
from services.web_search_service import WebSearchService

HISTORY_TURNS = 8
TITLE_LEN = 80
JIRA_TERMS = (
    "jira",
    "devo",
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
)
COUNT_TERMS = ("count", "how many", "number", "no of", "no. of", "total")
DONE_STATUS_TERMS = {"done", "closed", "resolved", "complete", "completed", "cancelled", "canceled"}
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


@dataclass(slots=True)
class ChatEvent:
    type: str  # "sources" | "delta" | "done" | "error"
    data: dict[str, object]


@dataclass(slots=True)
class JiraIssueCountRow:
    document_id: uuid.UUID
    key: str
    summary: str
    status: str


@dataclass(slots=True)
class JiraIssueCountResult:
    assignee_label: str
    issues: list[JiraIssueCountRow]
    chunks: list[RetrievedChunk]


@dataclass(slots=True)
class CouncilStatus:
    configured: bool
    models: list[str]
    available_models: list[str]
    chair_model: str | None
    reason: str


class ChatService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        retrieval: RetrievalPipeline,
        llm: LLMProvider,
        web_search: WebSearchService,
        settings: Settings,
    ) -> None:
        self._db = db
        self._conversations = ConversationRepository(db)
        self._messages = MessageRepository(db)
        self._kbs = KnowledgeBaseRepository(db)
        self._retrieval = retrieval
        self._llm = llm
        self._web_search = web_search
        self._settings = settings

    async def start_conversation(self, user: User, kb_id: uuid.UUID, title: str | None) -> Conversation:
        conversation = Conversation(
            organization_id=user.organization_id,
            user_id=user.id,
            knowledge_base_id=kb_id,
            title=title or "New conversation",
        )
        self._conversations.add(conversation)
        await self._db.commit()
        return conversation

    async def ask(
        self,
        *,
        user: User,
        conversation_id: uuid.UUID,
        question: str,
        regenerate: bool = False,
        source_mode: str = "knowledge",
        answer_mode: str = "fast",
        assistant_role: str | None = None,
        assistant_role_prompt: str | None = None,
        council_models: list[str] | None = None,
        council_chair_model: str | None = None,
    ) -> AsyncIterator[ChatEvent]:
        started = time.perf_counter()
        source_mode = _normalize_source_mode(source_mode)
        answer_mode = _normalize_answer_mode(answer_mode)
        conversation = await self._conversations.get_owned(conversation_id, user.id)
        if conversation is None:
            raise NotFoundError("Conversation not found")

        history = await self._messages.recent_turns(conversation_id, HISTORY_TURNS)
        if regenerate and history and history[-1].role == "assistant":
            history = history[:-1]

        if source_mode != "web":
            jira_count = await self._jira_assignee_open_count(
                org_id=user.organization_id,
                question=question,
            )
            if jira_count is not None:
                async for event in self._stream_jira_count_answer(
                    conversation=conversation,
                    question=question,
                    chunks=jira_count.chunks,
                    assignee_label=jira_count.assignee_label,
                    issues=jira_count.issues,
                    started=started,
                    regenerate=regenerate,
                    source_mode=source_mode,
                ):
                    yield event
                return

        chunks: list[RetrievedChunk] = []
        timings_ms: dict[str, int] = {}
        confidence: float | None = None

        if source_mode in {"knowledge", "blended"}:
            kb_scope = await self._knowledge_scope(
                org_id=user.organization_id,
                fallback_kb_id=conversation.knowledge_base_id,
                question=question,
            )
            top_k = self._settings.retrieval_top_k
            if _contains_any(question, COUNT_TERMS):
                top_k = max(top_k, 20)

            ctx = RetrievalContext(
                kb_id=conversation.knowledge_base_id,
                kb_ids=kb_scope,
                query=question,
                top_k=top_k,
                conversation_context="\n".join(m.content[:500] for m in history[-4:]),
            )
            ctx = await self._retrieval.run(ctx)
            chunks.extend(ctx.chunks)
            timings_ms.update(ctx.timings_ms)
            confidence = ctx.confidence

        if source_mode in {"web", "blended"}:
            web_started = time.perf_counter()
            web_chunks = await self._web_search.search(
                user=user,
                query=question,
                max_results=self._settings.web_search_top_k,
            )
            timings_ms["web_search"] = int((time.perf_counter() - web_started) * 1000)
            chunks.extend(web_chunks)
            if confidence is None:
                confidence = _confidence_from_chunks(web_chunks)

        chunks = _dedupe_chunks(chunks)

        yield ChatEvent(
            type="sources",
            data={
                "sources": [_source_payload(i + 1, c) for i, c in enumerate(chunks)],
                "confidence": confidence,
                "source_mode": source_mode,
                "answer_mode": answer_mode,
            },
        )

        request = LLMRequest(
            system=build_system_prompt(
                chunks,
                role_name=assistant_role,
                role_prompt=assistant_role_prompt,
            ),
            messages=[
                *(ChatMessage(role=m.role, content=m.content) for m in history),
                ChatMessage(role="user", content=question),
            ],
            max_tokens=self._settings.llm_max_output_tokens,
        )

        llm_started = time.perf_counter()
        answer_parts: list[str] = []
        usage = LLMUsage()
        model = self._llm.model
        if answer_mode == "council":
            answer, usage, model = await self._run_council(
                chunks=chunks,
                history=history,
                question=question,
                assistant_role=assistant_role,
                assistant_role_prompt=assistant_role_prompt,
                requested_models=council_models,
                requested_chair_model=council_chair_model,
            )
            answer_parts.append(answer)
            yield ChatEvent(type="delta", data={"text": answer})
        else:
            async for delta in self._llm.stream(request):
                if delta.text:
                    answer_parts.append(delta.text)
                    yield ChatEvent(type="delta", data={"text": delta.text})
                if delta.done and delta.usage:
                    usage = delta.usage
        timings_ms["llm"] = int((time.perf_counter() - llm_started) * 1000)

        answer = "".join(answer_parts)
        latency_ms = int((time.perf_counter() - started) * 1000)
        message_id = await self._persist_turn(
            conversation=conversation,
            question=question,
            answer=answer,
            chunks=chunks,
            usage=usage,
            latency_ms=latency_ms,
            timings=timings_ms,
            regenerate=regenerate,
            model=model,
        )

        yield ChatEvent(
            type="done",
            data={
                "message_id": str(message_id),
                "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
                "latency_ms": latency_ms,
                "timings_ms": timings_ms,
                "model": model,
                "source_mode": source_mode,
                "answer_mode": answer_mode,
            },
        )

    async def _stream_jira_count_answer(
        self,
        *,
        conversation: Conversation,
        question: str,
        chunks: list[RetrievedChunk],
        assignee_label: str,
        issues: list[JiraIssueCountRow],
        started: float,
        regenerate: bool,
        source_mode: str,
    ) -> AsyncIterator[ChatEvent]:
        yield ChatEvent(
            type="sources",
            data={
                "sources": [_source_payload(i + 1, chunk) for i, chunk in enumerate(chunks)],
                "confidence": 1.0,
                "source_mode": source_mode,
                "answer_mode": "fast",
            },
        )

        if issues:
            plural = "s" if len(issues) != 1 else ""
            lines = [
                f"Jira DEVO has **{len(issues)} open issue{plural}** assigned to "
                f"{assignee_label}.",
                "",
            ]
            for index, issue in enumerate(issues, start=1):
                lines.append(
                    f"{index}. **{issue.key}** - {issue.summary} - Status: {issue.status or 'Unknown'} [{index}]"
                )
        else:
            lines = [
                f"Jira DEVO has **0 open issues** assigned to {assignee_label}.",
                "",
                "I counted indexed Jira issue records where the assignee matched the question "
                "and the status category is not done.",
            ]

        answer = "\n".join(lines)
        yield ChatEvent(type="delta", data={"text": answer})

        latency_ms = int((time.perf_counter() - started) * 1000)
        timings = {"jira_count": latency_ms}
        message_id = await self._persist_turn(
            conversation=conversation,
            question=question,
            answer=answer,
            chunks=chunks,
            usage=LLMUsage(),
            latency_ms=latency_ms,
            timings=timings,
            regenerate=regenerate,
            model="deterministic-jira-count",
        )
        yield ChatEvent(
            type="done",
            data={
                "message_id": str(message_id),
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "latency_ms": latency_ms,
                "timings_ms": timings,
                "model": "deterministic-jira-count",
                "source_mode": source_mode,
                "answer_mode": "fast",
            },
        )

    async def _run_council(
        self,
        *,
        chunks: list[RetrievedChunk],
        history: list[Message],
        question: str,
        assistant_role: str | None = None,
        assistant_role_prompt: str | None = None,
        requested_models: list[str] | None = None,
        requested_chair_model: str | None = None,
    ) -> tuple[str, LLMUsage, str]:
        status = llm_council_status(
            self._settings,
            requested_models=requested_models,
            requested_chair_model=requested_chair_model,
        )
        if not status.configured:
            raise ValidationError(f"LLM Council is not configured. {status.reason}")

        api_key, base_url = _council_api_key_and_base_url(self._settings)
        total_usage = LLMUsage()
        failures: list[str] = []
        candidates: list[tuple[str, str]] = []
        member_system = (
            f"{build_system_prompt(chunks, role_name=assistant_role, role_prompt=assistant_role_prompt)}\n\n"
            "You are one independent council member. Produce a concise answer grounded only "
            "in the sources. Keep citation markers intact."
        )
        member_messages = [
            *(ChatMessage(role=m.role, content=m.content) for m in history),
            ChatMessage(role="user", content=question),
        ]

        for model in status.models:
            provider = OpenAICompatLLM(
                name=f"council:{model}",
                model=model,
                api_key=api_key,
                base_url=base_url,
                timeout=self._settings.llm_council_timeout_seconds,
            )
            try:
                text, usage = await _collect_llm_text(
                    provider,
                    LLMRequest(
                        system=member_system,
                        messages=member_messages,
                        max_tokens=self._settings.llm_max_output_tokens,
                    ),
                )
            except Exception as exc:
                failures.append(f"{model}: {exc}")
                continue
            if text.strip():
                candidates.append((model, text.strip()))
                total_usage.input_tokens += usage.input_tokens
                total_usage.output_tokens += usage.output_tokens

        if len(candidates) != len(status.models):
            detail = "; ".join(failures[:3]) or "no candidate answers were returned"
            raise ProviderError(
                f"LLM Council requires {len(status.models)} response models; "
                f"received {len(candidates)} candidate answers. {detail}"
            )

        chair_model = status.chair_model or candidates[0][0]
        chair = OpenAICompatLLM(
            name=f"council-chair:{chair_model}",
            model=chair_model,
            api_key=api_key,
            base_url=base_url,
            timeout=self._settings.llm_council_timeout_seconds,
        )
        candidate_block = "\n\n".join(
            f'<candidate model="{model}">\n{text}\n</candidate>' for model, text in candidates
        )
        chair_system = (
            f"{build_system_prompt(chunks, role_name=assistant_role, role_prompt=assistant_role_prompt)}\n\n"
            "You are the council evaluator and final answer writer. Two candidate answers are "
            "advisory analysis, not evidence. Evaluate them for source grounding, correctness, "
            "completeness, and citation discipline. Only the <source> blocks are evidence. Return "
            "one final answer with source citation markers and do not mention the council process."
        )
        chair_question = (
            f"Question:\n{question}\n\n"
            f"Candidate answers:\n{candidate_block}\n\n"
            "Evaluate both candidate answers, discard unsupported claims, and write the best final "
            "answer. Preserve correct citation markers such as [1]."
        )
        answer, chair_usage = await _collect_llm_text(
            chair,
            LLMRequest(
                system=chair_system,
                messages=[
                    *(ChatMessage(role=m.role, content=m.content) for m in history),
                    ChatMessage(role="user", content=chair_question),
                ],
                max_tokens=self._settings.llm_max_output_tokens,
            ),
        )
        total_usage.input_tokens += chair_usage.input_tokens
        total_usage.output_tokens += chair_usage.output_tokens
        return answer, total_usage, f"llm-council:{chair_model}"

    async def _jira_assignee_open_count(
        self,
        *,
        org_id: uuid.UUID,
        question: str,
    ) -> JiraIssueCountResult | None:
        normalized = question.lower()
        if not (
            _contains_any(normalized, JIRA_TERMS)
            and _contains_any(normalized, COUNT_TERMS)
            and ("assignee" in normalized or "assigned" in normalized)
            and "open" in normalized
        ):
            return None

        email_match = EMAIL_RE.search(question)
        email = email_match.group(0).lower() if email_match else ""
        name_match = re.search(r"\(([^)]+)\)", question)
        name = name_match.group(1).strip().lower() if name_match else ""
        if not email and not name:
            return None

        stmt = (
            select(Document)
            .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
            .where(
                KnowledgeBase.organization_id == org_id,
                KnowledgeBase.name == self._settings.jira_default_kb_name,
                Document.is_deleted.is_(False),
            )
            .order_by(Document.title)
        )
        documents = list(await self._db.scalars(stmt))
        issues: list[JiraIssueCountRow] = []
        for document in documents:
            metadata = document.doc_metadata or {}
            if metadata.get("source") != "jira":
                continue
            assignee_email = str(metadata.get("jira_assignee_email") or "").lower()
            assignee_name = str(metadata.get("jira_assignee") or "").lower()
            if email and assignee_email != email:
                continue
            if not email and name and assignee_name != name:
                continue
            category = str(metadata.get("jira_issue_status_category_key") or "").lower()
            status = str(metadata.get("jira_issue_status") or "").lower()
            if category in DONE_STATUS_TERMS or status in DONE_STATUS_TERMS:
                continue
            title = document.title
            issues.append(
                JiraIssueCountRow(
                    document_id=document.id,
                    key=str(metadata.get("jira_issue_key") or title.split(":", 1)[0]),
                    summary=title.split(":", 1)[1].strip() if ":" in title else title,
                    status=str(metadata.get("jira_issue_status") or ""),
                )
            )

        return JiraIssueCountResult(
            assignee_label=email or name,
            issues=issues,
            chunks=await self._first_chunks_for_documents([issue.document_id for issue in issues]),
        )

    async def _first_chunks_for_documents(self, document_ids: list[uuid.UUID]) -> list[RetrievedChunk]:
        if not document_ids:
            return []

        chunk_rows = list(
            await self._db.scalars(
                select(Chunk)
                .where(Chunk.document_id.in_(document_ids), Chunk.is_active.is_(True))
                .order_by(Chunk.ordinal)
            )
        )
        seen: set[uuid.UUID] = set()
        by_document: dict[uuid.UUID, RetrievedChunk] = {}
        for chunk in chunk_rows:
            if chunk.document_id in seen:
                continue
            seen.add(chunk.document_id)
            document = await self._db.get(Document, chunk.document_id)
            document_metadata = (
                document.doc_metadata
                if document is not None and isinstance(document.doc_metadata, dict)
                else {}
            )
            by_document[chunk.document_id] = RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=document.title if document is not None else "Jira issue",
                content=chunk.content,
                metadata=document_metadata | (chunk.chunk_metadata or {}),
                score=1.0,
            )
        return [by_document[document_id] for document_id in document_ids if document_id in by_document]

    async def _persist_turn(
        self,
        *,
        conversation: Conversation,
        question: str,
        answer: str,
        chunks: list[RetrievedChunk],
        usage: LLMUsage,
        latency_ms: int,
        timings: dict[str, int],
        regenerate: bool,
        model: str | None = None,
    ) -> uuid.UUID:
        if not regenerate:
            self._messages.add(
                Message(
                    conversation_id=conversation.id,
                    role="user",
                    content=question,
                    created_at=utcnow(),
                )
            )
        assistant = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=latency_ms,
            timings=timings,
            model=model or self._llm.model,
            created_at=utcnow(),
        )
        self._messages.add(assistant)
        await self._db.flush()

        citations = extract_citations(answer, chunks)
        self._messages.add_citations(
            [
                Citation(
                    message_id=assistant.id,
                    chunk_id=c.chunk.chunk_id,
                    document_id=c.chunk.document_id,
                    marker=c.marker,
                    score=c.chunk.score,
                    snippet=c.snippet,
                )
                for c in citations
            ]
        )
        if conversation.title == "New conversation":
            await self._conversations.set_title(conversation.id, question[:TITLE_LEN])
        await self._db.commit()
        return assistant.id

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
        non_web_kbs = [kb for kb in kbs if kb.name != self._settings.web_search_default_kb_name]
        external_kbs = [kb for kb in non_web_kbs if kb.name != "Kimbal Local Runbook"]
        candidates = external_kbs or non_web_kbs or kbs

        if _contains_any(normalized, JIRA_TERMS):
            jira_kbs = [kb.id for kb in candidates if kb.name == self._settings.jira_default_kb_name]
            if jira_kbs:
                return jira_kbs

        if _contains_any(normalized, CONFLUENCE_TERMS):
            confluence_kbs = [
                kb.id for kb in candidates if kb.name == self._settings.confluence_default_kb_name
            ]
            if confluence_kbs:
                return confluence_kbs

        return [kb.id for kb in candidates]


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    normalized = value.lower()
    return any(needle in normalized for needle in needles)


async def _collect_llm_text(provider: LLMProvider, request: LLMRequest) -> tuple[str, LLMUsage]:
    parts: list[str] = []
    usage = LLMUsage()
    async for delta in provider.stream(request):
        if delta.text:
            parts.append(delta.text)
        if delta.done and delta.usage:
            usage = delta.usage
    return "".join(parts), usage


def _source_payload(marker: int, chunk: RetrievedChunk) -> dict[str, object]:
    metadata = chunk.metadata or {}
    source_type = str(metadata.get("source") or metadata.get("source_type") or "knowledge")
    snippet = chunk.content[:240]
    if source_type == "web" and isinstance(metadata.get("web_snippet"), str):
        snippet = str(metadata["web_snippet"])[:240]
    url = _source_url(metadata)
    payload: dict[str, object] = {
        "marker": marker,
        "chunk_id": str(chunk.chunk_id),
        "document_id": str(chunk.document_id),
        "title": chunk.document_title,
        "document_title": chunk.document_title,
        "score": round(chunk.score, 4),
        "snippet": snippet,
        "source_type": source_type,
    }
    if isinstance(url, str) and url:
        payload["url"] = url
    return payload


def _source_url(metadata: dict[str, object]) -> str | None:
    for key in (
        "source_url",
        "source-url",
        "web_url",
        "jira_issue_url",
        "jira_url",
        "confluence_page_url",
        "confluence_url",
    ):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _dedupe_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: set[uuid.UUID] = set()
    deduped: list[RetrievedChunk] = []
    for chunk in chunks:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        deduped.append(chunk)
    return deduped


def _confidence_from_chunks(chunks: list[RetrievedChunk]) -> float | None:
    if not chunks:
        return None
    score = sum(chunk.score for chunk in chunks) / len(chunks)
    return round(max(0.0, min(score, 1.0)), 4)


def _normalize_source_mode(value: str) -> str:
    return value if value in {"knowledge", "web", "blended"} else "knowledge"


def _normalize_answer_mode(value: str) -> str:
    return value if value in {"fast", "council"} else "fast"


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _council_api_key_and_base_url(settings: Settings) -> tuple[str, str]:
    api_key = settings.llm_council_api_key or settings.openrouter_api_key or settings.openai_api_key
    if settings.llm_council_base_url:
        base_url = settings.llm_council_base_url
    elif settings.llm_base_url:
        base_url = settings.llm_base_url
    elif settings.openrouter_api_key:
        base_url = "https://openrouter.ai/api/v1"
    else:
        base_url = "https://api.openai.com/v1"
    return api_key, base_url


DEFAULT_COUNCIL_MODELS = (
    "anthropic/claude-haiku-4.5",
    "openai/gpt-4.1-mini",
    "google/gemini-2.5-flash",
)


def llm_council_status(
    settings: Settings,
    *,
    requested_models: list[str] | None = None,
    requested_chair_model: str | None = None,
) -> CouncilStatus:
    available_models = _council_available_models(settings)
    models = _split_csv(settings.llm_council_models)
    if requested_models is not None:
        models = _normalize_requested_council_models(requested_models)
    elif not models and available_models:
        default_chair_model = settings.llm_council_chair_model.strip() or _best_chair_model([], available_models)
        models = [model for model in available_models if model != default_chair_model][:2]
    if requested_models is None:
        models = models[:2]
    chair_model = (
        (requested_chair_model or "").strip()
        or settings.llm_council_chair_model.strip()
        or _best_chair_model(models, available_models)
    )
    api_key, _base_url = _council_api_key_and_base_url(settings)
    if not settings.llm_council_enabled:
        return CouncilStatus(
            configured=False,
            models=models,
            available_models=available_models,
            chair_model=chair_model,
            reason="Set LLM_COUNCIL_ENABLED=true.",
        )
    if len(models) < 2:
        return CouncilStatus(
            configured=False,
            models=models,
            available_models=available_models,
            chair_model=None,
            reason="Select exactly two Council response models.",
        )
    if requested_models is not None and len(models) != 2:
        return CouncilStatus(
            configured=False,
            models=models,
            available_models=available_models,
            chair_model=chair_model,
            reason="Select exactly two Council response models.",
        )
    if requested_models is not None and any(model not in available_models for model in models):
        return CouncilStatus(
            configured=False,
            models=models,
            available_models=available_models,
            chair_model=chair_model,
            reason="One or more selected Council models are not allowed by LLM_COUNCIL_AVAILABLE_MODELS.",
        )
    if not chair_model or chair_model not in available_models:
        return CouncilStatus(
            configured=False,
            models=models,
            available_models=available_models,
            chair_model=chair_model,
            reason="Select one allowed Council evaluator model.",
        )
    if chair_model in models:
        return CouncilStatus(
            configured=False,
            models=models,
            available_models=available_models,
            chair_model=chair_model,
            reason="The Council evaluator model must be different from the two response models.",
        )
    if not api_key:
        return CouncilStatus(
            configured=False,
            models=models,
            available_models=available_models,
            chair_model=chair_model,
            reason="Set LLM_COUNCIL_API_KEY, OPENROUTER_API_KEY, or OPENAI_API_KEY.",
        )
    return CouncilStatus(
        configured=True,
        models=models,
        available_models=available_models,
        chair_model=chair_model,
        reason="configured",
    )


def _council_available_models(settings: Settings) -> list[str]:
    configured = _split_csv(settings.llm_council_available_models)
    base = configured or list(DEFAULT_COUNCIL_MODELS)
    extras = _split_csv(settings.llm_council_models)
    if settings.llm_model:
        extras.append(settings.llm_model)
    return _dedupe_model_ids([*base, *extras])


def _normalize_requested_council_models(models: list[str]) -> list[str]:
    return _dedupe_model_ids(model.strip() for model in models if model.strip())


def _dedupe_model_ids(models: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for model in models:
        if not isinstance(model, str):
            continue
        if model in seen:
            continue
        seen.add(model)
        deduped.append(model)
    return deduped


def _best_chair_model(models: list[str], available_models: list[str]) -> str | None:
    candidates = [model for model in available_models if model not in models]
    if not candidates:
        return None
    for preferred in ("anthropic/claude-haiku-4.5", "anthropic/claude-sonnet-4.5"):
        if preferred in candidates:
            return preferred
    return candidates[0]
