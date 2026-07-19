# Testing

## Backend Commands

From `backend/`:

```bash
uv run ruff check .
uv run mypy services/confluence_service.py services/jira_service.py services/evidence_tools.py \
  services/knowledge_workflows.py api/routes/confluence.py api/routes/jira.py \
  api/routes/metrics.py api/routes/workflows.py
uv run pytest -q
```

The full strict mypy run includes a pre-existing annotation backlog across tests, generated test
uploads, legacy routes, and third-party libraries without typing markers. The scoped production-code
gate above must remain green until that separate backlog is completed.

## Frontend Commands

From repo root:

```bash
npm run lint
npx tsc --noEmit
env NODE_ENV=production npm run build
```

## Evaluations and migrations

```bash
cd backend
.venv/bin/python scripts/run_evals.py
MIGRATION_TEST_DATABASE_URL=postgresql+asyncpg://.../ragcore_migration_test \
  .venv/bin/pytest -q tests/integration/test_project_migration.py
```

The migration target must be explicitly disposable and contain `migration` or `test` in its name.

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
12. Switch Projects in Ask, Projects, Incident Copilot, and Content Health.
13. Run Incident Copilot with a key that lacks Slack/code data and verify it reports missing evidence
    without inventing history.
14. Verify Who Knows ranks exact-key ownership above broad topic matches and explains every signal.
15. Verify What Changed date validation, original links, and empty/success states.
16. Verify Content Health loading, failure, recovery, full-inventory totals, and bounded findings.
17. Use Arrow keys/Home/End on workflow tabs and verify focus follows selection.

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
- cross-organization Project/source IDs are denied
- restricted sources require explicit user grants even for admins
- planner scope injection and invalid output fall back safely
- parallel evidence tools use independent database sessions and return partial timeout results
- Slack public allowlists reject private channels/DMs and GitHub indexing rejects secret/generated paths

## Manual Evidence to Capture

For production-readiness checks, capture:

- command outputs for lint/build/tests
- connector sync result counts
- document readiness counts
- Ask SSE done event with timings
- browser screenshots for desktop and narrow viewport
- any known limitation that remains
