# Web Search and Council Mode

This document describes the optional Ask modes that extend normal internal RAG. They are disabled unless configured, so the UI must not imply live internet access or multi-model synthesis when provider credentials are absent.

## Source Modes

Ask supports three source modes:

- `knowledge`: the default. Searches local synced Jira, Confluence, and uploaded-document chunks only.
- `web`: calls the configured web-search provider, stores normalized snippets as local `Web Search` documents, embeds them, and cites those local chunks.
- `blended`: runs internal retrieval and web search, then sends the combined source list to the answer model.

Normal knowledge retrieval excludes the generated `Web Search` knowledge base. This prevents stale web snippets from silently affecting internal-only answers.

## Web Search Providers

Configure one provider:

```bash
WEB_SEARCH_PROVIDER=brave       # brave | tavily | searxng
WEB_SEARCH_API_KEY=             # required for brave and tavily
WEB_SEARCH_BASE_URL=            # optional for brave/tavily, required for searxng
WEB_SEARCH_DEFAULT_KB_NAME=Web Search
WEB_SEARCH_TOP_K=5
```

Provider notes:

- Brave uses the Web Search API endpoint with `X-Subscription-Token`.
- Tavily uses the `/search` endpoint with bearer auth.
- SearXNG uses a JSON-enabled `/search?q=...&format=json` instance.

The backend exposes `GET /api/v1/web-search/status` so the UI can disable Web and Both when search is not configured.

## LLM Council Mode

Fast mode streams one configured LLM answer. Council mode fans out to multiple OpenAI-compatible model ids, then asks a chair model to synthesize one final answer. Candidate answers are treated as advisory analysis only; source chunks remain the only evidence.

```bash
LLM_COUNCIL_ENABLED=true
LLM_COUNCIL_MODELS=model-a,model-b,model-c
LLM_COUNCIL_CHAIR_MODEL=model-a
LLM_COUNCIL_API_KEY=            # optional if OPENROUTER_API_KEY or OPENAI_API_KEY is set
LLM_COUNCIL_BASE_URL=https://openrouter.ai/api/v1
LLM_COUNCIL_MAX_MODELS=4
```

The UI reads `GET /api/v1/chat/capabilities`. Council remains disabled unless the backend reports that it has enabled models and an API key. This avoids fake council behavior in production.

## Citation Behavior

Web snippets become local `DocumentVersion` and `Chunk` rows before answer generation. That means answer markers such as `[1]` still map back to persisted chunk ids and remain compatible with existing citation storage.

## References

- GitHub LLM Council: https://github.com/karpathy/llm-council
- Brave Search API: https://api-dashboard.search.brave.com/api-reference/web/search/get
- Tavily Search API: https://docs.tavily.com/documentation/api-reference/endpoint/search
- SearXNG Search API: https://docs.searxng.org/dev/search_api.html
