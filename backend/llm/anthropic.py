import json
from collections.abc import AsyncIterator

import httpx

from core.exceptions import ProviderError
from llm.base import LLMDelta, LLMRequest, LLMUsage


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, *, model: str, api_key: str, timeout: float = 120.0) -> None:
        self.model = model
        self._headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        self._timeout = timeout

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMDelta]:
        payload = {
            "model": self.model,
            "stream": True,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "system": request.system,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
        }
        usage = LLMUsage()
        try:
            async with (
                httpx.AsyncClient(timeout=self._timeout) as client,
                client.stream(
                    "POST",
                    "https://api.anthropic.com/v1/messages",
                    headers=self._headers,
                    json=payload,
                ) as resp,
            ):
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode(errors="replace")[:500]
                    raise ProviderError(f"Anthropic HTTP {resp.status_code}: {body}")
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    match event.get("type"):
                        case "message_start":
                            usage.input_tokens = event["message"]["usage"].get("input_tokens", 0)
                        case "content_block_delta":
                            if text := event["delta"].get("text"):
                                yield LLMDelta(text=text)
                        case "message_delta":
                            usage.output_tokens = event["usage"].get("output_tokens", 0)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Anthropic failed: {exc}") from exc
        yield LLMDelta(done=True, usage=usage)
