"""Compare weighted and RRF retrieval on the local authorized golden scope.

This script is read-only. It refuses external embedding-provider calls unless
the operator explicitly passes ``--allow-provider-calls``.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from sqlalchemy import select

from api.routes.evals import _run_offline_gate
from core.config import get_settings
from database.session import SessionFactory, engine
from embeddings.factory import build_embedding_provider
from models import Role, User
from repositories.chunks import ChunkSearchRepository
from retrieval.pipeline import RetrievalPipeline


async def run(*, experimental_signals: bool, allow_provider_calls: bool) -> int:
    settings = get_settings()
    if settings.embedding_provider != "fake" and not allow_provider_calls:
        raise SystemExit(
            "Refusing external embedding-provider calls. Re-run with "
            "--allow-provider-calls only after confirming cost and data policy."
        )
    embedder = build_embedding_provider(settings)
    summaries: list[dict[str, object]] = []
    try:
        async with SessionFactory() as db:
            user = await db.scalar(
                select(User)
                .where(
                    User.is_active.is_(True),
                    User.role == Role.ADMIN,
                    User.email == settings.auth_super_admin_email.strip().lower(),
                )
                .order_by(User.created_at)
            )
            if user is None:
                user = await db.scalar(
                    select(User)
                    .where(User.is_active.is_(True), User.role == Role.ADMIN)
                    .order_by(User.created_at.desc())
                )
            if user is None:
                raise SystemExit("No active local admin user is available for the comparison.")
            for fusion_mode in ("weighted", "rrf"):
                variant = settings.model_copy(
                    update={
                        "retrieval_fusion_mode": fusion_mode,
                        "retrieval_exact_identifier_enabled": experimental_signals,
                        "retrieval_rare_token_enabled": experimental_signals,
                        "retrieval_model_reranker_enabled": False,
                        "retrieval_neighbor_expansion_enabled": False,
                        "retrieval_recency_decay_enabled": False,
                    }
                )
                pipeline = RetrievalPipeline(
                    search_repo=ChunkSearchRepository(db),
                    embedder=embedder,
                    settings=variant,
                )
                result = await _run_offline_gate(user=user, db=db, retrieval=pipeline)
                metrics = {
                    metric.id: metric.value
                    for metric in result.metrics
                    if metric.id
                    in {
                        "source_recall",
                        "context_precision",
                        "top_k_hit_rate",
                        "mrr",
                        "p95_latency_ms",
                    }
                }
                summaries.append(
                    {
                        "fusion_mode": fusion_mode,
                        "experimental_signals": experimental_signals,
                        "passed": result.passed,
                        "score": result.score,
                        "cases": result.cases,
                        "metrics": metrics,
                    }
                )
    finally:
        await engine.dispose()
    print(json.dumps({"comparisons": summaries}, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experimental-signals", action="store_true")
    parser.add_argument("--allow-provider-calls", action="store_true")
    args = parser.parse_args()
    return asyncio.run(
        run(
            experimental_signals=args.experimental_signals,
            allow_provider_calls=args.allow_provider_calls,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
