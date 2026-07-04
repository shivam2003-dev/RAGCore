# Discover

Discover is the department update surface for Kimbal Knowledge Hub. It keeps teams current with external articles, alerts, research, and an internal board pulse from indexed Jira, Confluence, uploads, and web snippets.

## User Experience

- Route: `/discover`
- API: `GET /api/v1/discover/feed?department=<id>`
- Departments: `for-you`, `devops`, `sre`, `development`, `security`, `hr`, `finance`, `product`
- Each department has a curated query used against the configured provider.
- Article titles and source links open the original external page.
- Board Pulse uses only local indexed documents and never fabricates counts.

## Provider Configuration

All runtime values live in environment variables. For local development, no key is required:

```bash
DISCOVER_ENABLED=true
DISCOVER_PROVIDER=google_news_rss
DISCOVER_API_KEY=
DISCOVER_BASE_URL=
DISCOVER_LOCALE=en-IN
DISCOVER_REGION=IN
DISCOVER_CACHE_TTL_SECONDS=900
DISCOVER_ITEMS_PER_DEPARTMENT=8
DISCOVER_DEPARTMENT_QUERIES=
```

Provider choices:

- `google_news_rss`: default no-key provider.
- `duckduckgo`: no-key HTML search fallback.
- `brave`: requires `DISCOVER_API_KEY`.
- `tavily`: requires `DISCOVER_API_KEY`.
- `searxng`: requires `DISCOVER_BASE_URL`.
- `fake`: offline tests and demos only.

Use `DISCOVER_BASE_URL` only when overriding the provider endpoint, for example a self-hosted SearXNG instance.

## Department Query Overrides

Use `DISCOVER_DEPARTMENT_QUERIES` to tune the organization feed without code changes:

```bash
DISCOVER_DEPARTMENT_QUERIES=security=cybersecurity zero day CVE exploit patch;devops=Kubernetes ArgoCD GitOps production incidents
```

Separate overrides with semicolons or new lines. Unknown department ids are ignored.

## Internal Board Pulse

The right rail is generated from local indexed documents:

- Jira documents are counted from `doc_metadata.source=jira`.
- Confluence documents are counted from `doc_metadata.source=confluence`.
- Web documents are counted from `doc_metadata.source=web`.
- Uploads are the remaining local document sources.

The latest indexed documents link back to their original Jira, Confluence, or web URL when metadata includes a source URL.

## Safety

Discover is read-only. It does not edit Jira, Confluence, external websites, or local source documents. External provider failures are returned as warnings while the internal board pulse still renders.
