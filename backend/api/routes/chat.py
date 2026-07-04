import json
import uuid

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from api.deps import ChatServiceDep, CurrentUser, DbDep
from api.schemas import AskRequest, ConversationCreate, ConversationOut, FeedbackCreate, MessageOut
from core.exceptions import AppError, NotFoundError
from database.base import utcnow
from models import Feedback
from repositories.conversations import (
    ConversationRepository,
    FeedbackRepository,
    MessageRepository,
)

router = APIRouter(tags=["chat"])


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate, user: CurrentUser, chat: ChatServiceDep
) -> ConversationOut:
    conversation = await chat.start_conversation(user, body.knowledge_base_id, body.title)
    return ConversationOut.model_validate(conversation)


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(user: CurrentUser, db: DbDep, limit: int = 50, offset: int = 0) -> list[ConversationOut]:
    convs = await ConversationRepository(db).list_for_user(user.id, limit=min(limit, 200), offset=offset)
    return [ConversationOut.model_validate(c) for c in convs]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: uuid.UUID, user: CurrentUser, db: DbDep
) -> list[MessageOut]:
    conv = await ConversationRepository(db).get_owned(conversation_id, user.id)
    if conv is None:
        raise NotFoundError("Conversation not found")
    messages = await MessageRepository(db).list_for_conversation(conversation_id)
    return [MessageOut.model_validate(m) for m in messages]


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: uuid.UUID, user: CurrentUser, db: DbDep) -> None:
    repo = ConversationRepository(db)
    conv = await repo.get_owned(conversation_id, user.id)
    if conv is None:
        raise NotFoundError("Conversation not found")
    await repo.soft_delete(conversation_id)
    await db.commit()


@router.post("/conversations/{conversation_id}/ask")
async def ask(
    conversation_id: uuid.UUID, body: AskRequest, user: CurrentUser, chat: ChatServiceDep
) -> EventSourceResponse:
    """Streamed RAG answer. SSE events: sources → delta* → done."""

    async def event_stream():  # type: ignore[no-untyped-def]
        try:
            async for event in chat.ask(
                user=user,
                conversation_id=conversation_id,
                question=body.question,
                regenerate=body.regenerate,
            ):
                yield {"event": event.type, "data": json.dumps(event.data)}
        except AppError as exc:
            # response already started — surface failure as a terminal SSE event
            yield {"event": "error", "data": json.dumps({"code": exc.code, "message": exc.message})}

    return EventSourceResponse(event_stream())


@router.post("/feedback", status_code=201)
async def submit_feedback(body: FeedbackCreate, user: CurrentUser, db: DbDep) -> dict[str, str]:
    message = await MessageRepository(db).get(body.message_id)
    if message is None:
        raise NotFoundError("Message not found")
    conv = await ConversationRepository(db).get_owned(message.conversation_id, user.id)
    if conv is None:
        raise NotFoundError("Message not found")
    FeedbackRepository(db).add(
        Feedback(
            message_id=body.message_id,
            user_id=user.id,
            rating=body.rating,
            comment=body.comment,
            created_at=utcnow(),
        )
    )
    await db.commit()
    return {"status": "recorded"}
