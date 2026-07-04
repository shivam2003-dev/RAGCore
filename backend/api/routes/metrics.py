import uuid

from fastapi import APIRouter
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import CurrentUser, DbDep
from api.schemas import (
    ActivityMetricOut,
    FeedbackMetricOut,
    MetricsOverviewOut,
    QuestionMetricOut,
    SourceMetricOut,
)
from models import AuditLog, Chunk, Conversation, Document, DocumentStatus, Feedback, KnowledgeBase, Message, User

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/overview", response_model=MetricsOverviewOut)
async def metrics_overview(user: CurrentUser, db: DbDep) -> MetricsOverviewOut:
    org_id = user.organization_id

    kb_count = await db.scalar(
        select(func.count(KnowledgeBase.id)).where(KnowledgeBase.organization_id == org_id)
    ) or 0

    doc_counts = (
        await db.execute(
            select(
                func.count(Document.id),
                func.sum(case((Document.status == DocumentStatus.READY, 1), else_=0)),
                func.sum(
                    case(
                        (Document.status.in_([DocumentStatus.PROCESSING, DocumentStatus.UPLOADED]), 1),
                        else_=0,
                    )
                ),
                func.sum(case((Document.status == DocumentStatus.FAILED, 1), else_=0)),
            )
            .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
            .where(KnowledgeBase.organization_id == org_id, Document.is_deleted.is_(False))
        )
    ).one()

    chunks_active = await db.scalar(
        select(func.count(Chunk.id))
        .join(KnowledgeBase, KnowledgeBase.id == Chunk.knowledge_base_id)
        .where(KnowledgeBase.organization_id == org_id, Chunk.is_active.is_(True))
    ) or 0

    conv_count = await db.scalar(
        select(func.count(Conversation.id)).where(
            Conversation.organization_id == org_id,
            Conversation.is_deleted.is_(False),
        )
    ) or 0

    message_counts = (
        await db.execute(
            select(
                func.sum(case((Message.role == "user", 1), else_=0)),
                func.sum(case((Message.role == "assistant", 1), else_=0)),
                func.avg(Message.latency_ms).filter(Message.role == "assistant"),
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.organization_id == org_id, Conversation.is_deleted.is_(False))
        )
    ).one()

    active_users = await db.scalar(
        select(func.count(User.id)).where(User.organization_id == org_id, User.is_active.is_(True))
    ) or 0

    feedback_counts = (
        await db.execute(
            select(
                func.sum(case((Feedback.rating == 1, 1), else_=0)),
                func.sum(case((Feedback.rating == -1, 1), else_=0)),
            )
            .join(Message, Message.id == Feedback.message_id)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.organization_id == org_id, Conversation.is_deleted.is_(False))
        )
    ).one()
    helpful = int(feedback_counts[0] or 0)
    not_helpful = int(feedback_counts[1] or 0)
    feedback_total = helpful + not_helpful

    sources = await _source_metrics(db, org_id)
    recent_activity = await _recent_activity(db, org_id)
    top_questions = await _top_questions(db, org_id)

    return MetricsOverviewOut(
        knowledge_bases=int(kb_count),
        documents_total=int(doc_counts[0] or 0),
        documents_ready=int(doc_counts[1] or 0),
        documents_processing=int(doc_counts[2] or 0),
        documents_failed=int(doc_counts[3] or 0),
        chunks_active=int(chunks_active),
        conversations=int(conv_count),
        questions_asked=int(message_counts[0] or 0),
        assistant_answers=int(message_counts[1] or 0),
        active_users=int(active_users),
        avg_latency_ms=int(message_counts[2]) if message_counts[2] is not None else None,
        feedback=FeedbackMetricOut(
            helpful=helpful,
            not_helpful=not_helpful,
            total=feedback_total,
            helpful_rate=(helpful / feedback_total) if feedback_total else None,
        ),
        sources=sources,
        recent_activity=recent_activity,
        top_questions=top_questions,
    )


async def _source_metrics(db: AsyncSession, org_id: uuid.UUID) -> list[SourceMetricOut]:
    source_expr = func.coalesce(Document.doc_metadata["source"].as_string(), Document.source_type)
    rows = await db.execute(
        select(
            source_expr.label("source"),
            Document.source_type,
            func.count(Document.id),
            func.sum(case((Document.status == DocumentStatus.READY, 1), else_=0)),
            func.sum(case((Document.status == DocumentStatus.FAILED, 1), else_=0)),
            func.max(Document.updated_at),
        )
        .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
        .where(KnowledgeBase.organization_id == org_id, Document.is_deleted.is_(False))
        .group_by(source_expr, Document.source_type)
        .order_by(desc(func.count(Document.id)))
    )
    return [
        SourceMetricOut(
            name=_source_label(str(row[0] or row[1] or "unknown")),
            source_type=str(row[1] or "unknown"),
            documents=int(row[2] or 0),
            ready_documents=int(row[3] or 0),
            failed_documents=int(row[4] or 0),
            last_updated_at=row[5],
        )
        for row in rows
    ]


async def _recent_activity(db: AsyncSession, org_id: uuid.UUID) -> list[ActivityMetricOut]:
    rows = await db.scalars(
        select(AuditLog)
        .where(AuditLog.organization_id == org_id)
        .order_by(AuditLog.created_at.desc())
        .limit(8)
    )
    return [
        ActivityMetricOut(
            action=row.action,
            resource_type=row.resource_type,
            detail=row.detail,
            created_at=row.created_at,
        )
        for row in rows
    ]


async def _top_questions(db: AsyncSession, org_id: uuid.UUID) -> list[QuestionMetricOut]:
    rows = await db.execute(
        select(Message.content, func.count(Message.id), func.max(Message.created_at))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.organization_id == org_id,
            Conversation.is_deleted.is_(False),
            Message.role == "user",
        )
        .group_by(Message.content)
        .order_by(desc(func.count(Message.id)), desc(func.max(Message.created_at)))
        .limit(10)
    )
    return [
        QuestionMetricOut(
            question=str(row[0]),
            count=int(row[1] or 0),
            last_asked_at=row[2],
        )
        for row in rows
    ]


def _source_label(value: str) -> str:
    labels = {
        "confluence": "Confluence",
        "jira": "Jira",
        "md": "Markdown uploads",
        "txt": "Text uploads",
        "pdf": "PDF uploads",
        "docx": "Word uploads",
        "csv": "CSV uploads",
        "html": "HTML uploads",
    }
    return labels.get(value.lower(), value.replace("_", " ").title())
