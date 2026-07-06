"""Chat orchestration: retrieval → prompt → streamed generation → persistence.

Yields typed SSE events; the router only serializes them.
"""

import re
import time
import uuid
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

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
from retrieval.context import RetrievedChunk
from retrieval.pipeline import RetrievalPipeline
from services.chat_memory import MemoryManager
from services.chat_sessions import ChatSessionManager
from services.conversational_retriever import ConversationalRetriever
from services.question_rewriter import QuestionRewriter
from services.response_generator import ResponseGenerator
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
    filter_label: str
    issues: list[JiraIssueCountRow]
    chunks: list[RetrievedChunk]
    counted_total: int


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
        self._sessions = ChatSessionManager(db)
        self._memory = MemoryManager(db, default_model=llm.model)
        self._question_rewriter = QuestionRewriter(llm)
        self._conversation_retriever = ConversationalRetriever(
            db=db,
            retrieval=retrieval,
            web_search=web_search,
            settings=settings,
        )
        self._response_generator = ResponseGenerator(llm=llm, settings=settings)

    async def start_conversation(self, user: User, kb_id: uuid.UUID, title: str | None) -> Conversation:
        return await self._sessions.start_conversation(user, kb_id, title)

    async def clear_history(self, *, user: User, conversation_id: uuid.UUID) -> None:
        conversation = await self._sessions.get_owned(conversation_id, user)
        if conversation is None:
            raise NotFoundError("Conversation not found")
        await self._memory.clear_history(conversation_id)

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
        conversation = await self._sessions.get_owned(conversation_id, user)
        if conversation is None:
            raise NotFoundError("Conversation not found")

        history = await self._memory.recent_history(
            conversation_id,
            limit=HISTORY_TURNS,
            regenerate=regenerate,
        )
        rewrite_started = time.perf_counter()
        standalone_question = await self._question_rewriter.rewrite(
            history=history,
            question=question,
        )
        rewrite_ms = int((time.perf_counter() - rewrite_started) * 1000)

        if source_mode != "web":
            jira_count = await self._jira_structured_count(
                org_id=user.organization_id,
                question=standalone_question or question,
            )
            if jira_count is not None:
                async for event in self._stream_jira_count_answer(
                    conversation=conversation,
                    question=question,
                    standalone_question=standalone_question,
                    chunks=jira_count.chunks,
                    assignee_label=jira_count.assignee_label,
                    filter_label=jira_count.filter_label,
                    issues=jira_count.issues,
                    counted_total=jira_count.counted_total,
                    started=started,
                    regenerate=regenerate,
                    source_mode=source_mode,
                ):
                    yield event
                return

        retrieval = await self._conversation_retriever.retrieve(
            user=user,
            conversation=conversation,
            current_question=question,
            standalone_question=standalone_question,
            history=history,
            source_mode=source_mode,
            assistant_role=assistant_role,
            assistant_role_prompt=assistant_role_prompt,
        )
        chunks = retrieval.chunks
        timings_ms = {"question_rewrite": rewrite_ms, **retrieval.timings_ms}
        confidence = retrieval.confidence

        yield ChatEvent(
            type="sources",
            data={
                "sources": [_source_payload(i + 1, c) for i, c in enumerate(chunks)],
                "confidence": confidence,
                "source_mode": source_mode,
                "answer_mode": answer_mode,
                "standalone_question": standalone_question,
                "subqueries": retrieval.subqueries,
                "retrieval_attempts": retrieval.attempts,
                "quality_notes": retrieval.quality_notes,
                "weak_internal_retrieval": retrieval.weak_internal_retrieval,
            },
        )

        if _should_refuse_for_weak_retrieval(
            source_mode=source_mode,
            chunks=chunks,
            weak_internal_retrieval=retrieval.weak_internal_retrieval,
        ):
            async for event in self._stream_weak_retrieval_answer(
                conversation=conversation,
                question=question,
                standalone_question=standalone_question,
                chunks=chunks,
                started=started,
                timings_ms=timings_ms,
                regenerate=regenerate,
                source_mode=source_mode,
                answer_mode=answer_mode,
            ):
                yield event
            return

        llm_started = time.perf_counter()
        answer_parts: list[str] = []
        usage = LLMUsage()
        model = self._llm.model
        async for delta in self._response_generator.stream(
            chunks=chunks,
            history=history,
            current_question=question,
            standalone_question=standalone_question,
            answer_mode=answer_mode,
            assistant_role=assistant_role,
            assistant_role_prompt=assistant_role_prompt,
            council_models=council_models,
            council_chair_model=council_chair_model,
        ):
            if delta.text:
                answer_parts.append(delta.text)
                yield ChatEvent(type="delta", data={"text": delta.text})
            if delta.done:
                usage = delta.usage or usage
                model = delta.model or model
        timings_ms["llm"] = int((time.perf_counter() - llm_started) * 1000)

        answer = _verify_and_shape_answer("".join(answer_parts), chunks)
        latency_ms = int((time.perf_counter() - started) * 1000)
        message_id = await self._memory.persist_turn(
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
                "standalone_question": standalone_question,
                "verification": _verification_summary(answer, chunks),
            },
        )

    async def _stream_jira_count_answer(
        self,
        *,
        conversation: Conversation,
        question: str,
        standalone_question: str,
        chunks: list[RetrievedChunk],
        assignee_label: str,
        filter_label: str,
        issues: list[JiraIssueCountRow],
        counted_total: int,
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
                "standalone_question": standalone_question,
            },
        )

        if counted_total:
            plural = "s" if counted_total != 1 else ""
            lines = [
                f"Indexed Jira has **{counted_total} issue{plural}** matching {filter_label}.",
                "This count is computed from Jira document metadata, not inferred from chunk text.",
                "",
            ]
            marker_by_document = {chunk.document_id: index for index, chunk in enumerate(chunks, start=1)}
            for index, issue in enumerate(issues[:10], start=1):
                marker = marker_by_document.get(issue.document_id)
                citation = f" [{marker}]" if marker is not None else ""
                lines.append(
                    f"{index}. **{issue.key}** - {issue.summary} - Status: {issue.status or 'Unknown'}{citation}"
                )
            if counted_total > len(issues[:10]):
                lines.append(f"...and {counted_total - len(issues[:10])} more matching Jira issues.")
        else:
            lines = [
                f"Indexed Jira has **0 issues** matching {filter_label}.",
                "",
                "I counted indexed Jira issue records using stored structured metadata.",
            ]

        answer = "\n".join(lines)
        yield ChatEvent(type="delta", data={"text": answer})

        latency_ms = int((time.perf_counter() - started) * 1000)
        timings = {"jira_count": latency_ms}
        message_id = await self._memory.persist_turn(
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
                "standalone_question": standalone_question,
            },
        )

    async def _stream_weak_retrieval_answer(
        self,
        *,
        conversation: Conversation,
        question: str,
        standalone_question: str,
        chunks: list[RetrievedChunk],
        started: float,
        timings_ms: dict[str, int],
        regenerate: bool,
        source_mode: str,
        answer_mode: str,
    ) -> AsyncIterator[ChatEvent]:
        answer = (
            "I can't answer that from the current internal sources with enough confidence.\n\n"
            "Try narrowing the question to a Jira project, Confluence space, runbook title, "
            "or issue key. Use Web or Both only when you want external web evidence included."
        )
        yield ChatEvent(type="delta", data={"text": answer})
        latency_ms = int((time.perf_counter() - started) * 1000)
        timings = {**timings_ms, "weak_retrieval_refusal": latency_ms}
        message_id = await self._memory.persist_turn(
            conversation=conversation,
            question=question,
            answer=answer,
            chunks=chunks,
            usage=LLMUsage(),
            latency_ms=latency_ms,
            timings=timings,
            regenerate=regenerate,
            model="deterministic-retrieval-gate",
        )
        yield ChatEvent(
            type="done",
            data={
                "message_id": str(message_id),
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "latency_ms": latency_ms,
                "timings_ms": timings,
                "model": "deterministic-retrieval-gate",
                "source_mode": source_mode,
                "answer_mode": answer_mode,
                "standalone_question": standalone_question,
                "verification": {"grounded": True, "unsupported_claim_rate": 0.0, "invalid_citations": []},
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

    async def _jira_structured_count(
        self,
        *,
        org_id: uuid.UUID,
        question: str,
    ) -> JiraIssueCountResult | None:
        normalized = question.lower()
        if not (_contains_any(normalized, JIRA_TERMS) and _contains_any(normalized, COUNT_TERMS)):
            return None

        email_match = EMAIL_RE.search(question)
        email = email_match.group(0).lower() if email_match else ""
        name_match = re.search(r"\(([^)]+)\)", question)
        name = name_match.group(1).strip().lower() if name_match else ""
        project_key = _jira_project_filter(normalized)
        open_only = "open" in normalized or "active" in normalized or "pending" in normalized
        status_filter = _jira_status_filter(normalized)
        if not any([email, name, project_key, open_only, status_filter]):
            return None

        stmt = (
            select(Document)
            .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
            .where(
                KnowledgeBase.organization_id == org_id,
                Document.is_deleted.is_(False),
                Document.doc_metadata["source"].as_string() == "jira",
            )
            .order_by(Document.title)
        )
        documents = list(await self._db.scalars(stmt))
        issues: list[JiraIssueCountRow] = []
        for document in documents:
            metadata = document.doc_metadata or {}
            if metadata.get("source") != "jira":
                continue
            issue_key = str(metadata.get("jira_issue_key") or document.title.split(":", 1)[0]).upper()
            document_project = str(metadata.get("jira_project_key") or issue_key.split("-", 1)[0]).upper()
            if project_key and document_project != project_key:
                continue
            assignee_email = str(metadata.get("jira_assignee_email") or "").lower()
            assignee_name = str(metadata.get("jira_assignee") or "").lower()
            if email and assignee_email != email:
                continue
            if not email and name and assignee_name != name:
                continue
            category = str(metadata.get("jira_issue_status_category_key") or "").lower()
            status = str(metadata.get("jira_issue_status") or "").lower()
            if open_only and (category in DONE_STATUS_TERMS or status in DONE_STATUS_TERMS):
                continue
            if status_filter and status_filter not in status:
                continue
            title = document.title
            issues.append(
                JiraIssueCountRow(
                    document_id=document.id,
                    key=issue_key,
                    summary=title.split(":", 1)[1].strip() if ":" in title else title,
                    status=str(metadata.get("jira_issue_status") or ""),
                )
            )

        filter_bits: list[str] = []
        if project_key:
            filter_bits.append(f"project={project_key}")
        if open_only:
            filter_bits.append("status category not done")
        if status_filter:
            filter_bits.append(f"status contains '{status_filter}'")
        if email or name:
            filter_bits.append(f"assignee={email or name}")
        filter_label = ", ".join(filter_bits) if filter_bits else "the Jira filters in the question"

        return JiraIssueCountResult(
            assignee_label=email or name or "the requested Jira filter",
            filter_label=filter_label,
            issues=issues,
            chunks=await self._first_chunks_for_documents([issue.document_id for issue in issues[:10]]),
            counted_total=len(issues),
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
    source_updated_at = _source_updated_at(metadata)
    payload: dict[str, object] = {
        "marker": marker,
        "chunk_id": str(chunk.chunk_id),
        "document_id": str(chunk.document_id),
        "title": chunk.document_title,
        "document_title": chunk.document_title,
        "score": round(chunk.score, 4),
        "snippet": snippet,
        "source_type": source_type,
        "source_updated_at": source_updated_at,
        "freshness_label": _freshness_label(source_updated_at),
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


def _source_updated_at(metadata: dict[str, object]) -> str | None:
    for key in (
        "source_updated_at",
        "jira_issue_updated_at",
        "jira_updated_at",
        "confluence_version_created_at",
        "updated_at",
    ):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _freshness_label(value: str | None) -> str:
    if not value:
        return "undated"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "undated"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    age_days = max(0, (datetime.now(UTC) - parsed).days)
    if age_days <= 30:
        return "fresh"
    if age_days <= 180:
        return "aging"
    return "stale"


def _should_refuse_for_weak_retrieval(
    *,
    source_mode: str,
    chunks: list[RetrievedChunk],
    weak_internal_retrieval: bool,
) -> bool:
    if source_mode == "web":
        return False
    if source_mode == "blended" and any(_chunk_source_type(chunk) == "web" for chunk in chunks):
        return False
    return weak_internal_retrieval


def _verify_and_shape_answer(answer: str, chunks: list[RetrievedChunk]) -> str:
    clean = _remove_invalid_citation_markers(answer.strip(), len(chunks))
    if not clean:
        return "I couldn't generate an answer from the retrieved sources."
    if _is_refusal(clean) or not chunks:
        return clean
    if not _valid_citation_markers(clean, len(chunks)):
        markers = " ".join(f"[{index}]" for index in range(1, min(len(chunks), 3) + 1))
        clean = f"{clean}\n\nSources: {markers}"
    unsupported_rate = _unsupported_claim_rate(clean, len(chunks))
    if unsupported_rate > 0.65:
        markers = " ".join(f"[{index}]" for index in range(1, min(len(chunks), 3) + 1))
        return (
            "I found relevant sources, but the drafted answer was not grounded tightly enough to save as final.\n\n"
            f"Review the top retrieved sources instead: {markers}"
        )
    return _compact_answer(clean)


def _verification_summary(answer: str, chunks: list[RetrievedChunk]) -> dict[str, object]:
    invalid = _invalid_citation_markers(answer, len(chunks))
    has_grounding = _is_refusal(answer) or bool(_valid_citation_markers(answer, len(chunks))) or not chunks
    return {
        "grounded": not invalid and has_grounding,
        "unsupported_claim_rate": _unsupported_claim_rate(answer, len(chunks)),
        "invalid_citations": invalid,
    }


def _remove_invalid_citation_markers(answer: str, source_count: int) -> str:
    invalid = set(_invalid_citation_markers(answer, source_count))
    if not invalid:
        return answer
    pattern = re.compile(r"\[(\d+)\]")
    return pattern.sub(lambda match: "" if int(match.group(1)) in invalid else match.group(0), answer)


def _invalid_citation_markers(answer: str, source_count: int) -> list[int]:
    markers = [int(value) for value in re.findall(r"\[(\d+)\]", answer)]
    return sorted({marker for marker in markers if marker < 1 or marker > source_count})


def _valid_citation_markers(answer: str, source_count: int) -> list[int]:
    markers = [int(value) for value in re.findall(r"\[(\d+)\]", answer)]
    return sorted({marker for marker in markers if 1 <= marker <= source_count})


def _unsupported_claim_rate(answer: str, source_count: int) -> float:
    if source_count <= 0 or _is_refusal(answer):
        return 0.0
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", answer)
        if len(sentence.split()) >= 7 and not sentence.strip().startswith(("Sources:", "-"))
    ]
    if not sentences:
        return 0.0
    unsupported = sum(1 for sentence in sentences if not _valid_citation_markers(sentence, source_count))
    return round(unsupported / len(sentences), 4)


def _compact_answer(answer: str) -> str:
    lines = [line.rstrip() for line in answer.splitlines()]
    compact: list[str] = []
    blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and blank:
            continue
        compact.append(line)
        blank = is_blank
    return "\n".join(compact).strip()


def _is_refusal(answer: str) -> bool:
    normalized = answer.lower()
    return "can't answer" in normalized or "cannot answer" in normalized or "do not contain" in normalized


def _chunk_source_type(chunk: RetrievedChunk) -> str:
    metadata = chunk.metadata or {}
    return str(metadata.get("source") or metadata.get("source_type") or "knowledge").lower()


def _jira_project_filter(normalized_question: str) -> str | None:
    if re.search(r"\bcvir\b", normalized_question):
        return "CVIR"
    if re.search(r"\bdevo\b|\bdevops\b", normalized_question):
        return "DEVO"
    match = re.search(r"\b([A-Z][A-Z0-9]{1,9})-\d+\b", normalized_question.upper())
    return match.group(1) if match else None


def _jira_status_filter(normalized_question: str) -> str | None:
    for status in ("to do", "in progress", "done", "closed", "resolved", "blocked", "reopened"):
        if status in normalized_question:
            return status
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
