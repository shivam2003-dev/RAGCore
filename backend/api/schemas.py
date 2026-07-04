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
    created_at: datetime


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
    created_at: datetime


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
    name: str
    source_type: str
    documents: int
    ready_documents: int
    failed_documents: int
    last_updated_at: datetime | None


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
    recent_activity: list[ActivityMetricOut]
    top_questions: list[QuestionMetricOut]


# --- web search ---
class WebSearchStatusOut(BaseModel):
    configured: bool
    provider: str
    default_kb_name: str
    top_k: int
    reason: str


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


# --- chat ---
class ConversationCreate(BaseModel):
    knowledge_base_id: uuid.UUID
    title: str | None = Field(default=None, max_length=300)


class ConversationOut(ORMModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    regenerate: bool = False
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
