# RAGCore Enterprise Knowledge Base — Retrieval and AI Improvement Blueprint

Status: proposed roadmap grounded in the current repository and the cited primary sources
Product name: CVUM
Repository: RAGCore
Date: 2026-07-20

## 1. Executive decision

RAGCore already has more than a basic vector RAG stack. It currently includes:

- PostgreSQL full-text search plus pgvector cosine search.
- An HNSW index with `m=16` and `ef_construction=64` in `backend/models/knowledge.py`.
- Dense, sparse, exact-identifier, and rare-token retrieval arms in
  `backend/retrieval/pipeline.py`.
- Weighted fusion and a feature-flagged weighted RRF implementation in
  `backend/retrieval/fusion.py`.
- Heuristic and optional bounded model reranking.
- Source-recency signals, document/source diversity, adjacent-chunk expansion, corrective retries,
  best-attempt retention, grounding checks, and citations.
- Project-scoped authorization, restricted-source grants, and seven read-only evidence tools.
- Incremental Jira, Confluence, Slack, GitHub, upload, and web ingestion paths.
- A deterministic or model-assisted planner with bounded parallel evidence execution.

The correct next step is not a rewrite or a new vector database. The highest-value path is to make
the existing retrieval system measurable, query-adaptive, context-aware, and operationally safe at
enterprise scale.

The recommended order is:

1. Establish retrieval and security evaluation gates.
2. Tune filtered HNSW behavior and observe approximate-recall loss.
3. Add source-specific contextual chunk enrichment.
4. Route queries between weighted fusion, RRF, exact search, and model reranking.
5. Improve final context packing against the lost-in-the-middle effect.
6. Add bounded Search-o1-style iterative retrieval for genuinely complex questions.
7. Evolve MCP into progressive tool discovery plus sandboxed, read-only code execution.
8. Add deletion lineage, backpressure, and SLOs for Slack-scale enterprise ingestion.
9. Learn code retrieval from real accepted agent traces only after sufficient feedback exists.

## 2. Evidence boundary

This document separates three things:

- **Verified current** means the behavior exists in this repository today.
- **Source finding** means the cited paper or engineering article reports the result.
- **Recommendation** means an engineering inference for RAGCore that still requires an experiment.

External benchmark percentages are not treated as guaranteed RAGCore gains. Every proposed change
must beat the repository's own golden and live evaluation gates before becoming a default.

## 3. Source-by-source findings and direct application

### 3.1 HNSW: fast approximate vector retrieval

