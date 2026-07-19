# CVUM Knowledge Hub Documentation

This folder is the source-safe operator and developer reference for the CVUM Knowledge Hub application. It intentionally excludes provider keys, Atlassian tokens, database passwords, and any production-only secret material.

## Contents

- [Architecture](./ARCHITECTURE.md) - backend, frontend, storage, and deployment shape.
- [RAG Pipeline](./RAG_PIPELINE.md) - ingestion, chunking, retrieval, citations, and chat streaming.
- [Atlassian Read-Only Sync](./ATLASSIAN_READ_ONLY_SYNC.md) - Confluence and Jira connector behavior.
- [Slack Knowledge Connector](./SLACK_CONNECTOR.md) - allowlisted Socket Mode thread ingestion and safety boundaries.
- [GitHub Code Connector](./GITHUB_CONNECTOR.md) - read-only incremental code and pull-request intelligence.
- [Projects and Authorization](./PROJECTS_AND_AUTHORIZATION.md) - Project Lens onboarding and enforceable source ACLs.
- [Evidence-backed Workflows](./KNOWLEDGE_WORKFLOWS.md) - Incident Copilot, expert ranking, changes, and freshness.
- [Environment Variables](./ENVIRONMENT_VARIABLES.md) - runtime flags, connector credentials, and safe defaults.
- [Migrations and Rollback](./MIGRATIONS_AND_ROLLBACK.md) - revision map, disposable round trips, and rollback order.
- [MCP Evidence Tools](./MCP_TOOLS.md) - authenticated read-only REST/MCP primitives.
- [Web Search and Council Mode](./WEB_SEARCH_AND_COUNCIL.md) - optional internet retrieval and multi-model answer synthesis.
- [Discover](./DISCOVER.md) - live department feeds, alerts, research, and board pulse configuration.
- [Evals](./EVALS.md) - live RAG answer quality, citation, latency, model, and feedback metrics.
- [Frontend Behavior](./FRONTEND_BEHAVIOR.md) - navigation, Ask, saved answers, settings, and live metrics.
- [Security and Secrets](./SECURITY_AND_SECRETS.md) - auth, RBAC, logging, uploads, and env handling.
- [Operations](./OPERATIONS.md) - local run, production env, Docker, Kubernetes, and observability.
- [Testing](./TESTING.md) - test commands, coverage expectations, and manual verification.

## Current Product Contract

CVUM Knowledge Hub is an enterprise knowledge application backed by FastAPI, Postgres with pgvector, Redis, and a Next.js frontend. The primary user workflows are:

1. Organize authorized sources into Project lenses without treating relevance as permission.
2. Sync read-only Confluence, Jira, public allowlisted Slack, and allowlisted GitHub content into the
   normalized local document pipeline.
3. Ask grounded questions with streamed answers, authorization-aware retrieval, and openable citations.
4. Investigate incident keys, rank evidence-backed experts, review source changes, and monitor
   knowledge freshness.
5. Expose the same typed, read-only evidence primitives through REST and a local MCP bridge.
6. Optionally blend answers with configured web search or use LLM Council mode when configured.

The Atlassian connectors only read from production systems. They write synced copies into the local CVUM database for retrieval.
