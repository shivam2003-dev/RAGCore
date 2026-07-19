"""Evidence-backed product workflows; no workflow widens project authorization."""

import uuid
from datetime import UTC, date, datetime, time, timedelta

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from database.base import utcnow
from models import (
    AuditLog,
    ConnectorState,
    Document,
    DocumentStatus,
    GitHubRepositoryMapping,
    User,
)
from repositories.projects import ProjectAuthorizationRepository
from services.evidence_contract import Evidence, EvidenceToolName, EvidenceToolRequest
from services.evidence_orchestrator import EvidenceOrchestrator
from services.evidence_tools import EvidenceToolService


class IncidentRequest(BaseModel):
    project_id: uuid.UUID
    issue_key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9]{1,9}-\d+$", max_length=32)


class IncidentTimelineItem(BaseModel):
    occurred_at: datetime
    label: str
    detail: str
    source_type: str
    source_url: str | None
    citation_identity: str


class IncidentCopilotResponse(BaseModel):
    issue_key: str
    project_id: uuid.UUID
    current_status: str
    owner: str
    facts: list[str]
    timeline: list[IncidentTimelineItem]
    immediate_checks: list[str]
    likely_next_actions: list[str]
    missing_evidence: list[str]
    evidence: list[Evidence]
    partial: bool
    tool_failures: list[str]


class ExpertRequest(BaseModel):
    project_id: uuid.UUID
    query: str = Field(min_length=2, max_length=2000)
    limit: int = Field(default=8, ge=1, le=25)


class ExpertRank(BaseModel):
    rank: int
    person: str
    score: float
    explanation: str
    signals: list[dict[str, object]]
    source_ids: list[str]
    citation_identity: str
    source_url: str | None


class ExpertResponse(BaseModel):
    project_id: uuid.UUID
    query: str
    experts: list[ExpertRank]
    empty_reason: str | None = None


class ChangeRequest(BaseModel):
    project_id: uuid.UUID
    start_date: date
    end_date: date
    limit: int = Field(default=100, ge=1, le=200)

    @model_validator(mode="after")
    def validate_range(self) -> "ChangeRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("date range cannot exceed 366 days")
        return self


class ChangeItem(BaseModel):
    changed_at: datetime
    change_type: str
    source_type: str
    source_id: str
    title: str
    source_url: str | None
    summary: str
    citation_identity: str
    document_id: uuid.UUID


class ChangeResponse(BaseModel):
    project_id: uuid.UUID
    start_date: date
    end_date: date
    changes: list[ChangeItem]
    deduplicated_count: int
    source_counts: dict[str, int]


class FreshnessIssue(BaseModel):
    kind: str
    severity: str
    source_type: str
    source_id: str
    title: str
    age_days: int | None
    source_url: str | None
    suggested_remediation: str


class ConnectorFreshness(BaseModel):
    kind: str
    status: str
    last_success_at: datetime | None
    lag_seconds: int | None
    failure_count: int
    detail: str | None


class FreshnessResponse(BaseModel):
    project_id: uuid.UUID
    generated_at: datetime
    score: int
    stale_sources: int
    failing_sources: int
    outdated_slack_resolutions: int
    repository_branch_lag: int
    replaced_documents: int
    total_findings: int
    issues: list[FreshnessIssue]
    connectors: list[ConnectorFreshness]
    suggestions: list[str]


