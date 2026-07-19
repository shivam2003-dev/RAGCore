import uuid

from repositories.chunks import NeighborSearchHit, SearchHit
from retrieval.context import RetrievedChunk
from retrieval.expansion import expand_ranked_neighbors


def _neighbor(anchor_id: uuid.UUID, ordinal: int, tokens: int) -> NeighborSearchHit:
    chunk_id = uuid.uuid4()
    return NeighborSearchHit(
        anchor_chunk_id=anchor_id,
        distance=1,
        ordinal=ordinal,
        token_count=tokens,
        hit=SearchHit(
            chunk_id=chunk_id,
            document_id=uuid.uuid4(),
            document_title=f"Section {ordinal}",
            content=f"neighbor {ordinal}",
            chunk_metadata={"ordinal": ordinal},
            score=0.0,
        ),
    )


def test_neighbor_expansion_preserves_anchor_order_and_token_limit():
    anchor = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Anchor",
        content="anchor",
        score=0.9,
        fusion_score=0.8,
        selected_rank=1,
    )
    previous = _neighbor(anchor.chunk_id, 4, 40)
    following = _neighbor(anchor.chunk_id, 6, 70)

    expanded = expand_ranked_neighbors(
        [anchor],
        [following, previous],
        token_budget=100,
        max_neighbors=4,
    )

    assert [chunk.content for chunk in expanded] == ["anchor", "neighbor 4"]
    assert expanded[1].expanded_from_chunk_id == anchor.chunk_id
    assert expanded[1].chunk_id == previous.hit.chunk_id
    assert expanded[1].retrieval_arms == ["neighbor"]
