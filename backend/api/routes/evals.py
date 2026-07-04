import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from statistics import mean

from fastapi import APIRouter, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.deps import CurrentUser, DbDep
from api.schemas import (
    EvalLatencyOut,
    EvalModelOut,
    EvalOverviewOut,
    EvalRecentAnswerOut,
    EvalScoreOut,
    FeedbackMetricOut,
)
from database.base import utcnow
from models import Conversation, Feedback, Message

router = APIRouter(prefix="/evals", tags=["evals"])

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_+-]{2,}")


@dataclass(frozen=True)
class AnswerEval:
    message: Message
    question: str
    citation_count: int
    citation_coverage: float
    marker_coverage: float
    citation_confidence: float | None
    groundedness: float
    relevance: float | None
    completeness: float
    success: float


@router.get("/overview", response_model=EvalOverviewOut)
async def evals_overview(
    user: CurrentUser,
    db: DbDep,
    limit: int = Query(default=500, ge=50, le=2000),
) -> EvalOverviewOut:
    """Read-only live eval overview from persisted answer, citation, latency, and feedback data."""

    org_id = user.organization_id
    total_answers = await db.scalar(
        select(func.count(Message.id))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.organization_id == org_id,
            Conversation.is_deleted.is_(False),
            Message.role == "assistant",
        )
    ) or 0

    sampled_messages = await _recent_messages(db, org_id, limit)
    evals = _evaluate_answers(sampled_messages)
    feedback = await _feedback(db, org_id)

    return EvalOverviewOut(
        generated_at=utcnow(),
        answers_total=int(total_answers),
        sample_size=len(evals),
        feedback=feedback,
        scores=_scorecards(evals, feedback),
        latency=_latency(evals),
        models=_model_breakdown(evals),
        recent_answers=_recent_answers(evals),
        methodology=[
            "Live heuristic evals over recent persisted assistant answers; no synthetic rows are generated.",
            "Groundedness proxy combines citation presence, citation marker coverage, and retrieval confidence.",
            "Answer relevance proxy uses lexical overlap between the user question and answer text.",
            "Use an offline golden dataset or LLM-as-judge pipeline before treating these values as benchmark scores.",
        ],
    )


async def _recent_messages(db: AsyncSession, org_id: uuid.UUID, limit: int) -> list[Message]:
    recent_ids = (
        select(Message.id)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.organization_id == org_id, Conversation.is_deleted.is_(False))
        .order_by(Message.created_at.desc())
        .limit(limit * 2)
        .subquery()
    )
    rows = await db.scalars(
        select(Message)
        .where(Message.id.in_(select(recent_ids.c.id)))
        .options(selectinload(Message.citations))
        .order_by(Message.conversation_id, Message.created_at)
    )
    return list(rows)


