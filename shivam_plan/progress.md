# KimbalGPT Enterprise Knowledge Upgrade — Progress

Last updated: 2026-07-19

Branch: `agent/cerebras-knowledge-upgrade`

## Current phase

Phase 0 — Baseline and architecture contract.

## Completed work

- Read `AGENTS.md`, `shivam_plan/new.md`, and the primary architecture, RAG, evaluation, security, and testing documentation.
- Preserved the current `KnowledgeBase -> Document -> DocumentVersion -> Chunk` architecture.
- Traced the current schema, public API layers, chat/retrieval flow, role enforcement, citation flow, connector behavior, and evaluation gates.
- Recorded the implementation contract in `shivam_plan/implementation_design.md`.
- Created the dedicated branch `agent/cerebras-knowledge-upgrade`.
- Confirmed GitHub CLI is authenticated through the OS keyring; the separately pasted PAT is not needed and has not been written to the repository.
- Established that Jira and Confluence connector work for this goal is fixture/read-only only. No production mutations are permitted.

## Baseline test results

| Command | Result |
|---|---|
| `npm run lint` | Passed |
| `npx tsc --noEmit` | Passed |
| `NODE_ENV=production npm run build` | Passed; 20 static pages generated |
| `cd backend && .venv/bin/pytest -q` | Passed; 97 tests |
| `backend/.venv/bin/python backend/scripts/run_evals.py` | Passed; 129 cases; live gate skipped because no API/token was provided |
| `cd backend && .venv/bin/ruff check .` | Baseline failure; 7 existing findings in metrics, extractor registry, source metadata, and document service |
| Scoped `mypy` command from `docs/TESTING.md` | Baseline failure; 6 existing findings in Jira service and metrics route, including missing third-party stubs |

The Ruff and mypy failures existed before application changes on this branch. They will be fixed and re-run before final completion.

## Files and migrations changed

- `shivam_plan/new.md` — source recommendation plan prepared before the goal began.
- `shivam_plan/goal.md` — complete phase-by-phase goal and acceptance criteria.
- `shivam_plan/implementation_design.md` — Phase 0 architecture/security/migration contract.
- `shivam_plan/progress.md` — this running evidence log.
- No database migration has been added yet.

## Remaining work

- Complete Phase 0 review and commit.
- Phase 1: project/default scope/source ACL schema, migration, API, UI, audit, and negative security tests.
- Phase 2: retrieval arms, RRF experiment, trace, scoring, reranker fallback, neighbors, and evaluation comparison.
- Phase 3: Slack read-only connector with fixture/contract coverage.
- Phase 4: GitHub read-only incremental indexing and code intelligence.
- Phase 5: planner/executor/evidence tools and MCP parity.
- Phase 6: product workflows and visible desktop/mobile verification.
- Phase 7: final docs, full matrix, containers/manifests, secret scan, commits, push, and draft PR.

## External input required

None for the current local implementation. Real Slack and connector smoke tests will remain pending until an allowlisted test workspace/channel and Slack app credentials are supplied. Real GitHub connector smoke testing will use the already authenticated CLI where suitable or request a least-privilege read-only connector credential later.

## Safety record

- No Jira or Confluence create/update/delete operation has been run.
- No Slack message has been sent.
- No connected GitHub source repository has been modified.
- No supplied credential has been committed or copied into a project file.
