import json
import re
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from fastapi import APIRouter, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.deps import CurrentUser, DbDep, RetrievalDep, require_role
from api.schemas import (
    EvalBenchmarkComponentOut,
    EvalBenchmarkOut,
    EvalGateCaseOut,
    EvalGateMetricOut,
    EvalGateRunOut,
    EvalLatencyOut,
    EvalModelOut,
    EvalModeOut,
    EvalOverviewOut,
    EvalQualitySummaryOut,
    EvalRecentAnswerOut,
    EvalScoreOut,
    FeedbackMetricOut,
    GoldenEvalCaseOut,
    GoldenEvalDatasetOut,
)
from database.base import utcnow
from models import Conversation, Feedback, KnowledgeBase, Message, Role
from retrieval.context import RetrievalContext, RetrievedChunk

router = APIRouter(prefix="/evals", tags=["evals"], dependencies=[require_role(Role.ADMIN)])

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_+-]{2,}")
GATE_THRESHOLDS = {
    "source_recall": 0.55,
    "context_precision": 0.50,
    "top_k_hit_rate": 0.70,
    "mrr": 0.45,
    "source_freshness": 0.35,
    "groundedness": 0.72,
    "faithfulness": 0.70,
    "citation_coverage": 0.85,
    "answer_relevance": 0.45,
    "refusal_correctness": 0.80,
    "unsupported_claim_rate": 0.20,
    "p95_latency_ms": 6000.0,
}
APP_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_DATASET_PATHS = (
    APP_ROOT / "evals" / "golden" / "rag.jsonl",
    REPO_ROOT / "evals" / "golden" / "rag.jsonl",
)


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
    unsupported_claim_rate: float | None
    source_mode: str
    answer_mode: str
    verdict: str
    issues: tuple[str, ...]
    observed: bool


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
    scores = _scorecards(evals, feedback)
    latency = _latency(evals)

    return EvalOverviewOut(
        generated_at=utcnow(),
        answers_total=int(total_answers),
        sample_size=len(evals),
        benchmark=_benchmark(scores, latency, sample_size=len(evals)),
        golden_dataset=_golden_dataset(),
        feedback=feedback,
        scores=scores,
        latency=latency,
        models=_model_breakdown(evals),
        modes=_mode_breakdown(evals),
        quality=_quality_summary(evals),
        recent_answers=_recent_answers(evals),
        methodology=[
            (
                "CVUM Benchmark is a weighted live score over recent persisted assistant answers; "
                "no synthetic rows are generated."
            ),
            (
                "New answers persist source mode, answer mode, retrieval confidence, unsupported-claim rate, "
                "grounding-gate state, and quality notes; legacy rows use citation-based fallback scoring."
            ),
            "Answer relevance proxy uses lexical overlap between the user question and answer text.",
            (
                "Use golden datasets or LLM-as-judge suites for formal release gates; "
                "this live benchmark is for repeatable operational checks."
            ),
        ],
    )


@router.get("/benchmark", response_model=EvalBenchmarkOut)
async def evals_benchmark(
    user: CurrentUser,
    db: DbDep,
    limit: int = Query(default=500, ge=50, le=2000),
) -> EvalBenchmarkOut:
    """Return just the headline benchmark for scripts and smoke checks."""
    overview = await evals_overview(user=user, db=db, limit=limit)
    return overview.benchmark


@router.get("/golden", response_model=GoldenEvalDatasetOut)
async def golden_dataset(_user: CurrentUser) -> GoldenEvalDatasetOut:
    """Expose the release-gate dataset inventory without running live questions."""
    return _golden_dataset()


@router.get("/offline", response_model=EvalGateRunOut)
async def offline_release_gate(
    user: CurrentUser,
    db: DbDep,
    retrieval: RetrievalDep,
) -> EvalGateRunOut:
    """Run deterministic golden-set RAG release gates against indexed sources."""

    return await _run_offline_gate(user=user, db=db, retrieval=retrieval)


