# KimbalGPT Enterprise Knowledge Upgrade — Implementation Design

Status: Phase 0 architecture contract

Branch: `agent/cerebras-knowledge-upgrade`

Date: 2026-07-19

## 1. Constraints and invariants

1. Retain the normalized `KnowledgeBase -> Document -> DocumentVersion -> Chunk` model. Connectors create and version documents; they do not bypass the ingestion pipeline or collapse storage into an embeddings-only table.
2. Jira and Confluence remain read-only. Local development and automated tests use fakes/fixtures and must not invoke production mutation APIs.
3. A Project narrows relevance. It never grants source permission.
4. Effective retrieval scope is always:

   ```text
   organization sources
   INTERSECT source ACL grants
   INTERSECT active project sources
   INTERSECT request source-mode constraints
   ```

5. The effective scope is calculated on the server and passed into every database retrieval query. Prompts, model output, frontend state, and metadata labels are not security boundaries.
6. Existing exact Jira-key, relationship, and structured-count paths remain deterministic.
7. Source text is untrusted evidence. It cannot select tools, expand permissions, or override system instructions.
8. New behaviors ship behind conservative feature flags. Existing weighted fusion and heuristic reranking remain available as fallbacks.
9. No credential is stored in connector JSON, application logs, committed files, traces, or API responses.

## 2. Current contract

### Storage

The current database contains organizations, users, refresh tokens, API keys, audit logs, knowledge bases, collections, documents, document versions, chunks, conversations, messages, citations, and feedback. PostgreSQL provides generated `tsvector` fields, GIN full-text indexing, pgvector embeddings, and an HNSW cosine index.

The schema is currently at Alembic revision `0002`. Revision `0001` bootstraps ORM metadata and `0002` adds message evaluation JSON.

### Public APIs

The FastAPI application exposes `/api/v1` routes for authentication, knowledge bases, documents, Jira, Confluence, search, chat/conversations, web search, discovery, evaluations, metrics, and administration. The frontend client in `lib/kimbal-api.ts` is the public browser integration point.

Compatibility requirements:

- Existing request properties remain accepted.
- New `project_id` inputs are optional during migration.
- Existing organizations receive an initial project mapped to their existing knowledge bases.
- Existing conversations continue working after backfill.
- Existing citations keep stable document and chunk foreign keys.

### Retrieval

The retrieval pipeline currently embeds the query, runs dense and strict/relaxed sparse search sequentially through one request-scoped `AsyncSession`, applies weighted fusion, heuristic reranking, corrective retries, final source-diversity selection, and citation validation. No new implementation may execute concurrent statements through that same session.

## 3. Project and authorization schema

### `projects`

- `id UUID PK`
- `organization_id UUID NOT NULL`
- `name VARCHAR(255) NOT NULL`
- `slug VARCHAR(100) NOT NULL`
- `description TEXT NOT NULL DEFAULT ''`
- `is_active BOOLEAN NOT NULL DEFAULT true`
- timestamps
- unique `(organization_id, slug)`
- unique `(organization_id, id)` to support organization-safe composite foreign keys

### `project_sources`

- `organization_id UUID NOT NULL`
- `project_id UUID NOT NULL`
- `knowledge_base_id UUID NOT NULL`
- timestamps
- primary/unique `(project_id, knowledge_base_id)`
- composite FK `(organization_id, project_id) -> projects(organization_id, id)`
- composite FK `(organization_id, knowledge_base_id) -> knowledge_bases(organization_id, id)`

These composite constraints make cross-organization source mapping invalid at the database layer.

### `project_members`

- `organization_id UUID NOT NULL`
- `project_id UUID NOT NULL`
- `user_id UUID NOT NULL`
- `project_role` enum: `member | manager`
- timestamps
- unique `(project_id, user_id)`
- organization-safe composite foreign keys to projects and users

Organization admins can administer every project. Non-admin users only see active projects where they are members. Editors may manage project details/source mappings only when they are project managers. Membership changes remain admin-only.

