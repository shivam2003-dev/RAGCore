# Kimbal Knowledge Hub Phase Plan

Date: 2026-07-04

## Live Release Status - 2026-07-06

Target: `https://kb.kimbal.ai` on EC2 `16.112.123.15`.

Current production release scope:

- Authentication is enabled for Kimbal email users only.
- Super admin account: `s.kumar@kimbal.io`.
- Credential handoff is stored locally in `output/kimbal-login.txt`; secrets are not repeated in chat.
- Public users should land on `/ask`; admin-only routes remain protected by role checks.
- Conversational RAG is implemented with separate services for memory, chat sessions, question rewriting, retrieval, and response generation.
- Chat history is persisted per conversation, included in follow-up rewriting, and can be cleared per conversation.
- Ask responses return sources and the rewritten standalone question used for retrieval.
- Data Sources now uses live source inventory rows instead of hard-coded Jira/Confluence buckets.
- Data Sources includes connector run history from audit logs and per-source pending/chunk/run details.
- Document lineage is available through the admin API for source URL, source id, version, metadata, chunks, and stored versions.
- Source Mix chart aggregation is fixed so Jira, Confluence, and Web proportions render from the actual values.
- Evals now include a `Kimbal Benchmark` headline score such as `50/100`, computed from live persisted answer signals.
- Evals expose a script-friendly `/api/v1/evals/benchmark` endpoint and a golden dataset inventory backed by `evals/golden/rag.jsonl`.
- Phase 2 additions now include connector failure audit records, document lineage UI, Ask freshness badges, and env-configured Jira/Confluence allowlist and denylist filters.
- Phase 3 additions now include `/api/v1/evals/offline`, golden-set release gate metrics, failing-case drilldowns, Fast vs Council comparison estimates, role-space checks, and `backend/scripts/run_evals.py` for CI/API gating.
- Phase 4 additions now include CRAG retrieval quality scoring, corrective query rewriting, multi-part query decomposition, post-fusion reranking, weak-retrieval refusal, final citation-marker cleanup, answer shaping, and structured Jira count answers from metadata.

Active EC2 data work:

- DevOps sources: Jira DEVO and Confluence DevOps1. Jira DEVO pending ingestion was repaired on EC2 and reached `ready=10191`, `uploaded=0`, `processing=0`, `failed=0`.
- SRE-priority sources: Jira CVIR, Confluence SRE, and Confluence AS.
- SRE ingestion is treated as release-critical; deploy/restart waits for a safe ingestion point.

Remaining release checks before closing this phase:

- Deploy the current code to EC2.
- Run backend/API and frontend build checks on EC2, not locally.
- Smoke test login, `/ask`, conversation follow-up rewriting, clear history, `/data-sources`, `/evals`, and live source counts on EC2.
- Confirm Data Sources shows SRE/CVIR/AS separately after the grouped source inventory deploy.
- Confirm the Source Mix donut no longer collapses to one full green ring when multiple sources have values.

This plan treats the current application as Phase 1. It is based on the implemented repo docs in `docs/`, the current Ask/Web/Council/Discover/Evals work, and current external references for RAG evaluation, Atlassian APIs, observability, and LLM application security.

## Guiding Principles

- Keep Kimbal as an enterprise knowledge product, not only a chatbot.
- Keep Jira, Confluence, uploaded docs, web search, and future connectors visibly source-backed.
- Never show fake static stats. Empty or unavailable data must render as empty, loading, or unavailable.
- Keep production Atlassian sync read-only unless a later phase explicitly introduces governed write actions.
- Treat citations, source links, and document provenance as first-class UX.
- Treat evals as release infrastructure, not a decorative dashboard.
- Make role spaces useful by changing retrieval scope, prompt posture, and workspace content, not just labels.

## Phase 1 - Current Baseline

Status: implemented and working locally.

What exists now:

- FastAPI backend with layered routes, services, repositories, providers, Postgres/pgvector, Redis, auth, audit logging, rate limiting, and Prometheus metrics.
- Next.js frontend with Home, Ask, Knowledge Sources, Documents, Saved Answers, Analytics, Usage & Insights, Content Health, Feedback, Data Sources, Access Control, Settings, Integrations, Discover, and Evals routes.
- Read-only Confluence and Jira sync into local knowledge bases.
- Document upload with validation and background ingestion.
- Hybrid retrieval with dense pgvector search, Postgres full-text search, weighted fusion, citations, and SSE chat streaming.
- Ask source modes: Knowledge, Web, Both.
- Ask answer modes: Fast and Council.
- Council mode now uses exactly two response models plus one different evaluator model.
- Role spaces: SRE, DevOps, Dev, HR, and Custom Role.
- Discover route and Discover inside Ask with department feeds and internal board pulse.
- Live metrics and heuristic evals backed by persisted data.
- Documentation for architecture, RAG, Atlassian sync, web search, Council, Discover, evals, security, operations, and testing.

Phase 1 hardening checklist before calling it a release candidate:

- Capture a clean browser QA pass for every sidebar route on desktop and narrow viewport.
- Verify clickable citations open the right-side source rail for Jira, Confluence, upload, and web snippets.
- Verify Confluence/Jira sync counts match backend document counts and are not capped at 100.
- Verify Ask never auto-submits a default prompt.
- Verify Web and Council controls disable with clear reasons when provider config is missing.
- Verify all stats on Home, Data Sources, Content Health, Analytics, Evals, and Discover come from backend APIs.

## Phase 2 - Source Quality, Sync Depth, and Provenance

Goal: make Kimbal trustworthy as a live source inventory.

Build next:

- Incremental Confluence sync using page ids, version numbers, updated timestamps, and source URLs.
- Incremental Jira sync using JQL windows, issue ids, updated timestamps, status, assignee, labels, priority, components, sprint, and board metadata.
- Connector run history with per-run created, updated, skipped, deleted, failed, duration, rate-limit, and warning details.
- Per-document lineage view showing source system, source URL, source id, source version, sync time, ingestion time, chunk count, embedding model, and latest retrieval use.
- Document diff awareness so updated pages/issues invalidate old chunks cleanly.
- Attachment handling policy for Confluence and Jira attachments: supported types, size limits, extraction status, and skipped reason.
- Source freshness badges in Ask and Documents.
- Admin-configured source allowlists and denylist patterns for spaces, projects, labels, page trees, and issue statuses.

Exit criteria:

- A user can answer: "which exact 10,300 documents are indexed and where did each come from?"
- Any synced answer can be traced back to its original Jira issue, Confluence page, upload, or web result.
- Connector failures are observable without reading backend logs.

Primary references:

- [Confluence Cloud REST API and CQL search](https://developer.atlassian.com/cloud/confluence/rest/v1/intro/)
- [Confluence Cloud REST API v2](https://developer.atlassian.com/cloud/confluence/rest/)
- [Jira Cloud REST API issue search and JQL](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/)
- [Jira Cloud webhooks](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-webhooks/)

## Phase 3 - Real RAG Evals and Release Gates

Goal: move from live heuristic evals to repeatable quality control.

Build next:

- Golden dataset under `evals/golden/` with representative SRE, DevOps, Developer, HR, Jira analytics, Confluence runbook, upload, and web/blended questions.
- Retriever evals for expected source recall, context precision, top-k hit rate, MRR, and source freshness.
- Generator evals for groundedness, faithfulness, citation coverage, answer relevance, refusal correctness, and unsupported-claim rate.
- Council-specific evals comparing Fast vs Council on quality, latency, cost, and citation discipline.
- Role-space evals that verify SRE/DevOps/Developer/HR prompts change answer format and retrieval focus without overriding safety rules.
- CI release gates with thresholds for retrieval recall, citation coverage, groundedness, and p95 latency.
- Evals dashboard drilldowns showing failing examples, expected sources, returned sources, answer text, judge rationale, and regression trend.

Exit criteria:

- A model, prompt, chunking, reranking, or embedding change cannot merge unless the golden set stays above agreed thresholds.
- The Evals UI clearly separates live production health from offline release-gate scores.

Primary references:

- [OpenAI evals guide](https://developers.openai.com/api/docs/guides/evals)
- [OpenAI evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
- [Ragas metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)
- [Ragas context precision](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/)
- [LangSmith RAG evaluation tutorial](https://docs.langchain.com/langsmith/evaluate-rag-tutorial)

## Phase 4 - Accuracy Engine: Full CRAG, Reranking, and Answer Verification

Goal: reduce confident wrong answers and make retrieval self-correcting.

Build next:

- Replace the accept-always CRAG policy with a real retrieval evaluator.
- Add query decomposition for multi-part questions, especially Jira count plus Confluence procedure questions.
- Add corrective query rewriting when retrieval quality is low.
- Add optional web fallback only when internal retrieval is weak or the user explicitly selects Web/Both.
- Add reranking after dense+sparse fusion, with pluggable cross-encoder or LLM reranker.
- Add claim-level grounding verification before final answer persistence.
- Add answer shaping for compact, readable responses with source-backed sections and fewer sparse markdown artifacts.
- Add analytics-aware paths for Jira count/stat questions so the system can compute counts from indexed structured metadata instead of asking the LLM to infer counts from chunks.

Exit criteria:

- If retrieval is irrelevant, Ask says it cannot answer from current sources or triggers the configured corrective path.
- Jira numeric/count questions are answered from structured metadata when possible.
- The final answer has no citation marker that cannot open a real source.

Primary references:

- [OpenAI retrieval guide](https://developers.openai.com/api/docs/guides/retrieval)
- [OpenAI file search guide](https://developers.openai.com/api/docs/guides/tools-file-search)
- [Promptfoo RAG evaluation guide](https://www.promptfoo.dev/docs/guides/evaluate-rag/)

## Phase 5 - Workspace UX and Department Operating System

Goal: make Kimbal useful for daily work by team and role, closer to a Perplexity-style work surface for the organization.

Build next:

- Full-page Discover for departments: For You, DevOps, SRE, Development, Security, HR, Finance, Product.
- Department pages combining external news, CVEs, releases, research, conferences, articles, books, internal Jira pulse, and Confluence changes.
- Persistent conversation library with search, rename, pin, delete, export, and source filters.
- Collapsible source rail with source previews, document snippets, related docs, and open-original links.
- Role workspace configuration: each role maps to preferred sources, default source mode, answer style, suggested prompts, eval expectations, and guardrails.
- Custom role builder that asks questions, generates a role prompt, stores it server-side, and lets admins approve shared roles.
- Saved Answers unification so Bookmarks and Saved Answers do not duplicate the same concept.
- Keyboard-first Ask experience with compact, readable answers and no UI controls that look clickable but do nothing.

Exit criteria:

- SRE, DevOps, Developer, HR, and custom role users each see a materially different useful workspace.
- Discover is a full route and also available inside Ask without becoming a cramped sidebar widget.
- A user can recover prior work without relying on browser-session-only history.

Primary references:

- [Karpathy LLM Council](https://github.com/karpathy/llm-council)

## Phase 6 - Enterprise Security, Governance, and Observability

Goal: make the product safe enough for production internal knowledge.

Build next:

- SSO/SAML/OIDC, SCIM user provisioning, group-to-role mapping, and tenant-aware RBAC.
- Source-level ACL enforcement so retrieved chunks respect Jira, Confluence, and document permissions.
- Prompt-injection test suite for hostile documents, web snippets, and user prompts.
- Data leakage controls: secret detection, PII redaction, downloadable audit trails, and admin review flows.
- Model/provider governance: approved model list, per-role model policy, cost caps, provider routing, and key rotation.
- OpenTelemetry traces across request, retrieval, connector sync, embedding, reranking, LLM, streaming, and persistence stages.
- Security review dashboard mapped to OWASP LLM risks and NIST AI RMF controls.
- Production incident runbooks for provider outage, connector auth failure, ingestion backlog, vector index drift, and eval regression.

Exit criteria:

- A production admin can prove who asked what, what sources were used, which model answered, what it cost, and whether the answer passed eval gates.
- Prompt-injection and sensitive-data tests are part of CI.
- Observability shows the full request path, not just API latency.

Primary references:

- [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [OWASP LLM01 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [NIST AI RMF Generative AI Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence)
- [OpenTelemetry FastAPI instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html)
- [OpenTelemetry Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)

## Phase 7 - Productization, Scale, and Governed Automation

Goal: turn Kimbal from a strong internal RAG app into a durable enterprise platform.

Build next:

- Multi-tenant organization model with isolated data, indexes, users, settings, audit logs, and provider keys.
- Connector expansion: Slack, Teams, Google Drive, GitHub, GitLab, ServiceNow, PagerDuty, Datadog, Grafana, Sentry, and cloud logs where approved.
- Workflows and automations that remain read-only by default but can produce drafts: Jira comments, Confluence summaries, incident briefs, RCA drafts, runbook updates, and release notes.
- Human approval gates before any external write action.
- Cost and quality optimizer that routes simple answers to cheaper models and difficult/high-risk answers to stronger models or Council.
- Background ingestion scale-out with queue workers, backpressure, retries, dead-letter queues, and tenant quotas.
- Disaster recovery: backup/restore drills, index rebuild procedure, migration rollback, and provider outage fallback.
- Production launch package: admin guide, user guide, security review, DPA/security questionnaire inputs, on-call runbook, and adoption metrics.

Exit criteria:

- Kimbal can be deployed for multiple teams without data leakage between teams.
- Connectors, evals, cost, latency, and security posture are visible at admin level.
- Write-capable actions, if enabled, require policy, approval, and audit.

## Suggested Roadmap Order

1. Finish Phase 1 QA evidence and fix any route/control regressions.
2. Build Phase 2 source inventory and connector run history.
3. Build Phase 3 golden evals before changing retrieval internals heavily.
4. Implement Phase 4 CRAG, reranking, and structured Jira analytics.
5. Upgrade Phase 5 workspace UX and Discover once the data contract is strong.
6. Add Phase 6 enterprise governance before broader internal rollout.
7. Scale Phase 7 connectors and governed automation after trust controls exist.

## Immediate Next Tickets

- Add connector run history tables and UI.
- Add document lineage drawer from Documents and Ask source rail.
- Create first `evals/golden/rag.jsonl` with 30 questions across Jira, Confluence, upload, web, blended, and role spaces.
- Add CI command for golden eval dry run with thresholds disabled, then enable thresholds after baseline.
- Replace CRAG accept-always evaluator with a simple deterministic first pass.
- Add structured Jira count API for assignee/status/project questions.
- Add browser E2E smoke for Ask modes, source rail, Discover, Saved Answers, Settings, Data Sources, and Evals.