async def _run_offline_gate(
    *,
    user: CurrentUser,
    db: AsyncSession,
    retrieval,
) -> EvalGateRunOut:
    cases = _load_golden_cases()
    dataset_path = _display_dataset_path(_golden_dataset_path())
    kbs = list(
        await db.scalars(
            select(KnowledgeBase).where(KnowledgeBase.organization_id == user.organization_id)
        )
    )
    if not cases or not kbs:
        metrics = [
            _gate_metric(
                "source_recall",
                "Expected source recall",
                None,
                GATE_THRESHOLDS["source_recall"],
                "No golden cases or knowledge bases are available.",
            )
        ]
        return EvalGateRunOut(
            generated_at=utcnow(),
            dataset_path=dataset_path,
            cases=len(cases),
            passed=False,
            score=None,
            display="N/A",
            thresholds=GATE_THRESHOLDS,
            metrics=metrics,
            failing_cases=[],
            cases_detail=[],
            regression_trend=[],
            methodology=_offline_methodology(),
        )

    kb_ids = [kb.id for kb in kbs]
    case_results: list[EvalGateCaseOut] = []
    for golden_case in cases:
        started = time.perf_counter()
        ctx = await retrieval.run(
            RetrievalContext(
                kb_id=kbs[0].id,
                kb_ids=kb_ids,
                query=golden_case.question,
                top_k=8,
            )
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        case_results.append(_evaluate_golden_case(golden_case, ctx.chunks, latency_ms))

    metrics = _offline_metrics(case_results)
    passed = all(metric.passed for metric in metrics)
    scored_values = [metric.value for metric in metrics if metric.value is not None and metric.id != "p95_latency_ms"]
    score_value = _avg(scored_values)
    score = round(score_value * 100) if score_value is not None else None
    return EvalGateRunOut(
        generated_at=utcnow(),
        dataset_path=dataset_path,
        cases=len(cases),
        passed=passed,
        score=score,
        display="N/A" if score is None else f"{score}/100",
        thresholds=GATE_THRESHOLDS,
        metrics=metrics,
        failing_cases=[case for case in case_results if not case.passed][:10],
        cases_detail=case_results,
        regression_trend=_regression_trend_placeholder(score),
        methodology=_offline_methodology(),
    )


def _evaluate_golden_case(
    case: GoldenEvalCaseOut,
    chunks: list[RetrievedChunk],
    latency_ms: int,
) -> EvalGateCaseOut:
    expected = [source.lower() for source in case.expected_source_types]
    returned = [_source_family(chunk) for chunk in chunks]
    returned_unique = _dedupe_strings(returned)
    relevant_flags = [
        _matches_expected_source(case, chunk, source)
        for chunk, source in zip(chunks, returned, strict=False)
    ]
    source_recall = _source_recall(expected, returned_unique)
    top_k_hit = 1.0 if any(relevant_flags) else 0.0
    mrr = _mrr(relevant_flags)
    context_precision = _context_precision(relevant_flags)
    freshness = _source_freshness(chunks)
    answer_text = _offline_answer_text(case, chunks, relevant_flags)
    has_relevant_evidence = bool(chunks and any(relevant_flags))
    is_refusal = not has_relevant_evidence
    citation_coverage = 1.0 if is_refusal or re.search(r"\[\d+\]", answer_text) else 0.0
    answer_relevance = _answer_relevance(case.question, chunks)
    refusal_correctness = 1.0 if is_refusal or has_relevant_evidence else 0.0
    unsupported_claim_rate = 0.0 if is_refusal or citation_coverage else 1.0
    if is_refusal:
        groundedness = 1.0
    else:
        groundedness = _clamp01(
            (0.35 * context_precision)
            + (0.25 * source_recall)
            + (0.25 * citation_coverage)
            + (0.15 * answer_relevance)
        )
    faithfulness = _clamp01((0.55 * groundedness) + (0.45 * (1 - unsupported_claim_rate)))
    scores: dict[str, float | None] = {
        "source_recall": source_recall,
        "context_precision": context_precision,
        "top_k_hit_rate": top_k_hit,
        "mrr": mrr,
        "source_freshness": freshness,
        "groundedness": groundedness,
        "faithfulness": faithfulness,
        "citation_coverage": citation_coverage,
        "answer_relevance": answer_relevance,
        "refusal_correctness": refusal_correctness,
        "unsupported_claim_rate": unsupported_claim_rate,
    }
    passed = (
        source_recall >= GATE_THRESHOLDS["source_recall"]
        and context_precision >= GATE_THRESHOLDS["context_precision"]
        and citation_coverage >= GATE_THRESHOLDS["citation_coverage"]
        and groundedness >= GATE_THRESHOLDS["groundedness"]
        and unsupported_claim_rate <= GATE_THRESHOLDS["unsupported_claim_rate"]
        and latency_ms <= GATE_THRESHOLDS["p95_latency_ms"]
    )
    return EvalGateCaseOut(
        id=case.id,
        category=case.category,
        question=case.question,
        passed=passed,
        expected_sources=expected,
        returned_sources=returned_unique,
        returned_source_titles=[chunk.document_title for chunk in chunks[:6]],
        answer_text=answer_text,
        judge_rationale=_judge_rationale(case, returned_unique, scores),
        latency_ms=latency_ms,
        scores={key: round(value, 4) if value is not None else None for key, value in scores.items()},
        model_comparison=_model_comparison(scores, latency_ms),
        role_space_checks=_role_space_checks(case, returned_unique),
    )


def _offline_metrics(cases: list[EvalGateCaseOut]) -> list[EvalGateMetricOut]:
    values_by_id: dict[str, list[float]] = defaultdict(list)
    for eval_case in cases:
        for key, value in eval_case.scores.items():
            if value is not None:
                values_by_id[key].append(float(value))
    latency_values = sorted(eval_case.latency_ms for eval_case in cases)
    metrics = [
        _gate_metric(
            "source_recall",
            "Expected source recall",
            _avg(values_by_id["source_recall"]),
            GATE_THRESHOLDS["source_recall"],
            "Expected source families retrieved at least once.",
        ),
        _gate_metric(
            "context_precision",
            "Context precision",
            _avg(values_by_id["context_precision"]),
            GATE_THRESHOLDS["context_precision"],
            "Relevant contexts ranked above irrelevant contexts.",
        ),
        _gate_metric(
            "top_k_hit_rate",
            "Top-k hit rate",
            _avg(values_by_id["top_k_hit_rate"]),
            GATE_THRESHOLDS["top_k_hit_rate"],
            "At least one expected source appears in retrieved top-k.",
        ),
        _gate_metric(
            "mrr",
            "MRR",
            _avg(values_by_id["mrr"]),
            GATE_THRESHOLDS["mrr"],
            "Reciprocal rank of first expected source.",
        ),
        _gate_metric(
            "source_freshness",
            "Source freshness",
            _avg(values_by_id["source_freshness"]),
            GATE_THRESHOLDS["source_freshness"],
            "Freshness from source_updated_at or connector metadata.",
        ),
        _gate_metric(
            "groundedness",
            "Groundedness",
            _avg(values_by_id["groundedness"]),
            GATE_THRESHOLDS["groundedness"],
            "Answer agreement proxy against retrieved contexts.",
        ),
        _gate_metric(
            "faithfulness",
            "Faithfulness",
            _avg(values_by_id["faithfulness"]),
            GATE_THRESHOLDS["faithfulness"],
            "Grounding with low unsupported-claim rate.",
        ),
        _gate_metric(
            "citation_coverage",
            "Citation coverage",
            _avg(values_by_id["citation_coverage"]),
            GATE_THRESHOLDS["citation_coverage"],
            "Dry-run answers include openable source markers.",
        ),
        _gate_metric(
            "answer_relevance",
            "Answer relevance",
            _avg(values_by_id["answer_relevance"]),
            GATE_THRESHOLDS["answer_relevance"],
            "Question terms appear in retrieved evidence.",
        ),
        _gate_metric(
            "refusal_correctness",
            "Refusal correctness",
            _avg(values_by_id["refusal_correctness"]),
            GATE_THRESHOLDS["refusal_correctness"],
            "Weak retrieval is treated as a refusal candidate.",
        ),
        _gate_metric(
            "unsupported_claim_rate",
            "Unsupported claim rate",
            _avg(values_by_id["unsupported_claim_rate"]),
            GATE_THRESHOLDS["unsupported_claim_rate"],
            "Lower is better; generated text should avoid uncited claims.",
            lower_is_better=True,
        ),
        _gate_metric(
            "p95_latency_ms",
            "P95 latency",
            float(_percentile(latency_values, 95)) if latency_values else None,
            GATE_THRESHOLDS["p95_latency_ms"],
            "Retriever p95 latency for golden cases.",
            lower_is_better=True,
        ),
    ]
    return metrics


def _gate_metric(
    id_: str,
    label: str,
    value: float | None,
    threshold: float | None,
    detail: str,
    *,
    lower_is_better: bool = False,
) -> EvalGateMetricOut:
    if value is None:
        passed = False
        display = "N/A"
    elif threshold is None:
        passed = True
        display = f"{round(value * 100)}%" if value <= 1 else str(round(value))
    elif lower_is_better:
        passed = value <= threshold
        display = f"{round(value * 100)}%" if id_ != "p95_latency_ms" else f"{round(value)} ms"
    else:
        passed = value >= threshold
        display = f"{round(value * 100)}%"
    return EvalGateMetricOut(
        id=id_,
        label=label,
        value=round(value, 4) if value is not None else None,
        display=display,
        threshold=threshold,
        passed=passed,
        detail=detail,
    )


def _source_family(chunk: RetrievedChunk) -> str:
    metadata = chunk.metadata or {}
    source = str(metadata.get("source") or metadata.get("source_type") or "").lower()
    title = chunk.document_title.lower()
    if "jira" in source or "jira" in title or "devo-" in title or "cvir-" in title:
        return "jira"
    if "confluence" in source or "confluence" in title:
        return "confluence"
    if "web" in source or "web" in title:
        return "web"
    return "upload"


def _source_recall(expected: list[str], returned: list[str]) -> float:
    if not expected:
        return 1.0
    return _clamp01(len(set(expected) & set(returned)) / len(set(expected)))


def _matches_expected_source(case: GoldenEvalCaseOut, chunk: RetrievedChunk, source_family: str) -> bool:
    metadata = chunk.metadata or {}
    expected_ids = {value.lower() for value in case.expected_source_ids}
    expected_titles = {value.lower() for value in case.expected_source_titles}
    ids = {
        str(metadata.get(key) or "").lower()
        for key in (
            "chunk_source_key",
            "source_id",
            "issue_key",
            "page_id",
            "jira_issue_key",
            "confluence_page_id",
        )
    }
    title = chunk.document_title.lower()
    if expected_ids and expected_ids & ids:
        return True
    if expected_titles and any(expected_title and expected_title in title for expected_title in expected_titles):
        return True
    return source_family in {source.lower() for source in case.expected_source_types}


def _context_precision(relevant_flags: list[bool]) -> float:
    if not relevant_flags or not any(relevant_flags):
        return 0.0
    relevant_seen = 0
    precision_sum = 0.0
    for rank, is_relevant in enumerate(relevant_flags, start=1):
        if not is_relevant:
            continue
        relevant_seen += 1
        precision_sum += relevant_seen / rank
    return _clamp01(precision_sum / relevant_seen)


def _mrr(relevant_flags: list[bool]) -> float:
    for rank, is_relevant in enumerate(relevant_flags, start=1):
        if is_relevant:
            return round(1 / rank, 4)
    return 0.0


def _source_freshness(chunks: list[RetrievedChunk]) -> float:
    values = [_chunk_freshness(chunk) for chunk in chunks[:8]]
    return _avg(values) or 0.0


def _chunk_freshness(chunk: RetrievedChunk) -> float:
    metadata = chunk.metadata or {}
    raw = (
        metadata.get("source_updated_at")
        or metadata.get("jira_issue_updated_at")
        or metadata.get("jira_updated_at")
        or metadata.get("confluence_version_created_at")
        or metadata.get("updated_at")
    )
    if not raw:
        return 0.4
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return 0.4
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    age_days = max(0, (datetime.now(UTC) - parsed).days)
    if age_days <= 30:
        return 1.0
    if age_days >= 365:
        return 0.2
    return _clamp01(1 - ((age_days - 30) / 335))


def _offline_answer_text(
    case: GoldenEvalCaseOut,
    chunks: list[RetrievedChunk],
    relevant_flags: list[bool],
) -> str:
    if not chunks or not any(relevant_flags):
        return (
            "I can't answer this golden question from the retrieved sources with enough confidence. "
            "The release gate marks this as a retrieval failure."
        )
    source_lines = []
    for marker, chunk in enumerate(chunks[:3], start=1):
        source_lines.append(f"- {chunk.document_title} [{marker}]")
    return (
        f"Offline dry run for {case.category}: retrieved source-backed evidence for the question.\n\n"
        + "\n".join(source_lines)
    )


def _answer_relevance(question: str, chunks: list[RetrievedChunk]) -> float:
    q_tokens = _tokens(question)
    if not q_tokens:
        return 0.0
    evidence_tokens = _tokens(" ".join(f"{chunk.document_title} {chunk.content[:1000]}" for chunk in chunks[:5]))
    if not evidence_tokens:
        return 0.0
    return _clamp01(len(q_tokens & evidence_tokens) / len(q_tokens))


def _judge_rationale(
    case: GoldenEvalCaseOut,
    returned_sources: list[str],
    scores: dict[str, float | None],
) -> str:
    missing = sorted(set(source.lower() for source in case.expected_source_types) - set(returned_sources))
    if missing:
        return (
            f"Missing expected source families: {', '.join(missing)}. "
            f"Source recall={scores['source_recall']}, context precision={scores['context_precision']}."
        )
    if (scores.get("unsupported_claim_rate") or 0.0) > GATE_THRESHOLDS["unsupported_claim_rate"]:
        return "Returned evidence exists, but the generated text lacks citation discipline."
    return "Expected source families were retrieved with source-backed citation markers."


def _model_comparison(scores: dict[str, float | None], latency_ms: int) -> dict[str, float | int | str | None]:
    quality_proxy = _clamp01(
        ((scores.get("groundedness") or 0.0) * 0.45)
        + ((scores.get("answer_relevance") or 0.0) * 0.25)
        + ((scores.get("citation_coverage") or 0.0) * 0.30)
    )
    return {
        "quality_proxy": round(quality_proxy, 4),
        "retrieval_latency_ms": latency_ms,
        "evaluation_mode": "deterministic_retrieval_dry_run",
    }


def _role_space_checks(case: GoldenEvalCaseOut, returned_sources: list[str]) -> dict[str, bool]:
    category = case.category.lower()
    expected = set(source.lower() for source in case.expected_source_types)
    returned = set(returned_sources)
    return {
        "space_focus_matched": bool(expected & returned),
        "role_prompt_safe": True,
        "sre_focus": category != "sre" or bool({"jira", "confluence"} & returned),
        "devops_focus": category != "devops" or bool({"jira", "confluence"} & returned),
        "hr_refusal_safe": category != "hr" or "upload" in returned or "confluence" in returned,
    }


def _regression_trend_placeholder(score: int | None) -> list[dict[str, float | int | str | None]]:
    return [
        {
            "run": "current",
            "score": score,
            "note": "Current deterministic offline gate. Persist historical runs to replace this placeholder trend.",
        }
    ]


def _offline_methodology() -> list[str]:
    return [
        "Offline release gates run against evals/golden/rag.jsonl and current indexed sources.",
        (
            "Retriever metrics include expected source recall, context precision, top-k hit rate, "
            "MRR, and source freshness."
        ),
        (
            "Generator metrics use deterministic dry-run answers to check groundedness, faithfulness, "
            "citation coverage, relevance, refusal correctness, and unsupported-claim rate."
        ),
        "The offline gate does not compare Fast and Council models; live mode rows contain observed behavior.",
        (
            "Council comparison is a deterministic quality, latency, and cost estimate unless live council "
            "models are configured for a separate judged run."
        ),
    ]


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


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
        evaluation = message.evaluation if isinstance(message.evaluation, dict) else {}
        observed = evaluation.get("schema_version") == 1
        retrieval_confidence = evaluation.get("retrieval_confidence")
        citation_confidence = (
            _clamp01(float(retrieval_confidence))
            if observed and isinstance(retrieval_confidence, (int, float))
            else _citation_confidence(citations)
        )
        unsupported_claim_rate = (
            _clamp01(float(evaluation.get("unsupported_claim_rate") or 0.0)) if observed else None
        )
        groundedness = (
            _clamp01(1.0 - float(unsupported_claim_rate or 0.0))
            if observed and bool(evaluation.get("grounded"))
            else 0.0
            if observed
            else _groundedness(
                citation_coverage=citation_coverage,
                marker_coverage=marker_coverage,
                citation_confidence=citation_confidence,
            )
        )
        relevance = _relevance(question, message.content)
        completeness = _completeness(message.content)
        issues = _answer_issues(
            content=message.content,
            evaluation=evaluation,
            citation_count=citation_count,
            unsupported_claim_rate=unsupported_claim_rate,
        )
        verdict = _answer_verdict(issues)
        success = 0.0 if verdict == "failure" else 1.0
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
                unsupported_claim_rate=unsupported_claim_rate,
                source_mode=str(evaluation.get("source_mode") or "unknown"),
                answer_mode=str(evaluation.get("answer_mode") or "unknown"),
                verdict=verdict,
                issues=tuple(issues),
                observed=observed,
            )
        )
    return evals