### Source permissions

`knowledge_bases` gains `access_scope` with values `organization | restricted`, defaulting to `organization` for backward compatibility. It also gains unique `(organization_id, id)`.

`source_access_grants` stores explicit user access to restricted sources:

- `organization_id UUID NOT NULL`
- `knowledge_base_id UUID NOT NULL`
- `user_id UUID NOT NULL`
- `granted_by UUID NULL`
- timestamps
- unique `(knowledge_base_id, user_id)`
- organization-safe composite foreign keys to knowledge bases and users

A user can retrieve a knowledge base only when it belongs to the same organization and either:

- `access_scope = organization`, or
- a matching `source_access_grants` row exists.

Project membership or project-source mapping never satisfies this check. Restricted Slack/private repository sources must use explicit grants. Admins may configure restricted sources but do not implicitly retrieve their content without a grant.

### User and conversation scope

- `users.default_project_id UUID NULL` uses an organization-safe composite FK.
- `conversations.project_id UUID NULL` records the active project and uses an organization-safe composite FK.
- Conversation creation accepts an optional project. If omitted, it uses the user default, then the first authorized active project.
- Ask may explicitly select an authorized project. The server persists the selection to the conversation so follow-up questions use the same scope.

### Backfill

For each existing organization, migration/service bootstrap creates an `All Knowledge` project, adds all current organization knowledge bases, adds all current users as members, and assigns it as the default project where missing. Existing knowledge bases remain organization-visible. New organizations receive the project as part of registration.

### Authorization repository

One repository/service owns project and source authorization. It returns only knowledge-base IDs satisfying the full intersection. These IDs are passed to dense search, sparse search, exact identifier search, Jira relationship mapping, direct search, chat, product tools, and MCP.

All authorization-aware response caches use a versioned key containing:

```text
organization_id:user_id:role:project_id:sorted_authorized_source_ids:query/options
```

Membership, source mapping, grant, role, or project changes invalidate/bump the relevant authorization version.

## 4. API and audit contract

New REST resources:

- `GET/POST /api/v1/projects`
- `GET/PATCH/DELETE /api/v1/projects/{project_id}`
- `GET/PUT /api/v1/projects/{project_id}/sources`
- `GET/PUT /api/v1/projects/{project_id}/members`
- `PUT /api/v1/users/me/default-project`
- `GET/PUT /api/v1/knowledge-bases/{id}/permissions`

Mutation rules:

- Project read: organization admin or member.
- Project create: editor/admin; creator becomes manager.
- Project update/source map: admin or editor project-manager.
- Membership and restricted-source grants: admin only.
- Viewer: read and select only.
- Cross-organization IDs return not found/denied without leaking object existence.

Audit actions include `project.create`, `project.update`, `project.delete`, `project.source.update`, `project.member.update`, `user.default_project.update`, `source.permission.update`, and connector configuration/sync actions. Details contain identifiers and counts, never source content or secrets.

## 5. Retrieval experiment

### Feature flags

All settings are server-managed environment variables with safe defaults:

- `RETRIEVAL_FUSION_MODE=weighted|rrf` (default `weighted`)
- `RETRIEVAL_RRF_SMOOTHING_K=60`
- `RETRIEVAL_EXACT_IDENTIFIER_ENABLED=false`
- `RETRIEVAL_EXACT_IDENTIFIER_WEIGHT=0.25`
- `RETRIEVAL_RARE_TOKEN_ENABLED=false`
- `RETRIEVAL_RARE_TOKEN_WEIGHT=0.15`
- `RETRIEVAL_RECENCY_DECAY_ENABLED=false`
- `RETRIEVAL_RECENCY_HALF_LIVES=jira=45,confluence=180,slack=30,github=90,upload=365,web=14,default=180`
- `RETRIEVAL_RECENCY_FLOOR=0.35`
- `RETRIEVAL_MODEL_RERANKER_ENABLED=false`
- `RETRIEVAL_MODEL_RERANKER_TIMEOUT_SECONDS=3`
- `RETRIEVAL_MODEL_RERANKER_CANDIDATE_K=20`
- `RETRIEVAL_NEIGHBOR_EXPANSION_ENABLED=false`
- `RETRIEVAL_NEIGHBOR_WINDOW=1`
- `RETRIEVAL_NEIGHBOR_TOKEN_BUDGET=1200`
- `RETRIEVAL_NEIGHBOR_MAX_CHUNKS=8`

