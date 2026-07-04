from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
RAG_STAGE_LATENCY = Histogram(
    "rag_stage_duration_seconds",
    "RAG pipeline stage latency",
    ["stage"],  # embedding | retrieval | llm
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
LLM_TOKENS = Counter("llm_tokens_total", "LLM tokens", ["direction"])  # input | output
CACHE_HITS = Counter("cache_hits_total", "Cache hits", ["cache"])
CACHE_MISSES = Counter("cache_misses_total", "Cache misses", ["cache"])
INGESTED_DOCUMENTS = Counter(
    "ingested_documents_total", "Documents ingested", ["status"]  # ready | failed
)
