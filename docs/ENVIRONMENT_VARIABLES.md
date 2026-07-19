# Environment-variable reference

Copy `backend/.env.example` to the ignored `backend/.env` for local development. Production values
belong in a secret manager. Never put a real token, private key, database credential, or populated
`.env` in Git, documentation, an issue, or a pull request.

## Runtime and authentication

| Variables | Purpose |
| --- | --- |
| `APP_ENV`, `APP_DEBUG`, `APP_SECRET_KEY` | Runtime mode and signing secret. Replace the development secret outside local use. |
| `DATABASE_URL`, `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW` | PostgreSQL/pgvector connection and pool. |
| `REDIS_URL` | Cache and rate-limit storage. |
| `AUTH_DISABLED` | Local-only bypass. Must remain false in shared/staging/production environments. |
| `AUTH_ALLOWED_EMAIL_DOMAIN`, `AUTH_SUPER_ADMIN_EMAIL`, `JWT_*` | Registration and token policy. |

## Models and retrieval

| Variables | Purpose |
| --- | --- |
| `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, provider API keys | Embedding backend. Keep dimensions consistent with the database vector column. |
| `LLM_PROVIDER`, `LLM_MODEL`, provider API keys | Answer provider. `fake` is deterministic for tests. |
| `RETRIEVAL_TOP_K`, `RETRIEVAL_CANDIDATE_K`, `RETRIEVAL_DENSE_WEIGHT`, `RETRIEVAL_SPARSE_WEIGHT` | Base retrieval sizes and weighted fusion. |
| `RETRIEVAL_FUSION_MODE`, `RETRIEVAL_RRF_SMOOTHING_K` | `weighted` default or experimental RRF. |
| `RETRIEVAL_EXACT_IDENTIFIER_*`, `RETRIEVAL_RARE_TOKEN_*`, `RETRIEVAL_RECENCY_*` | Optional exact, rare-token, and source-age signals. |
| `RETRIEVAL_MODEL_RERANKER_*` | Bounded optional model reranker with heuristic fallback. |
| `RETRIEVAL_NEIGHBOR_*` | Post-ranking adjacent-chunk context budget. |
| `KNOWLEDGE_PLANNER_*` | Planner enablement, optional model planning, and tool deadlines. |

The accepted values and safe defaults are in `backend/.env.example` and `backend/core/config.py`.
Change one retrieval flag at a time and rerun the 129-case evaluation gate before rollout.

## Connectors

| Connector | Credential variables | Non-secret scope/state variables |
| --- | --- | --- |
| Confluence | `CONFLUENCE_EMAIL`, `CONFLUENCE_API_TOKEN` | `CONFLUENCE_BASE_URL`, space, filters, limits, timeouts |
| Jira | `JIRA_EMAIL`, `JIRA_API_TOKEN` | base URL, project/board, filters, hydration/attachment limits |
| Slack | `SLACK_APP_TOKEN`, `SLACK_BOT_TOKEN` | workspace ID, public-channel mappings in the database, retry/burst limits |
| GitHub | `GITHUB_TOKEN` | API URL/version, repository mappings, branch/path policies, size/count/lease limits |
| Web/Discover | provider API key variables | provider, endpoint, locale, result/cache limits |

Production GitHub should prefer a GitHub App installation token. Slack must use an app-level
Socket Mode token plus a least-privilege bot token. Connector configuration APIs store only
non-secret allowlists and status.

## MCP client process

`KIMBAL_API_BASE_URL` and `KIMBAL_API_KEY` configure the local stdio MCP bridge. The API key should
be injected from the client secret store or OS keychain, not from a committed MCP config.
