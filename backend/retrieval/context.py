import time
import uuid
from dataclasses import dataclass, field


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    content: str
    metadata: dict = field(default_factory=dict)
    dense_score: float = 0.0
    sparse_score: float = 0.0
    score: float = 0.0  # fused


@dataclass(slots=True)
class RetrievalAttempt:
    query: str
    top_k: int
    result_count: int
    confidence: float | None = None


@dataclass(slots=True)
class RetrievalContext:
    """Mutable state threaded through pipeline steps.

    confidence + attempts exist for CRAG: an evaluator fills confidence, a
    policy inspects it and may loop (rewrite / widen K / fallback), appending
    one RetrievalAttempt per try.
    """

    kb_id: uuid.UUID
    query: str
    top_k: int
    collection_id: uuid.UUID | None = None
    rewritten_query: str | None = None
    conversation_context: str = ""
    chunks: list[RetrievedChunk] = field(default_factory=list)
    confidence: float | None = None
    attempts: list[RetrievalAttempt] = field(default_factory=list)
    timings_ms: dict[str, int] = field(default_factory=dict)

    @property
    def effective_query(self) -> str:
        return self.rewritten_query or self.query

    def time_stage(self, stage: str, started_at: float) -> None:
        self.timings_ms[stage] = int((time.perf_counter() - started_at) * 1000)
