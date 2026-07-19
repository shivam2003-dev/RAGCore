"""Wire models (Pydantic). Deliberately separate from ORM models."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth ---
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    organization_name: str = Field(min_length=2, max_length=255)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    default_project_id: uuid.UUID | None
    created_at: datetime


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    role: str = Field(default="viewer", pattern="^(admin|editor|viewer)$")


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ApiKeyCreatedResponse(BaseModel):
    id: uuid.UUID
    name: str
    key: str  # returned exactly once
    key_prefix: str


# --- knowledge ---
class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""


class KnowledgeBaseOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str
    embedding_model: str
    access_scope: str
    created_at: datetime


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=100)
    description: str = Field(default="", max_length=2000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class ProjectOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str
    is_active: bool
    source_ids: list[uuid.UUID] = Field(default_factory=list)
    authorized_source_ids: list[uuid.UUID] = Field(default_factory=list)
    member_count: int = 0
    user_project_role: str | None = None
    created_at: datetime
    updated_at: datetime


class ProjectSourceUpdate(BaseModel):
    knowledge_base_ids: list[uuid.UUID] = Field(max_length=500)


class ProjectMemberWrite(BaseModel):
    user_id: uuid.UUID
    project_role: str = Field(default="member", pattern="^(member|manager)$")


class ProjectMemberUpdate(BaseModel):
    members: list[ProjectMemberWrite] = Field(max_length=500)


class ProjectMemberOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    project_role: str


class DefaultProjectUpdate(BaseModel):
    project_id: uuid.UUID


class SourcePermissionUpdate(BaseModel):
    access_scope: str = Field(pattern="^(organization|restricted)$")
    user_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


class SourcePermissionOut(BaseModel):
    knowledge_base_id: uuid.UUID
    access_scope: str
    user_ids: list[uuid.UUID]


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""


class CollectionOut(ORMModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    name: str
    description: str


class DocumentOut(ORMModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    collection_id: uuid.UUID | None
    title: str
    source_type: str
    knowledge_base_name: str | None = None
    status: str
    error: str | None
    current_version: int
    created_at: datetime
    updated_at: datetime


class DocumentVersionLineageOut(BaseModel):
    version: int
    file_sha256: str
    file_size_bytes: int
    created_at: datetime


class DocumentLineageOut(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    knowledge_base_name: str | None
    title: str
    source_type: str
    source_system: str
    source_id: str | None
    source_url: str | None
    source_version: str | int | None
    source_updated_at: str | None
    source_sha256: str | None
    status: str
    current_version: int
    chunk_count: int
    active_chunk_count: int
    embedding_model: str | None
    created_at: datetime
    updated_at: datetime
    metadata: dict
    versions: list[DocumentVersionLineageOut]


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    total: int


# --- Confluence ---
class ConfluenceStatusOut(BaseModel):
    configured: bool
    read_only: bool = True
    base_url: str | None
    space_key: str
    default_kb_name: str
    auth_mode: str
    email_configured: bool
    token_configured: bool
    requires_email: bool


class ConfluenceSyncRequest(BaseModel):
    knowledge_base_id: uuid.UUID | None = None
    max_pages: int | None = Field(default=None, ge=1, le=100_000)


class ConfluencePageSyncOut(BaseModel):
    page_id: str
    title: str
    url: str
    version: int | None
    document_id: uuid.UUID
    document_status: str
    action: str


class ConfluenceSyncResponse(BaseModel):
    knowledge_base_id: uuid.UUID
    knowledge_base_name: str
    space_key: str
    space_name: str
    total_pages: int
    created: int
    updated: int
    skipped: int
    documents: list[ConfluencePageSyncOut]


# --- Jira ---
class JiraStatusOut(BaseModel):
    configured: bool
    read_only: bool = True
    base_url: str | None
    project_key: str
    board_id: int
    default_kb_name: str
    auth_mode: str
    email_configured: bool
    token_configured: bool
    using_atlassian_fallback_credentials: bool
    requires_email: bool


class JiraSyncRequest(BaseModel):
    knowledge_base_id: uuid.UUID | None = None
    max_issues: int | None = Field(default=None, ge=1, le=100_000)


class JiraIssueSyncOut(BaseModel):
    issue_id: str
    issue_key: str
    title: str
    url: str
    status: str | None
    updated_at: str | None
    document_id: uuid.UUID
    document_status: str
    action: str


# --- Slack ---
class SlackChannelConfigIn(BaseModel):
    channel_id: str = Field(min_length=3, max_length=64)
    channel_name: str = Field(min_length=1, max_length=255)
    project_id: uuid.UUID
    visibility: str = Field(default="public", pattern="^public$")


class SlackConfigurationIn(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=64)
    channels: list[SlackChannelConfigIn] = Field(default_factory=list, max_length=100)


class SlackChannelOut(BaseModel):
    id: uuid.UUID
    workspace_id: str
    channel_id: str
    channel_name: str
    visibility: str
    is_enabled: bool
    project_id: uuid.UUID
    knowledge_base_id: uuid.UUID
    last_thread_ts: str | None


class SlackStatusOut(BaseModel):
    configured: bool
    credentials_configured: bool
    socket_mode_configured: bool
    read_only: bool = True
    workspace_id: str | None
    status: str
    allowlisted_channels: int
    last_event_at: datetime | None
    last_success_at: datetime | None
    last_error_at: datetime | None
    lag_seconds: int | None
    failure_count: int
    error_detail: str | None
    channels: list[SlackChannelOut]


class SlackSyncRequest(BaseModel):
    channel_id: str | None = Field(default=None, min_length=3, max_length=64)


class SlackSyncOut(BaseModel):
    created: int
    updated: int
    skipped: int
    deleted: int
    failed: int


# --- GitHub ---
class GitHubRepositoryConfigIn(BaseModel):
    owner: str = Field(min_length=1, max_length=255)
    repository: str = Field(min_length=1, max_length=255)
    branch: str = Field(default="main", min_length=1, max_length=255)
    project_id: uuid.UUID
    path_allowlist: list[str] = Field(default_factory=list, max_length=200)
    path_denylist: list[str] = Field(default_factory=list, max_length=200)


class GitHubRepositoryOut(BaseModel):
    id: uuid.UUID
    owner: str
    repository: str
    branch: str
    project_id: uuid.UUID
    knowledge_base_id: uuid.UUID
    path_allowlist: list[str]
    path_denylist: list[str]
    is_enabled: bool
    status: str
    head_commit_sha: str | None
    head_tree_sha: str | None
    last_indexed_at: datetime | None
    last_error_at: datetime | None
    error_detail: str | None


class GitHubStatusOut(BaseModel):
    configured: bool
    credentials_configured: bool
    read_only: bool = True
    preferred_auth: str
    status: str
    repositories: list[GitHubRepositoryOut]
    last_success_at: datetime | None
    last_error_at: datetime | None
    lag_seconds: int | None
    failure_count: int
    error_detail: str | None


class GitHubSyncOut(BaseModel):
    created: int
    updated: int
    renamed: int
    deleted: int
    skipped: int
    denied: int
    oversized: int
    binary: int
    commit_sha: str
    tree_sha: str


class GitHubPullRequestOut(BaseModel):
    number: int
    title: str
    body: str
    state: str
    author: str
    url: str
    base_branch: str
    head_branch: str
    created_at: str
    updated_at: str
    merged_at: str | None
    draft: bool
    labels: list[str]


class ExactCodeSearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=256)
    project_id: uuid.UUID | None = None
    limit: int = Field(default=20, ge=1, le=100)


class ExactCodeHitOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    path: str
    symbol: str | None
    language: str
    commit_sha: str
    url: str
    snippet: str


class ExactCodeSearchOut(BaseModel):
    hits: list[ExactCodeHitOut]


class JiraSyncResponse(BaseModel):
    knowledge_base_id: uuid.UUID
    knowledge_base_name: str
    project_key: str
    board_id: int
    board_name: str
    total_issues: int
    created: int
    updated: int
    skipped: int
    documents: list[JiraIssueSyncOut]


# --- live metrics ---
class SourceMetricOut(BaseModel):
    knowledge_base_id: uuid.UUID | None = None
    name: str
    source_type: str
    source_scope: str | None = None
    connector: str | None = None
    health: str = "unknown"
    documents: int
    ready_documents: int
    pending_documents: int = 0
    uploaded_documents: int = 0
    processing_documents: int = 0
    failed_documents: int
    chunks_active: int = 0
    last_updated_at: datetime | None
    last_ingested_at: datetime | None = None
    last_run_at: datetime | None = None
    last_run_detail: str | None = None


class ConnectorRunOut(BaseModel):
    connector: str
    knowledge_base_id: uuid.UUID | None
    status: str
    total: int
    created: int
    updated: int
    skipped: int
    failed: int
    detail: str | None
    created_at: datetime


class ActivityMetricOut(BaseModel):
    action: str
    resource_type: str
    detail: str | None
    created_at: datetime


class QuestionMetricOut(BaseModel):
    question: str
    count: int
    last_asked_at: datetime


class FeedbackMetricOut(BaseModel):
    helpful: int
    not_helpful: int
    total: int
    helpful_rate: float | None


class MetricsOverviewOut(BaseModel):
    knowledge_bases: int
    documents_total: int
    documents_ready: int
    documents_processing: int
    documents_failed: int
    chunks_active: int
    conversations: int
    questions_asked: int
    assistant_answers: int
    active_users: int
    avg_latency_ms: int | None
    feedback: FeedbackMetricOut
    sources: list[SourceMetricOut]
    connector_runs: list[ConnectorRunOut]
    recent_activity: list[ActivityMetricOut]
    top_questions: list[QuestionMetricOut]


# --- evals ---
class EvalScoreOut(BaseModel):
    id: str
    label: str
    value: float | None
    display: str
    status: str
    detail: str


class EvalLatencyOut(BaseModel):
    avg_ms: int | None
    p50_ms: int | None
    p95_ms: int | None
    sample_size: int


class EvalModelOut(BaseModel):
    model: str
    answers: int
    avg_latency_ms: int | None
    citation_coverage: float | None
    groundedness_score: float | None


class EvalRecentAnswerOut(BaseModel):
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    question: str
    answer_preview: str
    model: str | None
    created_at: datetime
    latency_ms: int | None
    citations: int
    groundedness_score: float | None
    relevance_score: float | None
    unsupported_claim_rate: float | None = None
    source_mode: str = "unknown"
    answer_mode: str = "unknown"
    verdict: str = "unknown"
    issues: list[str] = []


class EvalModeOut(BaseModel):
    source_mode: str
    answer_mode: str
    answers: int
    avg_latency_ms: int | None
    groundedness_score: float | None
    unsupported_claim_rate: float | None
    failure_rate: float | None


class EvalQualitySummaryOut(BaseModel):
    evaluated: int
    healthy: int
    needs_review: int
    failures: int
    issue_counts: dict[str, int]


class EvalBenchmarkComponentOut(BaseModel):
    id: str
    label: str
    value: float | None
    weight: float
    display: str


class EvalBenchmarkOut(BaseModel):
    label: str
    score: int | None
    value: float | None
    display: str
    status: str
    sample_size: int
    detail: str
    components: list[EvalBenchmarkComponentOut]


class GoldenEvalCaseOut(BaseModel):
    id: str
    category: str
    question: str
    expected_source_types: list[str]
    expected_source_ids: list[str] = []
    expected_source_titles: list[str] = []
    expected_answer_traits: list[str]
    tags: list[str] = []


class GoldenEvalDatasetOut(BaseModel):
    dataset_path: str
    cases: int
    categories: dict[str, int]
    source_types: dict[str, int]
    benchmark_ready: bool
    run_command: str
    sample: list[GoldenEvalCaseOut]


class EvalGateMetricOut(BaseModel):
    id: str
    label: str
    value: float | None
    display: str
    threshold: float | None = None
    passed: bool
    detail: str


class EvalGateCaseOut(BaseModel):
    id: str
    category: str
    question: str
    passed: bool
    expected_sources: list[str]
    returned_sources: list[str]
    returned_source_titles: list[str]
    answer_text: str
    judge_rationale: str
    latency_ms: int
    scores: dict[str, float | None]
    model_comparison: dict[str, float | int | str | None]
    role_space_checks: dict[str, bool]


class EvalGateRunOut(BaseModel):
    generated_at: datetime
    dataset_path: str
    cases: int
    passed: bool
    score: int | None
    display: str
    thresholds: dict[str, float]
    metrics: list[EvalGateMetricOut]
    failing_cases: list[EvalGateCaseOut]
    cases_detail: list[EvalGateCaseOut]
    regression_trend: list[dict[str, float | int | str | None]]
    methodology: list[str]


class EvalOverviewOut(BaseModel):
    generated_at: datetime
    answers_total: int
    sample_size: int
    benchmark: EvalBenchmarkOut
    golden_dataset: GoldenEvalDatasetOut
    feedback: FeedbackMetricOut
    scores: list[EvalScoreOut]
    latency: EvalLatencyOut
    models: list[EvalModelOut]
    modes: list[EvalModeOut]
    quality: EvalQualitySummaryOut
    recent_answers: list[EvalRecentAnswerOut]
    methodology: list[str]


# --- web search ---
class WebSearchStatusOut(BaseModel):
    configured: bool
    provider: str
    default_kb_name: str
    top_k: int
    reason: str


# --- discover ---
class DiscoverDepartmentOut(BaseModel):
    id: str
    label: str
    description: str
    query: str


class DiscoverArticleOut(BaseModel):
    id: str
    title: str
    url: str
    source: str
    summary: str
    section: str
    department: str
    published_at: str | None = None
    score: float


class DiscoverBoardItemOut(BaseModel):
    title: str
    url: str | None = None
    source_type: str
    status: str
    updated_at: datetime


class DiscoverBoardPulseOut(BaseModel):
    jira_documents: int
    confluence_documents: int
    upload_documents: int
    web_documents: int
    latest_items: list[DiscoverBoardItemOut]


class DiscoverFeedOut(BaseModel):
    generated_at: datetime
    provider: str
    configured: bool
    department: str
    departments: list[DiscoverDepartmentOut]
    lead: DiscoverArticleOut | None
    articles: list[DiscoverArticleOut]
    alerts: list[DiscoverArticleOut]
    research: list[DiscoverArticleOut]
    board_pulse: DiscoverBoardPulseOut
    warnings: list[str] = []


class ChatCapabilitiesOut(BaseModel):
    answer_modes: list[str]
    council_configured: bool
    council_models: list[str]
    council_available_models: list[str]
    council_chair_model: str | None
    council_reason: str


class RoleGenerateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    goal: str = Field(min_length=1, max_length=800)
    source_focus: str = Field(default="", max_length=500)
    output_style: str = Field(default="", max_length=500)


class RoleGenerateResponse(BaseModel):
    name: str
    prompt: str


# --- search ---
class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    knowledge_base_id: uuid.UUID
    project_id: uuid.UUID | None = None
    collection_id: uuid.UUID | None = None
    top_k: int = Field(default=8, ge=1, le=50)


class SearchHitOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    content: str
    score: float
    dense_score: float
    sparse_score: float


class SearchResponse(BaseModel):
    hits: list[SearchHitOut]
    confidence: float | None
    timings_ms: dict[str, int]
    trace: dict[str, object] | None = None


# --- chat ---
class ConversationCreate(BaseModel):
    knowledge_base_id: uuid.UUID
    project_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=300)


class ConversationOut(ORMModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    created_at: datetime
    updated_at: datetime


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    regenerate: bool = False
    project_id: uuid.UUID | None = None
    source_mode: str = Field(default="knowledge", pattern="^(knowledge|web|blended)$")
    answer_mode: str = Field(default="fast", pattern="^(fast|council)$")
    assistant_role: str | None = Field(default=None, max_length=80)
    assistant_role_prompt: str | None = Field(default=None, max_length=1800)
    council_models: list[str] | None = Field(default=None, min_length=2, max_length=3)
    council_chair_model: str | None = Field(default=None, max_length=200)


class CitationOut(ORMModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    marker: int
    score: float
    snippet: str
    document_title: str | None = None
    title: str | None = None
    source_type: str | None = None
    url: str | None = None


class MessageOut(ORMModel):
    id: uuid.UUID
    role: str
    content: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int | None
    timings: dict
    model: str | None
    created_at: datetime
    citations: list[CitationOut] = []


# --- feedback ---
class FeedbackCreate(BaseModel):
    message_id: uuid.UUID
    rating: int = Field(ge=-1, le=1)
    comment: str | None = Field(default=None, max_length=2000)


# --- admin ---
class RoleUpdate(BaseModel):
    role: str = Field(pattern="^(admin|editor|viewer)$")


class AuditLogOut(ORMModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    detail: str | None
    created_at: datetime
