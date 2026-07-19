# RAG Pipeline

## Ingestion

Documents enter the system from manual uploads or read-only source syncs.

1. The API validates the upload or connector payload.
2. `DocumentService` creates or updates a `Document` and `DocumentVersion`.
3. The ingestion queue processes the document in the background.
4. Chunkers split content into bounded chunks with metadata.
5. The embedding provider embeds chunk text.
6. Chunks are stored in Postgres with pgvector embeddings and a generated full-text `tsv` column.

Manual uploads go into `CVUM Local Uploads`. Confluence and Jira write into dedicated source knowledge bases.
Each allowlisted Slack public channel writes into its own project-mapped knowledge base so channel
scope is enforced before retrieval.

## Chunking

Chunking is implemented under `backend/ingestion/chunkers`. The system keeps chunk size and overlap configurable through backend settings:

- `CHUNK_SIZE_TOKENS`
- `CHUNK_OVERLAP_TOKENS`

Source profiles are intentionally different:

- Confluence uses `400/60` heading-aware chunks with parent-section context
  (`confluence-heading-context-v2`). A larger `600/80` ablation reduced recall and MRR on the
  local golden set, so it is not the default.
- Jira uses `320/40` relationship-aware chunks
  (`jira-relationship-comments-attachments-v5`). Descriptions, visible comments, parent/child and
  issue-link metadata, and extracted XLSX/DOCX/PDF/image evidence are kept with the issue title and
  key in every chunk.

Jira preprocessing removes empty/automation boilerplate but preserves headings, tables, lists,
code, user-visible mentions, and comments. Attachment extraction is size/count bounded and the
connector remains read-only.

Slack stores one normalized, versioned document per thread. The document preserves the searchable
question, summary, resolution, systems, code/config references, participants, permalink, timestamps,
selected high-signal message bursts, and raw thread text. Embedding input includes the normalized
thread context; raw text remains available to Postgres full-text retrieval.

GitHub stores one versioned document per allowed repository path. Unchanged blob SHAs are neither
downloaded nor re-embedded. Code chunks preserve repository, branch, path, language, symbol,
CODEOWNERS, contributors, blob/commit SHAs, and a commit-pinned citation URL. Exact code search is a
parameterized literal database query; semantic code search uses the normal authorized hybrid path.

## Retrieval

The retrieval pipeline is in `backend/retrieval/pipeline.py`.

For a query, the pipeline:

1. Optionally rewrites the query.
2. Embeds the effective query.
3. Runs dense vector search over pgvector.
4. Runs strict and relaxed sparse search through Postgres full-text search, with normalized content
   ranking, document-title boosts, and exact Jira-key boosts.
5. Optionally runs explicit exact-identifier and document-frequency-weighted rare-token arms.
6. Fuses candidates with either the existing weighted strategy or configurable weighted Reciprocal
   Rank Fusion (RRF). Each candidate retains the contributing arms, native arm scores, and arm ranks.
7. Optionally applies a floor-bounded, source-specific recency multiplier when a valid source update
   timestamp exists. Missing dates are not penalized.
8. Reranks a bounded candidate set against the original user intent. Heuristic reranking is always
   available; the optional model reranker has a timeout and falls back on any provider or output error.
9. Selects the final diverse context and only then optionally inserts adjacent chunks from the same
   active document version, within a separate context token budget.
10. Evaluates evidence quality and source coverage and applies the corrective retrieval policy loop.

An exact Jira key also activates relationship retrieval. Indexed metadata expands the issue to
parent, child, and linked tickets. Ask then performs a read-only live Jira refresh for that issue
family so comments and supported attachments are current even when the routine board refresh has
not reached an older epic. Live text is mapped to persisted Jira document/chunk ids before citation
storage.

Default fusion weights:

- Dense: `0.7`
- Sparse: `0.3`

The request-scoped SQLAlchemy session is deliberately used sequentially. Retrieval arms do not run
concurrent statements through the same `AsyncSession`.

### Retrieval experiment flags

The conservative production defaults preserve weighted fusion, heuristic reranking, and no extra
arms or expansion. The experimental path is controlled with:

- `RETRIEVAL_FUSION_MODE=weighted|rrf`
- `RETRIEVAL_RRF_SMOOTHING_K`
- `RETRIEVAL_EXACT_IDENTIFIER_ENABLED` and `RETRIEVAL_EXACT_IDENTIFIER_WEIGHT`
- `RETRIEVAL_RARE_TOKEN_ENABLED` and `RETRIEVAL_RARE_TOKEN_WEIGHT`
- `RETRIEVAL_RECENCY_DECAY_ENABLED`, `RETRIEVAL_RECENCY_HALF_LIVES`, and
  `RETRIEVAL_RECENCY_FLOOR`
