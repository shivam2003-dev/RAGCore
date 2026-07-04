"""OpenAI-compatible chat completions with SSE streaming.

Serves OpenAI itself and OpenRouter (base_url swap). OpenRouter fronts
Anthropic/Google/Meta models behind the same wire format.
"""

import json
from collections.abc import AsyncIterator

import httpx

from core.exceptions import ProviderError
from llm.base import LLMDelta, LLMRequest, LLMUsage


class OpenAICompatLLM:
    def __init__(
        self,
        *,
        name: str,
        model: str,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120.0,
    ) -> None:
        self.name = name
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._timeout = timeout

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMDelta]:
        payload = {
            "model": self.model,
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [
                {"role": "system", "content": request.system},
                *({"role": m.role, "content": m.content} for m in request.messages),
            ],
        }
        usage = LLMUsage()
        try:
            async with (
                httpx.AsyncClient(timeout=self._timeout) as client,
                client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    headers=self._headers,
                    json=payload,
                ) as resp,
            ):
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode(errors="replace")[:500]
                    raise ProviderError(f"LLM {self.name} HTTP {resp.status_code}: {body}")
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    if u := event.get("usage"):
                        usage = LLMUsage(
                            input_tokens=u.get("prompt_tokens", 0),
                            output_tokens=u.get("completion_tokens", 0),
                        )
                    choices = event.get("choices") or []
                    if choices and (delta := choices[0].get("delta", {}).get("content")):
                        yield LLMDelta(text=delta)
        except httpx.HTTPError as exc:
            raise ProviderError(f"LLM {self.name} failed: {exc}") from exc
        yield LLMDelta(done=True, usage=usage)
