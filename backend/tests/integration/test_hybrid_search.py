"""Repository-level hybrid search against real Postgres + pgvector."""

import pytest

from core.config import get_settings
from database.base import utcnow
from embeddings.fake import FakeEmbeddings
from models import Chunk, Document, DocumentStatus, DocumentVersion, KnowledgeBase, Organization
from repositories.chunks import ChunkSearchRepository
from retrieval.context import RetrievalContext
from retrieval.pipeline import RetrievalPipeline

CONTENTS = [
    "Kubernetes deployment requires a manifest and an image in the registry.",
    "The vacation policy allows twenty days of paid leave per year.",
    "Incident response begins by paging the on-call engineer in PagerDuty.",
]


@pytest.fixture
async def seeded_kb(db):
    embedder = FakeEmbeddings(dimensions=get_settings().embedding_dimensions)
    org = Organization(name="T", slug=f"t-{utcnow().timestamp()}")
    db.add(org)
    await db.flush()
    kb = KnowledgeBase(
        organization_id=org.id, name="KB", embedding_model="fake",
        embedding_dimensions=embedder.dimensions,
    )
    db.add(kb)
    await db.flush()
    doc = Document(
        knowledge_base_id=kb.id, title="Handbook", source_type="txt",
        status=DocumentStatus.READY,
    )
    db.add(doc)
    await db.flush()
    version = DocumentVersion(
        document_id=doc.id, version=1, file_path="/dev/null",
        file_sha256="0" * 64, file_size_bytes=1, created_at=utcnow(),
    )
    db.add(version)
    await db.flush()
    vectors = await embedder.embed(CONTENTS)
    for i, (content, vec) in enumerate(zip(CONTENTS, vectors, strict=True)):
        db.add(
            Chunk(
                knowledge_base_id=kb.id, document_id=doc.id,
                document_version_id=version.id, ordinal=i, content=content,
                token_count=20, embedding=vec, created_at=utcnow(),
            )
        )
    await db.commit()
    return kb, embedder


async def test_dense_search_ranks_related_content_first(db, seeded_kb):
    kb, embedder = seeded_kb
    repo = ChunkSearchRepository(db)
    qvec = (await embedder.embed(["how to deploy kubernetes manifest"]))[0]
    hits = await repo.dense_search(kb.id, qvec, limit=3)
    assert hits
    assert "Kubernetes" in hits[0].content


async def test_sparse_search_matches_keywords(db, seeded_kb):
    kb, _ = seeded_kb
    repo = ChunkSearchRepository(db)
    hits = await repo.sparse_search(kb.id, "vacation paid leave", limit=3)
    assert hits
    assert "vacation" in hits[0].content


async def test_pipeline_end_to_end(db, seeded_kb):
    kb, embedder = seeded_kb
    pipeline = RetrievalPipeline(
        search_repo=ChunkSearchRepository(db), embedder=embedder, settings=get_settings()
    )
    ctx = await pipeline.run(
        RetrievalContext(kb_id=kb.id, query="incident response on-call paging", top_k=2)
    )
    assert ctx.chunks
    assert "on-call" in ctx.chunks[0].content
    assert ctx.confidence is not None and ctx.confidence > 0
    assert ctx.attempts[0].result_count == len(ctx.chunks)
    assert "retrieval" in ctx.timings_ms and "embedding" in ctx.timings_ms
