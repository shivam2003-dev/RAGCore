# Evals

Kimbal exposes a live eval dashboard at `/evals` backed by `GET /api/v1/evals/overview`.

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

- Citation coverage: share of assistant answers with at least one source citation.
- Groundedness proxy: citation presence, rendered citation-marker coverage, and mean retrieved chunk confidence.
- Answer relevance proxy: lexical overlap between the user question and answer text.
- Retrieval confidence: mean cited chunk score.
- Completeness proxy: non-empty answer length signal.
- Streaming success: persisted assistant answers without terminal error text.
- Helpful feedback: user feedback ratio.
- Latency: average, p50, and p95 over recent persisted answers.
- Model breakdown: answer count, average latency, citation coverage, and groundedness by model.

These are production health signals, not a formal benchmark score.

## Why These Evals

Current RAG evaluation practice separates retrieval quality from answer generation quality. Ragas documents RAG metrics such as context precision, context recall, response relevancy, faithfulness, and response groundedness. DeepEval also frames RAG testing around retriever and generator metrics such as answer relevancy and faithfulness. OpenAI's eval guidance emphasizes using evals to understand application behavior and model changes.

Kimbal maps those ideas to the telemetry already available in this app:

- Faithfulness / groundedness becomes a citation and chunk-score proxy.
- Answer relevancy becomes a deterministic question-answer overlap proxy.
- Retriever quality becomes retrieval confidence from cited chunk scores.
- Production performance becomes latency and feedback.

## Future Golden-Set Evals

For release gates, add a separate eval harness with:

1. A golden dataset of representative questions, expected answer traits, and expected source documents.
2. A retriever eval that checks whether expected chunks are returned.
3. A generator eval that uses deterministic rules plus an optional LLM judge.
4. CI thresholds for citation coverage, faithfulness, answer relevance, and latency.
5. Dataset versioning so score changes are explainable across model or prompt updates.

Recommended future env variables if LLM-as-judge evals are added:

```bash
# Optional future offline eval judge. Not used by the current live dashboard.
EVALS_JUDGE_PROVIDER=openrouter
EVALS_JUDGE_MODEL=openai/gpt-4.1-mini
EVALS_JUDGE_API_KEY=
EVALS_GOLDEN_DATASET_PATH=evals/golden/rag.jsonl
```

Do not reuse production Atlassian or user data in a public eval dataset.
