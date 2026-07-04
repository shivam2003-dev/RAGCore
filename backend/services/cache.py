"""Redis response cache + rate limiting. Cache-only Redis usage by design."""

import hashlib
import json
from typing import Any

from redis.asyncio import Redis

from core.metrics import CACHE_HITS, CACHE_MISSES


class ResponseCache:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def key_for(*parts: str) -> str:
        digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
        return f"resp:{digest}"

    async def get(self, key: str) -> Any | None:
        raw = await self._redis.get(key)
        if raw is None:
            CACHE_MISSES.labels(cache="response").inc()
            return None
        CACHE_HITS.labels(cache="response").inc()
        return json.loads(raw)

    async def set(self, key: str, value: Any) -> None:
        await self._redis.set(key, json.dumps(value), ex=self._ttl)


class RateLimiter:
    """Fixed one-minute window per subject. Coarse but predictable and one Redis op."""

    def __init__(self, redis: Redis, limit_per_minute: int) -> None:
        self._redis = redis
        self._limit = limit_per_minute

    async def allow(self, subject: str) -> bool:
        key = f"rl:{subject}"
        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60, nx=True)
        count, _ = await pipe.execute()
        return int(count) <= self._limit
