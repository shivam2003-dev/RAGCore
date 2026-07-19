"""Repository-level hybrid search against real Postgres + pgvector."""

import pytest
from sqlalchemy import select

from core.config import get_settings
from database.base import utcnow
from embeddings.fake import FakeEmbeddings
from models import Chunk, Document, DocumentStatus, DocumentVersion, KnowledgeBase, Organization
from repositories.chunks import ChunkSearchRepository
from retrieval.context import RetrievalContext
from retrieval.crag import AlwaysAcceptPolicy
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
        organization_id=org.id,
        name="KB",
        embedding_model="fake",
        embedding_dimensions=embedder.dimensions,
    )
    db.add(kb)
    await db.flush()
    doc = Document(
        knowledge_base_id=kb.id,
        title="Handbook",
        source_type="txt",
        status=DocumentStatus.READY,
    )
    db.add(doc)
    await db.flush()
    version = DocumentVersion(
        document_id=doc.id,
        version=1,
        file_path="/dev/null",
        file_sha256="0" * 64,
        file_size_bytes=1,
        created_at=utcnow(),
    )
    db.add(version)
    await db.flush()
    vectors = await embedder.embed(CONTENTS)
    for i, (content, vec) in enumerate(zip(CONTENTS, vectors, strict=True)):
        db.add(
            Chunk(
                knowledge_base_id=kb.id,
                document_id=doc.id,
                document_version_id=version.id,
                ordinal=i,
                content=content,
                token_count=20,
                embedding=vec,
                created_at=utcnow(),
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


async def test_sparse_search_uses_document_titles_for_broad_questions(db, seeded_kb):
    kb, embedder = seeded_kb
    doc = Document(
        knowledge_base_id=kb.id,
        title="Kubernetes Deployment Architecture",
        source_type="md",
        status=DocumentStatus.READY,
    )
    db.add(doc)
    await db.flush()
    version = DocumentVersion(
        document_id=doc.id,
        version=1,
        file_path="/dev/null",
        file_sha256="2" * 64,
        file_size_bytes=1,
        created_at=utcnow(),
    )
    db.add(version)
    await db.flush()
    content = "System overview with control plane, worker nodes, and rollout flow."
    vector = (await embedder.embed([content]))[0]
    db.add(
        Chunk(
            knowledge_base_id=kb.id,
            document_id=doc.id,
            document_version_id=version.id,
            ordinal=0,
            content=content,
            token_count=20,
            embedding=vector,
            created_at=utcnow(),
        )
    )
    await db.commit()

    hits = await ChunkSearchRepository(db).sparse_search(
        kb.id,
        "Explain Kubernetes deployment architecture and components",
        limit=5,
    )

    assert hits
    assert hits[0].document_id == doc.id


async def test_pipeline_end_to_end(db, seeded_kb):
    kb, embedder = seeded_kb
    pipeline = RetrievalPipeline(search_repo=ChunkSearchRepository(db), embedder=embedder, settings=get_settings())
    ctx = await pipeline.run(RetrievalContext(kb_id=kb.id, query="incident response on-call paging", top_k=2))
    assert ctx.chunks
    assert "on-call" in ctx.chunks[0].content
    assert ctx.confidence is not None and ctx.confidence > 0
    assert ctx.attempts[0].result_count == len(ctx.chunks)
    assert "retrieval" in ctx.timings_ms and "embedding" in ctx.timings_ms


async def test_pipeline_can_search_across_multiple_knowledge_bases(db, seeded_kb):
    kb, embedder = seeded_kb
    jira_kb = KnowledgeBase(
        organization_id=kb.organization_id,
        name="Jira DEVO",
        embedding_model="fake",
        embedding_dimensions=embedder.dimensions,
    )
    db.add(jira_kb)
    await db.flush()
    doc = Document(
        knowledge_base_id=jira_kb.id,
        title="DEVO-10555: Broker installation",
        source_type="md",
        status=DocumentStatus.READY,
    )
    db.add(doc)
    await db.flush()
    version = DocumentVersion(
        document_id=doc.id,
        version=1,
        file_path="/dev/null",
        file_sha256="1" * 64,
        file_size_bytes=1,
        created_at=utcnow(),
    )
    db.add(version)
    await db.flush()
    content = "Issue key: DEVO-10555\nStatus: To Do\nAssignee email: s.kumar@kimbal.io"
    vector = (await embedder.embed([content]))[0]
    db.add(
        Chunk(
            knowledge_base_id=jira_kb.id,
            document_id=doc.id,
            document_version_id=version.id,
            ordinal=0,
            content=content,
            token_count=20,
            embedding=vector,
            created_at=utcnow(),
        )
    )
    await db.commit()

    pipeline = RetrievalPipeline(search_repo=ChunkSearchRepository(db), embedder=embedder, settings=get_settings())
    ctx = await pipeline.run(
        RetrievalContext(
            kb_id=kb.id,
            kb_ids=[kb.id, jira_kb.id],
            query="open issue assigned to s.kumar@kimbal.io from DEVO board",
            top_k=3,
        )
    )

    assert ctx.chunks
    assert any("DEVO-10555" in chunk.content for chunk in ctx.chunks)


async def test_rrf_exact_and_rare_arms_expose_provenance(db, seeded_kb):
    kb, embedder = seeded_kb
    document = Document(
        knowledge_base_id=kb.id,
        title="ERR5029 broker-17.prod.example.com",
        source_type="txt",
        status=DocumentStatus.READY,
        doc_metadata={"source": "upload"},
    )
    db.add(document)
    await db.flush()
    version = DocumentVersion(
        document_id=document.id,
        version=1,
        file_path="/dev/null",
        file_sha256="3" * 64,
        file_size_bytes=1,
        created_at=utcnow(),
    )
    db.add(version)
    await db.flush()
    content = "ERR5029 occurs on broker-17.prod.example.com when --retry-limit is exhausted."
    vector = (await embedder.embed([content]))[0]
    db.add(
        Chunk(
            knowledge_base_id=kb.id,
            document_id=document.id,
            document_version_id=version.id,
            ordinal=0,
            content=content,
            token_count=20,
            embedding=vector,
            created_at=utcnow(),
        )
    )
    await db.commit()

    settings = get_settings().model_copy(
        update={
            "retrieval_fusion_mode": "rrf",
            "retrieval_exact_identifier_enabled": True,
            "retrieval_rare_token_enabled": True,
        }
    )
    pipeline = RetrievalPipeline(
        search_repo=ChunkSearchRepository(db),
        embedder=embedder,
        settings=settings,
        policy=AlwaysAcceptPolicy(),
    )
    ctx = await pipeline.run(
        RetrievalContext(
            kb_id=kb.id,
            query="Find ERR5029 on broker-17.prod.example.com with --retry-limit",
            top_k=3,
        )
    )

    assert ctx.chunks[0].document_id == document.id
    assert {"exact_identifier", "rare_token"}.issubset(ctx.chunks[0].retrieval_arms)
    assert ctx.trace["fusion_mode"] == "rrf"
    assert {arm["arm"] for arm in ctx.trace["arms"]} >= {
        "dense",
        "sparse",
        "exact_identifier",
        "rare_token",
    }
    rare_trace = ctx.trace["rare_token_signal"]
    assert rare_trace["total_documents"] >= 2
    assert rare_trace["document_frequencies"]["err5029"] == 1


async def test_neighbor_expansion_uses_real_chunk_identity_after_ranking(db, seeded_kb):
    kb, embedder = seeded_kb
    settings = get_settings().model_copy(
        update={
            "retrieval_neighbor_expansion_enabled": True,
            "retrieval_neighbor_window": 1,
            "retrieval_neighbor_token_budget": 20,
            "retrieval_neighbor_max_chunks": 1,
        }
    )
    pipeline = RetrievalPipeline(
        search_repo=ChunkSearchRepository(db),
        embedder=embedder,
        settings=settings,
        policy=AlwaysAcceptPolicy(),
    )
    ctx = await pipeline.run(RetrievalContext(kb_id=kb.id, query="vacation paid leave", top_k=1))

    assert len(ctx.chunks) == 2
    anchor, neighbor = ctx.chunks
    assert neighbor.expanded_from_chunk_id == anchor.chunk_id
    persisted_ids = {
        chunk.id for chunk in await db.scalars(select(Chunk).where(Chunk.id.in_([anchor.chunk_id, neighbor.chunk_id])))
    }
    assert persisted_ids == {anchor.chunk_id, neighbor.chunk_id}
