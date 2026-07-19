# KimbalGPT Enterprise Knowledge Upgrade — Progress

Last updated: 2026-07-19

Branch: `agent/cerebras-knowledge-upgrade`

## Current phase

Phase 2 complete — Retrieval ranking experiment and observable admin trace.
Phase 3 is next — Read-only, allowlisted Slack knowledge ingestion.

## Completed work

- Read `AGENTS.md`, `shivam_plan/new.md`, and the primary architecture, RAG, evaluation, security, and testing documentation.
- Preserved the current `KnowledgeBase -> Document -> DocumentVersion -> Chunk` architecture.
- Traced the current schema, public API layers, chat/retrieval flow, role enforcement, citation flow, connector behavior, and evaluation gates.
- Recorded the implementation contract in `shivam_plan/implementation_design.md`.
- Created the dedicated branch `agent/cerebras-knowledge-upgrade`.
- Confirmed GitHub CLI is authenticated through the OS keyring; the separately pasted PAT is not needed and has not been written to the repository.
- Established that Jira and Confluence connector work for this goal is fixture/read-only only. No production mutations are permitted.

### Phase 1

- Added organization-scoped projects, project-source mappings, project membership/manager roles, user defaults, conversation project scope, source access modes, and explicit user source grants.
- Added migration `0003_projects_and_source_acl.py`, including backfill to an `All Knowledge` project, upgrade/downgrade support, and compatibility guards for the repository's historical metadata-driven initial migration.
- Added project CRUD, source mapping, membership, default selection, source-permission, and audit APIs.
- Enforced active-project and explicit source authorization before database retrieval, deterministic Jira counts, live Jira evidence mapping, citation reads, direct knowledge-base metadata reads, collection reads, and document reads.
- Added authorization context to retrieval cache keys so user, project, role, and effective source scope cannot share cached results.
- Added the `/projects` management interface and project selectors in the Ask composer and settings surface.
- New organizations/users receive a usable default project; new knowledge bases are mapped into the default project.
- Revoked citations now redact the stored assistant answer instead of returning previously derived restricted content.

### Phase 2

- Added configurable weighted and RRF fusion paths with stable tie handling, duplicate suppression,
  weighted arm contributions, native arm scores, and per-arm rank provenance.
- Added independently flagged exact-identifier and IDF-based rare-token retrieval arms for Jira keys,
  error codes, hostnames, flags, IP addresses, and other uncommon identifiers.
- Added source-specific, floor-bounded recency decay that leaves missing timestamps unpenalized.
- Added an optional bounded model reranker for ambiguous semantic questions with deterministic
  heuristic fallback on timeout, provider error, or invalid output.
- Added post-rank neighboring-chunk expansion with document-version boundaries, stable persisted
  citation identities, deterministic ordering, and token/count budgets.
- Preserved deterministic exact Jira-key, relationship, and structured count paths.
- Added an admin-only, content-free retrieval trace to search/chat and the Ask source drawer.
- Added a read-only weighted/RRF comparison script and recorded the evidence in
  `shivam_plan/retrieval_experiment.md`.

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

## Phase 1 test evidence

| Check | Result |
|---|---|
| Backend suite | Passed; 101 tests, 1 migration test skipped without its explicit disposable-DB variable |
| Phase 1 ACL/API tests | Passed; project role matrix, CRUD, membership, default persistence, cross-project/cross-org denial, restricted grants/revocation, direct-read denial, cache isolation, and conversation scope |
| Migration round trip | Passed against explicit disposable clone DB; downgrade to `0002` preserved organization/user/KB/conversation rows and upgrade to `0003` restored/backfilled project schema |
| Fresh migration chain | Passed upgrade to head, downgrade to base, and upgrade to head against an explicit disposable database |
| Golden dataset gate | Passed; 129 cases; live gate intentionally skipped because no API base/token was supplied |
| Frontend lint and TypeScript | Passed |
| Next production build | Passed; 21 static pages, including `/projects` |
| Changed Python files Ruff | Passed |
| Browser desktop | Passed in Chrome against `localhost:3100`; create, source-map, default, switch, reload persistence, and safe deactivation verified |
| Browser mobile | Passed at 390x844 for `/projects` and Ask project selection |
| Browser console | No errors during the Phase 1 path |

The temporary browser-test project was safely deactivated after verification. Its source was not deleted. The local All Knowledge project remains the default.

## Phase 2 test evidence

| Check | Result |
|---|---|
| Retrieval unit tests | Passed; RRF formula/weights/ties/duplicates/provenance, recency boundaries, rare tokens, neighbors, and model timeout/fallback |
| Retrieval integration tests | Passed; weighted/RRF paths, exact and rare-token arms, source diversity, real neighbor identities, and citation metadata |
| RAG/API regressions | Passed; deterministic Jira count, admin trace without content, and viewer trace omission |
| Local 129-case comparison | Weighted: recall 0.8372, precision 0.9298, MRR 0.9607, top-k 0.9845, p95 1293 ms; RRF: recall 0.8643, precision 0.9191, MRR 0.9566, top-k 0.9845, p95 1473 ms |
| Default decision | Weighted retained; RRF remains flagged because recall improved but precision, MRR, and p95 latency regressed |
| Frontend lint and TypeScript | Passed |
| Changed Python files Ruff | Passed |
| Browser desktop | Passed in Chrome against `localhost:3100` using the fake local LLM; admin trace displayed fusion/reranker modes, counts, per-arm latency, chunk IDs, ranks, and provenance |

The pre-commit full backend suite passed with 113 tests and 1 explicitly gated migration test
skipped. The 129-case dataset gate, frontend lint, TypeScript check, 21-page production build,
changed-file Ruff check, and `git diff --check` also passed. These checks run again in Phase 7.

## Files and migrations changed

- `shivam_plan/new.md` — source recommendation plan prepared before the goal began.
- `shivam_plan/goal.md` — complete phase-by-phase goal and acceptance criteria.
- `shivam_plan/implementation_design.md` — Phase 0 architecture/security/migration contract.
- `shivam_plan/progress.md` — this running evidence log.
- `backend/config/alembic/versions/0003_projects_and_source_acl.py` — additive/backfilled Phase 1 schema and reversible downgrade.
- `backend/models/project.py`, project repositories/routes/schemas — project and source authorization domain.
- Chat/search/document/knowledge-base/auth services and routes — project propagation and ACL enforcement.
- `app/projects/`, `components/projects-client.tsx`, Ask/sidebar/API client changes — project administration and selection UI.
- Phase 1 API/security and migration tests.

## Remaining work

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
