# Architecture

## System Shape

The application is split into a Next.js frontend and a FastAPI backend.

- Frontend: `app/`, `components/`, `lib/`
- Backend: `backend/api`, `backend/services`, `backend/repositories`, `backend/models`
- Storage: PostgreSQL with pgvector for documents, chunks, messages, citations, audit logs, and vector search
- Cache/rate limit: Redis
- Providers: LLM and embedding providers are behind interfaces so tests can run with deterministic fakes

## Backend Layers

Requests flow through these layers:

1. Routes validate request and response schemas in `backend/api/routes`.
2. Services own business workflows such as document upload, chat, Confluence sync, and Jira sync.
3. Repositories isolate database access.
4. Providers implement embeddings and LLM streaming behind protocol-style interfaces.

Vector search is isolated in `backend/repositories/chunks.py`. The retrieval pipeline calls repository methods, so swapping the vector store should not affect routes or service-level logic.

## Core Domains

- Auth: Argon2 passwords, JWT access tokens, rotating refresh tokens, API keys, RBAC, and audit logs.
- Knowledge: knowledge bases, documents, document versions, chunks, and collections.
- Retrieval: dense pgvector HNSW search plus sparse Postgres full-text search.
- Chat: conversations, messages, streamed SSE answers, citations, feedback, and timings.
- Connectors: read-only Confluence/Jira sync services and the allowlisted Slack Socket Mode worker.
- Metrics: live aggregate metrics from database tables, with no static dashboard numbers.

## Frontend Shape

The frontend uses a conversation-first Ask surface plus a separate enterprise admin shell. Major routes are:

- `/` RAG chat
- `/ask` permanent compatibility redirect to `/`
- `/admin` Home dashboard
- `/knowledge-sources`
- `/documents`
- `/saved-answers`
- `/analytics`
- `/usage-insights`
- `/content-health`
- `/feedback`
- `/data-sources`
- `/access-control`
- `/settings`
- `/integrations`

The frontend API client lives in `lib/kimbal-api.ts`. It performs local development session bootstrap and calls the backend APIs. Session bootstrap is single-flight so concurrent widgets do not race through register/login.

## Deployment

The backend includes:

- Multi-stage Dockerfile
- Docker Compose full profile
- Kubernetes manifests with migration init container, probes, HPA, and SSE-friendly ingress
- GitHub Actions CI for lint, type-check, tests, image build, scan, and deploy gate

The frontend currently runs locally on port `3100` and targets `http://localhost:8000/api/v1` unless `NEXT_PUBLIC_CVUM_API_BASE` overrides it.
