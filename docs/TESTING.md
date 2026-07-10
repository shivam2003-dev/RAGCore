# Testing

## Backend Commands

From `backend/`:

```bash
uv run ruff check .
uv run mypy services/confluence_service.py services/jira_service.py api/routes/confluence.py api/routes/jira.py api/routes/metrics.py
uv run pytest -q
```

The full repository mypy run currently includes older strictness issues outside the new connector and metrics files. Keep the scoped mypy command green for connector changes unless the broader strictness backlog is being addressed.

## Frontend Commands

From repo root:

```bash
npm run lint
NODE_ENV=production npm run build
```

## Browser Verification

Use a real browser for UI verification after passing automated checks.

Minimum browser path:

1. Open `http://localhost:3100`.
2. Open `/admin` and visit every admin sidebar route.
3. Open `/knowledge-sources` and verify Confluence/Jira status cards.
4. Sync Jira and Confluence if configured.
5. Open `/documents` and verify synced documents are listed.
6. Open `/` directly and verify it does not auto-submit; verify `/ask` redirects to `/`.
7. Ask a Jira issue question and verify Jira sources appear in the right rail.
8. Ask for an epic's benchmarking/server details and verify child-ticket comments and attachment
   evidence appear, including a child that is not semantically similar to the epic title.
9. Click Copy, Helpful, Not Helpful, New Chat, reopen a chat, and open its source drawer.
10. Open Settings and verify connector tests/sync actions work and non-backed settings stay read-only.
11. Open Evals twice and verify the prior benchmark renders immediately while background refresh runs.

## Regression Cases

Keep coverage for:

- background ingestion actually awaits async work
- mid-stream LLM failures emit terminal SSE error events
- hybrid retrieval against real pgvector
- citation extraction and persistence
- upload magic-byte rejection
- delete removes documents from search
- refresh-token rotation
- RBAC enforcement
- connector status endpoints do not expose secrets
- multi-KB retrieval can find Jira evidence when the conversation was created on another KB

## Manual Evidence to Capture

For production-readiness checks, capture:

- command outputs for lint/build/tests
- connector sync result counts
- document readiness counts
- Ask SSE done event with timings
- browser screenshots for desktop and narrow viewport
- any known limitation that remains
