# Kimbal Knowledge Hub Documentation

This folder is the source-safe operator and developer reference for the Kimbal Knowledge Hub application. It intentionally excludes provider keys, Atlassian tokens, database passwords, and any production-only secret material.

## Contents

- [Architecture](./ARCHITECTURE.md) - backend, frontend, storage, and deployment shape.
- [RAG Pipeline](./RAG_PIPELINE.md) - ingestion, chunking, retrieval, citations, and chat streaming.
- [Atlassian Read-Only Sync](./ATLASSIAN_READ_ONLY_SYNC.md) - Confluence and Jira connector behavior.
- [Web Search and Council Mode](./WEB_SEARCH_AND_COUNCIL.md) - optional internet retrieval and multi-model answer synthesis.
- [Discover](./DISCOVER.md) - live department feeds, alerts, research, and board pulse configuration.
- [Frontend Behavior](./FRONTEND_BEHAVIOR.md) - navigation, Ask, saved answers, settings, and live metrics.
- [Security and Secrets](./SECURITY_AND_SECRETS.md) - auth, RBAC, logging, uploads, and env handling.
- [Operations](./OPERATIONS.md) - local run, production env, Docker, Kubernetes, and observability.
- [Testing](./TESTING.md) - test commands, coverage expectations, and manual verification.

## Current Product Contract

Kimbal Knowledge Hub is an enterprise knowledge application backed by FastAPI, Postgres with pgvector, Redis, and a Next.js frontend. The primary user workflows are:

1. Sync read-only Confluence and Jira content into local knowledge bases.
2. Upload local documents into a separate local uploads knowledge base.
3. Ask grounded questions across synced knowledge, with streamed answers and citations.
4. Optionally blend answers with configured web search or use LLM Council mode when configured.
5. Inspect live metrics, documents, content health, feedback, and access control without fake dashboard numbers.

The Atlassian connectors only read from production systems. They write synced copies into the local Kimbal database for retrieval.
