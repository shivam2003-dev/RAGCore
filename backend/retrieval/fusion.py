"""Weighted and reciprocal-rank fusion for retrieval arms.

Scores are max-normalized per arm before weighting: cosine similarity and
ts_rank_cd live on incomparable scales. Pure function — unit-testable without
a database.
"""

from repositories.chunks import SearchHit
from retrieval.context import RetrievedChunk


def fuse(
    dense: list[SearchHit],
    sparse: list[SearchHit],
    *,
    dense_weight: float,
    sparse_weight: float,
    top_k: int,
) -> list[RetrievedChunk]:
    return fuse_weighted(
        {"dense": dense, "sparse": sparse},
        weights={"dense": dense_weight, "sparse": sparse_weight},
        top_k=top_k,
    )


def fuse_weighted(
    arms: dict[str, list[SearchHit]],
    *,
    weights: dict[str, float],
    top_k: int,
) -> list[RetrievedChunk]:
    """Max-normalize each arm, then combine duplicate chunk identities."""

    merged: dict[object, RetrievedChunk] = {}
    for arm_name, hits in arms.items():
        unique_hits = _ranked_unique_hits(hits)
        arm_max = max((hit.score for hit, _rank in unique_hits), default=1.0) or 1.0
        for hit, rank in unique_hits:
            normalized_score = hit.score / arm_max
            chunk = merged.setdefault(hit.chunk_id, _chunk_from_hit(hit))
            chunk.retrieval_arms.append(arm_name)
            chunk.arm_ranks[arm_name] = rank
            chunk.arm_scores[arm_name] = normalized_score
            if arm_name == "dense":
                chunk.dense_score = normalized_score
            elif arm_name == "sparse":
                chunk.sparse_score = normalized_score

    for chunk in merged.values():
        chunk.score = sum(weights.get(arm_name, 0.0) * arm_score for arm_name, arm_score in chunk.arm_scores.items())
        chunk.fusion_score = chunk.score

    ranked = sorted(
        merged.values(),
        key=lambda chunk: (-chunk.score, str(chunk.chunk_id)),
    )
    return ranked[:top_k]


def reciprocal_rank_fusion(
    arms: dict[str, list[SearchHit]],
    *,
    weights: dict[str, float],
    smoothing_k: int,
    top_k: int,
) -> list[RetrievedChunk]:
    """Fuse ranked arms using weighted RRF with competition ranks for ties.

    ``raw_rrf = sum(weight / (smoothing_k + rank))``. The stored fused score
    is normalized by the best possible score so downstream quality heuristics
    continue to operate on a 0..1 range without changing RRF ordering.
    """

    if smoothing_k < 0:
        raise ValueError("RRF smoothing constant must be non-negative")

    merged: dict[object, RetrievedChunk] = {}
    raw_scores: dict[object, float] = {}
    for arm_name, hits in arms.items():
        unique_hits = _ranked_unique_hits(hits)
        arm_max = max((hit.score for hit, _rank in unique_hits), default=1.0) or 1.0
        for hit, rank in unique_hits:
            chunk = merged.setdefault(hit.chunk_id, _chunk_from_hit(hit))
            chunk.retrieval_arms.append(arm_name)
            chunk.arm_ranks[arm_name] = rank
            normalized_score = hit.score / arm_max
            chunk.arm_scores[arm_name] = normalized_score
            if arm_name == "dense":
                chunk.dense_score = normalized_score
            elif arm_name == "sparse":
                chunk.sparse_score = normalized_score
            raw_scores[hit.chunk_id] = raw_scores.get(hit.chunk_id, 0.0) + (
                weights.get(arm_name, 0.0) / (smoothing_k + rank)
            )

    maximum = sum(max(weight, 0.0) for weight in weights.values()) / (smoothing_k + 1)
    maximum = maximum or 1.0
    for chunk in merged.values():
        raw_score = raw_scores.get(chunk.chunk_id, 0.0)
        chunk.metadata = {**chunk.metadata, "rrf_raw_score": raw_score}
        chunk.score = raw_score / maximum
        chunk.fusion_score = chunk.score

    ranked = sorted(
        merged.values(),
        key=lambda chunk: (-chunk.score, str(chunk.chunk_id)),
    )
    return ranked[:top_k]


def _chunk_from_hit(hit: SearchHit) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=hit.chunk_id,
        document_id=hit.document_id,
        document_title=hit.document_title,
        content=hit.content,
        metadata=dict(hit.chunk_metadata),
    )


def _ranked_unique_hits(hits: list[SearchHit]) -> list[tuple[SearchHit, int]]:
    ordered = sorted(hits, key=lambda hit: (-hit.score, str(hit.chunk_id)))
    result: list[tuple[SearchHit, int]] = []
    seen: set[object] = set()
    previous_score: float | None = None
    current_rank = 0
    for position, hit in enumerate(ordered, start=1):
        if hit.chunk_id in seen:
            continue
        seen.add(hit.chunk_id)
        if previous_score is None or hit.score != previous_score:
            current_rank = position
            previous_score = hit.score
        result.append((hit, current_rank))
    return result
