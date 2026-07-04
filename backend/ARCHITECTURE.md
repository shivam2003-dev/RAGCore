# Kimbal Knowledge Hub — Backend Architecture

Production backend for the Kimbal enterprise RAG platform. Python 3.13, FastAPI, PostgreSQL + pgvector, Redis.

## 1. System overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Next.js Frontend (done)                       │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ HTTPS / SSE (streaming)
┌──────────────────────────────▼───────────────────────────────────────┐
│  FastAPI                                                              │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ Middleware: request-id → auth → rate-limit → logging → metrics │  │
│  └────────────────────────────────────────────────────────────────┘  │
│  API layer (routers, request/response schemas — no business logic)   │
│  Service layer (use-cases: ingestion, retrieval, chat, auth, admin)  │
│  Repository layer (all SQL; one interface per aggregate)             │
└───────┬──────────────────────────────┬────────────────────┬──────────┘
        │ SQLAlchemy 2 (async)         │ redis-py (async)   │ httpx
┌───────▼────────────┐        ┌────────▼────────┐  ┌────────▼─────────┐
│ PostgreSQL 17      │        │ Redis 7         │  │ Providers        │
│  + pgvector 0.8    │        │  response cache │  │  embeddings      │
│  + pg_trgm         │        │  embedding cache│  │  (OpenAI/BGE/…)  │
│  relational + FTS  │        │  sessions       │  │  LLM             │
│  + vector search   │        │  rate limiting  │  │  (Claude/GPT/…)  │
└────────────────────┘        └─────────────────┘  └──────────────────┘
```

One process, one database, one cache. Horizontal scale = more FastAPI replicas; Postgres and Redis are the only stateful pieces.

## 2. Layering rules

```
api/routes  →  services  →  repositories  →  database
                  ↓
        retrieval / ingestion / embeddings / llm  (domain engines)
```

- **api/** — routers + Pydantic schemas. Translates HTTP ↔ domain. Never touches SQLAlchemy models.
- **services/** — orchestration and business rules. Only layer allowed to compose repositories, engines, and cache. Transaction boundaries live here.
- **repositories/** — all persistence. One class per aggregate (users, documents, chunks, conversations…). Vector search hidden behind `ChunkSearchRepository` so a future vector DB swap touches exactly one module.
- **models/** — SQLAlchemy ORM models (DB shape), separate from API schemas (wire shape).
- **retrieval/, ingestion/, embeddings/, llm/** — domain engines: pure logic + provider adapters, injected into services.
- **core/** — settings, security primitives, DI wiring, exceptions, logging setup. Depends on nothing above it.

Dependency direction is strictly downward. Enforced by convention + import-linter in CI.

### Dependency injection

FastAPI `Depends` for request-scoped wiring (db session, current user); constructor injection for services and engines so tests build them with fakes — no global singletons except the settings object and connection pools.

## 3. Retrieval pipeline (request path)

```
query ─ auth ─ conversation context ─ [query rewrite] ─┐
                                                       ▼
                       ┌── dense: pgvector cosine top-K ──┐
                       │                                  ├─ weighted fusion ─ [rerank] ─ prompt ─ LLM ─ SSE stream
                       └── sparse: Postgres FTS top-K ────┘                                  │
                                                                              citations extracted from
                                                                              chunk-ids echoed in output
```

- Hybrid fusion: normalized weighted sum (`score = w_dense·cos + w_sparse·ts_rank`), weights in config. Simple, debuggable, good enough until measured otherwise.
- Every stage is a `PipelineStep` protocol: `async def run(ctx: RetrievalContext) -> RetrievalContext`. The pipeline is an ordered list of steps.

### CRAG extension points (designed now, implemented later)

`RetrievalContext` carries `confidence: float | None` and `attempts: list[RetrievalAttempt]`. Three seams already in the pipeline:

1. **`RetrievalEvaluator`** protocol — scores retrieved set post-fusion. Ships as `NoopEvaluator`; CRAG drops in an LLM/classifier grader.
2. **`RetrievalPolicy`** protocol — decides `ACCEPT | REWRITE | WIDEN_K | FALLBACK` from the context. Ships as `AlwaysAccept`; CRAG adds retry loops without touching the pipeline.
3. **`GroundingVerifier`** protocol — post-generation answer-vs-sources check. Ships as noop.

Agentic RAG later = a planner service composing the same pipeline steps as tools. No rewrite needed.

## 4. Ingestion pipeline (background path)

```
upload → validate (type, size, magic bytes) → store file → extract text
      → metadata → chunk (strategy per content type) → embed (batched, cached)
      → upsert chunks+vectors (one tx) → mark document READY
```

- Runs as FastAPI `BackgroundTasks` for now — no broker (Redis stays cache-only per spec). The `IngestionQueue` interface makes a move to a real worker (arq/Celery) a config change, not a refactor.
- Document status machine: `UPLOADED → PROCESSING → READY | FAILED` with per-stage error capture.
- Versioning: new upload of same logical doc creates a new `document_version`; chunks link to version; old versions soft-deleted from search.

## 5. Data model (summary — full DDL in Module 3)

`organizations → users → knowledge_bases → collections → documents → document_versions → chunks (embedding vector(D), tsv tsvector)` plus `conversations → messages → citations`, `feedback`, `api_keys`, `audit_logs`, `refresh_tokens`.

- UUIDv7 primary keys (time-ordered, index-friendly).
- `chunks.embedding` → HNSW index (cosine); `chunks.tsv` → GIN index. Both in the same row: hybrid search is one SQL query with two CTEs.
- Embedding dimension fixed per knowledge base at creation (pgvector requires typed columns).

## 6. Cross-cutting

| Concern | Approach |
|---|---|
| AuthN | OAuth2 password flow → short-lived JWT access + rotating refresh tokens; API keys for service access |
| AuthZ | RBAC: `admin / editor / viewer` per organization, enforced in a single `require_role` dependency |
| Caching | Redis: embedding cache (hash of text+model), response cache (hash of query+kb+filters, short TTL), rate-limit counters, session/refresh state |
| Observability | structlog JSON logs w/ request-id; Prometheus `/metrics`; OpenTelemetry traces spanning retrieve→embed→llm; per-request timing breakdown returned in response metadata |
| Security | Pydantic validation everywhere, file magic-byte checks, prompt-injection guards (source-tagging + instruction hierarchy in prompt builder), PII redaction hook in logging pipeline, secrets via env only |
| Testing | pytest + pytest-asyncio; unit (engines, pure logic), integration (repos against dockerized pg w/ `kimbal_test` db), API (httpx ASGI client) |

## 7. Module build order

1. ~~Architecture~~ ← this document
2. ~~Folder structure~~ ← created
3. Database schema + Alembic
4. Configuration management
5. Authentication
6. Document upload
7. Ingestion pipeline
8. Embedding service
9. Retrieval engine
10. Hybrid search
11. Prompt builder
12. Chat service
13. Citation engine
14. Redis caching
15. REST APIs (assembly + OpenAPI polish)
16. Observability
17. Docker (backend image)
18. Kubernetes
19. Testing (fill gaps, coverage gate)
20. CI/CD

## 8. Local development

```bash
docker compose up -d          # Postgres (pgvector) on :5433, Redis on :6379
cd backend
uv sync                       # or: pip install -e ".[dev]"
alembic upgrade head
uvicorn api.main:app --reload --port 8000
```

Note: this machine exports `NODE_ENV=development` globally — irrelevant to Python, but documented for the frontend build (`NODE_ENV=production npx next build`).
