# CVUM Knowledge Hub: Retrieval Accuracy Roadmap

Primary goal: improve retrieval accuracy before improving answer style. A better answer generator cannot fix missing, stale, irrelevant, or poorly ranked evidence. This plan turns CVUM Knowledge Hub from a basic enterprise RAG app into a measurable, self-correcting retrieval system for Jira, Confluence, web, uploads, and future multimodal sources.

Source basis: `RAG_Survey_2023-2026.pdf` in `~/Downloads`. The survey's strongest production lessons are: move beyond naive top-k dense search; use modular RAG operators; combine dense, sparse, metadata, reranking, and structured retrieval; evaluate continuously; make the system abstain when evidence is weak; and treat citations, freshness, ACLs, and latency as part of accuracy.

## Current Product Target

CVUM should answer from internal sources with:

- High source recall for SRE, DevOps, Jira analytics, Confluence runbooks, uploaded docs, and web/blended questions.
- Correct answers for numeric Jira questions by computing from structured metadata instead of asking the LLM to infer counts from text chunks.
- Clear refusal when current sources do not support the answer.
- Every citation opening a real source.
- Conversation context without letting old chat history pollute retrieval.
- Release gates so retrieval regressions cannot ship silently.

## Implementation Status - 2026-07-06

Current completed implementation slice:

- Phase 1 source fidelity is implemented in code for new/reindexed content:
  - canonical source metadata helper for Jira, Confluence, web, and uploads
  - stable inventory keys, connector scope, source freshness bucket, ACL state, owner, URL, title, status, and source id
  - scoped source metrics so inventory separates Jira DEVO/CVIR, Confluence DevOps1/SRE/AS, uploads, and web
  - duplicate connector rows are still handled by connector identity keys, with chunks deactivated when duplicate documents are soft-deleted
- Phase 2 chunking is implemented for Markdown and Confluence HTML:
  - Confluence HTML now routes through Markdown-aware section chunking
  - chunks carry heading path, section title, table/procedure/code flags, chunk kind, and parent section context
  - contextual chunk text includes source, title, scope, status, freshness, section, kind, and parent section context
- Source-diverse final context selection is implemented:
  - architecture/runbook/documentation questions keep Confluence evidence even when Jira has many high-scoring chunks
  - final context limits repeated chunks from the same document/source key
- Phase 3 exact identifier handling is implemented in the heuristic reranker/evaluator:
  - Jira keys, source ids, source URLs, page ids, section titles, hostnames, and exact page title terms boost relevant chunks
  - final context selection enforces document/source diversity after reranking
- Phase 4 query classification is implemented in retrieval traces:
  - source/done events now include query classification such as `jira_count_stat`, `architecture_docs`, `procedure_runbook`, `multi_hop_rca`, `comparison`, and `global_summary`
- Phase 10 offline release-gate hardening is implemented:
  - CI runs the golden eval gate when backend or golden dataset files change
  - the eval runner now enforces at least 100 golden cases, required categories, required source types, and unique case ids

Verification evidence:

- `PYTHONPATH=backend pytest -q backend/tests/unit/test_source_metadata.py backend/tests/unit/test_confluence_service.py backend/tests/unit/test_jira_service.py backend/tests/unit/test_chunkers.py backend/tests/unit/test_final_context_selection.py backend/tests/unit/test_crag_source_ranking.py backend/tests/unit/test_retrieval_diversity.py backend/tests/unit/test_citations.py` -> 30 passed
- `PYTHONPATH=backend pytest -q backend/tests/unit/test_retrieval_diversity.py backend/tests/unit/test_crag_source_ranking.py backend/tests/unit/test_final_context_selection.py backend/tests/unit/test_chunkers.py backend/tests/unit/test_source_metadata.py` -> 20 passed
- `python -m py_compile` on changed backend modules -> passed
- `npx tsc --noEmit` -> passed
- `npx eslint components/ask-client.tsx components/data-sources-client.tsx` -> passed
- `python backend/scripts/run_evals.py` -> passed with 129 golden cases across Blended, DevOps, Developer, HR, SRE, and Web

Not complete yet:

- Existing production content must be reindexed/resynced to receive the new metadata and chunk structure.
- Remaining enterprise features still in progress: live API eval gate in protected CI, pluggable cross-encoder/LLM reranker, full corrective CRAG loop, full claim-level verifier, graph retrieval, and deep investigation mode.

## North-Star Metrics

- `source_recall_at_10`: expected source appears in top 10 retrieved items.
- `context_precision_at_5`: top 5 contexts are relevant and non-duplicative.
- `mrr`: expected source rank quality.
- `citation_coverage`: answer claims with citations.
- `citation_open_rate`: citation marker opens a real source URL or document view.
- `groundedness`: claims supported by retrieved evidence.
- `unsupported_claim_rate`: answer claims not backed by evidence.
- `abstention_correctness`: refuses when the corpus does not support the question.
- `jira_numeric_accuracy`: Jira count/stat answers match structured metadata.
- `p95_answer_latency`: quality improvements stay within product latency targets.

