# CVUM read-only MCP evidence server

CVUM exposes the same seven primitive retrieval tools through authenticated REST and a local MCP stdio bridge:

- `search_knowledge`
- `search_jira`
- `search_confluence`
- `search_slack`
- `search_code`
- `recent_prs`
- `who_knows`

Each call requires an explicit `project_id`. The API resolves the caller from an API key, checks active project membership, filters project sources, and applies restricted-source grants before retrieval. MCP never opens the database and cannot widen the API result. It contains no answer generation and advertises every tool as read-only, non-destructive, and idempotent.

## Local configuration

Create a CVUM API key in the product, then expose it only to the MCP process. Do not put the key in this repository.

```json
{
  "mcpServers": {
    "cvum-evidence": {
      "command": "/absolute/path/to/RAGCore/backend/.venv/bin/python",
      "args": ["/absolute/path/to/RAGCore/backend/scripts/run_mcp_server.py"],
      "env": {
        "CVUM_API_BASE_URL": "http://127.0.0.1:8000",
        "CVUM_API_KEY": "set-in-your-local-secret-store"
      }
    }
  }
}
```

For a local `AUTH_DISABLED=true` server, omit `CVUM_API_KEY`. Never use that mode on a shared or production host.

## Protocol surface

The stdio server implements `initialize`, `ping`, `tools/list`, `tools/call`, and `notifications/initialized`. Input schemas reject unknown fields and bound query length, result count, tool count, time per tool, and the overall planner deadline. Authorization errors are returned as MCP errors; they are never converted into empty evidence because that would hide a permission failure.

The web Ask path uses the planner only when `KNOWLEDGE_PLANNER_ENABLED=true`. Model-based tool selection is a second opt-in through `KNOWLEDGE_PLANNER_MODEL_ENABLED=true`; invalid or unavailable model output falls back to deterministic routing. Retrieved evidence still flows through CVUM's existing citation, grounding, and weak-evidence refusal controls.
