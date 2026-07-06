"""Deterministic LLM for tests: answers by quoting the top sources with citation markers."""

import json
import re
from collections.abc import AsyncIterator

from llm.base import LLMDelta, LLMRequest, LLMUsage


class FakeLLM:
    name = "fake"
    model = "fake-llm"

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMDelta]:
        if "CVUM question rewriter" in request.system:
            latest = request.messages[-1].content if request.messages else ""
            history_text = " ".join(message.content for message in request.messages[:-1])
            if re.search(r"\b(it|that|this|those|they|them|same|previous|above)\b", latest, re.I):
                topic = " ".join(
                    re.findall(
                        r"\b(?:deploy|deployment|image|registry|harbor|jira|sre|cvir|confluence|runbook)\b",
                        history_text,
                        re.I,
                    )
                )
                answer = f"{latest} about {topic}".strip() if topic else latest
            else:
                answer = latest
            yield LLMDelta(text=answer)
            yield LLMDelta(done=True, usage=LLMUsage(input_tokens=60, output_tokens=len(answer) // 4))
            return

        if "CVUM role prompt generator" in request.system:
            payload = _json_from_message(request.messages[-1].content if request.messages else "")
            role_name = str(payload.get("name") or "Custom Specialist")[:80]
            goal = str(payload.get("goal") or "answer the user's workflow questions")
            source_focus = str(payload.get("source_focus") or "relevant synced sources")
            output_style = str(payload.get("output_style") or "concise, grounded answers")
            answer = json.dumps(
                {
                    "name": role_name,
                    "prompt": (
                        f"Act as {role_name} for CVUM. Primary focus: {goal}. "
                        f"Prefer these source areas when retrieval returns them: {source_focus}. "
                        f"Response style: {output_style}. Keep citations, RBAC, secret handling, "
                        "and source-grounding rules above this role."
                    ),
                }
            )
            yield LLMDelta(text=answer)
            yield LLMDelta(done=True, usage=LLMUsage(input_tokens=80, output_tokens=len(answer) // 4))
            return

        source_ids = re.findall(r'<source id="(\d+)"', request.system)
        question = request.messages[-1].content if request.messages else ""
        cites = "".join(f"[{sid}]" for sid in source_ids[:2]) or ""
        answer = f"Based on the provided sources{cites}, here is what I found about: {question[:80]}"
        for word in answer.split(" "):
            yield LLMDelta(text=word + " ")
        yield LLMDelta(done=True, usage=LLMUsage(input_tokens=100, output_tokens=len(answer) // 4))


def _json_from_message(message: str) -> dict[str, object]:
    start = message.find("{")
    end = message.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(message[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
