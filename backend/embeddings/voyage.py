from collections.abc import Sequence

import httpx

from core.exceptions import ProviderError


class VoyageEmbeddings:
    """Voyage AI — near-OpenAI wire format but distinct enough for its own adapter."""

    name = "voyage"

    def __init__(self, *, model: str, dimensions: int, api_key: str, timeout: float = 30.0) -> None:
        self.model = model
        self.dimensions = dimensions
        self._client = httpx.AsyncClient(
            base_url="https://api.voyageai.com/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            resp = await self._client.post(
                "/embeddings",
                json={"model": self.model, "input": list(texts), "input_type": "document"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Voyage embeddings failed: {exc}") from exc
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]
