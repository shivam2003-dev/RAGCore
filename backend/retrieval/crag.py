"""CRAG extension points — protocols wired into the pipeline today, no-op
implementations shipped. A future CRAG module replaces these via the factory
without touching pipeline or service code.
"""

import enum
from typing import Protocol

from retrieval.context import RetrievalContext


class PolicyDecision(enum.StrEnum):
    ACCEPT = "accept"
    REWRITE = "rewrite"
    WIDEN_K = "widen_k"
    FALLBACK = "fallback"


class QueryRewriter(Protocol):
    async def rewrite(self, ctx: RetrievalContext) -> str | None:
        """Return a rewritten query, or None to keep the original."""
        ...


class RetrievalEvaluator(Protocol):
    async def evaluate(self, ctx: RetrievalContext) -> float:
        """Score retrieved-set quality in [0, 1]."""
        ...


class RetrievalPolicy(Protocol):
    def decide(self, ctx: RetrievalContext) -> PolicyDecision: ...


class GroundingVerifier(Protocol):
    async def verify(self, answer: str, ctx: RetrievalContext) -> bool:
        """Post-generation: is the answer supported by retrieved sources?"""
        ...


class NoopRewriter:
    async def rewrite(self, ctx: RetrievalContext) -> str | None:
        return None


class HeuristicEvaluator:
    """Cheap confidence proxy: top fused score. CRAG swaps in an LLM/classifier grader."""

    async def evaluate(self, ctx: RetrievalContext) -> float:
        return max((c.score for c in ctx.chunks), default=0.0)


class AlwaysAcceptPolicy:
    def decide(self, ctx: RetrievalContext) -> PolicyDecision:
        return PolicyDecision.ACCEPT


class NoopGroundingVerifier:
    async def verify(self, answer: str, ctx: RetrievalContext) -> bool:
        return True
