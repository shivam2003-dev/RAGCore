# Evals

CVUM exposes a live eval dashboard at `/evals` backed by `GET /api/v1/evals/overview`.
Scripts can fetch only the headline score from `GET /api/v1/evals/benchmark`, which returns
the same `CVUM Benchmark` object shown in the UI, for example `50/100`.
The release-gate dataset inventory is exposed by `GET /api/v1/evals/golden` and loaded from
`evals/golden/rag.jsonl`. Offline release gates run through `GET /api/v1/evals/offline`.

The current implementation is intentionally deterministic and read-only. It does not invent scores, call a judge model, or require a new provider key. It computes quality and performance signals from data already persisted by the chat pipeline:

- user question
- assistant answer
- returned citations
- citation markers such as `[1]`
- retrieval chunk scores
- model name
- answer latency
- Helpful / Not Helpful feedback

## Metrics

The dashboard reports:

- CVUM Benchmark: a single `NN/100` live score for quick deployment checks.
- Citation coverage: share of assistant answers with at least one source citation.
- Groundedness proxy: citation presence, rendered citation-marker coverage, and mean retrieved chunk confidence.
- Answer relevance proxy: lexical overlap between the user question and answer text.
- Retrieval confidence: mean cited chunk score.
- Completeness proxy: non-empty answer length signal.
- Streaming success: persisted assistant answers without terminal error text.
- Helpful feedback: user feedback ratio.
- Latency: average, p50, and p95 over recent persisted answers.
- Model breakdown: answer count, average latency, citation coverage, and groundedness by model.

The CVUM Benchmark is deterministic and weighted from live persisted answer signals:

- groundedness: 30%
- citation coverage: 20%
- answer relevance: 20%
- retrieval confidence: 15%
- streaming success: 10%
- latency health: 5%

These are production health signals. The CVUM Benchmark is useful for repeatable operational checks after a deployment, but formal release gates use the golden-set offline gate below.

## Why These Evals

Current RAG evaluation practice separates retrieval quality from answer generation quality. Ragas documents RAG metrics such as context precision, context recall, response relevancy, faithfulness, and response groundedness. DeepEval also frames RAG testing around retriever and generator metrics such as answer relevancy and faithfulness. OpenAI's eval guidance emphasizes using evals to understand application behavior and model changes.

CVUM maps those ideas to the telemetry already available in this app:

- Faithfulness / groundedness becomes a citation and chunk-score proxy.
- Answer relevancy becomes a deterministic question-answer overlap proxy.
- Retriever quality becomes retrieval confidence from cited chunk scores.
- Production performance becomes latency and feedback.

## Golden-Set Release Gates

The first dataset slice lives at `evals/golden/rag.jsonl`. It covers SRE, DevOps,
Developer, HR, Jira analytics, follow-up questions, and blended web fallback cases.

The offline gate reports:

- Retriever metrics: expected source recall, context precision, top-k hit rate, MRR, and source freshness.
- Generator metrics: groundedness, faithfulness, citation coverage, answer relevance, refusal correctness, and unsupported-claim rate.
- Council comparison estimates: Fast vs Council quality, latency, cost units, and citation discipline.
- Role-space checks for SRE, DevOps, Developer, and HR categories.
- Dashboard drilldowns with failing examples, expected sources, returned sources, answer text, judge rationale, and a regression-trend slot.

Run local dataset validation:

```bash
cd backend
python scripts/run_evals.py
```

Run a live gate against a deployed API:

```bash
cd backend
python scripts/run_evals.py \
  --api-base http://localhost:8000/api/v1 \
  --token "$CVUM_EVALS_TOKEN"
```

Recommended future env variables if LLM-as-judge evals are added:

```bash
# Optional future offline eval judge. Not used by the current live dashboard.
EVALS_JUDGE_PROVIDER=openrouter
EVALS_JUDGE_MODEL=openai/gpt-4.1-mini
EVALS_JUDGE_API_KEY=
EVALS_GOLDEN_DATASET_PATH=evals/golden/rag.jsonl
```

Do not reuse production Atlassian or user data in a public eval dataset.
