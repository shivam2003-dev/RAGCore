# Operations

## Local Services

Expected local ports:

- Frontend: `http://localhost:3100`
- Backend: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`

Backend from `backend/`:

```bash
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Frontend from repo root:

```bash
npm run dev -- -p 3100
```

## Environment

Use `backend/.env` for local development. Use real secret storage in production.

Important backend variables:

```bash
APP_ENV=local
APP_DEBUG=false
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
LLM_PROVIDER=openrouter
LLM_MODEL=anthropic/claude-haiku-4.5
OPENROUTER_API_KEY=...
EMBEDDING_PROVIDER=fake
```

For production retrieval quality, configure a real embedding provider such as OpenAI, Jina, Voyage, or a TEI-compatible endpoint.

## Health and Metrics

- `GET /healthz`
- `GET /readyz`
- `GET /metrics`
- `GET /api/v1/metrics/overview`

`/metrics` exposes Prometheus metrics. `/api/v1/metrics/overview` returns product metrics used by the frontend and is authenticated.

## Docker

The backend Dockerfile is multi-stage and runs as a non-root user. Use the compose full profile when local Postgres, Redis, and backend need to run together.

## Kubernetes

Kubernetes manifests include:

- migration init container
- readiness and liveness probes
- horizontal pod autoscaling
- ingress tuned for SSE streaming

Run migrations before serving API traffic.

## Atlassian Sync Operations

Use the UI buttons in Knowledge Sources or Data Sources, or call:

```bash
POST /api/v1/confluence/sync
POST /api/v1/jira/sync
```

After sync, ingestion runs in the background. Check Documents or Content Health for ready/failed status.

## Runtime Debugging

Common checks:

1. Confirm API status in `/docs`.
2. Confirm connector status endpoints show `configured: true`.
3. Sync Confluence/Jira.
4. Wait until documents are `ready`.
5. Ask a source-specific question in `/ask`.
6. Verify sources in the right rail point to the expected synced documents.
