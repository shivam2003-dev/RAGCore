# Kimbal Backend

Enterprise RAG backend. FastAPI + PostgreSQL/pgvector + Redis. See `ARCHITECTURE.md` for design.

## Quick start

```bash
docker compose up -d postgres redis     # from repo root: pgvector on :5433, redis on :6379
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env                    # add provider keys
.venv/bin/alembic upgrade head
.venv/bin/uvicorn api.main:app --reload --port 8000
```

- OpenAPI docs: http://localhost:8000/docs
- Prometheus metrics: http://localhost:8000/metrics
- Health: `/health/live`, `/health/ready`

## Try the full RAG loop

```bash
# register (first user in an org becomes admin)
curl -s -X POST localhost:8000/api/v1/auth/register -H 'content-type: application/json' \
  -d '{"email":"you@kimbal.io","password":"SuperSecret123!","full_name":"You","organization_name":"Kimbal"}'

# then: create knowledge base → upload document → search → create conversation → ask (SSE)
```

## Tests

```bash
.venv/bin/pytest -q          # 35 tests: unit + integration (real pgvector) + API
.venv/bin/ruff check .
```

## Layout

| dir | contents |
|---|---|
| `api/` | FastAPI app, routers, wire schemas, DI |
| `services/` | auth, documents, chat orchestration |
| `repositories/` | all SQL; `chunks.py` hides vector search |
| `retrieval/` | hybrid pipeline, fusion, CRAG seams |
| `ingestion/` | extractors (pdf/docx/md/txt/csv/html) + chunkers |
| `embeddings/`, `llm/` | provider adapters + fakes |
| `models/` | SQLAlchemy ORM |
| `config/alembic/` | migrations |
| `../k8s/` | Kubernetes manifests |

## Providers

Set in `.env`:

- `LLM_PROVIDER`: `openrouter` (default local setup) | `anthropic` | `openai` | `fake`
- `EMBEDDING_PROVIDER`: `openai` | `jina` | `voyage` | `tei` (self-hosted BGE) | `fake`

`fake` providers are deterministic and offline — used by the test suite and fine for local UI work.