## Phase 0 - Baseline, Labels, and Observability

Goal: know the current retrieval quality before changing retrieval.

Build:

- Create a golden dataset under `evals/golden/` with real SRE, DevOps, Jira analytics, Confluence runbook, upload, web, and blended questions.
- For each example, store expected sources, expected answer facts, allowed refusal behavior, role/space, source mode, and freshness expectation.
- Log retrieval traces for every Ask request: rewritten query, source mode, selected space, retriever candidates, scores, reranker scores, final contexts, citations, latency, and answer id.
- Add an eval runner that can replay golden examples against the same service path used by production.
- Add dashboard drilldowns for failing examples: question, expected source, returned source, answer, judge rationale, and latency.

Accuracy impact:

- Prevents blind tuning.
- Makes source recall, ranking quality, citation discipline, and hallucination visible separately.

Exit criteria:

- At least 80 labeled examples covering SRE, DevOps, Developer, HR, Jira counts, Confluence procedures, uploaded docs, and web/blended queries.
- Baseline retrieval and generation scores recorded.
- Every production answer stores enough trace data to debug why retrieval succeeded or failed.

## Phase 1 - Corpus Hygiene and Source Fidelity

Goal: make sure the right content is indexed with correct metadata before optimizing ranking.

Build:

- Normalize source metadata: `source_type`, `space`, `project`, `issue_key`, `page_id`, `title`, `url`, `updated_at`, `status`, `labels`, `owner`, `acl`, and `connector_sync_id`.
- Deduplicate documents and chunks across repeated Jira syncs, Confluence page revisions, and uploads.
- Track deleted, archived, moved, and permission-restricted sources.
- Add freshness scoring so newer runbooks, active incidents, and current Jira states rank above stale duplicates.
- Add connector health checks for DevOps and SRE source coverage.

Accuracy impact:

- Reduces wrong answers caused by stale pages, duplicate chunks, and incorrect source routing.
- Improves exact Jira/Confluence citation quality.

Exit criteria:

- No synthetic or duplicate connector rows in source counts.
- Each indexed chunk maps back to one real openable source.
- Source inventory clearly separates Jira DEVO, Jira CVIR, Confluence DevOps1, Confluence SRE, Confluence AS, uploads, and web.

## Phase 2 - Chunking and Index Enrichment

Goal: improve the document units the retriever sees.

Build:

- Replace fixed chunking with structure-aware chunking:
  - Confluence: headings, sections, tables, code blocks, runbook steps.
  - Jira: issue title, description, comments, status history, labels, components, fix versions, linked issues.
  - Uploads: page, heading, table, figure, and section boundaries.
- Add parent-child retrieval: retrieve small chunks but include parent section/page context for generation.
- Add contextual retrieval: prepend short LLM-generated context to chunks before dense embedding and sparse indexing.
- Add chunk summaries and document summaries for global questions.
- Store both chunk text and metadata fields for hybrid retrieval and filtering.

Accuracy impact:

- Fixes chunks that lose context, sever runbook procedures, or rank comments without the issue/page title.
- Survey signal: contextual retrieval plus hybrid search and reranking can sharply reduce retrieval failures.

Exit criteria:

- Retrieval eval shows improved context precision without reducing recall.
- For runbook questions, returned chunks include the procedure title and surrounding step context.
- For Jira questions, returned chunks include issue key, status, project, and source URL.

## Phase 3 - Hybrid Retrieval and Source Routing

Goal: stop relying on one vector similarity signal.

Build:

- Run dense vector retrieval and sparse BM25/full-text retrieval in parallel.
- Fuse candidate lists with reciprocal rank fusion.
- Add metadata filters and boosts for selected role/space:
  - SRE questions prefer SRE Confluence, AS Confluence, and CVIR Jira.
  - DevOps questions prefer DevOps1 Confluence and DEVO Jira.
  - Jira count/stat questions route to structured metadata first.
  - Web/Both modes only include web when selected or internal retrieval is weak.
- Add exact identifier handling for issue keys, service names, hostnames, URLs, error codes, and runbook titles.
- Add candidate diversity so near-duplicate chunks do not crowd out distinct evidence.

Accuracy impact:

- Sparse search catches exact operational terms; dense search catches semantic variants.
- Routing prevents irrelevant spaces from dominating top-k.

Exit criteria:

- Hybrid retrieval beats dense-only on source recall, MRR, and exact identifier queries.
- Queries containing Jira keys, CVIR/DEVO identifiers, service names, or runbook titles resolve to the expected source in top 3.

