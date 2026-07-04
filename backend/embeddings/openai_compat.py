"""OpenAI-compatible embeddings client.

Covers OpenAI itself plus every server speaking the same wire format:
Jina (api.jina.ai/v1), HF Text-Embeddings-Inference serving BGE, LM Studio, vLLM.
One adapter instead of four — providers differ only in base_url + key.
"""

from collections.abc import Sequence

import httpx

from core.exceptions import ProviderError


class OpenAICompatEmbeddings:
    def __init__(
        self,
        *,
        name: str,
        model: str,
        dimensions: int,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
    ) -> None:
        self.name = name
        self.model = model
        self.dimensions = dimensions
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            resp = await self._client.post(
                "/embeddings", json={"model": self.model, "input": list(texts)}
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Embedding provider {self.name} failed: {exc}") from exc
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]
