# Phase 2 Retrieval Experiment

Date: 2026-07-19

Branch: `agent/cerebras-knowledge-upgrade`

## Decision

Keep weighted fusion as the default. RRF remains available through
`RETRIEVAL_FUSION_MODE=rrf`.

The local indexed comparison showed a useful recall increase with RRF, but lower precision and MRR
and higher p95 latency. That mixed result does not justify changing the default without a larger
production-representative evaluation.

## Method

The read-only comparison used the existing authorized local index and the complete 129-case golden
dataset. Both modes ran through the same offline evaluation gate, user authorization scope, reranker,
and database. The embedding provider was the repository's deterministic fake provider, so no source
content was sent to an external embedding or language-model service.

Command:

```bash
cd backend
.venv/bin/python scripts/compare_retrieval_modes.py
```

## Results

| Metric | Weighted | RRF |
|---|---:|---:|
| Dataset cases | 129 | 129 |
| Gate passed | yes | yes |
| Gate score | 82 | 82 |
| Source recall | 0.8372 | 0.8643 |
| Context precision | 0.9298 | 0.9191 |
| Top-k hit rate | 0.9845 | 0.9845 |
| MRR | 0.9607 | 0.9566 |
| p95 latency | 1293 ms | 1473 ms |

Relative to weighted fusion, RRF increased source recall by 0.0271, reduced context precision by
0.0107, reduced MRR by 0.0041, kept top-k hit rate unchanged, and increased p95 latency by 180 ms.

## Safety and scope

- Weighted and RRF share the same server-calculated project and source authorization scope.
- Exact Jira-key, relationship, and structured count paths remain deterministic.
- Exact-identifier, rare-token, recency, model reranking, and neighbor expansion are independently
  configurable and disabled by default.
- Model reranking receives a bounded candidate set and falls back to heuristic ranking on timeout,
  invalid output, or provider failure.
- Neighbor expansion happens only after final ranking and retains persisted citation identities.
- Admin trace data contains identifiers, ranks, contributions, counts, and timings, never chunk text.

## Limitations and next evidence

The deterministic local embedding provider is useful for a repeatable regression comparison but is
not a substitute for an evaluation using the production embedding model and representative live
questions. Before enabling RRF or the model reranker by default, repeat this comparison against a
staging copy of the intended index and review per-source regressions, cost, and tail latency.
