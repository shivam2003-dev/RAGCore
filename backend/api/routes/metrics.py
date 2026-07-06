import re
import uuid

from fastapi import APIRouter
from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import CurrentUser, DbDep, require_role
from api.schemas import (
    ActivityMetricOut,
    ConnectorRunOut,
    FeedbackMetricOut,
    MetricsOverviewOut,
    QuestionMetricOut,
    SourceMetricOut,
)
from models import AuditLog, Chunk, Conversation, Document, DocumentStatus, Feedback, KnowledgeBase, Message, Role, User

router = APIRouter(prefix="/metrics", tags=["metrics"], dependencies=[require_role(Role.ADMIN)])
RUN_DETAIL_RE = re.compile(r"(?P<value>\d+)\s+(?P<name>created|updated|skipped|failed)")


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
    connector_runs = await _connector_runs(db, org_id)
    runs_by_kb = {str(run.knowledge_base_id): run for run in connector_runs if run.knowledge_base_id}
    sources = [
        source.model_copy(
            update={
                "last_run_at": runs_by_kb.get(str(source.knowledge_base_id)).created_at
                if source.knowledge_base_id and runs_by_kb.get(str(source.knowledge_base_id))
                else None,
                "last_run_detail": runs_by_kb.get(str(source.knowledge_base_id)).detail
                if source.knowledge_base_id and runs_by_kb.get(str(source.knowledge_base_id))
                else None,
            }
        )
        for source in sources
    ]
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
        connector_runs=connector_runs,
        recent_activity=recent_activity,
        top_questions=top_questions,
    )


async def _source_metrics(db: AsyncSession, org_id: uuid.UUID) -> list[SourceMetricOut]:
    source_expr = func.coalesce(Document.doc_metadata["source"].as_string(), Document.source_type)
    rows = await db.execute(
        select(
            KnowledgeBase.id,
            KnowledgeBase.name,
            source_expr.label("source"),
            func.count(func.distinct(Document.id)),
            func.count(func.distinct(case((Document.status == DocumentStatus.READY, Document.id)))),
            func.count(func.distinct(case((Document.status == DocumentStatus.UPLOADED, Document.id)))),
            func.count(func.distinct(case((Document.status == DocumentStatus.PROCESSING, Document.id)))),
            func.count(func.distinct(case((Document.status == DocumentStatus.FAILED, Document.id)))),
            func.count(Chunk.id),
            func.max(Document.updated_at),
            func.max(Chunk.created_at),
        )
        .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
        .outerjoin(
            Chunk,
            and_(Chunk.document_id == Document.id, Chunk.is_active.is_(True)),
        )
        .where(KnowledgeBase.organization_id == org_id, Document.is_deleted.is_(False))
        .group_by(KnowledgeBase.id, KnowledgeBase.name, source_expr)
        .order_by(desc(func.count(func.distinct(Document.id))))
    )
    sources: list[SourceMetricOut] = []
    for row in rows:
        documents = int(row[3] or 0)
        ready = int(row[4] or 0)
        uploaded = int(row[5] or 0)
        processing = int(row[6] or 0)
        failed = int(row[7] or 0)
        sources.append(
            SourceMetricOut(
                knowledge_base_id=row[0],
                name=str(row[1] or _source_label(str(row[2] or "unknown"))),
                source_type=str(row[2] or "unknown"),
                documents=documents,
                ready_documents=ready,
                pending_documents=max(0, uploaded + processing),
                uploaded_documents=uploaded,
                processing_documents=processing,
                failed_documents=failed,
                chunks_active=int(row[8] or 0),
                last_updated_at=row[9],
                last_ingested_at=row[10],
            )
        )
    return sources


async def _connector_runs(db: AsyncSession, org_id: uuid.UUID) -> list[ConnectorRunOut]:
    rows = await db.scalars(
        select(AuditLog)
        .where(
            AuditLog.organization_id == org_id,
            AuditLog.action.in_(["confluence.sync", "jira.sync"]),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(12)
    )
    return [_connector_run_from_audit(row) for row in rows]


def _connector_run_from_audit(row: AuditLog) -> ConnectorRunOut:
    counts = {match.group("name"): int(match.group("value")) for match in RUN_DETAIL_RE.finditer(row.detail or "")}
    failed = counts.get("failed", 0)
    created = counts.get("created", 0)
    updated = counts.get("updated", 0)
    skipped = counts.get("skipped", 0)
    total = created + updated + skipped + failed
    knowledge_base_id: uuid.UUID | None = None
    if row.resource_id:
        try:
            knowledge_base_id = uuid.UUID(row.resource_id)
        except ValueError:
            knowledge_base_id = None
    return ConnectorRunOut(
        connector=row.action.removesuffix(".sync"),
        knowledge_base_id=knowledge_base_id,
        status="failed" if failed else "completed",
        total=total,
        created=created,
        updated=updated,
        skipped=skipped,
        failed=failed,
        detail=row.detail,
        created_at=row.created_at,
    )


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
