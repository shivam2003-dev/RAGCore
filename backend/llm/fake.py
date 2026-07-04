"""Deterministic LLM for tests: answers by quoting the top sources with citation markers."""

import re
from collections.abc import AsyncIterator

from llm.base import LLMDelta, LLMRequest, LLMUsage


class FakeLLM:
    name = "fake"
    model = "fake-llm"

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMDelta]:
        source_ids = re.findall(r'<source id="(\d+)"', request.system)
        question = request.messages[-1].content if request.messages else ""
        cites = "".join(f"[{sid}]" for sid in source_ids[:2]) or ""
        answer = f"Based on the provided sources{cites}, here is what I found about: {question[:80]}"
        for word in answer.split(" "):
            yield LLMDelta(text=word + " ")
        yield LLMDelta(done=True, usage=LLMUsage(input_tokens=100, output_tokens=len(answer) // 4))
