"""Chat orchestration: retrieval → prompt → streamed generation → persistence.

Yields typed SSE events; the router only serializes them.
"""

import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from chat.citations import extract_citations
from chat.prompts import build_system_prompt
from core.config import Settings
from core.exceptions import NotFoundError
from database.base import utcnow
from llm.base import ChatMessage, LLMProvider, LLMRequest, LLMUsage
from models import Citation, Conversation, Message, User
from repositories.conversations import ConversationRepository, MessageRepository
from retrieval.context import RetrievalContext, RetrievedChunk
from retrieval.pipeline import RetrievalPipeline

HISTORY_TURNS = 8
TITLE_LEN = 80


@dataclass(slots=True)
class ChatEvent:
    type: str  # "sources" | "delta" | "done" | "error"
    data: dict


class ChatService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        retrieval: RetrievalPipeline,
        llm: LLMProvider,
        settings: Settings,
    ) -> None:
        self._db = db
        self._conversations = ConversationRepository(db)
        self._messages = MessageRepository(db)
        self._retrieval = retrieval
        self._llm = llm
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
    ) -> AsyncIterator[ChatEvent]:
        started = time.perf_counter()
        conversation = await self._conversations.get_owned(conversation_id, user.id)
        if conversation is None:
            raise NotFoundError("Conversation not found")

        history = await self._messages.recent_turns(conversation_id, HISTORY_TURNS)
        if regenerate and history and history[-1].role == "assistant":
            history = history[:-1]

        ctx = RetrievalContext(
            kb_id=conversation.knowledge_base_id,
            query=question,
            top_k=self._settings.retrieval_top_k,
            conversation_context="\n".join(m.content[:500] for m in history[-4:]),
        )
        ctx = await self._retrieval.run(ctx)

        yield ChatEvent(
            type="sources",
            data={
                "sources": [
                    {
                        "marker": i + 1,
                        "chunk_id": str(c.chunk_id),
                        "document_id": str(c.document_id),
                        "title": c.document_title,
                        "score": round(c.score, 4),
                        "snippet": c.content[:240],
                    }
                    for i, c in enumerate(ctx.chunks)
                ],
                "confidence": ctx.confidence,
            },
        )

        request = LLMRequest(
            system=build_system_prompt(ctx.chunks),
            messages=[
                *(ChatMessage(role=m.role, content=m.content) for m in history),
                ChatMessage(role="user", content=question),
            ],
            max_tokens=self._settings.llm_max_output_tokens,
        )

        llm_started = time.perf_counter()
        answer_parts: list[str] = []
        usage = LLMUsage()
        async for delta in self._llm.stream(request):
            if delta.text:
                answer_parts.append(delta.text)
                yield ChatEvent(type="delta", data={"text": delta.text})
            if delta.done and delta.usage:
                usage = delta.usage
        ctx.timings_ms["llm"] = int((time.perf_counter() - llm_started) * 1000)

        answer = "".join(answer_parts)
        latency_ms = int((time.perf_counter() - started) * 1000)
        message_id = await self._persist_turn(
            conversation=conversation,
            question=question,
            answer=answer,
            chunks=ctx.chunks,
            usage=usage,
            latency_ms=latency_ms,
            timings=ctx.timings_ms,
            regenerate=regenerate,
        )

        yield ChatEvent(
            type="done",
            data={
                "message_id": str(message_id),
                "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
                "latency_ms": latency_ms,
                "timings_ms": ctx.timings_ms,
                "model": self._llm.model,
            },
        )

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
            model=self._llm.model,
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