### Arms and fusion

Dense, sparse, and exact-identifier arms return ranked candidates carrying an arm name and native score. Weighted fusion preserves existing normalized-score behavior. RRF computes per-document contribution as `weight / (k + rank)` and sums duplicate candidates. Trace metadata records arm ranks/contributions but never hidden content.

Rare-token scoring uses bounded query tokens and corpus/document-frequency statistics derived in SQL. Identifier-shaped values such as Jira keys, error codes, flags, hostnames, and paths receive measurable contribution. Source-specific recency applies a configurable half-life only when valid source timestamps exist.

The optional model reranker receives at most the bounded candidate count and returns validated candidate IDs/scores. Timeout, invalid output, provider failure, or disabled state falls back to the heuristic reranker.

Neighbor expansion occurs only after final ranking. It fetches adjacent active chunks from the same document version under the same authorized scope, preserves the winning chunk as the citation identity, records expanded chunk IDs, and respects the context token budget.

### Concurrency

Phase 2 keeps request-scoped SQL arms sequential. Phase 5 may fan out independent tools only through independent session-factory contexts. A shared `AsyncSession` is never used concurrently.

## 6. Connector interface

Connectors implement a normalized read-only protocol:

```text
capabilities() -> source/search/sync metadata
validate_config(config_without_secrets)
status()
sync(cursor, allowlist) -> normalized changes
normalize(change) -> document payload(s)
```

Common connector state stores organization, connector kind, project mappings, non-secret allowlists, cursor/version, status, last event/success/error timestamps, lag, and sanitized error detail. Secret references are environment-variable names or secret-manager handles only.

Connector writes are limited to KimbalGPT-owned database/files. Source-system clients expose read methods only. Tests assert the absence of mutation calls.

## 7. Slack normalized thread contract

Slack ingestion is deny-by-default and channel-allowlisted. DMs, group DMs, and private channels are rejected unless a later explicit security decision adds a tested mapping.

A stable Slack thread document contains:

```json
{
  "source_type": "slack",
  "workspace_id": "...",
  "channel_id": "...",
  "thread_ts": "...",
  "event_ids": ["..."],
  "searchable_question": "...",
  "summary": "...",
  "resolution": "...",
  "systems": ["..."],
  "code_references": ["..."],
  "participants": [{"id": "...", "display_name": "..."}],
  "thread_url": "...",
  "created_at": "...",
  "last_activity_at": "...",
  "raw_thread_text": "...",
  "bursts": [{"start_ts": "...", "end_ts": "...", "text": "...", "reason": "..."}]
}
```

Socket Mode acknowledges first, deduplicates by stable event ID, queues work, and refetches the complete thread after create/edit/reply/delete events. Summary failure falls back to deterministic normalized raw text. The embedded text combines question, summary, resolution, systems, code references, and selected bursts; raw text remains full-text searchable.

## 8. GitHub incremental indexing contract

Production should use a GitHub App. Initial verification may use a read-only fine-grained token. Connector configuration contains repository/branch/path allowlists and denylists, not credentials.

State is tracked by repository, branch, head commit/tree SHA, and per-path blob SHA. A sync diffs the prior tree against the new tree:

- unchanged blob SHA: no download, extraction, or embedding;
- added/modified: normalize and version the document;
- renamed: retain lineage and replace source path/citation metadata;
- deleted: soft-delete the document and deactivate chunks.

