import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from models import Conversation, User
from repositories.conversations import ConversationRepository, MessageRepository


class ChatSessionManager:
    """Owns conversation/session lifecycle for a user's persisted chats."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._conversations = ConversationRepository(db)
        self._messages = MessageRepository(db)

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

    async def get_owned(self, conversation_id: uuid.UUID, user: User) -> Conversation | None:
        return await self._conversations.get_owned(conversation_id, user.id)

    async def list_for_user(self, user: User, *, limit: int = 50, offset: int = 0) -> list[Conversation]:
        return await self._conversations.list_for_user(user.id, limit=limit, offset=offset)

    async def delete(self, conversation_id: uuid.UUID) -> None:
        await self._conversations.soft_delete(conversation_id)
        await self._db.commit()

    async def clear_history(self, conversation_id: uuid.UUID) -> None:
        await self._messages.delete_for_conversation(conversation_id)
        await self._conversations.set_title(conversation_id, "New conversation")
        await self._db.commit()
