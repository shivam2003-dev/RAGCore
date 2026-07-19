import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.config import get_settings
from database.base import Base, TimestampMixin, UUIDPKMixin

EMBEDDING_DIM = get_settings().embedding_dimensions


class DocumentStatus(enum.StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class AccessScope(enum.StrEnum):
    ORGANIZATION = "organization"
    RESTRICTED = "restricted"


class KnowledgeBase(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_bases"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    embedding_model: Mapped[str] = mapped_column(String(100))
    embedding_dimensions: Mapped[int] = mapped_column(Integer, default=EMBEDDING_DIM)
    access_scope: Mapped[AccessScope] = mapped_column(
        Enum(AccessScope, name="access_scope", values_callable=lambda values: [item.value for item in values]),
        default=AccessScope.ORGANIZATION,
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_kb_org_name"),
        UniqueConstraint("organization_id", "id", name="uq_kb_org_id"),
        Index("ix_knowledge_bases_organization_id", "organization_id"),
    )


class Collection(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "collections"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        UniqueConstraint("knowledge_base_id", "name", name="uq_collection_kb_name"),
        Index("ix_collections_knowledge_base_id", "knowledge_base_id"),
    )


class Document(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"))
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collections.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[str] = mapped_column(String(20))  # pdf | docx | md | txt | csv | html
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", values_callable=lambda e: [m.value for m in e]),
        default=DocumentStatus.UPLOADED,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    doc_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document")

    __table_args__ = (Index("ix_documents_knowledge_base_id", "knowledge_base_id"),)


class DocumentVersion(UUIDPKMixin, Base):
    __tablename__ = "document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str] = mapped_column(String(64))
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    document: Mapped[Document] = relationship(back_populates="versions")

    __table_args__ = (UniqueConstraint("document_id", "version", name="uq_docver_doc_version"),)


class Chunk(UUIDPKMixin, Base):
    __tablename__ = "chunks"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"))
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer)  # position within document
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    chunk_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)  # headings, page, language
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    tsv: Mapped[str] = mapped_column(TSVECTOR, Computed("to_tsvector('english', content)", persisted=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # false for superseded versions
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_chunks_kb_active", "knowledge_base_id", "is_active"),
        Index("ix_chunks_document_id", "document_id"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
