from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass(slots=True)
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(slots=True)
class LLMDelta:
    """One streamed event: a text delta, and on the final event, usage totals."""

    text: str = ""
    usage: LLMUsage | None = None
    done: bool = False


@dataclass(slots=True)
class LLMRequest:
    system: str
    messages: list[ChatMessage] = field(default_factory=list)
    max_tokens: int = 1024
    temperature: float = 0.2


class LLMProvider(Protocol):
    name: str
    model: str

    def stream(self, request: LLMRequest) -> AsyncIterator[LLMDelta]:
        """Stream completion deltas; final delta has done=True and usage set."""
        ...