Code metadata includes owner/repository, branch, path, symbol, language, blob SHA, commit SHA, source URL, CODEOWNERS, and contributors. Generated, vendor, dependency, secret-like, binary, oversized, and denied paths are never indexed.

Exact search is implemented against indexed text/data through validated arguments—never by interpolating a query into a shell. Indexed code is never executed. Recent pull requests and CODEOWNERS are read-only evidence documents/tools.

## 9. Planner and evidence contract

Every tool returns `Evidence` with:

- source type and source identifier;
- stable source URL;
- project ID;
- permission-context fingerprint (not raw grants);
- content/snippet;
- retrieval arm, rank, and score;
- freshness timestamp/label;
- sanitized metadata;
- citation identity (`chunk_id`, `document_id`, marker candidate).

Planner output is schema-validated and bounded by maximum tool count/subqueries. It receives capability descriptions and the already-authorized active project; it cannot supply or widen authorization IDs. Invalid/unavailable planner output uses deterministic routing.

The executor creates one database session per parallel database tool, applies per-tool and overall deadlines, records timings/failures, and returns successful partial evidence. Synthesis reuses existing citation validation, grounding, prompt-injection defense, and weak-evidence refusal.

## 10. MCP boundary

MCP exposes narrow, read-only retrieval primitives (`search_knowledge`, `search_jira`, `search_confluence`, `search_slack`, `search_code`, `recent_prs`, `who_knows`). Authentication resolves to the same KimbalGPT user and organization model. The server computes project/source scope exactly as REST/chat do; caller-supplied project IDs are validated and caller-supplied source IDs can only narrow scope.

MCP tools return typed evidence, not generated final answers. Inputs have length/count/date validation, deadlines, and audit correlation. No connector configuration, source mutation, credential, raw ACL list, or unrestricted SQL/filesystem operation is exposed.

## 11. Product features

Incident Copilot, Who Knows This, What Changed, Knowledge Freshness Center, and Project Lens consume the common evidence tools. They do not add alternate retrieval paths. Facts and inference are distinct fields/sections, and every person, timeline event, change, status, and recommendation retains source evidence.

## 12. Migration and rollback strategy

1. Add tables/enums/nullable columns and composite uniqueness constraints.
2. Backfill projects, sources, members, user defaults, and conversation projects transactionally.
3. Add composite foreign keys after backfill validation.
4. Deploy code that tolerates nullable project fields during a compatibility window.
5. Make new organizations/project selection use the new model immediately.
6. Connector migrations are additive and independent from project migrations.

Downgrade removes connector/product tables first, then project foreign keys/columns/tables/enums. It does not delete or rewrite knowledge bases, documents, versions, chunks, Jira data, or Confluence data. Before destructive schema downgrade, operations documentation requires a backup and verifies no application release still depends on the new columns.

## 13. Verification strategy

- Unit tests cover pure ranking, parsing, ACL, normalization, and planning behavior.
- API tests prove role matrices, cross-organization denial, project persistence, connector status, and product behavior.
- Integration tests use a disposable PostgreSQL database for migration round trips and retrieval filtering.
- Slack/GitHub fixtures prove ingestion and incremental behavior without real credentials.
- Existing Jira/Confluence tests stay fixture-only and their exact structured retrieval regressions remain green.
- The 129-case gate runs after retrieval-affecting phases.
- Frontend lint, TypeScript, build, and real-browser desktop/mobile checks gate UI phases.
- Final secret scan checks tracked and intended-diff content; real credentials stay in keychain/environment only.

## 14. Rollout and kill switches

Projects/ACL enforcement is mandatory after migration. Ranking, Slack, GitHub, planner, MCP, and product routes have independent enablement flags. Rollout order is local fixtures, disposable integration environment, explicit allowlisted smoke source, then production enablement. Connector failures never widen permissions or fall back to unscoped retrieval. Disabling a connector stops new sync/tool selection while preserving auditable indexed data subject to the same ACL checks.
