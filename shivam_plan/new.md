# CVUM Improvements Inspired by Cerebras Knowledge

Yes—CVUM can gain several valuable Cerebras-style capabilities without rewriting its RAG foundation. Its retrieval core is already strong; the main opportunities are better source ingestion, project-level scoping, learned ranking, and agent/tool access.

The [Cerebras article](https://www.cerebras.ai/blog/how-we-built-our-knowledge-base) centers on normalized multi-source ingestion, Slack conversation distillation, incremental code indexing, hybrid scoring, planner/executor/synthesis orchestration, project-scoped search, and MCP tools.

## What CVUM already does well

- It has a unified enterprise metadata contract for Jira, Confluence, uploads, freshness, source identity and lineage in [`backend/knowledgebase/source_metadata.py`](../backend/knowledgebase/source_metadata.py).
- The relational `KnowledgeBase -> Document -> Version -> Chunk` design in [`backend/models/knowledge.py`](../backend/models/knowledge.py) is better for versioning and citations than copying Cerebras's literal single-table design.
- It already has HNSW vector search, PostgreSQL full-text search, title/exact-key boosts, corrective retrieval, freshness scoring and source diversity in [`backend/retrieval/pipeline.py`](../backend/retrieval/pipeline.py), [`backend/repositories/chunks.py`](../backend/repositories/chunks.py), and [`backend/retrieval/crag.py`](../backend/retrieval/crag.py).
- Confluence and Jira syncs skip unchanged content and version changed documents rather than reprocessing everything.
- Contextual metadata is already prepended before embedding in [`backend/ingestion/pipeline.py`](../backend/ingestion/pipeline.py).
- It has citations, refusal gates, feedback, analytics and a 129-case evaluation set.

Therefore, the current storage and safety architecture should be retained.

## Main gaps compared with Cerebras

| Cerebras capability | CVUM today | Recommendation |
|---|---|---|
| Slack thread ingestion | Explicitly not implemented in [`components/integrations-client.tsx`](../components/integrations-client.tsx) | High-value addition |
| Incremental repository indexing | Code chunker exists, but only through file ingestion in [`backend/ingestion/chunkers/code.py`](../backend/ingestion/chunkers/code.py) | Add GitHub/Git connector |
| Project bundles and user default scope | Query scoping is based on keywords and assistant role | Add real Projects |
| RRF fusion | Current fusion max-normalizes and weights dense/sparse scores in [`backend/retrieval/fusion.py`](../backend/retrieval/fusion.py) | Test RRF behind a feature flag |
| Model reranking | Current reranker is deterministic | Add an optional small-model reranker |
| Post-ranking context expansion | Parent context is embedded, but adjacent winning sections are not fetched | Add neighbor expansion after ranking |
| Planner and parallel tool fan-out | Current routing is heuristic and subqueries run sequentially in [`backend/services/conversational_retriever.py`](../backend/services/conversational_retriever.py) | Add after more connectors exist |
| MCP retrieval primitives | Not implemented | Expose stable search tools |
| `who_knows` and recent PRs | Not implemented | Useful CVUM-specific features |
| Connector plugin SDK | Jira and Confluence are dedicated services | Introduce a normalized connector interface |

## Recommended implementation order

### 1. Projects and source-level permissions

This should come before Slack or private repositories.

Add:

- `projects`
- `project_sources`
- `project_members`
- `users.default_project_id`
- A Project selector beside the existing source-mode selector in [`components/chat-ask-client.tsx`](../components/chat-ask-client.tsx)
- Project filtering inside retrieval SQL

Currently users are organization-scoped in [`backend/models/user.py`](../backend/models/user.py), and KB lookup checks only organization membership in [`backend/repositories/knowledge.py`](../backend/repositories/knowledge.py). The metadata contains an `acl` label, but search does not enforce per-source principals.

Project relevance and authorization must remain separate: belonging to a project must never grant access the user did not already have.

Estimated effort: **1–2 weeks**.

### 2. Retrieval upgrade experiment

Implement behind feature flags:

- RRF across dense, sparse, exact-identifier and future source-specific retrievers.
- Optional small-model reranking of approximately 20 candidates down to 8–10.
- Adjacent-section expansion only after final ranking.
- Stronger source-specific age decay.
- Explicit rare-token/IDF boost for error strings, hostnames and configuration flags.
- Retrieval trace showing which retrievers contributed each result.

Keep exact Jira-key lookups and structured Jira counts deterministic; they do not need an LLM planner.

Estimated effort: **4–7 days**.

### 3. Slack Knowledge connector

The valuable Cerebras pattern is not simply “embed every Slack message.” Build:

1. Socket Mode event receiver.
2. Immediate acknowledgement and event-ID deduplication.
3. Queue processing that refetches the complete thread.
4. Raw thread storage for full-text search.
5. LLM distillation into:

   - Searchable question
   - Summary
   - Resolution
   - Systems
   - Code/config references
   - Participants
   - Last activity

6. “Burst” embeddings for substantial consecutive messages omitted by the thread summary.
7. Channel-to-project and Slack-ACL mapping.
8. Optional `/cvum ask` Slack command with cited answers.

Never index DMs or private channels by default.

Estimated effort: **2–3 weeks** for a production-quality MVP.

### 4. GitHub/code intelligence

Reuse the existing code chunker, but add:

- GitHub App or webhook-driven synchronization.
- Blob-SHA tracking so only changed files are re-indexed.
- Repository and path allow/deny lists.
- File-, class-, function- and method-level chunks.
- Combined semantic search and exact `ripgrep`-style search.
- `recent_prs` retrieval.
- CODEOWNERS and contributor metadata.

CVUM does not need to adopt CocoIndex immediately; the existing ingestion pipeline can support incremental indexing using Git blob hashes.

Estimated effort: **2–3 weeks**.

### 5. Planner, tools and MCP

Once Slack and GitHub exist, introduce typed retrieval tools:

- `search_knowledge`
- `search_jira`
- `search_confluence`
- `search_slack`
- `search_code`
- `recent_prs`
- `who_knows`

A lightweight planner selects tools using the active project. The executor runs independent tools concurrently using separate database sessions/connections, and the existing answer generator performs synthesis.

Expose the same primitives through MCP so IDE agents can retrieve raw evidence without forcing CVUM to generate the final answer.

Estimated effort: **1–2 weeks**.

## Best product features this enables

### Incident Copilot

Given a Jira/CVIR key, combine the ticket, Slack incident thread, runbook, related code and recent PRs into a cited timeline and next-action checklist.

### Who Knows This?

Rank experts using Slack authorship, Jira ownership, Confluence authorship, CODEOWNERS and recent contributions—with evidence explaining every recommendation.

### What Changed?

Summarize changes since a selected date across Jira, Confluence, Slack and repositories.

### Knowledge Freshness Center

Extend [`components/content-health-client.tsx`](../components/content-health-client.tsx) beyond ready/failed status to show stale sources, sync lag, unresolved threads and obsolete answers.

### Project Lens

New users choose DevOps, SRE, HES, CVIR or another project and immediately receive relevant default results.

## Final recommendation

Build **Projects and ACL enforcement first**, run the **RRF/reranker experiment second**, and then build **Slack plus the Incident Copilot**. That combination would provide the clearest improvement for CVUM's SRE/DevOps use case.

## Validation baseline

- The 129-case golden dataset gate passed.
- 33 targeted retrieval, chunking and source-metadata tests passed.
- The working tree was clean before this plan file was added.