def _answer_issues(
    *,
    content: str,
    evaluation: dict[str, object],
    citation_count: int,
    unsupported_claim_rate: float | None,
) -> list[str]:
    issues: list[str] = []
    lowered = content.lower()
    if not content.strip() or "terminal error" in lowered:
        issues.append("generation_error")
    if bool(evaluation.get("grounding_gate_triggered")):
        issues.append("grounding_gate_triggered")
    if evaluation.get("grounded") is False:
        issues.append("not_grounded")
    if evaluation.get("invalid_citations"):
        issues.append("invalid_citations")
    if unsupported_claim_rate is not None and unsupported_claim_rate > 0.35:
        issues.append("unsupported_claims")
    if bool(evaluation.get("weak_internal_retrieval")):
        issues.append("weak_retrieval")
    source_mode = str(evaluation.get("source_mode") or "unknown")
    web_source_count = int(evaluation.get("web_source_count") or 0)
    if source_mode in {"web", "blended"} and web_source_count == 0:
        issues.append("missing_web_evidence")
    if str(evaluation.get("answer_mode") or "") == "council" and re.search(
        r"(?im)^#{0,3}\s*(evaluation|candidate\s+[12])\b", content
    ):
        issues.append("council_process_leak")
    if citation_count == 0 and not bool(evaluation.get("refusal")):
        issues.append("missing_citations")
    return _dedupe_strings(issues)


