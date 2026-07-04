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
    status: str
    error: str | None
    current_version: int
    created_at: datetime
    updated_at: datetime


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    total: int


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
