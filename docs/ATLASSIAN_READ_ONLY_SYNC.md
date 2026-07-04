# Atlassian Read-Only Sync

## Safety Contract

The Confluence and Jira integrations are read-only. They use Atlassian GET endpoints and never edit production Confluence pages, Jira boards, or Jira issues.

Synced content is written only into the local Kimbal database for indexing and retrieval.

## Configuration

Set these backend environment variables in `backend/.env` or the production secret store:

```bash
CONFLUENCE_BASE_URL=https://your-domain.atlassian.net/wiki/spaces/SPACE/overview
CONFLUENCE_SPACE_KEY=SPACE
CONFLUENCE_EMAIL=person@example.com
CONFLUENCE_API_TOKEN=...

JIRA_BASE_URL=https://your-domain.atlassian.net/jira/software/c/projects/KEY/boards/123
JIRA_PROJECT_KEY=KEY
JIRA_BOARD_ID=123
JIRA_EMAIL=person@example.com
JIRA_API_TOKEN=...
```

For Atlassian Cloud API tokens, Basic auth requires the Atlassian account email plus token. Jira can reuse the Confluence email/token when Jira-specific credentials are blank.

Never commit real tokens.

## Confluence Flow

Implementation: `backend/services/confluence_service.py`

The sync flow:

1. Resolve the configured space by key.
2. Page through current pages with `body-format=storage`.
3. Convert each page into a local HTML document.
4. Upsert by `confluence_page_id`.
5. Skip unchanged ready/processing pages.
6. Queue background ingestion for changed pages.
7. Record an audit entry.

Default KB name: `Confluence DevOps1`

## Jira Flow

Implementation: `backend/services/jira_service.py`

The sync flow:

1. Read the configured board.
2. Page through board issues.
3. Render each issue as Markdown.
4. Upsert by `jira_issue_id`.
5. Include issue fields used by search and assignment questions:
   - issue key
   - status
   - status category
   - priority
   - assignee display name
   - assignee email when Atlassian returns it
   - assignee account id
   - reporter details
   - project and board metadata
6. Queue background ingestion for changed issues.
7. Record an audit entry.

Default KB name: `Jira DEVO`

## API Endpoints

```text
GET  /api/v1/confluence/status
POST /api/v1/confluence/sync

GET  /api/v1/jira/status
POST /api/v1/jira/sync
```

Sync endpoints require editor or admin role.

Status endpoints return configuration state without exposing tokens.

## Resync Guidance

Run a resync after changing connector code, metadata fields, or environment variables. Existing documents are skipped only when their rendered source hash is unchanged.

For Jira assignment questions, resync Jira after deploying code that adds assignee email/account-id indexing.
