from collections.abc import Sequence
from typing import Protocol


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of texts. Order-preserving. Raises ProviderError on failure."""
        ...
