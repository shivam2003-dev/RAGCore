# RAG Pipeline

## Ingestion

Documents enter the system from manual uploads or read-only source syncs.

1. The API validates the upload or connector payload.
2. `DocumentService` creates or updates a `Document` and `DocumentVersion`.
3. The ingestion queue processes the document in the background.
4. Chunkers split content into bounded chunks with metadata.
5. The embedding provider embeds chunk text.
6. Chunks are stored in Postgres with pgvector embeddings and a generated full-text `tsv` column.

Manual uploads go into `Kimbal Local Uploads`. Confluence and Jira write into dedicated source knowledge bases.

## Chunking

Chunking is implemented under `backend/ingestion/chunkers`. The system keeps chunk size and overlap configurable through backend settings:

- `CHUNK_SIZE_TOKENS`
- `CHUNK_OVERLAP_TOKENS`

Chunk metadata is preserved where available, including headings and source-specific metadata.

## Retrieval

The retrieval pipeline is in `backend/retrieval/pipeline.py`.

For a query, the pipeline:

1. Optionally rewrites the query.
2. Embeds the effective query.
3. Runs dense vector search over pgvector.
4. Runs sparse keyword search through Postgres full-text search.
5. Fuses results using max-normalized weighted fusion.
6. Evaluates confidence and applies the retrieval policy loop.

Default fusion weights:

- Dense: `0.7`
- Sparse: `0.3`

The CRAG seams already exist:

- `RetrievalEvaluator`
- `RetrievalPolicy`
- `QueryRewriter`

The current shipped policy accepts results, but the loop is in place for future retry/rewrite behavior.

## Multi-KB Scope

The chat service can retrieve across more than one knowledge base. It chooses the scope from the question:

- Jira/board/issue/assignee questions prefer the Jira KB.
- Confluence/wiki/docs/runbook/setup questions prefer the Confluence KB.
- General questions search all non-seed knowledge bases.

This prevents a local sample or upload KB from hiding production-synced Jira and Confluence evidence.

## Prompting

The system prompt is built in `backend/chat/prompts.py`.

Retrieved chunks are wrapped in `<source>` tags. The model is instructed that source text is evidence only and never instructions. Answers must use bracket citations like `[1]`.

## Streaming

The chat API streams Server-Sent Events:

1. `sources` - ranked retrieved chunks
2. `delta` - streamed model text
3. `done` - persisted message id, token usage, model, latency, and stage timings
4. `error` - terminal stream error if the model or backend fails mid-stream

The frontend maps source markers to the right rail in `/ask`.

## Optional Source Modes

Ask supports `knowledge`, `web`, and `blended` source modes.

- `knowledge` searches local synced Jira, Confluence, and uploaded-document chunks only.
- `web` stores configured provider snippets as local chunks before prompting.
- `blended` combines internal retrieval and web chunks in one cited answer.

The generated `Web Search` knowledge base is excluded from normal knowledge retrieval so stale internet snippets do not silently affect internal-only answers.

## Citations

After the answer is complete, citation extraction maps `[n]` markers back to retrieved chunks and persists rows in `citations`. The UI can then show answer text and source evidence consistently.

## Known Limitations

- Embeddings are deterministic local embeddings unless a production embedding provider is configured.
- Exact analytics questions over Jira, such as counts by assignee, are only as good as the synced Jira issue fields and the retrieved issue set.
- Historical trend charts are not fabricated; the UI only shows data that the backend collects.