Malkov and Yashunin describe HNSW as a multi-layer proximity graph that starts at sparse upper
layers and descends toward denser local neighborhoods. The paper reports logarithmic scaling and a
strong speed/recall tradeoff for approximate nearest-neighbor search. See [Efficient and Robust
Approximate Nearest Neighbor Search Using Hierarchical Navigable Small World Graphs](https://arxiv.org/abs/1603.09320).

Verified current:

- `backend/models/knowledge.py` defines `ix_chunks_embedding_hnsw` with cosine operators,
  `m=16`, and `ef_construction=64`.
- `backend/repositories/chunks.py::dense_search` applies knowledge-base, active-version, and
  collection filters before returning candidates.

Important gap:

- The index construction parameters are explicit, but query-time `hnsw.ef_search` is not tuned per
  request.
- Project and knowledge-base filters can reduce the number of surviving ANN results. pgvector's
  official documentation notes that filtering is applied after an approximate index scan and
  recommends raising `hnsw.ef_search` or using iterative scans when filters remove candidates. See
  the [pgvector HNSW and filtering documentation](https://github.com/pgvector/pgvector/blob/master/README.md#filtering).

Recommendation:

- Add `RETRIEVAL_HNSW_EF_SEARCH`, `RETRIEVAL_HNSW_ITERATIVE_SCAN`, and
  `RETRIEVAL_HNSW_MAX_SCAN_TUPLES` settings.
- In `ChunkSearchRepository.dense_search`, use transaction-local settings so one request cannot
  change another request's search behavior.
- Start with three evaluation profiles, not one guessed default:

  | Profile | Intended use | Initial values to test |
  | --- | --- | --- |
  | Fast | autocomplete and broad discovery | `ef_search=40` |
  | Balanced | normal enterprise Ask | `ef_search=100`, strict iterative scan |
  | High recall | incident and compliance queries | `ef_search=200`, bounded iterative scan |

- Measure ANN recall against an exact-search sample for each project size and filter selectivity.
- Add a nightly HNSW recall audit that compares approximate top-k with exact top-k on sampled
  queries.
- Consider project/source partitioning or partial indexes only after measurements show that
  post-filter loss is material. Do not create one HNSW index per project by default.

Acceptance gate:

- Recall@20 loss versus exact cosine search is at most 2 percentage points for the balanced profile.
- p95 dense-search latency remains inside the retrieval SLO.
- Restricted-source and project filters produce zero unauthorized candidates before ranking.

### 3.2 Contextual Retrieval: recover meaning lost during chunking

Anthropic's Contextual Retrieval prepends a short, chunk-specific explanation before both embedding
and BM25 indexing. Their experiments report a 35% reduction in top-20 retrieval failure from
contextual embeddings, 49% when contextual BM25 is added, and 67% when contextual retrieval is
combined with reranking. These are source-reported results, not expected RAGCore numbers. See
[Introducing Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval).

Verified current:

- RAGCore already normalizes source metadata in `backend/knowledgebase/source_metadata.py`.
- The ingestion path creates embedding text that includes source context.
- Confluence chunks preserve headings, Jira chunks preserve issue/relationship context, Slack
  stores normalized threads, and GitHub code chunks preserve symbols and repository metadata.

Gap:

- The contextual prefix is largely deterministic metadata. RAGCore does not yet create a concise
  chunk-specific explanation derived from the whole document.
- Dense embedding context and sparse indexed text are not versioned as an independently measurable
  contextualization artifact.

Recommendation:

- Add a `ChunkContextualizer` interface after chunking and before embedding.
- Implement source-specific contextualizers:

  - Confluence: page title, heading ancestry, document purpose, effective date, owning team.
  - Jira: issue key, issue type, parent/epic, status, affected service, resolution relationship.
  - Slack: channel, thread question, resolution state, systems, incident or decision identity.
  - GitHub: repository, path, symbol, callers/owners when known, commit identity.
  - Upload: document title, section path, page range, extracted document class.

- Store `context_text`, `contextualizer_version`, `context_model`, and `context_generated_at` in
  chunk metadata so reindexing and ablations are reproducible.
- Build both embeddings and sparse `tsvector` content from `context_text + original_chunk`, while
  retaining original content for citation display.
- Use prompt caching or document-level memoization so the full document is not resent for every
  chunk.
- Keep a deterministic contextualizer fallback for outages, local development, and sensitive
  sources that cannot be sent to an external model.

Safety constraints:

- Context generation is ingestion-time enrichment, never an authorization decision.
- Generated context cannot add new facts to the cited source; it is search metadata only.
- The answer UI must quote/display original source text, not generated context as if it were source
  evidence.
- A source deletion or new restricted ACL invalidates contextualized chunks and their derivatives.

Acceptance gate:

- Compare current versus contextual retrieval on at least 200 hard queries where isolated chunks
  are ambiguous.
- Require improvement in recall@20 and nDCG@10 without a material citation-precision regression.
- Human reviewers must find no unsupported entity, date, owner, or incident linkage in generated
  context metadata.

### 3.3 Reciprocal Rank Fusion: combine incomparable retrieval systems

Cormack, Clarke, and Büttcher define RRF as the sum of `1 / (k + rank)` across ranked lists and show
that this simple unsupervised fusion consistently matches or outperforms individual systems and
other metarankers in their experiments. Their pilot used `k=60`. See [Reciprocal Rank Fusion
Outperforms Condorcet and Individual Rank Learning Methods](https://research.google/pubs/reciprocal-rank-fusion-outperforms-condorcet-and-individual-rank-learning-methods/).

Verified current:

- `backend/retrieval/fusion.py::reciprocal_rank_fusion` implements weighted RRF with competition
  ranks and a default smoothing value of 60.
- It can combine dense, sparse, exact-identifier, and rare-token arms.
- The repository's 129-case comparison found higher recall for RRF but slightly lower precision and
  MRR, plus higher latency; therefore weighted fusion remains the measured default.

Recommendation:

- Do not globally flip `RETRIEVAL_FUSION_MODE=rrf`.
- Add a deterministic query router that selects the fusion profile:

  | Query type | Primary strategy |
  | --- | --- |
  | Exact Jira key, error code, path, symbol, hostname | exact/rare-token arms plus weighted fusion |
  | Broad semantic policy or architecture question | RRF across dense and sparse arms |
  | Time-sensitive status or incident question | weighted fusion plus source-aware freshness |
  | Cross-source investigation | RRF, diversity constraints, then reranking |

- Record the chosen profile, active arms, ranks, and contributions in the existing content-free
  retrieval trace.
- Tune arm weights and RRF smoothing on held-out queries, not the final test set.
- Add deduplication at stable evidence identity so the same Jira issue, Slack thread, or file version
  cannot dominate through multiple near-identical chunks.

Acceptance gate:

- Per-intent routing must beat the current weighted default on macro nDCG@10 or task success while
  staying within the p95 latency budget.
- A fallback to the current weighted path must always be available.

### 3.4 Search-o1: retrieve during reasoning only when knowledge is missing

Search-o1 adds agent-triggered retrieval during reasoning and a separate Reason-in-Documents module
that condenses retrieved pages before adding their useful content back into the reasoning process.
The paper argues that blindly injecting long retrieved documents can interrupt reasoning coherence.
See [Search-o1: Agentic Search-Enhanced Large Reasoning Models](https://arxiv.org/abs/2501.05366).

Verified current:

- `backend/services/evidence_planner.py` selects up to five typed evidence tools.
- `backend/services/evidence_executor.py` runs tools with per-tool and overall deadlines using
  independent sessions.
- `backend/services/evidence_orchestrator.py` normalizes the result into a shared evidence contract.
- The planner is optional and has a deterministic fallback.

Gap:

- Planning is currently one-shot before synthesis.
- There is no explicit knowledge-insufficiency detector or query-specific Reason-in-Documents pass.

Recommendation:

- Add an optional `agentic_retrieval_v2` mode for complex multi-hop questions only.
- Use this bounded state machine:

  ```text
  classify complexity
      -> retrieve initial evidence
      -> assess missing claim/entity/time range
      -> create one targeted subquery
      -> retrieve with one or more read-only tools
      -> extract evidence notes with source identities
      -> repeat at most twice
      -> synthesize or refuse
  ```

- The Reason-in-Documents output must be structured evidence notes containing source ID, supported
  proposition, exact location, confidence, and unresolved conflict. It must not become a hidden
  uncited answer.
- Trigger iterative search when the current evidence has low coverage, conflicting versions, an
  unresolved entity, or a missing link in a multi-hop chain.
- Do not trigger it for exact keys, simple lookups, deterministic counts, or high-confidence
  single-source questions.
- Limit the loop to two additional retrieval rounds, three subqueries, five tools per round, and a
  total token/cost/deadline budget.

Acceptance gate:

- Multi-hop task success improves on a dedicated cross-source set.
- Simple-query p95 latency and cost do not regress because the mode stays off for simple intents.
- Every final factual claim maps to original evidence, not only to a generated evidence note.

### 3.5 Code execution with MCP: progressive tool use without context overload

Anthropic describes two MCP scaling problems: loading many tool schemas up front and passing large
intermediate results through the model. Their proposed code-execution pattern loads tools on demand
and filters or aggregates results in a sandbox before returning small outputs to the model. See
[Code Execution with MCP: Building More Efficient Agents](https://www.anthropic.com/engineering/code-execution-with-mcp).

Verified current:

- RAGCore exposes seven project-scoped, read-only evidence tools through REST and a local MCP stdio
  bridge.
- Tool inputs are schema-validated; authorization is resolved by the API; MCP never opens the
  database directly.

Recommendation:

- Add a minimal `search_tools` capability that returns tool name and short description first, with
  full schemas only on demand.
- Provide generated, typed wrappers for the seven evidence tools.
- Introduce an optional sandbox for read-only data transformation:

  - no network except the local MCP proxy;
  - no host filesystem mounts;
  - CPU, memory, process, output, and wall-time limits;
  - ephemeral workspace;
  - no source mutation tools;
  - organization/project/user identity fixed outside model control;
  - complete audit of tools invoked, result counts, and policy decisions.

- Let code filter, join, aggregate, and select evidence, but require the final result to return
  stable citation identities.
- Never pass raw credentials, unrestricted connector responses, or a general shell to the model.
- Start with deterministic server-side compositions for incident timelines and change summaries;
  enable generated code only after sandbox and adversarial tests pass.

Acceptance gate:

- Tool-schema and intermediate-result tokens decrease on multi-tool tasks.
- Sandbox escape, network egress, secret access, write operations, and authorization-widening tests
  all fail closed.
- Code execution never replaces evidence/citation validation.

### 3.6 Lost in the Middle: final context order is a retrieval feature

Liu et al. found a U-shaped performance curve: models often use information best near the beginning
or end of long contexts and perform worse when relevant evidence is buried in the middle. They also
found that reader accuracy can saturate before retriever recall. See [Lost in the Middle: How
Language Models Use Long Contexts](https://arxiv.org/abs/2307.03172).

Verified current:

- `select_final_context` already enforces document and source diversity.
- Neighbor expansion is bounded and happens only after ranking.
- Retrieved evidence is placed inside source-delimited prompt blocks.

Recommendation:

- Add a final `ContextPacker` after reranking and neighbor expansion.
- Pack by claim utility, not only by score:

  1. Put the strongest direct evidence first.
  2. Put the strongest corroborating or decisive contradictory evidence last.
  3. Put secondary context and neighbors in the middle.
  4. Repeat the question or a short evidence objective immediately before synthesis.

- Allocate a token budget per source family and per document so a long Slack thread cannot crowd
  out the authoritative runbook or ticket.
- Collapse near-duplicates and extract only the relevant region from very long chunks.
- Preserve source order inside each document when multi-chunk reasoning depends on sequence.
- Add an explicit conflict block when sources disagree; do not silently rank the conflict away.

Evaluation:

- Create a position-sensitivity test that places the same relevant source first, middle, and last.
- Track the best-versus-worst answer accuracy gap as a first-class metric.
- Test 5, 10, 20, and 30 context blocks instead of assuming more retrieved text is better.

Acceptance gate:

- Reduce the position-sensitivity gap without lowering grounded answer accuracy.
- Keep prompt tokens flat or lower for the same task set.

### 3.7 XML prompt sections and nested-data payload format are different decisions

Anthropic recommends consistent XML-style tags to separate documents, content, source metadata,
examples, and instructions in complex prompts. See [Anthropic prompting best
practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices).

Improving Agents tested large, deeply nested synthetic Terraform-like data in JSON, YAML, XML, and
Markdown. YAML had the best accuracy for two of three tested models, while Markdown used the fewest
tokens; the author explicitly notes limitations across models, domains, and question types. See
[Which Nested Data Format Do LLMs Understand Best?](https://www.improvingagents.com/blog/best-nested-data-format).

These findings are not contradictory:

- XML tags can be a good **prompt envelope** that separates trusted instructions from untrusted
  evidence.
- YAML or Markdown can be a better **bulk nested-data payload** for some models.

Recommendation:

- Keep the high-level prompt envelope explicit and source-delimited:

  ```xml
  <task>...</task>
  <question>...</question>
  <evidence_set>
    <source id="S1" type="jira">...</source>
    <source id="S2" type="confluence">...</source>
  </evidence_set>
  <constraints>...</constraints>
  ```

- Render nested payloads inside each source as Markdown or YAML when that is more compact and clear.
- Keep JSON for machine-to-machine APIs and schema-validated model outputs.
- Do not convert executable code, logs, stack traces, or exact config fragments into YAML when doing
  so could alter whitespace or semantics.
- Benchmark format per production model and source type. Do not set one universal format from a
  three-model synthetic benchmark.
- Escape or delimit user/source content so it cannot close trusted tags or inject new instructions.

Acceptance gate:

- Add a format matrix across every supported production model using nested Jira, Slack, GitHub, and
  infrastructure data.
- Measure answer accuracy, parse success, token count, latency, and prompt-injection resistance.

### 3.8 Slack-scale knowledge: lineage, privacy, backpressure, and deletion

Salesforce's overview describes Slack AI at billions-of-message scale. Slack's more detailed
security architecture states four especially relevant principles: customer data stays in the trust
boundary, customer data is not used to train the LLM, AI only operates on data the user can already
see, and derived summaries are invalidated when underlying content is tombstoned. See [How Slack AI
Processes Billions of Messages](https://engineering.salesforce.com/how-slack-ai-processes-billions-of-messages-to-reduce-information-overload-with-ai-powered-search-and-summarization/)
and [How We Built Slack AI to Be Secure and Private](https://slack.engineering/how-we-built-slack-ai-to-be-secure-and-private/).

Verified current:

- RAGCore allowlists public channels, records event receipts, deduplicates events, stores one
  normalized versioned document per thread, and maps channels into project-scoped knowledge bases.
- Restricted-source grants and project authorization are applied before retrieval.

Recommendation:

- Add a derivation graph linking raw messages -> normalized bursts -> thread document -> chunks ->
  summaries/cached answers.
- On edit, delete, retention expiry, DLP event, channel visibility change, or membership revocation,
  invalidate every derivative before it can be retrieved again.
- Store only stable Slack IDs and minimum required metadata; never duplicate secrets or complete
  user profiles into chunk metadata.
- Separate the real-time event path from heavy normalization:

  ```text
  Socket event -> validate -> dedupe -> acknowledge -> durable queue
      -> fetch authorized thread -> normalize -> version -> embed -> activate atomically
  ```

- Partition event receipts and audit history by time; enforce retention policies.
- Add queue lag, oldest event age, retry count, dead-letter count, per-workspace throughput, and
  invalidation lag metrics.
- Use idempotency keys at event, thread-version, and embedding-job levels.
- Apply backpressure and per-workspace quotas so one tenant cannot exhaust workers.
- Keep summaries ephemeral when they do not need persistence; when persisted, store complete source
  lineage and access policy version.

Acceptance gate:

- Deleted or newly unauthorized content disappears from retrieval and derived answers within the
  defined revocation SLO.
- Replayed and out-of-order events produce the same final thread version.
- Load tests demonstrate bounded queue lag and stable memory under burst traffic.

### 3.9 Cursor-style semantic code search: combine meaning and exact search

Cursor reports that adding semantic search to traditional code search improved answer accuracy by
12.5% on average in its offline evaluation and improved online retention particularly for large
codebases. Cursor also states that its agent uses semantic search and grep together and learns a
custom embedding model from agent traces. See [Improving Agent with Semantic
Search](https://cursor.com/blog/semsearch).

Verified current:

- GitHub indexing is blob-SHA incremental and path-policy constrained.
- `CodeChunker` recognizes common class/function/method boundaries and falls back to bounded
  recursive chunks.
- Exact code search and normal authorized hybrid semantic search both exist.
- Repository/path/symbol/commit/CODEOWNERS/contributor metadata and commit-pinned citations are
  preserved.

Recommendation:

- Keep exact and semantic code search together; never replace exact identifier search with vectors.
- Add language-aware parsing with tree-sitter for supported languages, retaining the current regex
  chunker as fallback.
- Create repository-level context for modules, imports, call edges, tests, and ownership.
- Add query routing:

  - symbols, file paths, error strings -> exact search first;
  - behavior questions -> semantic search first;
  - change-risk questions -> semantic + call/reference graph + recent PR evidence.

- Build a `Code Context Bench` from known repository questions with stable expected files/symbols.
- Capture privacy-safe retrieval traces: searches, opened files, accepted citations, user
  correction, and whether generated changes survived review.
- Only after enough high-quality traces exist, train or fine-tune a code retrieval model. Keep data
  project-scoped and do not train across customer code without explicit permission.
- Use hard negatives from similar symbols in wrong modules and old file versions.

Acceptance gate:

- Improve file/symbol recall@k and end-task code-answer accuracy on repositories larger than 1,000
  files.
- Never return denied paths, deleted versions, or a branch/commit other than the cited identity.

## 4. Target enterprise retrieval architecture

```text
Authorized request
  -> resolve organization + user + project + source grants
  -> classify intent, complexity, freshness, and exact-identifier needs
  -> query rewrite and subquery budget
  -> candidate generation
       - dense HNSW with filtered-ANN profile
       - PostgreSQL sparse/BM25-like full-text arm
       - exact identifier/path/key arm
       - rare-token arm
       - optional relationship/source-native arms
  -> query-adaptive weighted fusion or RRF
  -> source recency and authority policy
  -> heuristic or bounded model reranker
  -> stable-evidence dedupe and source/document diversity
  -> optional neighbor/relationship expansion
  -> context compression and lost-in-the-middle-aware packing
  -> optional bounded agentic evidence loop
  -> grounded synthesis with citation validation
  -> feedback, retrieval trace, cost, latency, and quality events
```

Security is an outer boundary around every stage. Authorization IDs come from server-side policy,
not the planner, model, source text, client, or MCP code.

## 5. Proposed component changes

| Area | Current file | Proposed addition |
| --- | --- | --- |
| HNSW search profile | `backend/repositories/chunks.py` | transaction-local ANN settings and exact-recall audit mode |
| Configuration | `backend/core/config.py` | ANN, contextualization, packing, and agentic-loop flags |
| Context enrichment | `backend/ingestion/pipeline.py` | `ChunkContextualizer` with versioned source profiles |
| Chunk schema | `backend/models/knowledge.py` | stored contextual text/hash/model/version or versioned metadata contract |
| Fusion routing | `backend/retrieval/pipeline.py` | deterministic per-intent retrieval profile selector |
| Fusion | `backend/retrieval/fusion.py` | stable evidence dedupe and calibrated contribution trace |
| Reranking | `backend/retrieval/rerankers.py` | batch cross-encoder provider and per-intent activation |
| Context packing | new `backend/retrieval/packing.py` | compression, token allocation, conflict grouping, end-aware ordering |
| Agentic retrieval | `backend/services/evidence_*` | missing-evidence assessment and bounded iterative subqueries |
| MCP | `backend/scripts/run_mcp_server.py` | progressive tool discovery and typed wrappers |
| Sandbox | new isolated service/package | read-only code composition with resource and network policy |
| Slack lineage | `backend/services/slack_service.py` | derivative graph and policy-version invalidation |
| Code parsing | `backend/ingestion/chunkers/code.py` | tree-sitter adapters with current fallback |
| Evaluation | `backend/scripts/run_evals.py` and `evals/` | retrieval labels, ANN exact comparison, position and ACL suites |

## 6. Evaluation system required before rollout

### 6.1 Dataset layers

1. **Golden answer set** — keep the current 129 cases as a regression baseline.
2. **Retrieval judgment set** — query-to-relevant-evidence labels, including multiple valid sources.
3. **Hard negatives** — same names, old versions, similar incidents, wrong projects, and denied
   sources.
4. **Cross-source multi-hop set** — questions requiring Jira + Slack + Confluence + code/PR evidence.
5. **Exact identifier set** — ticket keys, hostnames, flags, hashes, paths, symbols, and error codes.
6. **Position set** — same evidence placed at different context positions.
7. **Deletion/ACL set** — revoked users, removed project mappings, tombstoned messages, and deleted
   versions.
8. **Scale set** — small, medium, and enterprise-sized projects with realistic filter selectivity.

### 6.2 Offline metrics

- ANN recall@k versus exact vector search.
- Retrieval recall@5/10/20.
- Precision@k and nDCG@10.
- MRR for exact and navigational queries.
- Source coverage and unique-document coverage.
- Citation precision and citation completeness.
- Grounded claim precision and unsupported-claim rate.
- Refusal correctness when evidence is weak.
- Position-sensitivity gap.
- Unauthorized-result count, which must remain zero.
- p50/p95/p99 latency by stage.
- prompt, embedding, reranking, and agentic-search tokens/cost.

### 6.3 Online metrics

- Answer acceptance and saved-answer rate.
- Follow-up correction rate.
- Citation open rate and source usefulness.
- Search reformulation rate.
- Time to first useful evidence.
- Incident workflow completion rate.
- Retrieval profile and model fallback rate.
- Connector lag, invalidation lag, and dead-letter rate.

### 6.4 Experiment discipline

- Pin dataset, code commit, embedding model, index parameters, and source snapshot.
- Run at least three repetitions for latency-sensitive configurations.
- Use a held-out final test set.
- Compare both quality and cost; do not accept a quality gain that violates the product SLO unless
  it is isolated to an explicit deep-research mode.
- Roll out per organization/project behind flags with instant rollback.

## 7. Enterprise SLO proposal

These are initial targets to validate, not claims about current production performance.

| Capability | Target |
| --- | --- |
| Authorization leakage | 0 unauthorized chunks or citations |
| Exact identifier retrieval | >= 99% recall@5 |
| Normal Ask retrieval | p95 <= 1.5 seconds before LLM generation |
| Agentic evidence mode | p95 <= 8 seconds before synthesis |
| Source sync success | >= 99.5% excluding provider outages |
| Slack event acknowledgement | p95 <= 3 seconds |
| Connector lag | p95 <= 5 minutes for real-time sources |
| Deletion/access revocation | excluded from retrieval within 5 minutes, target < 1 minute |
| Citation completeness | >= 98% for externally verifiable factual claims |
| Weak-evidence refusal | >= 95% precision on refusal evaluation set |

## 8. Phase plan with implementation and test gates

### Phase 0 — Measurement and safety baseline

Deliver:

- Retrieval judgment schema and labeled dataset.
- Stage-level traces and dashboards.
- Exact-versus-HNSW audit script.
- ACL/deletion/red-team evaluation suite.
- Cost and latency budgets per mode.

Tests:

- Unit tests for metric calculations.
- Integration tests for project/restricted-source filtering in every arm.
- Golden answer regression.
- Secret and PII checks for traces.

Exit condition: no retrieval change ships without reproducible baseline results.

### Phase 1 — Filtered HNSW tuning

Deliver:

- Request-scoped ANN profiles.
- Iterative scan experiment.
- Per-project size/selectivity benchmark.
- Operational index size/build/health dashboard.

Tests:

- Compare approximate results with exact cosine results.
- Concurrent requests with different ANN profiles do not leak session settings.
- Explain plans confirm index use where expected.
- Load and soak tests during document updates.

Exit condition: balanced profile meets recall and latency gates.

### Phase 2 — Contextual chunk enrichment

Deliver:

- Versioned contextualizer interface and deterministic fallback.
- Confluence and Jira pilots, then Slack/GitHub/upload profiles.
- Original-versus-contextual ablation runner.

Tests:

- No generated context shown as original evidence.
- Context metadata regenerates when the source version changes.
- Injection strings in source content cannot alter contextualizer instructions.
- Deletion/ACL changes invalidate contextual derivatives.

Exit condition: held-out retrieval improves with no citation or safety regression.

### Phase 3 — Query-adaptive fusion and reranking

Deliver:

- Intent-based retrieval profiles.
- Calibrated weighted/RRF routing.
- Optional batch cross-encoder reranker.
- Stable evidence-level deduplication.

Tests:

- Per-intent offline comparison.
- Reranker timeout and malformed-output fallback.
- Exact query behavior stays deterministic.
- Latency, cost, and diversity regression tests.

Exit condition: macro task success beats the static weighted baseline.

### Phase 4 — Context packing and compression

Deliver:

- Token-aware context packer.
- Strong-first/corroboration-last ordering.
- Conflict groups and relevant-region extraction.
- Position-sensitivity benchmark.

Tests:

- First/middle/last evidence permutations.
- Multi-document chronology and neighbor ordering.
- Citation identities remain stable after compression.
- Prompt-injection delimiters cannot be closed by source content.

Exit condition: lower position gap and equal-or-better grounded accuracy at no higher token budget.

### Phase 5 — Bounded agentic retrieval

Deliver:

- Complexity and missing-evidence detector.
- Up to two iterative targeted search rounds.
- Reason-in-Documents evidence-note schema.
- Complete planner/executor/decision trace.

Tests:

- Multi-hop source coverage and answer correctness.
- Hard loop/deadline/token limits.
- Partial tool failure and timeout behavior.
- Planner cannot set organization, project, user, or grants.
- All claims cite original evidence.

Exit condition: complex-task gains justify added cost; simple tasks remain on the direct path.

### Phase 6 — MCP progressive discovery and sandboxed composition

Deliver:

- `search_tools` and on-demand schemas.
- Typed read-only wrappers.
- Sandboxed data-reduction prototype.
- Audit and policy enforcement.

Tests:

- Sandbox escape, fork bomb, memory, CPU, output, filesystem, and network tests.
- Secret exfiltration and prompt-injection tests.
- Authorization remains server-derived.
- Citation identity survives joins/aggregation.

Exit condition: security review passes and context/token use decreases on multi-tool tasks.

### Phase 7 — Slack and connector scale hardening

Deliver:

- Durable queue/backpressure and tenant quotas.
- Derivative lineage/invalidation graph.
- Partitioned receipts/audits and retention jobs.
- Lag, replay, dead-letter, and revocation dashboards.

Tests:

- Replay, out-of-order, duplicate, edit, delete, and visibility-change events.
- Burst and soak tests.
- Tenant fairness tests.
- Disaster recovery replay from durable cursor/event state.

Exit condition: connector and revocation SLOs hold under peak load.

### Phase 8 — Learned code retrieval

Deliver:

- Tree-sitter code graph pilot.
- Code Context Bench.
- Privacy-safe accepted-session trace pipeline.
- Domain retriever experiment only after enough labels exist.

Tests:

- Exact symbol/path and semantic behavior queries.
- Cross-language parsing fallback.
- Old-commit, denied-path, and duplicate-symbol negatives.
- Large-repository task success and latency.

Exit condition: learned retrieval beats strong hybrid search on held-out repositories and respects
data-use policy.

## 9. Enterprise features enabled by this roadmap

### Incident evidence graph

Build a cited timeline from incident Jira tickets, Slack threads, runbooks, affected code, recent
PRs, owners, and source timestamps. Show conflicts and missing evidence explicitly.

### Decision memory

Identify a decision, its alternatives, approvers, implementation tickets, code changes, and later
reversals. Invalidate derived decision summaries when source messages or documents are deleted.

### Change impact search

Given a service, flag, or symbol, retrieve code references, CODEOWNERS, recent PRs, runbooks,
incidents, and dependent Jira work without losing exact identifiers.

### Compliance answer mode

Use high-recall HNSW, authoritative-source boosts, strict project/grant filtering, immutable audit
events, and claim-complete citations. Refuse if evidence is missing or contradictory.

### Knowledge health center

Measure stale sources, orphaned documents, low-recall queries, frequently corrected answers,
uncited claims, connector lag, embedding/version drift, and ACL invalidation health.

### Expert finder with evidence

Rank experts from CODEOWNERS, code contributions, Jira ownership, Confluence authorship, and Slack
participation. Explain each recommendation with permission-safe evidence and do not expose private
activity.

## 10. What not to do

- Do not replace PostgreSQL/pgvector before measuring a concrete scale or reliability failure.
- Do not enable RRF, model reranking, or agentic retrieval globally from external benchmark claims.
- Do not embed every raw Slack message without thread normalization, deduplication, ACLs, and
  deletion propagation.
- Do not send generated contextual summaries to users as original citations.
- Do not use long context as a substitute for retrieval and context selection.
- Do not expose a general-purpose shell or raw credentials through MCP.
- Do not let a planner or model choose authorization scope.
- Do not train a custom retriever on customer code or conversations without explicit policy and
  tenant isolation.
- Do not optimize only answer fluency; retrieval recall, citation quality, revocation, latency, and
  cost are product requirements.

## 11. Final recommendation

For the next production milestone, implement only Phases 0 through 3:

1. retrieval/ACL evaluation;
2. filtered-HNSW tuning;
3. contextual chunk enrichment;
4. query-adaptive fusion and bounded reranking.

Those phases improve the evidence entering the model while preserving the current architecture and
security boundaries. Context packing should follow immediately. Agentic retrieval, code-executing
MCP, and learned code embeddings should remain opt-in research tracks until their security, cost,
and evaluation gates are demonstrably satisfied.

## 12. References

1. Malkov, Yu. A., and Yashunin, D. A. [Efficient and Robust Approximate Nearest Neighbor Search
   Using Hierarchical Navigable Small World Graphs](https://arxiv.org/abs/1603.09320), arXiv v4,
   2018; later published in IEEE TPAMI.
2. Anthropic. [Introducing Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval),
   2024.
3. Cormack, Gordon V., Clarke, Charles L. A., and Büttcher, Stefan. [Reciprocal Rank Fusion
   Outperforms Condorcet and Individual Rank Learning
   Methods](https://research.google/pubs/reciprocal-rank-fusion-outperforms-condorcet-and-individual-rank-learning-methods/), SIGIR 2009.
4. Li, Xiaoxi, et al. [Search-o1: Agentic Search-Enhanced Large Reasoning
   Models](https://arxiv.org/abs/2501.05366), 2025.
5. Anthropic. [Code Execution with MCP: Building More Efficient
   Agents](https://www.anthropic.com/engineering/code-execution-with-mcp), 2025.
6. Liu, Nelson F., et al. [Lost in the Middle: How Language Models Use Long
   Contexts](https://arxiv.org/abs/2307.03172), 2023; TACL 2024.
7. Anthropic. [Prompting Best
   Practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices).
8. Salesforce Engineering. [How Slack AI Processes Billions of Messages to Reduce Information
   Overload](https://engineering.salesforce.com/how-slack-ai-processes-billions-of-messages-to-reduce-information-overload-with-ai-powered-search-and-summarization/),
   2025.
9. Slack Engineering. [How We Built Slack AI to Be Secure and
   Private](https://slack.engineering/how-we-built-slack-ai-to-be-secure-and-private/), updated 2025.
10. Improving Agents. [Which Nested Data Format Do LLMs Understand
    Best?](https://www.improvingagents.com/blog/best-nested-data-format), 2025.
11. Cursor. [Improving Agent with Semantic Search](https://cursor.com/blog/semsearch), 2025.
12. pgvector. [HNSW Index and Query Options](https://github.com/pgvector/pgvector#hnsw).
