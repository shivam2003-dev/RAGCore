import math
from datetime import UTC, datetime

from retrieval.context import RetrievedChunk

DEFAULT_HALF_LIFE_DAYS = 180.0


def parse_half_lives(value: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for item in value.split(","):
        name, separator, raw_days = item.strip().partition("=")
        if not separator or not name.strip():
            continue
        try:
            days = float(raw_days)
        except ValueError:
            continue
        if days > 0:
            result[name.strip().lower()] = days
    return result


def recency_multiplier(
    metadata: dict[str, object],
    *,
    half_life_days: float,
    floor: float,
    now: datetime | None = None,
) -> float:
    raw = _updated_at(metadata)
    if raw is None or half_life_days <= 0:
        return 1.0
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return 1.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    reference = now or datetime.now(UTC)
    age_days = max(0.0, (reference - parsed).total_seconds() / 86_400)
    decay = math.pow(0.5, age_days / half_life_days)
    bounded_floor = max(0.0, min(1.0, floor))
    return bounded_floor + ((1.0 - bounded_floor) * decay)


def apply_source_recency_decay(
    chunks: list[RetrievedChunk],
    *,
    half_lives: dict[str, float],
    floor: float,
    now: datetime | None = None,
) -> list[RetrievedChunk]:
    for chunk in chunks:
        source = _source_family(chunk.metadata)
        half_life = half_lives.get(source, half_lives.get("default", DEFAULT_HALF_LIFE_DAYS))
        multiplier = recency_multiplier(
            chunk.metadata,
            half_life_days=half_life,
            floor=floor,
            now=now,
        )
        chunk.metadata = {
            **chunk.metadata,
            "recency_half_life_days": half_life,
            "recency_multiplier": round(multiplier, 6),
        }
        chunk.score = round(chunk.score * multiplier, 8)
        chunk.fusion_score = chunk.score
    return sorted(chunks, key=lambda chunk: (-chunk.score, str(chunk.chunk_id)))


def _updated_at(metadata: dict[str, object]) -> str | None:
    for key in (
        "source_updated_at",
        "jira_issue_updated_at",
        "jira_updated_at",
        "confluence_version_created_at",
        "updated_at",
    ):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _source_family(metadata: dict[str, object]) -> str:
    source = str(
        metadata.get("source")
        or metadata.get("source_type")
        or metadata.get("source_family")
        or metadata.get("connector")
        or "default"
    ).lower()
    if "jira" in source:
        return "jira"
    if "confluence" in source:
        return "confluence"
    if "web" in source:
        return "web"
    if "upload" in source:
        return "upload"
    if "github" in source:
        return "github"
    if "slack" in source:
        return "slack"
    return source or "default"