## Phase 4 - Query Understanding and Rewrite Layer

Goal: retrieve for the user's real information need, not only the literal latest message.

Build:

- Keep conversational question rewriting, but make it retrieval-safe:
  - Rewrite follow-ups into standalone questions.
  - Preserve exact entities, issue keys, spaces, dates, and source mode.
  - Do not invent filters not present in conversation.
- Add query classification:
  - factual lookup
  - procedure/runbook
  - Jira count/stat
  - multi-hop RCA
  - comparison
  - global summary
  - unsupported/out-of-scope
- Add query decomposition for multi-part questions, especially Jira count plus Confluence procedure questions.
- Add step-back or HyDE-style expansion only when plain retrieval quality is weak.
- Store rewritten queries in traces and eval outputs.

Accuracy impact:

- Follow-up questions retrieve relevant documents.
- Multi-part questions no longer collapse into one weak search.

Exit criteria:

- Follow-up eval cases improve without degrading first-turn questions.
- Multi-part questions return evidence for each sub-question.
- Rewrites remain faithful to chat history and do not add unsupported assumptions.

## Phase 5 - Reranking, Context Selection, and Compression

Goal: make top context high precision before generation.

Build:

- Add a pluggable reranking interface:
  - local cross-encoder or BGE-style reranker when available
  - LLM listwise reranker as fallback for hard queries
  - provider reranker if configured later
- Rerank 50-200 fused candidates down to a compact final context set.
- Add context packing:
  - remove duplicates
  - preserve source diversity
  - keep procedure steps in order
  - prefer newer active Jira states
  - include parent section title and source metadata
- Add context compression for long pages, comments, and incident threads.
- Keep a no-compression path for exact procedural steps and commands.

Accuracy impact:

- Reranking is one of the highest-leverage post-retrieval improvements.
- Compression reduces distracting context without losing answer-critical facts.

Exit criteria:

- Reranked top 5 has higher context precision than fused top 5.
- No final answer cites a source that was not in final context.
- p95 latency increase stays within the agreed budget.

## Phase 6 - Corrective and Adaptive RAG

Goal: make retrieval self-correcting instead of accepting weak context.

Build:

- Replace accept-always retrieval policy with a retrieval evaluator.
- Score candidate context for relevance, coverage, freshness, contradiction, and citation viability.
- If quality is low, trigger corrective paths:
  - rewrite query
  - decompose query
  - broaden/narrow source filters
  - switch from dense-only to hybrid if not already used
  - add web fallback only when configured or explicitly selected
  - abstain when evidence remains weak
- Add adaptive routing:
  - no retrieval for pure UI/help questions
  - single retrieval for simple lookups
  - structured path for Jira counts
  - iterative retrieval for multi-hop SRE/RCA questions

Accuracy impact:

- Reduces confident wrong answers.
- Converts weak retrieval into either a better retrieval attempt or a clear refusal.

Exit criteria:

- Unsupported questions either abstain or use the configured fallback.
- Weak first retrieval improves after corrective rewrite in eval traces.
- Hallucination and unsupported-claim rates drop.

## Phase 7 - Structured Jira Analytics and Graph Retrieval

Goal: answer operational questions from the right retrieval substrate.

Build:

- Add analytics-aware Jira paths:
  - counts by project, status, assignee, priority, component, labels, created/resolved windows
  - open/closed/aging queries
  - recent incidents and top recurring labels
  - structured filters generated from natural language
- Compute Jira numeric answers from indexed structured metadata, not from chunks.
- Add source-backed explanation for computed results, including filters used.
- Add a lightweight graph layer:
  - Jira issue to component/service/runbook
  - Confluence page to service/team/process
  - incidents to related issues and postmortems
  - labels/entities to owners
- Use graph retrieval for global and multi-hop questions such as "what are common SRE incident patterns?" or "which runbook applies to this Jira issue?"

Accuracy impact:

- Numeric and aggregation questions become deterministic.
- Graph retrieval handles cross-source relationships that vector search misses.

Exit criteria:

- Jira count evals match database counts.
- Multi-hop SRE questions return evidence from both Jira and Confluence when expected.
- Global summary questions no longer depend on random top-k chunks.

## Phase 8 - Grounded Answer Generation and Verification

Goal: only persist answers that are backed by evidence.

Build:

- Generate answers using current question, standalone rewritten question, chat history, and final context.
- Add claim-level grounding verification before saving assistant responses.
- Reject or revise answer sentences that lack support.
- Resolve contradictions:
  - prefer latest source
  - show conflict when sources disagree
  - cite both conflicting sources
- Enforce citation rules:
  - every citation marker maps to a real source object
  - no citation marker appears if it cannot open
  - source list includes title, type, updated date, and URL/page id
- Shape final answers into compact operational sections: direct answer, steps/evidence, caveats, sources.

Accuracy impact:

