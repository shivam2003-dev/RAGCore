from redis.asyncio import Redis

from core.config import Settings
from embeddings.base import EmbeddingProvider
from embeddings.fake import FakeEmbeddings
from embeddings.openai_compat import OpenAICompatEmbeddings
from embeddings.voyage import VoyageEmbeddings


def build_embedding_provider(settings: Settings, redis: Redis | None = None) -> EmbeddingProvider:
    provider: EmbeddingProvider
    match settings.embedding_provider:
        case "openai":
            provider = OpenAICompatEmbeddings(
                name="openai",
                model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
                api_key=settings.openai_api_key,
            )
        case "jina":
            provider = OpenAICompatEmbeddings(
                name="jina",
                model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
                api_key=settings.jina_api_key,
                base_url="https://api.jina.ai/v1",
            )
        case "tei":  # self-hosted BGE / sentence-transformers via Text-Embeddings-Inference
            provider = OpenAICompatEmbeddings(
                name="tei",
                model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
                api_key="unused",
                base_url=settings.embedding_base_url,
            )
        case "voyage":
            provider = VoyageEmbeddings(
                model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
                api_key=settings.voyage_api_key,
            )
        case "fake":
            provider = FakeEmbeddings(dimensions=settings.embedding_dimensions)
        case other:
            raise ValueError(f"Unknown embedding provider: {other}")

    if redis is not None:
        from embeddings.cache import CachedEmbeddings

        return CachedEmbeddings(provider, redis, settings.embedding_cache_ttl_seconds)
    return provider
