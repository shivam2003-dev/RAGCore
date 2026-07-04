"""Redis-backed embedding cache wrapping any provider (decorator pattern)."""

import hashlib
import json
from collections.abc import Sequence

from redis.asyncio import Redis

from embeddings.base import EmbeddingProvider


class CachedEmbeddings:
    def __init__(self, inner: EmbeddingProvider, redis: Redis, ttl_seconds: int) -> None:
        self._inner = inner
        self._redis = redis
        self._ttl = ttl_seconds
        self.name = inner.name
        self.model = inner.model
        self.dimensions = inner.dimensions

    def _key(self, text: str) -> str:
        digest = hashlib.sha256(f"{self.name}:{self.model}:{text}".encode()).hexdigest()
        return f"emb:{digest}"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        keys = [self._key(t) for t in texts]
        cached = await self._redis.mget(keys)
        results: list[list[float] | None] = [
            json.loads(c) if c else None for c in cached
        ]
        missing_idx = [i for i, r in enumerate(results) if r is None]
        if missing_idx:
            fresh = await self._inner.embed([texts[i] for i in missing_idx])
            pipe = self._redis.pipeline()
            for i, vec in zip(missing_idx, fresh, strict=True):
                results[i] = vec
                pipe.set(keys[i], json.dumps(vec), ex=self._ttl)
            await pipe.execute()
        return results  # type: ignore[return-value]