- Prevents answer polish from hiding unsupported claims.
- Keeps citations useful for operators.

Exit criteria:

- Citation coverage and citation open rate meet release thresholds.
- Unsupported-claim rate drops below threshold.
- Persisted answers include grounding metadata for audit.

## Phase 9 - Multimodal and Visual Document Retrieval

Goal: retrieve evidence from the way enterprise knowledge actually appears: PDFs, screenshots, slides, tables, and diagrams.

Build:

- Add high-quality PDF extraction with page-level source mapping.
- Preserve tables, code blocks, diagrams, and screenshots as retrievable units.
- Add OCR fallback for scanned documents.
- Evaluate visual-document retrieval options such as page-level multimodal embeddings or ColPali-style late interaction when feasible.
- Add table-aware retrieval for runbook matrices, ownership tables, escalation paths, and Jira exports.

Accuracy impact:

- Stops losing answers that exist only in PDFs, screenshots, diagrams, or tables.
- Improves source fidelity for uploaded operational docs.

Exit criteria:

- Uploaded PDF/table questions pass golden evals.
- Citations can open the exact page or document section.
- Visual/table extraction failures are visible in ingestion health.

## Phase 10 - Release Gates and Continuous Retrieval QA

Goal: make retrieval accuracy a shipping requirement.

Build:

- Add CI gates for:
  - source recall
  - context precision
  - citation coverage
  - groundedness
  - unsupported-claim rate
  - Jira numeric accuracy
  - p95 latency
- Separate live production health from offline release-gate eval scores in the Evals UI.
- Add regression history by model, embedding version, chunking strategy, reranker, prompt, source connector, and deployment.
- Add "why failed" drilldowns for every failed golden example.
- Require threshold approval before merging changes to embeddings, chunking, retrieval, reranking, prompts, or generation.

Accuracy impact:

- Prevents quiet regressions.
- Makes improvement measurable over time.

Exit criteria:

- A model, prompt, embedding, chunking, reranking, or retrieval change cannot merge unless golden scores stay above thresholds.
- Evals UI shows offline score, live score, failures, trend, and cost/latency.

## Phase 11 - Systems, Cost, and Latency Optimization

Goal: keep higher accuracy usable in production.

Build:

- Cache embeddings, retrieved candidates, reranked contexts, and hot answer traces where safe.
- Add prompt/context caching for repeated stable runbooks and high-frequency SRE/DevOps procedures.
- Add budget-aware routing:
  - fast path for simple factual queries
  - high-accuracy path for SRE/RCA and multi-hop queries
  - council/deep path only when needed
- Track token usage, reranker latency, LLM latency, and total cost per answer.
- Add context-length control so top evidence is not lost in the middle of a long prompt.

Accuracy impact:

- Lets the product use stronger retrieval paths without making every query slow or expensive.

Exit criteria:

- p95 latency and cost stay inside product thresholds.
- High-accuracy mode is available for hard queries without slowing simple queries.

## Phase 12 - Agentic Retrieval and Memory

Goal: support deep SRE/DevOps investigations while keeping normal Ask fast.

Build:

- Add a controlled "Deep Investigation" mode for multi-step retrieval.
- Use a planner that can decide: search Jira, search Confluence, compute Jira stats, inspect history, ask web, verify, or abstain.
- Store session memory separately from source memory:
  - session memory helps conversation continuity
  - source memory remains auditable retrieved evidence
- Add operator-visible reasoning trace without exposing hidden chain-of-thought: steps taken, tools used, sources checked, and why the answer is supported or not.

Accuracy impact:

- Handles complex incident, RCA, and cross-source questions that one retrieval pass cannot solve.
- Keeps normal Ask from becoming an expensive agent for simple queries.

Exit criteria:

- Deep Investigation improves multi-hop SRE/DevOps evals.
- Simple Ask latency does not regress.
- The user can see what sources and tools were checked.

## Recommended Build Order

1. Phase 0 and Phase 1 first: measurement and source fidelity.
2. Phase 2 and Phase 3 next: chunking plus hybrid retrieval.
3. Phase 4, Phase 5, and Phase 6 next: rewrite, rerank, corrective retrieval.
4. Phase 7 and Phase 8 next: structured Jira analytics plus grounded verification.
5. Phase 10 continuously: release gates should begin as soon as the first golden dataset exists.
6. Phase 9, Phase 11, and Phase 12 after core retrieval quality is stable.

## Immediate Priorities for CVUM

- Fix retrieval quality before adding more answer UI.
- Make SRE and DevOps source routing explicit and measurable.
- Make Jira count/stat questions deterministic from metadata.
- Add reranking and a retrieval-quality evaluator.
- Add claim-level verification before answer persistence.
- Keep `/ask` as the main user path, but make admin evals/source pages the control plane for accuracy.