- `RETRIEVAL_MODEL_RERANKER_ENABLED`, `RETRIEVAL_MODEL_RERANKER_TIMEOUT_SECONDS`, and
  `RETRIEVAL_MODEL_RERANKER_CANDIDATE_K`
- `RETRIEVAL_NEIGHBOR_EXPANSION_ENABLED`, `RETRIEVAL_NEIGHBOR_WINDOW`,
  `RETRIEVAL_NEIGHBOR_TOKEN_BUDGET`, and `RETRIEVAL_NEIGHBOR_MAX_CHUNKS`

An administrator can inspect a content-free retrieval trace in the Ask source drawer. It reports
fusion/reranker mode, arm hit counts and latency, selected and discarded counts, selected chunk IDs,
contributing arms, and ranks. Non-admin responses omit the trace. The local 129-case weighted/RRF
comparison and default decision are recorded in `shivam_plan/retrieval_experiment.md`.

The CRAG path includes:

- `RetrievalEvaluator`
- `RetrievalPolicy`
- `QueryRewriter`
- `GroundingVerifier`

The pipeline keeps the strongest attempt across retries so a weaker rewrite cannot replace better
evidence found earlier.

## CRAG Status

This application ships a deterministic corrective retrieval grader and retry policy. It does not add
an LLM grading call to every request.

Implemented now:

- Dense plus sparse retrieval with weighted fusion.
- Retrieval quality grading from fused score, original-query overlap, source-family fit, exact
  identifier agreement, document diversity, and source coverage.
- Corrective query rewriting, top-k widening, a three-attempt hard stop, and weak-evidence fallback.
- Best-attempt retention across the corrective loop.
- Final answer citation validation and unsupported-claim gating.

Not implemented yet:

- Claim-level natural-language inference against each cited source.
- Automatic web fallback for Knowledge mode. Web evidence remains explicit through Web or Both mode.

The current CRAG implementation is provider-free and operational. It improves retrieval and blocks
weak internal answers, while the remaining model-based grader and claim-level verifier are future
quality layers rather than prerequisites for the corrective loop.

## Multi-KB Scope

The chat service can retrieve across more than one knowledge base. It chooses the scope from the question:

- Jira/board/issue/assignee questions prefer the Jira KB.
- Confluence/wiki/docs/runbook/setup questions prefer the Confluence KB.
- General questions search all non-seed knowledge bases.

This prevents a local sample or upload KB from hiding production-synced Jira and Confluence evidence.

## Prompting

The system prompt is built in `backend/chat/prompts.py`.

Retrieved chunks are wrapped in `<source>` tags. The model is instructed that source text is evidence only and never instructions. Answers must use bracket citations like `[1]`.

Ask can also include an `<assistant_role>` block for SRE, DevOps, Developer, HR, or a generated custom role. This role prompt is advisory only. It can shape persona and workflow, but source-grounding, RBAC, citation, secret handling, and prompt-injection rules stay higher priority.

## Streaming

The chat API streams Server-Sent Events:

1. `sources` - ranked retrieved chunks
2. `delta` - streamed model text
3. `done` - persisted message id, token usage, model, latency, and stage timings
4. `error` - terminal stream error if the model or backend fails mid-stream

The frontend maps source markers to the right-side source drawer on `/`.

## Optional Source Modes

Ask supports `knowledge`, `web`, and `blended` source modes.

- `knowledge` searches local synced Jira, Confluence, and uploaded-document chunks only.
- `web` stores configured provider snippets as local chunks before prompting.
- `blended` combines internal retrieval and web chunks in one cited answer.

The generated `Web Search` knowledge base is excluded from normal knowledge retrieval so stale internet snippets do not silently affect internal-only answers.

## Citations

After the answer is complete, citation extraction maps `[n]` markers back to retrieved chunks and persists rows in `citations`. The UI can then show answer text and source evidence consistently.

## Known Limitations

- Local deterministic embeddings carry lexical similarity rather than full semantic meaning. The
  pipeline compensates by weighting sparse/title retrieval more heavily in that mode; configure a
  production embedding provider for stronger semantic recall.
- Exact analytics questions over Jira, such as counts by assignee, are only as good as the synced Jira issue fields and the retrieved issue set.
- Historical trend charts are not fabricated; the UI only shows data that the backend collects.
- Live exact-key Jira expansion depends on the configured Jira account's issue/comment/attachment
  visibility. It never bypasses Atlassian permissions.
