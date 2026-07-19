from repositories.chunks import NeighborSearchHit
from retrieval.context import RetrievedChunk


def expand_ranked_neighbors(
    anchors: list[RetrievedChunk],
    neighbors: list[NeighborSearchHit],
    *,
    token_budget: int,
    max_neighbors: int,
) -> list[RetrievedChunk]:
    """Insert bounded adjacent chunks only after anchors have been ranked."""

    if not anchors or token_budget <= 0 or max_neighbors <= 0:
        return anchors
    grouped: dict[object, list[NeighborSearchHit]] = {}
    for neighbor in neighbors:
        grouped.setdefault(neighbor.anchor_chunk_id, []).append(neighbor)
    for values in grouped.values():
        values.sort(key=lambda item: (item.distance, item.ordinal, str(item.hit.chunk_id)))

    expanded: list[RetrievedChunk] = []
    seen = {anchor.chunk_id for anchor in anchors}
    used_tokens = 0
    added_neighbors = 0
    for anchor in anchors:
        expanded.append(anchor)
        for neighbor in grouped.get(anchor.chunk_id, []):
            if neighbor.hit.chunk_id in seen:
                continue
            if added_neighbors >= max_neighbors:
                break
            if used_tokens + neighbor.token_count > token_budget:
                continue
            seen.add(neighbor.hit.chunk_id)
            used_tokens += neighbor.token_count
            added_neighbors += 1
            expanded.append(
                RetrievedChunk(
                    chunk_id=neighbor.hit.chunk_id,
                    document_id=neighbor.hit.document_id,
                    document_title=neighbor.hit.document_title,
                    content=neighbor.hit.content,
                    metadata={
                        **neighbor.hit.chunk_metadata,
                        "neighbor_distance": neighbor.distance,
                    },
                    score=round(anchor.score * (0.95**neighbor.distance), 8),
                    fusion_score=anchor.fusion_score,
                    retrieval_arms=["neighbor"],
                    arm_ranks={"neighbor": neighbor.distance},
                    expanded_from_chunk_id=anchor.chunk_id,
                )
            )
    return expanded
