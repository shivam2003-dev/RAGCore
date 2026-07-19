# Slack Knowledge Connector

The Slack connector is read-only and deny-by-default. It indexes complete threads from explicitly
allowlisted public channels into project-scoped knowledge bases. It does not request or use message,
channel, or workspace mutation APIs.

## Safety boundary

- Only public channel IDs (`C...`) are accepted by configuration and event processing.
- Direct messages, group DMs, and private channels are rejected even if an event reaches the worker.
- Every channel is mapped to one Project and gets its own knowledge base. Project membership and the
  normal source ACL intersection are enforced before retrieval.
- Tokens remain server-side environment values. Status/configuration APIs expose booleans and
  non-secret channel mappings, never token values.
- Slack messages are treated as untrusted evidence and cannot select tools or alter permissions.
- Tests use fixtures and never connect to Slack or send a Slack message.

## Slack app setup

Use Socket Mode with an app-level token containing `connections:write`. For the bot token, grant
`channels:history` and subscribe only to `message.channels`. Add the app to each public channel that
will be allowlisted. `channels:read` is optional when operators already provide channel IDs; the
connector does not need it for the configured-channel path.

Do not grant `chat:write`, `groups:history`, `im:history`, or `mpim:history` for this connector.

Slack creates the WebSocket URL at runtime through `apps.connections.open`. Each envelope is
acknowledged with its `envelope_id` before database validation or background work. Slack's
`conversations.replies` pagination and `Retry-After` behavior are handled by the read-only client.

Primary Slack references:

- [Using Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/)
- [Public-channel message event](https://docs.slack.dev/reference/events/message.channels/)
- [`channels:history` scope](https://docs.slack.dev/reference/scopes/channels.history/)
- [`conversations.replies`](https://docs.slack.dev/reference/methods/conversations.replies/)
- [`chat.getPermalink`](https://docs.slack.dev/reference/methods/chat.getPermalink/)
- [Web API rate limits](https://docs.slack.dev/apis/web-api/rate-limits/)

## Environment

```dotenv
SLACK_APP_TOKEN=
SLACK_BOT_TOKEN=
SLACK_WORKSPACE_ID=
SLACK_DEFAULT_KB_NAME_PREFIX=Slack
SLACK_REQUEST_TIMEOUT_SECONDS=20
SLACK_API_MAX_RETRIES=3
SLACK_HISTORY_LIMIT=15
SLACK_BURST_MIN_MESSAGES=2
SLACK_BURST_RARE_TOKEN_THRESHOLD=2
SLACK_BURST_REACTION_THRESHOLD=2
SLACK_SUMMARY_MAX_CHARS=1800
```

Start the API normally, then run the dedicated Socket Mode worker in a separate process:

```bash
cd backend
.venv/bin/python scripts/run_slack_socket_mode.py
```

The worker reconnects when Slack requests a connection refresh. WebSocket ticket URLs and tokens are
not logged.

## Configure channel-to-project mappings

An organization admin sends only non-secret configuration:

```http
PUT /api/v1/slack/configuration
Content-Type: application/json

{
  "workspace_id": "T01234567",
  "channels": [
    {
      "channel_id": "C01234567",
      "channel_name": "sre-help",
      "project_id": "00000000-0000-0000-0000-000000000000",
      "visibility": "public"
    }
  ]
}
```

Replacing the allowlist disables removed mappings and removes those knowledge bases from their
former project scope. It does not delete indexed data; disabled content is no longer in an active
project retrieval scope.

Status and manual read-only refresh controls:

```text
GET  /api/v1/slack/status
POST /api/v1/slack/sync
```

The status includes connection state, allowlisted-channel count, last event/success/error times,
freshness lag, failure count, and sanitized error detail.

## Event and ingestion flow

1. A Socket Mode envelope is acknowledged immediately.
2. The worker rejects unsupported events and non-public/non-allowlisted channels.
3. A `(connector_state_id, event_id)` unique receipt suppresses Slack retries and duplicate delivery.
4. New messages, replies, edits, and deletes queue a refresh of the complete thread.
5. The thread is normalized into one versioned document containing question, summary, resolution,
   systems, code/config references, participants, channel, permalink, timestamps, selected
   high-signal bursts, and raw thread text.
6. Dense embeddings are based on the normalized thread context plus the local section; raw text
   remains in chunk content for Postgres full-text search.
7. A deleted root thread soft-deletes the local document and deactivates its chunks. Other deletions
   produce an updated version from Slack's currently visible full thread.

Reprocessing unchanged content is idempotent. A content hash avoids creating a new document version
or embedding job when the normalized thread has not changed.

## Verification

Fixture/contract coverage includes acknowledgement ordering, event deduplication, new/reply/edit
refreshes, idempotency, summary fallback, burst thresholds, deletion, allowlist and DM/private denial,
project mapping, ACL isolation, rate-limit retry, and citation/source metadata.

The real smoke gate is intentionally pending until a dedicated test workspace/channel and
least-privilege tokens are supplied. The smoke test must not send messages; an operator can create,
reply to, and edit the fixture thread manually while the connector only reads it.
