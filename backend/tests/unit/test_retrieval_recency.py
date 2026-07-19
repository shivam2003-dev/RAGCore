from datetime import UTC, datetime, timedelta

from retrieval.recency import parse_half_lives, recency_multiplier


def test_recency_decay_boundaries_and_floor():
    now = datetime(2026, 7, 19, tzinfo=UTC)
    fresh = recency_multiplier(
        {"source_updated_at": now.isoformat()},
        half_life_days=30,
        floor=0.2,
        now=now,
    )
    half_life = recency_multiplier(
        {"source_updated_at": (now - timedelta(days=30)).isoformat()},
        half_life_days=30,
        floor=0.2,
        now=now,
    )
    very_old = recency_multiplier(
        {"source_updated_at": (now - timedelta(days=3000)).isoformat()},
        half_life_days=30,
        floor=0.2,
        now=now,
    )

    assert fresh == 1.0
    assert abs(half_life - 0.6) < 1e-9
    assert 0.2 <= very_old < 0.201
    assert recency_multiplier({}, half_life_days=30, floor=0.2, now=now) == 1.0


def test_source_half_life_configuration_ignores_invalid_entries():
    assert parse_half_lives("jira=45, confluence=180,broken=x,negative=-1") == {
        "jira": 45.0,
        "confluence": 180.0,
    }
