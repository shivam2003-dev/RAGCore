import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Citation, Conversation, Feedback, Message


class ConversationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add(self, conversation: Conversation) -> None:
        self.db.add(conversation)

    async def get_owned(self, conv_id: uuid.UUID, user_id: uuid.UUID) -> Conversation | None:
        return await self.db.scalar(
            select(Conversation).where(
                Conversation.id == conv_id,
                Conversation.user_id == user_id,
                Conversation.is_deleted.is_(False),
            )
        )

    async def list_for_user(
        self, user_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[Conversation]:
        rows = await self.db.scalars(
            select(Conversation)
            .where(Conversation.user_id == user_id, Conversation.is_deleted.is_(False))
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows)

    async def soft_delete(self, conv_id: uuid.UUID) -> None:
        await self.db.execute(
            update(Conversation).where(Conversation.id == conv_id).values(is_deleted=True)
        )

    async def set_title(self, conv_id: uuid.UUID, title: str) -> None:
        await self.db.execute(
            update(Conversation).where(Conversation.id == conv_id).values(title=title)
        )


class MessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add(self, message: Message) -> None:
        self.db.add(message)

    def add_citations(self, citations: list[Citation]) -> None:
        self.db.add_all(citations)

    async def get(self, message_id: uuid.UUID) -> Message | None:
        return await self.db.scalar(
            select(Message)
            .where(Message.id == message_id)
            .options(selectinload(Message.citations))
        )

    async def list_for_conversation(
        self, conv_id: uuid.UUID, limit: int = 100
    ) -> list[Message]:
        rows = await self.db.scalars(
            select(Message)
            .where(Message.conversation_id == conv_id)
            .options(selectinload(Message.citations))
            .order_by(Message.created_at)
            .limit(limit)
        )
        return list(rows)

    async def recent_turns(self, conv_id: uuid.UUID, limit: int = 10) -> list[Message]:
        rows = await self.db.scalars(
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(list(rows)))

    async def delete_for_conversation(self, conv_id: uuid.UUID) -> None:
        await self.db.execute(delete(Message).where(Message.conversation_id == conv_id))


class FeedbackRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add(self, feedback: Feedback) -> None:
        self.db.add(feedback)

    async def stats_for_org(self, org_id: uuid.UUID) -> dict[str, int]:
        stmt = (
            select(Feedback.rating, func.count())
            .join(Message, Message.id == Feedback.message_id)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.organization_id == org_id)
            .group_by(Feedback.rating)
        )
        rows = await self.db.execute(stmt)
        counts = dict(rows.all())
        return {"helpful": counts.get(1, 0), "not_helpful": counts.get(-1, 0)}
