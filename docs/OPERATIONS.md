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

Routine Jira refreshes are bounded by `JIRA_SYNC_MAX_ISSUES=500` and process the most recently
updated visible issues. Set the value to `0` only for an intentional full-project refresh; large
projects can contain many thousands of issues and comment/attachment hydration will take time.
Exact Jira-key questions do not wait for this sweep: Ask reads that issue family live and read-only.

Jira evidence controls:

```bash
JIRA_INCLUDE_COMMENTS=true
JIRA_MAX_COMMENTS_PER_ISSUE=100
JIRA_EXTRACT_ATTACHMENTS=true
JIRA_MAX_ATTACHMENTS_PER_ISSUE=10
JIRA_ATTACHMENT_MAX_BYTES=5242880
JIRA_HYDRATION_CONCURRENCY=8
```

## Runtime Debugging

Common checks:

1. Confirm API status in `/docs`.
2. Confirm connector status endpoints show `configured: true`.
3. Sync Confluence/Jira.
4. Wait until documents are `ready`.
5. Ask a source-specific question in `/`.
6. Verify sources in the right rail point to the expected synced documents.