async def _feedback(db: AsyncSession, org_id: uuid.UUID) -> FeedbackMetricOut:
    counts = (
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
    helpful = int(counts[0] or 0)
    not_helpful = int(counts[1] or 0)
    total = helpful + not_helpful
    return FeedbackMetricOut(
        helpful=helpful,
        not_helpful=not_helpful,
        total=total,
        helpful_rate=(helpful / total) if total else None,
    )


def _evaluate_answers(messages: list[Message]) -> list[AnswerEval]:
    previous_question_by_conversation: dict[uuid.UUID, str] = {}
    evals: list[AnswerEval] = []

    for message in messages:
        if message.role == "user":
            previous_question_by_conversation[message.conversation_id] = message.content
            continue
        if message.role != "assistant":
            continue

        question = previous_question_by_conversation.get(message.conversation_id, "")
        citations = list(message.citations)
        citation_count = len(citations)
        citation_coverage = 1.0 if citation_count else 0.0
        marker_coverage = _marker_coverage(message.content, citations)
        citation_confidence = _citation_confidence(citations)
        groundedness = _groundedness(
            citation_coverage=citation_coverage,
            marker_coverage=marker_coverage,
            citation_confidence=citation_confidence,
        )
        relevance = _relevance(question, message.content)
        completeness = _completeness(message.content)
        success = 1.0 if message.content.strip() and "terminal error" not in message.content.lower() else 0.0
        evals.append(
            AnswerEval(
                message=message,
                question=question,
                citation_count=citation_count,
                citation_coverage=citation_coverage,
                marker_coverage=marker_coverage,
                citation_confidence=citation_confidence,
                groundedness=groundedness,
                relevance=relevance,
                completeness=completeness,
                success=success,
            )
        )
    return evals


def _scorecards(evals: list[AnswerEval], feedback: FeedbackMetricOut) -> list[EvalScoreOut]:
    citation_coverage = _avg([item.citation_coverage for item in evals])
    groundedness = _avg([item.groundedness for item in evals])
    relevance = _avg([item.relevance for item in evals if item.relevance is not None])
    completeness = _avg([item.completeness for item in evals])
    success = _avg([item.success for item in evals])
    retrieval_confidence = _avg(
        [item.citation_confidence for item in evals if item.citation_confidence is not None]
    )
    return [
        _score("citation_coverage", "Citation coverage", citation_coverage, "Answers with at least one cited source."),
        _score(
            "groundedness",
            "Groundedness proxy",
            groundedness,
            "Citation presence, marker coverage, and retrieval score.",
        ),
        _score("answer_relevance", "Answer relevance proxy", relevance, "Question-to-answer lexical alignment."),
        _score("retrieval_confidence", "Retrieval confidence", retrieval_confidence, "Mean score of cited chunks."),
        _score("completeness", "Completeness proxy", completeness, "Answer length and non-empty response signal."),
        _score(
            "success_rate",
            "Streaming success",
            success,
            "Persisted assistant answers without terminal error text.",
        ),
        _score("helpful_rate", "Helpful feedback", feedback.helpful_rate, "User Helpful vs Not Helpful submissions."),
    ]


def _latency(evals: list[AnswerEval]) -> EvalLatencyOut:
    values = sorted(item.message.latency_ms for item in evals if item.message.latency_ms is not None)
    if not values:
        return EvalLatencyOut(avg_ms=None, p50_ms=None, p95_ms=None, sample_size=0)
    return EvalLatencyOut(
        avg_ms=round(mean(values)),
        p50_ms=_percentile(values, 50),
        p95_ms=_percentile(values, 95),
        sample_size=len(values),
    )


def _model_breakdown(evals: list[AnswerEval]) -> list[EvalModelOut]:
    by_model: dict[str, list[AnswerEval]] = defaultdict(list)
    for item in evals:
        by_model[item.message.model or "unknown"].append(item)

    rows: list[EvalModelOut] = []
    for model, items in by_model.items():
        latencies = [item.message.latency_ms for item in items if item.message.latency_ms is not None]
        rows.append(
            EvalModelOut(
                model=model,
                answers=len(items),
                avg_latency_ms=round(mean(latencies)) if latencies else None,
                citation_coverage=_avg([item.citation_coverage for item in items]),
                groundedness_score=_avg([item.groundedness for item in items]),
            )
        )
    return sorted(rows, key=lambda item: item.answers, reverse=True)


def _recent_answers(evals: list[AnswerEval]) -> list[EvalRecentAnswerOut]:
    rows = sorted(evals, key=lambda item: item.message.created_at, reverse=True)[:10]
    return [
        EvalRecentAnswerOut(
            message_id=item.message.id,
            conversation_id=item.message.conversation_id,
            question=_preview(item.question, 160),
            answer_preview=_preview(item.message.content, 260),
            model=item.message.model,
            created_at=item.message.created_at,
            latency_ms=item.message.latency_ms,
            citations=item.citation_count,
            groundedness_score=item.groundedness,
            relevance_score=item.relevance,
        )
        for item in rows
    ]


def _score(id_: str, label: str, value: float | None, detail: str) -> EvalScoreOut:
    return EvalScoreOut(
        id=id_,
        label=label,
        value=round(value, 4) if value is not None else None,
        display="N/A" if value is None else f"{round(value * 100)}%",
        status=_status(value),
        detail=detail,
    )


def _groundedness(
    *,
    citation_coverage: float,
    marker_coverage: float,
    citation_confidence: float | None,
) -> float:
    confidence = citation_confidence or 0.0
    return _clamp01((0.25 * citation_coverage) + (0.35 * marker_coverage) + (0.40 * confidence))


def _marker_coverage(content: str, citations: list) -> float:
    if not citations:
        return 0.0
    found = sum(1 for citation in citations if f"[{citation.marker}]" in content)
    return _clamp01(found / len(citations))


def _citation_confidence(citations: list) -> float | None:
    scores = [_clamp01(float(citation.score or 0.0)) for citation in citations]
    return _avg(scores)


def _relevance(question: str, answer: str) -> float | None:
    q_tokens = _tokens(question)
    if not q_tokens:
        return None
    a_tokens = _tokens(answer)
    if not a_tokens:
        return 0.0
    return _clamp01(len(q_tokens & a_tokens) / len(q_tokens))


def _completeness(answer: str) -> float:
    text = answer.strip()
    if not text:
        return 0.0
    if len(text) < 80:
        return _clamp01(len(text) / 80)
    return _clamp01(len(text) / 600)


def _tokens(text: str) -> set[str]:
    stop = {"the", "and", "for", "with", "from", "that", "this", "what", "how", "are", "you", "your"}
    return {token.lower() for token in TOKEN_RE.findall(text) if token.lower() not in stop}


def _avg(values: list[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return round(mean(clean), 4) if clean else None


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    index = round((len(values) - 1) * (percentile / 100))
    return int(values[index])


def _status(value: float | None) -> str:
    if value is None:
        return "no_data"
    if value >= 0.8:
        return "good"
    if value >= 0.6:
        return "watch"
    return "needs_attention"


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _preview(text: str, max_length: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_length:
        return clean
    return f"{clean[: max_length - 1].rstrip()}..."
