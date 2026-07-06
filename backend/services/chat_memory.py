import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from chat.citations import extract_citations
from database.base import utcnow
from llm.base import LLMUsage
from models import Citation, Conversation, Message
from repositories.conversations import ConversationRepository, MessageRepository
from retrieval.context import RetrievedChunk

TITLE_LEN = 80


class MemoryManager:
    """Persists and retrieves per-session conversational memory."""

    def __init__(self, db: AsyncSession, *, default_model: str) -> None:
        self._db = db
        self._default_model = default_model
        self._conversations = ConversationRepository(db)
        self._messages = MessageRepository(db)

    async def recent_history(
        self, conversation_id: uuid.UUID, *, limit: int, regenerate: bool = False
    ) -> list[Message]:
        history = await self._messages.recent_turns(conversation_id, limit)
        if regenerate and history and history[-1].role == "assistant":
            return history[:-1]
        return history

    async def list_messages(self, conversation_id: uuid.UUID, *, limit: int = 100) -> list[Message]:
        return await self._messages.list_for_conversation(conversation_id, limit=limit)

    async def clear_history(self, conversation_id: uuid.UUID) -> None:
        await self._messages.delete_for_conversation(conversation_id)
        await self._conversations.set_title(conversation_id, "New conversation")
        await self._db.commit()

    async def persist_turn(
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
            model=model or self._default_model,
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
