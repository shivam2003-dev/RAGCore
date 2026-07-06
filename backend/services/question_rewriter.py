from llm.base import ChatMessage, LLMProvider, LLMRequest
from models import Message


class QuestionRewriter:
    """Rewrites follow-up questions into standalone retrieval queries."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def rewrite(self, *, history: list[Message], question: str) -> str:
        cleaned = question.strip()
        if not cleaned or not history:
            return cleaned
        if _looks_standalone(cleaned):
            return cleaned

        messages = [
            *(ChatMessage(role=message.role, content=message.content[:1200]) for message in history[-8:]),
            ChatMessage(role="user", content=cleaned),
        ]
        request = LLMRequest(
            system=(
                "You are the Kimbal question rewriter. Rewrite the latest user message into one "
                "standalone retrieval question using the previous chat history for references. "
                "Return only the standalone question. If the latest message is already standalone, "
                "return it unchanged. Do not answer the question."
            ),
            messages=messages,
            max_tokens=220,
            temperature=0.0,
        )
        rewritten = await _collect_text(self._llm, request)
        rewritten = _clean_rewrite(rewritten)
        return rewritten or cleaned


async def _collect_text(llm: LLMProvider, request: LLMRequest) -> str:
    parts: list[str] = []
    async for delta in llm.stream(request):
        if delta.text:
            parts.append(delta.text)
    return "".join(parts).strip()


def _looks_standalone(question: str) -> bool:
    normalized = question.lower()
    followup_terms = (
        "it",
        "that",
        "those",
        "they",
        "them",
        "this",
        "same",
        "above",
        "previous",
        "earlier",
        "there",
        "he",
        "she",
    )
    words = {part.strip(".,?!:;()[]{}\"'").lower() for part in normalized.split()}
    if words & set(followup_terms):
        return False
    return not (
        len(question.split()) <= 5 and any(term in normalized for term in ("why", "how", "what about", "and"))
    )


def _clean_rewrite(value: str) -> str:
    text = value.strip().strip("\"'")
    prefixes = ("standalone question:", "rewritten question:", "question:")
    lowered = text.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return text[len(prefix) :].strip()
    return text
