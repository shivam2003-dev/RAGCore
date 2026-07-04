# Frontend Behavior

## Navigation

Every sidebar item routes to a real page. Pages that do not have backend support must show an honest disabled or read-only state instead of fake data.

## Ask Kimbal

`/ask` opens as an empty chat when visited directly. It only starts generation when the user submits a question or arrives with an explicit `?q=` query parameter from Home search.

The Ask page:

- creates or reuses a conversation
- streams SSE events from the backend
- shows retrieved source chunks in the right rail
- renders simple markdown formatting
- posts Helpful and Not Helpful feedback to the backend
- stores Save locally in browser storage
- uses native share or clipboard for Share
- starts a clean conversation on New Chat

Ask no longer uploads or queries a sample runbook automatically.

## Live Metrics

Dashboard and analytics surfaces read `/api/v1/metrics/overview`. They do not show fabricated numbers or static time series. If historical data is not collected, the UI says so.

## Knowledge Sources

Confluence and Jira cards show live configuration status. Sync buttons call backend sync endpoints and remain disabled when the connector is not configured.

Manual local documents are managed through `/documents`.

## Documents

The Documents page lists documents from all knowledge bases, including Jira, Confluence, and local uploads. New manual uploads go to `Kimbal Local Uploads` so read-only connector KBs are not polluted.

## Saved Answers

Saved answers are stored in local browser storage. Search, share, and delete actions are functional. This is local user state, not a backend persistence feature.

## Settings

Settings intentionally split two categories:

- Editable local preferences: organization label, locale, theme, and accent color.
- Server-managed runtime settings: auth, SSO, RBAC, connector scopes, RAG weights, provider keys, audit export, rate limits, and cache TTL.

Server-managed rows are read-only so the UI does not pretend to change backend behavior that has no API.

## Access Control

Access Control lists real backend users and role counts. Role changes call the backend admin API. Invite and SSO actions are disabled because those endpoints are not implemented.
