"""Weighted score fusion of dense and sparse arms.

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
    dense_max = max((h.score for h in dense), default=1.0) or 1.0
    sparse_max = max((h.score for h in sparse), default=1.0) or 1.0

    merged: dict[object, RetrievedChunk] = {}
    for hit in dense:
        merged[hit.chunk_id] = RetrievedChunk(
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            document_title=hit.document_title,
            content=hit.content,
            metadata=hit.chunk_metadata,
            dense_score=hit.score / dense_max,
        )
    for hit in sparse:
        existing = merged.get(hit.chunk_id)
        if existing:
            existing.sparse_score = hit.score / sparse_max
        else:
            merged[hit.chunk_id] = RetrievedChunk(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                document_title=hit.document_title,
                content=hit.content,
                metadata=hit.chunk_metadata,
                sparse_score=hit.score / sparse_max,
            )

    for chunk in merged.values():
        chunk.score = dense_weight * chunk.dense_score + sparse_weight * chunk.sparse_score

    ranked = sorted(merged.values(), key=lambda c: c.score, reverse=True)
    return ranked[:top_k]
