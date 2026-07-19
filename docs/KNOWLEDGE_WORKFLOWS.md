# Evidence-backed knowledge workflows

The workflow APIs consume the same typed `Evidence` contract and authorization boundary as Ask.
Evidence carries source type/ID/URL, Project and permission context, snippet/content, retrieval arm,
rank/score, freshness, metadata, citation identity, and document/chunk identity.

## Incident Copilot

`POST /api/v1/workflows/incident` accepts an explicit Project and Jira/CVIR key. It attempts Jira,
public allowlisted Slack, Confluence, indexed code, and recent pull-request evidence. The response
separates:

- verified facts, current status, and owner;
- a timeline containing only evidence that explicitly references the incident key;
- immediate checks;
- likely next actions labeled as inference;
- missing source families and independent tool failures;
- the complete authorized evidence list with citations.

The service never manufactures incident events to fill a missing Slack, code, or PR history.

## Who Knows This?

`POST /api/v1/workflows/experts` ranks only people found in authorized metadata. Signals and default
weights are GitHub CODEOWNER (4), Jira assignee (3), public Slack participant (2), Confluence author
(2), GitHub contributor (1), and Jira reporter (1). Exact incident keys restrict ranking to evidence
that contains that key. Repeated signals are capped so a large number of weak matches cannot swamp
an exact owner. Results explain their score and retain source/citation identities.

Private Slack channels, DMs, and group DMs are never queried.

## What Changed?

`POST /api/v1/workflows/changes` accepts an inclusive date range of at most 366 days. It filters the
authorized Project inventory using source timestamps, deduplicates connector inventory identities,
and returns created/updated items with original source links and citations.

## Knowledge Freshness Center

`GET /api/v1/workflows/freshness?project_id=...` calculates live, Project-authorized inventory
health: stale sources, failures, old Slack resolutions, GitHub branch-index lag, replaced versions,
connector sync state, score, and remediation. Counts use the full inventory; only the 200
highest-priority findings are returned to keep the response and browser bounded.

## Feature and failure behavior

Ask uses planner/tool orchestration only when `KNOWLEDGE_PLANNER_ENABLED=true`. Model planning is a
separate opt-in. Workflow routes themselves remain deterministic and return partial results when a
source is missing or an independent tool times out. A connector failure never broadens scope or
falls back to unscoped retrieval.
