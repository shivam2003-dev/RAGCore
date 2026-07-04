"""Deterministic local embeddings for development and tests.

Hash-seeded pseudo-random unit vectors: identical text always maps to the same
vector, different texts are near-orthogonal, and shared-token bags add lexical
signal so similar sentences land measurably closer. No network, no keys.
"""

import hashlib
import math
import random
import re
from collections.abc import Sequence

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class FakeEmbeddings:
    name = "fake"

    def __init__(self, *, model: str = "fake-embed", dimensions: int = 1536) -> None:
        self.model = model
        self.dimensions = dimensions

    def _vector_for(self, seed: str, weight: float) -> list[float]:
        rng = random.Random(hashlib.sha256(seed.encode()).digest())  # noqa: S311 — non-crypto
        return [rng.gauss(0, 1) * weight for _ in range(self.dimensions)]

    def _embed_one(self, text: str) -> list[float]:
        acc = [0.0] * self.dimensions
        tokens = _TOKEN_RE.findall(text.lower())
        for token in set(tokens):
            for i, v in enumerate(self._vector_for(f"tok:{token}", 1.0)):
                acc[i] += v
        # small whole-text component keeps distinct texts from ever colliding
        for i, v in enumerate(self._vector_for(f"txt:{text}", 0.05)):
            acc[i] += v
        norm = math.sqrt(sum(v * v for v in acc)) or 1.0
        return [v / norm for v in acc]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]
