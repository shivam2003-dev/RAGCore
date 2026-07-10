import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from api.deps import ChatServiceDep, CurrentUser, DbDep, LLMDep, SettingsDep
from api.schemas import (
    AskRequest,
    ChatCapabilitiesOut,
    ConversationCreate,
    ConversationOut,
    FeedbackCreate,
    MessageOut,
    RoleGenerateRequest,
    RoleGenerateResponse,
)
from core.exceptions import AppError, NotFoundError, ProviderError
from database.base import utcnow
from llm.base import ChatMessage, LLMProvider, LLMRequest
from models import Document, Feedback, KnowledgeBase, Message
from repositories.conversations import (
    ConversationRepository,
    FeedbackRepository,
    MessageRepository,
)
from services.chat_service import llm_council_status

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


@router.get("/chat/capabilities", response_model=ChatCapabilitiesOut)
async def chat_capabilities(_user: CurrentUser, settings: SettingsDep) -> ChatCapabilitiesOut:
    status = llm_council_status(settings)
    return ChatCapabilitiesOut(
        answer_modes=["fast", "council"],
        council_configured=status.configured,
        council_models=status.models,
        council_available_models=status.available_models,
        council_chair_model=status.chair_model,
        council_reason=status.reason,
    )


@router.post("/chat/roles/generate", response_model=RoleGenerateResponse)
async def generate_role_prompt(
    body: RoleGenerateRequest, _user: CurrentUser, llm: LLMDep
) -> RoleGenerateResponse:
    system = (
        "You are the CVUM role prompt generator. Return valid JSON only with keys "
        '"name" and "prompt". Build a safe background role prompt for an enterprise '
        "RAG assistant. The role may guide persona, source preference, workflow, and "
        "format, but it must never override RBAC, citation, source-grounding, secret "
        "handling, PII, or security rules. Keep prompt under 1700 characters."
    )
    payload = {
        "name": body.name,
        "goal": body.goal,
        "source_focus": body.source_focus,
        "output_style": body.output_style,
    }
    raw = await _collect_llm_text(
        llm,
        LLMRequest(
            system=system,
            messages=[
                ChatMessage(
                    role="user",
                    content=f"Create a reusable role prompt from this JSON:\n{json.dumps(payload)}",
                )
            ],
            max_tokens=650,
            temperature=0.2,
        ),
    )
    name, prompt = _parse_role_generation(raw=raw, fallback_name=body.name)
    return RoleGenerateResponse(name=name, prompt=prompt)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: uuid.UUID, user: CurrentUser, db: DbDep
) -> list[MessageOut]:
    conv = await ConversationRepository(db).get_owned(conversation_id, user.id)
    if conv is None:
        raise NotFoundError("Conversation not found")
    messages = await MessageRepository(db).list_for_conversation(conversation_id)
    document_ids = {
        citation.document_id
        for message in messages
        for citation in message.citations
    }
    docs_by_id: dict[uuid.UUID, Document] = {}
    if document_ids:
        rows = await db.scalars(
            select(Document)
            .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
            .where(
                Document.id.in_(document_ids),
                KnowledgeBase.organization_id == user.organization_id,
            )
        )
        docs_by_id = {doc.id: doc for doc in rows}
    return [_message_out(message, docs_by_id) for message in messages]


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: uuid.UUID, user: CurrentUser, db: DbDep) -> None:
    repo = ConversationRepository(db)
    conv = await repo.get_owned(conversation_id, user.id)
    if conv is None:
        raise NotFoundError("Conversation not found")
    await repo.soft_delete(conversation_id)
    await db.commit()


@router.delete("/conversations/{conversation_id}/messages", status_code=204)
async def clear_conversation_history(
    conversation_id: uuid.UUID, user: CurrentUser, chat: ChatServiceDep
) -> None:
    await chat.clear_history(user=user, conversation_id=conversation_id)


@router.post("/conversations/{conversation_id}/ask")
async def ask(
    conversation_id: uuid.UUID, body: AskRequest, user: CurrentUser, chat: ChatServiceDep
) -> EventSourceResponse:
    """Streamed RAG answer. SSE events: sources → delta* → done."""

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        try:
            async for event in chat.ask(
                user=user,
                conversation_id=conversation_id,
                question=body.question,
                regenerate=body.regenerate,
                source_mode=body.source_mode,
                answer_mode=body.answer_mode,
                assistant_role=body.assistant_role,
                assistant_role_prompt=body.assistant_role_prompt,
                council_models=body.council_models,
                council_chair_model=body.council_chair_model,
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


def _message_out(message: Message, docs_by_id: dict[uuid.UUID, Document]) -> MessageOut:
    output = MessageOut.model_validate(message)
    citations = []
    for citation in message.citations:
        doc = docs_by_id.get(citation.document_id)
        citation_out = output.citations[len(citations)]
        if doc is not None:
            citation_out = citation_out.model_copy(
                update={
                    "document_title": doc.title,
                    "title": doc.title,
                    "source_type": _citation_source_type(doc),
                    "url": _document_source_url(doc),
                }
            )
        citations.append(citation_out)
    return output.model_copy(update={"citations": citations})


async def _collect_llm_text(llm: LLMProvider, request: LLMRequest) -> str:
    parts: list[str] = []
    async for delta in llm.stream(request):
        if delta.text:
            parts.append(delta.text)
    return "".join(parts).strip()


def _parse_role_generation(*, raw: str, fallback_name: str) -> tuple[str, str]:
    text = raw.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ProviderError("Role generator returned invalid JSON") from None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ProviderError("Role generator returned invalid JSON") from exc

    if not isinstance(parsed, dict):
        raise ProviderError("Role generator returned invalid JSON")
    name = str(parsed.get("name") or fallback_name).strip()[:80]
    prompt = str(parsed.get("prompt") or "").strip()[:1800]
    if not name or not prompt:
        raise ProviderError("Role generator returned an empty role prompt")
    return name, prompt


def _citation_source_type(doc: Document) -> str:
    source = doc.doc_metadata.get("source") if isinstance(doc.doc_metadata, dict) else None
    return str(source or doc.source_type)


def _document_source_url(doc: Document) -> str | None:
    metadata = doc.doc_metadata if isinstance(doc.doc_metadata, dict) else {}
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
