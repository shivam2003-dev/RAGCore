# Security and Secrets

## Authentication

The backend implements:

- Argon2 password hashing
- Short-lived JWT access tokens
- Rotating one-time refresh tokens
- API keys with SHA-256 storage
- Role-based access control with admin, editor, and viewer roles

Sensitive actions are audit logged.

## Project and source authorization

A Project narrows relevance and never grants access. The backend intersects organization ownership,
restricted-source grants, Project source mappings, and request filters before retrieval. Project
membership alone cannot reveal a restricted source. Organization admins can configure restricted
sources but do not implicitly retrieve them without a grant.

The same repository enforces scope for Ask, direct search, exact identifiers, Jira relationships,
workflow APIs, REST evidence tools, MCP, citations, and authorization-aware cache keys. Cross-org
identifiers do not leak object existence. Source/membership/grant changes invalidate the relevant
authorization cache version.

## Upload Safety

Document uploads are validated before ingestion. Magic-byte checks reject files whose content does not match the expected type. Upload size is controlled by `UPLOAD_MAX_BYTES`.

## Prompt-Injection Defense

Retrieved source text is wrapped in `<source>` tags and the system prompt states that source text is evidence, not instructions. This prevents source documents from overriding system instructions.

Planner output is validated against a bounded schema and an already-authorized Project. Source text
cannot select tools, inject Project/source IDs, increase deadlines, or change permissions.

## Logging

Structured logs include request IDs and PII redaction. Low-level HTTP transport loggers are kept at warning level so model stream chunks and connector internals are not dumped during normal local runs.

## Secrets

Secrets belong in backend environment variables or a production secret manager:

- `APP_SECRET_KEY`
- `OPENROUTER_API_KEY`
- `OPENAI_API_KEY`
- `CONFLUENCE_API_TOKEN`
- `JIRA_API_TOKEN`
- database and Redis credentials
- `SLACK_APP_TOKEN` and `SLACK_BOT_TOKEN`
- `GITHUB_TOKEN`
- `CVUM_API_KEY` for an MCP client process

Do not commit `.env` files or pasted tokens. The repository should contain only `.env.example` placeholders.

## Connector Safety

Atlassian connectors use GET-only API calls. Production Confluence and Jira are never modified by CVUM sync jobs.

The Slack connector uses Socket Mode and GET-only Web API methods. It accepts only explicitly
allowlisted public channel IDs, rejects private channels and direct messages, and does not require
`chat:write`, `groups:history`, `im:history`, or `mpim:history`. Slack tokens remain environment or
secret-manager values and are never persisted in connector state.

The GitHub connector exposes GET-only REST operations and never runs repository code or shell search.
Repository, branch, and path policies deny dependency/vendor/generated/build, secret-like, binary,
and oversized files. GitHub credentials are server-side only, and code/PR retrieval uses the same
Project and source ACL intersection as Ask.

The evidence REST and MCP surfaces are read-only. MCP calls traverse the authenticated API instead
of opening the database, and authorization errors are not disguised as empty results.

## Frontend Settings Boundary

The Settings page separates local UI preferences from backend-managed runtime controls. Runtime controls such as auth TTLs, RAG weights, provider keys, and connector scopes are shown as server-managed instead of editable browser toggles.