class KnowledgeWorkflowService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        settings: Settings,
        orchestrator: EvidenceOrchestrator,
        tools: EvidenceToolService,
    ) -> None:
        self._db = db
        self._settings = settings
        self._orchestrator = orchestrator
        self._tools = tools
        self._authorization = ProjectAuthorizationRepository(db)

    async def incident(self, *, body: IncidentRequest, user: User) -> IncidentCopilotResponse:
        issue_key = body.issue_key.upper()
        scope = await self._authorization.authorized_scope(user=user, project_id=body.project_id)
        result = await self._orchestrator.retrieve(
            question=(
                f"Investigate incident {issue_key}: status ownership timeline "
                "resolution runbook code recent changes"
            ),
            project_id=scope.project.id,
            user=user,
        )
        evidence = _dedupe_evidence(result.execution.evidence, limit=40)
        incident_evidence = _dedupe_incident_sources(
            [item for item in evidence if _matches_issue(item, issue_key)]
        )
        jira = next((item for item in incident_evidence if item.source_type == "jira"), None)
        status = _metadata_text(jira, "jira_issue_status", "status") or "Unknown from available evidence"
        owner = _metadata_text(jira, "jira_assignee", "owner") or "Unknown from available evidence"
        timeline = [
            IncidentTimelineItem(
                occurred_at=item.freshness,
                label=item.title,
                detail=_timeline_detail(item),
                source_type=item.source_type,
                source_url=item.source_url,
                citation_identity=item.citation_identity,
            )
            for item in incident_evidence
            if item.freshness is not None
        ]
        timeline.sort(key=lambda item: item.occurred_at)
        facts = []
        if jira:
            facts.append(f"Fact [{jira.citation_identity}]: {issue_key} status is {status}; owner is {owner}.")
        facts.extend(
            f"Fact [{item.citation_identity}]: {item.title} is linked to {issue_key} in authorized "
            f"{item.source_type} evidence."
            for item in incident_evidence[:12]
            if item is not jira
        )
        families = {item.source_type for item in evidence}
        missing = []
        expected = {
            "jira": "No authorized Jira issue evidence was found.",
            "slack": "No authorized public Slack incident thread was found.",
            "confluence": "No authorized Confluence runbook was found.",
            "github": "No authorized indexed code evidence was found.",
            "github_pr": "No authorized recent pull-request evidence was found.",
        }
        for family, message in expected.items():
            if family not in families:
                missing.append(message)
        checks = [f"Confirm the live Jira status and owner for {issue_key} before acting."]
        if "confluence" in families:
            checks.append("Run the validation steps in the cited Confluence runbook and record the observed result.")
        if "slack" in families:
            checks.append("Verify that the cited Slack resolution still matches current production behavior.")
        if "github" in families:
            checks.append("Review the cited code paths and their current branch versions before changing production.")
        actions = [
            "Inference: resolve the missing evidence items before declaring root cause.",
            "Inference: use the cited timeline to confirm sequence with the incident owner.",
        ]
        failures = [
            f"{item.tool.value}: {item.failure}"
            for item in result.execution.executions
            if item.failure
        ]
        return IncidentCopilotResponse(
            issue_key=issue_key,
            project_id=scope.project.id,
            current_status=status,
            owner=owner,
            facts=facts,
            timeline=timeline,
            immediate_checks=checks,
            likely_next_actions=actions,
            missing_evidence=missing,
            evidence=evidence,
            partial=bool(missing or failures),
            tool_failures=failures,
        )

    async def experts(self, *, body: ExpertRequest, user: User) -> ExpertResponse:
        scope = await self._authorization.authorized_scope(user=user, project_id=body.project_id)
        rows = await self._tools.invoke(
            tool=EvidenceToolName.WHO_KNOWS,
            request=EvidenceToolRequest(query=body.query, project_id=scope.project.id, limit=body.limit),
            user=user,
        )
        experts = [
            ExpertRank(
                rank=index,
                person=str(item.metadata.get("person") or item.title),
                score=item.score,
                explanation=item.content,
                signals=[value for value in _metadata_list(item, "signals") if isinstance(value, dict)],
                source_ids=[str(value) for value in _metadata_list(item, "source_ids")],
                citation_identity=item.citation_identity,
                source_url=item.source_url,
            )
            for index, item in enumerate(rows, start=1)
        ]
        return ExpertResponse(
            project_id=scope.project.id,
            query=body.query,
            experts=experts,
            empty_reason=None if experts else "No ownership or participation signals were found in authorized sources.",
        )

    async def changes(self, *, body: ChangeRequest, user: User) -> ChangeResponse:
        scope = await self._authorization.authorized_scope(user=user, project_id=body.project_id)
        start = datetime.combine(body.start_date, time.min, tzinfo=UTC)
        end = datetime.combine(body.end_date + timedelta(days=1), time.min, tzinfo=UTC)
        rows = list(
            await self._db.scalars(
                select(Document)
                .where(
                    Document.knowledge_base_id.in_(scope.knowledge_base_ids),
                    Document.is_deleted.is_(False),
                    Document.updated_at >= start,
                    Document.updated_at < end,
                )
                .order_by(Document.updated_at.desc())
                .limit(min(body.limit * 5, 1000))
            )
        )
        eligible: list[Document] = []
        for document in rows:
            changed_at = _source_datetime(document) or document.updated_at
            if start <= changed_at < end:
                eligible.append(document)
        deduped: dict[str, Document] = {}
        for document in eligible:
            metadata = document.doc_metadata or {}
            key = str(
                metadata.get("source_inventory_key")
                or f"{metadata.get('source') or document.source_type}:{metadata.get('source_id') or document.id}"
            )
            deduped.setdefault(key, document)
        selected = list(deduped.values())[: body.limit]
        evidence = await self._tools.evidence_for_documents(
            document_ids=[item.id for item in selected],
            project_id=scope.project.id,
            user=user,
            limit=body.limit,
        )
        evidence_by_document = {item.document_id: item for item in evidence}
        changes: list[ChangeItem] = []
        counts: dict[str, int] = {}
        for document in selected:
            item = evidence_by_document.get(document.id)
            if item is None:
                continue
            changed_at = _source_datetime(document) or document.updated_at
            counts[item.source_type] = counts.get(item.source_type, 0) + 1
            changes.append(
                ChangeItem(
                    changed_at=changed_at,
                    change_type="updated" if document.current_version > 1 else "created",
                    source_type=item.source_type,
                    source_id=item.source_id,
                    title=item.title,
                    source_url=item.source_url,
                    summary=item.snippet,
                    citation_identity=item.citation_identity,
                    document_id=document.id,
                )
            )
        changes.sort(key=lambda item: item.changed_at, reverse=True)
        return ChangeResponse(
            project_id=scope.project.id,
            start_date=body.start_date,
            end_date=body.end_date,
            changes=changes,
            deduplicated_count=max(0, len(eligible) - len(deduped)),
            source_counts=counts,
        )

    async def freshness(self, *, project_id: uuid.UUID, user: User) -> FreshnessResponse:
        scope = await self._authorization.authorized_scope(user=user, project_id=project_id)
        documents = list(
            await self._db.scalars(
                select(Document).where(
                    Document.knowledge_base_id.in_(scope.knowledge_base_ids),
                    Document.is_deleted.is_(False),
                )
            )
        )
        now = utcnow()
        issues: list[FreshnessIssue] = []
        stale = 0
        failing = 0
        outdated_slack = 0
        replaced = 0
        thresholds = {"jira": 45, "confluence": 180, "slack": 30, "github": 90, "upload": 365}
        for document in documents:
            metadata = document.doc_metadata or {}
            source_type = str(metadata.get("source_family") or metadata.get("source") or document.source_type)
            source_id = str(metadata.get("source_id") or document.id)
            source_url = str(metadata.get("source_url") or "").strip() or None
            updated = _source_datetime(document) or document.updated_at
            age_days = max(0, (now - updated).days)
            threshold = thresholds.get(source_type, 180)
            if age_days > threshold:
                stale += 1
                if source_type == "slack":
                    outdated_slack += 1
                issues.append(
                    FreshnessIssue(
                        kind="outdated_slack_resolution" if source_type == "slack" else "stale_source",
                        severity="warning",
                        source_type=source_type,
                        source_id=source_id,
                        title=document.title,
                        age_days=age_days,
                        source_url=source_url,
                        suggested_remediation=(
                            "Re-check the public Slack thread and ingest a current resolution."
                            if source_type == "slack"
                            else "Refresh or revalidate this source with its owner."
                        ),
                    )
                )
            if document.status == DocumentStatus.FAILED:
                failing += 1
                issues.append(
                    FreshnessIssue(
                        kind="failing_source",
                        severity="critical",
                        source_type=source_type,
                        source_id=source_id,
                        title=document.title,
                        age_days=age_days,
                        source_url=source_url,
                        suggested_remediation="Inspect the ingestion error, correct the source, and reindex.",
                    )
                )
            if document.current_version > 1:
                replaced += 1
        mappings = list(
            await self._db.scalars(
                select(GitHubRepositoryMapping).where(
                    GitHubRepositoryMapping.organization_id == user.organization_id,
                    GitHubRepositoryMapping.project_id == scope.project.id,
                    GitHubRepositoryMapping.knowledge_base_id.in_(scope.knowledge_base_ids),
                    GitHubRepositoryMapping.is_enabled.is_(True),
                )
            )
        )
        branch_lag = 0
        for mapping in mappings:
            age_seconds = int((now - mapping.last_indexed_at).total_seconds()) if mapping.last_indexed_at else None
            if age_seconds is None or age_seconds > 86_400:
                branch_lag += 1
                issues.append(
                    FreshnessIssue(
                        kind="repository_branch_lag",
                        severity="warning",
                        source_type="github",
                        source_id=f"{mapping.owner}/{mapping.repository}@{mapping.branch}",
                        title=f"{mapping.owner}/{mapping.repository} ({mapping.branch})",
                        age_days=(age_seconds // 86_400) if age_seconds is not None else None,
                        source_url=f"https://github.com/{mapping.owner}/{mapping.repository}/tree/{mapping.branch}",
                        suggested_remediation="Run a read-only incremental repository sync.",
                    )
                )
        connector_rows = list(
            await self._db.scalars(
                select(ConnectorState).where(ConnectorState.organization_id == user.organization_id)
            )
        )
        connectors = [
            ConnectorFreshness(
                kind=row.kind,
                status=row.status,
                last_success_at=row.last_success_at,
                lag_seconds=row.lag_seconds,
                failure_count=row.failure_count,
                detail=row.error_detail,
            )
            for row in connector_rows
        ]
        existing_kinds = {item.kind for item in connectors}
        audit_rows = list(
            await self._db.scalars(
                select(AuditLog)
                .where(
                    AuditLog.organization_id == user.organization_id,
                    AuditLog.action.in_(["jira.sync", "confluence.sync"]),
                )
                .order_by(AuditLog.created_at.desc())
            )
        )
        for kind in ("jira", "confluence"):
            if kind in existing_kinds:
                continue
            latest = next((row for row in audit_rows if row.action == f"{kind}.sync"), None)
            connectors.append(
                ConnectorFreshness(
                    kind=kind,
                    status="connected" if latest else "not_synced",
                    last_success_at=latest.created_at if latest else None,
                    lag_seconds=int((now - latest.created_at).total_seconds()) if latest else None,
                    failure_count=0,
                    detail=latest.detail if latest else None,
                )
            )
        suggestions = []
        if stale:
            suggestions.append(f"Revalidate {stale} stale authorized source(s) with their owners.")
        if failing:
            suggestions.append(f"Repair and reindex {failing} failed document(s).")
        if branch_lag:
            suggestions.append(f"Refresh {branch_lag} repository mapping(s) whose indexed branch is old or missing.")
        if not suggestions:
            suggestions.append("No urgent freshness remediation is required for the selected project.")
        penalty = min(100, stale * 2 + failing * 15 + branch_lag * 8 + outdated_slack * 3)
        sorted_issues = sorted(
            issues,
            key=lambda item: (item.severity != "critical", -(item.age_days or 0)),
        )
        return FreshnessResponse(
            project_id=scope.project.id,
            generated_at=now,
            score=max(0, 100 - penalty),
            stale_sources=stale,
            failing_sources=failing,
            outdated_slack_resolutions=outdated_slack,
            repository_branch_lag=branch_lag,
            replaced_documents=replaced,
            total_findings=len(sorted_issues),
            issues=sorted_issues[:200],
            connectors=sorted(connectors, key=lambda item: item.kind),
            suggestions=suggestions,
        )


def _dedupe_evidence(evidence: list[Evidence], *, limit: int) -> list[Evidence]:
    seen: set[str] = set()
    result: list[Evidence] = []
    for item in evidence:
        if item.citation_identity in seen:
            continue
        seen.add(item.citation_identity)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _metadata_text(evidence: Evidence | None, *keys: str) -> str | None:
    if evidence is None:
        return None
    for key in keys:
        value = str(evidence.metadata.get(key) or "").strip()
        if value:
            return value
    return None


def _metadata_list(evidence: Evidence, key: str) -> list[object]:
    value = evidence.metadata.get(key)
    return value if isinstance(value, list) else []


def _matches_issue(evidence: Evidence, issue_key: str) -> bool:
    searchable = " ".join(
        (
            evidence.source_id,
            evidence.title,
            evidence.snippet,
            evidence.content,
        )
    ).upper()
    return issue_key.upper() in searchable


def _dedupe_incident_sources(evidence: list[Evidence]) -> list[Evidence]:
    seen: set[tuple[str, str]] = set()
    result: list[Evidence] = []
    for item in evidence:
        identity = (item.source_type, item.source_id)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(item)
    return result


def _timeline_detail(evidence: Evidence) -> str:
    status = _metadata_text(evidence, "jira_issue_status", "state", "status")
    return f"{status + ': ' if status else ''}{evidence.snippet[:280]}"


def _source_datetime(document: Document) -> datetime | None:
    metadata = document.doc_metadata or {}
    value = metadata.get("source_updated_at") or metadata.get("updated_at")
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
