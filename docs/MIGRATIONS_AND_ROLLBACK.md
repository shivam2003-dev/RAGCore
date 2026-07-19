# Database migrations and rollback

The current Alembic chain is:

| Revision | Change |
| --- | --- |
| `0001` | Initial application schema |
| `0002` | Message evaluation payload |
| `0003` | Projects, memberships, Project-source mapping, restricted-source grants, defaults/backfill |
| `0004` | Common connector state and allowlisted Slack thread ingestion |
| `0005` | GitHub repository mapping, incremental file state, and code-index metadata |

## Upgrade

1. Back up the database and record the deployed application image/revision.
2. Confirm `DATABASE_URL` points to the intended environment.
3. Stop or drain application writers.
4. Run from `backend/`:

   ```bash
   .venv/bin/alembic current
   .venv/bin/alembic upgrade head
   .venv/bin/alembic current
   ```

5. Start the new API and verify `/health/live`, `/health/ready`, project defaults, and connector status.

Migrations are additive through `0005`. They do not mutate Jira, Confluence, Slack, or GitHub.

## Disposable round-trip gate

The migration integration test refuses a database whose name lacks `migration` or `test`:

```bash
MIGRATION_TEST_DATABASE_URL=postgresql+asyncpg://.../ragcore_migration_test \
  .venv/bin/pytest -q tests/integration/test_project_migration.py
```

For the final chain, validate `upgrade head`, `downgrade base`, and `upgrade head` against a newly
created disposable database. Never point this command at a shared or production database.

## Rollback

Prefer an application rollback with the additive schema left in place. Disable optional behavior
first:

```dotenv
KNOWLEDGE_PLANNER_ENABLED=false
KNOWLEDGE_PLANNER_MODEL_ENABLED=false
RETRIEVAL_FUSION_MODE=weighted
RETRIEVAL_EXACT_IDENTIFIER_ENABLED=false
RETRIEVAL_RARE_TOKEN_ENABLED=false
RETRIEVAL_RECENCY_DECAY_ENABLED=false
RETRIEVAL_MODEL_RERANKER_ENABLED=false
RETRIEVAL_NEIGHBOR_EXPANSION_ENABLED=false
```

Disable Slack/GitHub mappings to stop new indexing while retaining auditable local data under the
same ACL rules.

Only run a schema downgrade after a backup and after confirming no deployed application version
depends on the removed tables/columns:

```bash
.venv/bin/alembic downgrade 0004  # remove GitHub schema
.venv/bin/alembic downgrade 0003  # remove Slack/common connector schema
.venv/bin/alembic downgrade 0002  # remove Project/ACL schema
```

Downgrade removes CVUM-owned connector/project schema. It does not delete or update source
systems. Restore the database backup if a downgrade is interrupted or application data validation
fails.
