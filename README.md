# RAGCore

RAGCore is the repository for the CVUM enterprise knowledge hub: a Next.js 16 frontend and
FastAPI backend backed by PostgreSQL/pgvector and Redis. It provides Project-scoped, permission-aware
RAG across local documents and read-only Confluence, Jira, public Slack, and GitHub sources.

Core workflows include grounded Ask with citations, Incident Copilot, evidence-backed expert
ranking, authorized change summaries, a Knowledge Freshness Center, and read-only REST/MCP evidence
tools.

## Local development

Prerequisites: Node.js/npm, Python 3.13 with `uv`, Docker, and Docker Compose.

```bash
docker compose up -d postgres redis
cd backend
uv sync
.venv/bin/alembic upgrade head
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
npm install
npm run dev -- --hostname 127.0.0.1 --port 3100
```

Open `http://localhost:3100`. Copy `backend/.env.example` to the ignored `backend/.env` for local
configuration. Never commit populated environment files or credentials.

## Verification

```bash
npm run lint
npx tsc --noEmit
env NODE_ENV=production npm run build

cd backend
.venv/bin/ruff check .
.venv/bin/pytest -q
.venv/bin/python scripts/run_evals.py
```

See [Testing](./docs/TESTING.md) for scoped type checks, migration gates, and the browser matrix.

## Documentation

- [Documentation index](./docs/README.md)
- [Architecture](./docs/ARCHITECTURE.md)
- [Projects and authorization](./docs/PROJECTS_AND_AUTHORIZATION.md)
- [RAG pipeline](./docs/RAG_PIPELINE.md)
- [Evidence-backed workflows](./docs/KNOWLEDGE_WORKFLOWS.md)
- [Slack connector](./docs/SLACK_CONNECTOR.md)
- [GitHub connector](./docs/GITHUB_CONNECTOR.md)
- [MCP evidence tools](./docs/MCP_TOOLS.md)
- [Operations](./docs/OPERATIONS.md)
- [Migrations and rollback](./docs/MIGRATIONS_AND_ROLLBACK.md)
- [Security and secrets](./docs/SECURITY_AND_SECRETS.md)

Jira and Confluence integrations are read-only. Slack is restricted to explicitly allowlisted public
channels. GitHub indexing uses GET-only APIs and never executes connected repository code.