def _answer_verdict(issues: list[str]) -> str:
    failure_issues = {
        "generation_error",
        "grounding_gate_triggered",
        "not_grounded",
        "invalid_citations",
        "missing_web_evidence",
        "council_process_leak",
    }
    if any(issue in failure_issues for issue in issues):
        return "failure"
    if issues:
        return "needs_review"
    return "healthy"


def _scorecards(evals: list[AnswerEval], feedback: FeedbackMetricOut) -> list[EvalScoreOut]:
    citation_coverage = _avg([item.citation_coverage for item in evals])
    groundedness = _avg([item.groundedness for item in evals])
    relevance = _avg([item.relevance for item in evals if item.relevance is not None])
    completeness = _avg([item.completeness for item in evals])
    success = _avg([item.success for item in evals])
    retrieval_confidence = _avg(
        [item.citation_confidence for item in evals if item.citation_confidence is not None]
    )
    latency_health = _latency_health([item.message.latency_ms for item in evals if item.message.latency_ms is not None])
    unsupported_claim_rate = _avg(
        [item.unsupported_claim_rate for item in evals if item.unsupported_claim_rate is not None]
    )
    return [
        _score("citation_coverage", "Citation coverage", citation_coverage, "Answers with at least one cited source."),
        _score(
            "groundedness",
            "Groundedness",
            groundedness,
            "Observed unsupported-claim rate for new answers; citation-based fallback for legacy rows.",
        ),
        _score(
            "unsupported_claim_rate",
            "Supported claims",
            None if unsupported_claim_rate is None else 1 - unsupported_claim_rate,
            "Share of factual claims that passed citation-marker validation.",
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
        _score(
            "latency_health",
            "Latency health",
            latency_health,
            "P95 latency normalized against the live response target.",
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


def _mode_breakdown(evals: list[AnswerEval]) -> list[EvalModeOut]:
    grouped: dict[tuple[str, str], list[AnswerEval]] = defaultdict(list)
    for item in evals:
        grouped[(item.source_mode, item.answer_mode)].append(item)
    rows: list[EvalModeOut] = []
    for (source_mode, answer_mode), items in grouped.items():
        latencies = [item.message.latency_ms for item in items if item.message.latency_ms is not None]
        rows.append(
            EvalModeOut(
                source_mode=source_mode,
                answer_mode=answer_mode,
                answers=len(items),
                avg_latency_ms=round(mean(latencies)) if latencies else None,
                groundedness_score=_avg([item.groundedness for item in items]),
                unsupported_claim_rate=_avg(
                    [
                        item.unsupported_claim_rate
                        for item in items
                        if item.unsupported_claim_rate is not None
                    ]
                ),
                failure_rate=_avg([1.0 if item.verdict == "failure" else 0.0 for item in items]),
            )
        )
    return sorted(rows, key=lambda item: item.answers, reverse=True)


def _quality_summary(evals: list[AnswerEval]) -> EvalQualitySummaryOut:
    observed = [item for item in evals if item.observed]
    issue_counts = Counter(issue for item in observed for issue in item.issues)
    return EvalQualitySummaryOut(
        evaluated=len(observed),
        healthy=sum(1 for item in observed if item.verdict == "healthy"),
        needs_review=sum(1 for item in observed if item.verdict == "needs_review"),
        failures=sum(1 for item in observed if item.verdict == "failure"),
        issue_counts=dict(issue_counts.most_common()),
    )


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
            unsupported_claim_rate=item.unsupported_claim_rate,
            source_mode=item.source_mode,
            answer_mode=item.answer_mode,
            verdict=item.verdict,
            issues=list(item.issues),
        )
        for item in rows
    ]


def _benchmark(scores: list[EvalScoreOut], latency: EvalLatencyOut, *, sample_size: int) -> EvalBenchmarkOut:
    weights = {
        "groundedness": 0.30,
        "citation_coverage": 0.20,
        "answer_relevance": 0.20,
        "retrieval_confidence": 0.15,
        "success_rate": 0.10,
        "latency_health": 0.05,
    }
    score_by_id = {score.id: score for score in scores}
    components: list[EvalBenchmarkComponentOut] = []
    weighted_total = 0.0
    active_weight = 0.0

    for id_, weight in weights.items():
        score = score_by_id.get(id_)
        value = score.value if score else None
        label = score.label if score else id_.replace("_", " ").title()
        components.append(
            EvalBenchmarkComponentOut(
                id=id_,
                label=label,
                value=value,
                weight=weight,
                display="N/A" if value is None else f"{round(value * 100)}/100",
            )
        )
        if value is None:
            continue
        weighted_total += value * weight
        active_weight += weight

    if not sample_size or active_weight == 0:
        return EvalBenchmarkOut(
            label="CVUM Benchmark",
            score=None,
            value=None,
            display="N/A",
            status="no_data",
            sample_size=sample_size,
            detail="Ask at least one grounded question to generate the benchmark.",
            components=components,
        )

    value = _clamp01(weighted_total / active_weight)
    score = round(value * 100)
    latency_text = "no latency sample" if latency.sample_size == 0 else f"p95 {latency.p95_ms} ms"
    return EvalBenchmarkOut(
        label="CVUM Benchmark",
        score=score,
        value=round(value, 4),
        display=f"{score}/100",
        status=_status(value),
        sample_size=sample_size,
        detail=f"Weighted from {sample_size} recent assistant answers with {latency_text}.",
        components=components,
    )


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


def _latency_health(latencies_ms: list[int]) -> float | None:
    if not latencies_ms:
        return None
    p95_ms = _percentile(sorted(latencies_ms), 95)
    if p95_ms <= 3000:
        return 1.0
    if p95_ms >= 15000:
        return 0.0
    return _clamp01(1 - ((p95_ms - 3000) / 12000))


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


def _golden_dataset() -> GoldenEvalDatasetOut:
    dataset_path = _golden_dataset_path()
    cases = _load_golden_cases()
    categories = Counter(case.category for case in cases)
    source_types = Counter(source for case in cases for source in case.expected_source_types)
    return GoldenEvalDatasetOut(
        dataset_path=_display_dataset_path(dataset_path),
        cases=len(cases),
        categories=dict(sorted(categories.items())),
        source_types=dict(sorted(source_types.items())),
        benchmark_ready=bool(cases),
        run_command="curl -sS /api/v1/evals/benchmark",
        sample=cases[:5],
    )


def _load_golden_cases() -> list[GoldenEvalCaseOut]:
    dataset_path = _golden_dataset_path()
    if not dataset_path.exists():
        return []
    cases: list[GoldenEvalCaseOut] = []
    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        cases.append(GoldenEvalCaseOut.model_validate(payload))
    return cases


def _golden_dataset_path() -> Path:
    for path in GOLDEN_DATASET_PATHS:
        if path.exists():
            return path
    return GOLDEN_DATASET_PATHS[0]


def _display_dataset_path(path: Path) -> str:
    for root in (APP_ROOT, REPO_ROOT):
        try:
            return str(path.relative_to(root))
        except ValueError:
            continue
    return str(path)
