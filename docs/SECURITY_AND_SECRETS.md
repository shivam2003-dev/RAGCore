# Security and Secrets

## Authentication

The backend implements:

- Argon2 password hashing
- Short-lived JWT access tokens
- Rotating one-time refresh tokens
- API keys with SHA-256 storage
- Role-based access control with admin, editor, and viewer roles

Sensitive actions are audit logged.

## Upload Safety

Document uploads are validated before ingestion. Magic-byte checks reject files whose content does not match the expected type. Upload size is controlled by `UPLOAD_MAX_BYTES`.

## Prompt-Injection Defense

Retrieved source text is wrapped in `<source>` tags and the system prompt states that source text is evidence, not instructions. This prevents source documents from overriding system instructions.

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

Do not commit `.env` files or pasted tokens. The repository should contain only `.env.example` placeholders.

## Connector Safety

Atlassian connectors use GET-only API calls. Production Confluence and Jira are never modified by CVUM sync jobs.

## Frontend Settings Boundary

The Settings page separates local UI preferences from backend-managed runtime controls. Runtime controls such as auth TTLs, RAG weights, provider keys, and connector scopes are shown as server-managed instead of editable browser toggles.
