import uuid

from repositories.chunks import SearchHit
from retrieval.fusion import fuse


def _hit(cid: uuid.UUID, score: float) -> SearchHit:
    return SearchHit(cid, uuid.uuid4(), "doc", "content", {}, score)


def test_fuse_merges_overlapping_hits():
    shared = uuid.uuid4()
    dense = [_hit(shared, 0.9), _hit(uuid.uuid4(), 0.5)]
    sparse = [_hit(shared, 0.4)]
    result = fuse(dense, sparse, dense_weight=0.7, sparse_weight=0.3, top_k=10)
    top = result[0]
    assert top.chunk_id == shared
    # appears in both arms with max scores → normalized 1.0 each → 0.7 + 0.3
    assert abs(top.score - 1.0) < 1e-9
    assert top.dense_score == 1.0 and top.sparse_score == 1.0


def test_fuse_respects_top_k():
    dense = [_hit(uuid.uuid4(), s / 10) for s in range(10, 0, -1)]
    result = fuse(dense, [], dense_weight=0.7, sparse_weight=0.3, top_k=3)
    assert len(result) == 3
    assert result[0].score >= result[1].score >= result[2].score


def test_fuse_empty_arms():
    assert fuse([], [], dense_weight=0.7, sparse_weight=0.3, top_k=5) == []


def test_sparse_only_results_survive():
    sparse = [_hit(uuid.uuid4(), 2.5)]
    result = fuse([], sparse, dense_weight=0.7, sparse_weight=0.3, top_k=5)
    assert len(result) == 1
    assert abs(result[0].score - 0.3) < 1e-9
