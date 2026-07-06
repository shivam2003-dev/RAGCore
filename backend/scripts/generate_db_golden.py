"""Generate golden RAG eval cases from indexed production documents.

The script samples real active chunks/documents and writes JSONL cases that
point back to exact source IDs and titles. It is deterministic by default so
regressions are comparable across runs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from database.session import SessionFactory

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = BACKEND_ROOT / "evals" / "golden" / "rag.generated.jsonl"
SOURCE_TARGETS = {
    "confluence": 50,
    "jira": 50,
    "web": 10,
    "upload": 10,
}


@dataclass(frozen=True)
class SourceSample:
    knowledge_base_name: str
    document_title: str
    source_type: str
    source_id: str
    source_url: str
    status: str
    source_space: str
    chunk_text: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate DB-backed golden RAG eval cases")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSONL path")
    parser.add_argument("--min-cases", type=int, default=120)
    parser.add_argument("--per-family-limit", type=int, default=80)
    args = parser.parse_args()

    cases = asyncio.run(generate_cases(min_cases=args.min_cases, per_family_limit=args.per_family_limit))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(json.dumps(case, sort_keys=True) for case in cases) + "\n", encoding="utf-8")
    print(f"generated_cases={len(cases)} output={output}")
    print("source_counts=" + json.dumps(_source_counts(cases), sort_keys=True))
    return 0


async def generate_cases(*, min_cases: int, per_family_limit: int) -> list[dict]:
    samples = await _load_samples(per_family_limit=per_family_limit)
    cases: list[dict] = []
    seen_sources: set[str] = set()
    samples_by_family: dict[str, list[SourceSample]] = {family: [] for family in SOURCE_TARGETS}
    for sample in samples:
        samples_by_family.setdefault(_family(sample.source_type), []).append(sample)

    for family, target in SOURCE_TARGETS.items():
        for sample in samples_by_family.get(family, [])[:target]:
            _append_case(cases, seen_sources, sample, family)

    family_order = [family for family in SOURCE_TARGETS if samples_by_family.get(family)]
    cursor = 0
    while len(cases) < min_cases and family_order:
        family = family_order[cursor % len(family_order)]
        sample_index = SOURCE_TARGETS.get(family, 0) + (cursor // len(family_order))
        family_samples = samples_by_family.get(family, [])
        if sample_index < len(family_samples):
            _append_case(cases, seen_sources, family_samples[sample_index], family)
        if _all_family_samples_consumed(samples_by_family, family_order, cursor):
            break
        cursor += 1

    if len(cases) < min_cases:
        raise SystemExit(f"Only generated {len(cases)} cases; need at least {min_cases}")
    return cases[:min_cases]


async def _load_samples(*, per_family_limit: int) -> list[SourceSample]:
    query = text(
        """
        WITH document_chunks AS (
            SELECT
                kb.name AS knowledge_base_name,
                d.title AS document_title,
                COALESCE(d.doc_metadata->>'source', d.source_type, 'upload') AS source_type,
                COALESCE(
                    d.doc_metadata->>'source_id',
                    d.doc_metadata->>'jira_issue_key',
                    d.doc_metadata->>'confluence_page_id',
                    d.id::text
                ) AS source_id,
                COALESCE(
                    d.doc_metadata->>'source_url',
                    d.doc_metadata->>'jira_issue_url',
                    d.doc_metadata->>'confluence_page_url',
                    ''
                ) AS source_url,
                COALESCE(d.doc_metadata->>'status', d.doc_metadata->>'jira_issue_status', '') AS status,
                COALESCE(
                    d.doc_metadata->>'space',
                    d.doc_metadata->>'project',
                    d.doc_metadata->>'source_space',
                    kb.name
                ) AS source_space,
                c.content AS chunk_text,
                ROW_NUMBER() OVER (PARTITION BY d.id ORDER BY c.ordinal ASC) AS document_chunk_rank,
                d.updated_at AS document_updated_at
            FROM documents d
            JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
            JOIN chunks c ON c.document_id = d.id
            WHERE d.is_deleted IS FALSE
              AND c.is_active IS TRUE
              AND LENGTH(c.content) >= 120
        ),
        ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY source_type
                    ORDER BY document_updated_at DESC, document_title ASC
                ) AS source_rank
            FROM document_chunks
            WHERE document_chunk_rank = 1
        )
        SELECT *
        FROM ranked
        WHERE source_rank <= :per_family_limit
        ORDER BY source_type, knowledge_base_name, document_title
        """
    )
    async with SessionFactory() as db:
        rows = (await db.execute(query, {"per_family_limit": per_family_limit})).mappings().all()
    return [
        SourceSample(
            knowledge_base_name=str(row["knowledge_base_name"] or ""),
            document_title=str(row["document_title"] or "Untitled source"),
            source_type=str(row["source_type"] or "upload"),
            source_id=str(row["source_id"] or ""),
            source_url=str(row["source_url"] or ""),
            status=str(row["status"] or ""),
            source_space=str(row["source_space"] or ""),
            chunk_text=str(row["chunk_text"] or ""),
        )
        for row in rows
    ]


def _case_from_sample(sample: SourceSample, family: str, index: int) -> dict:
    title = _clean_title(sample.document_title)
    source_id = sample.source_id or title
    category = _category(sample)
    question = _question(sample, family, title)
    return {
        "id": f"db-{family}-{_slug(source_id or title)}-{index:03d}",
        "category": category,
        "question": question,
        "expected_source_types": [family],
        "expected_source_ids": [source_id] if source_id else [],
        "expected_source_titles": [sample.document_title],
        "expected_answer_traits": [
            "retrieves the exact indexed source",
            "uses current indexed chunk evidence",
            "includes openable citations",
        ],
        "tags": _tags(sample, family),
    }


def _append_case(
    cases: list[dict],
    seen_sources: set[str],
    sample: SourceSample,
    family: str,
) -> None:
    source_key = f"{family}:{sample.source_id or sample.document_title}".lower()
    if source_key in seen_sources:
        return
    seen_sources.add(source_key)
    cases.append(_case_from_sample(sample, family, len(cases) + 1))


def _all_family_samples_consumed(
    samples_by_family: dict[str, list[SourceSample]],
    family_order: list[str],
    cursor: int,
) -> bool:
    offset = cursor // len(family_order)
    return all(SOURCE_TARGETS.get(family, 0) + offset >= len(samples_by_family[family]) for family in family_order)


def _question(sample: SourceSample, family: str, title: str) -> str:
    topic = _topic_from_chunk(sample.chunk_text)
    meaningful_topic = _meaningful_topic(topic, title, sample.source_id)
    if family == "jira":
        status_hint = f" and current status {sample.status}" if sample.status else ""
        topic_hint = f" with respect to {topic}" if meaningful_topic else ""
        return (
            f"What is the operational context for Jira issue {sample.source_id}{status_hint}"
            f"{topic_hint}: {_trim_text(title, 100)}?"
        )
    if family == "confluence":
        if meaningful_topic:
            return f"What does the internal documentation say about {topic} in {title}?"
        return f"What does the internal documentation say about {title}?"
    if family == "web":
        if meaningful_topic:
            return f"What does the indexed web source say about {topic} in {title}?"
        return f"What does the indexed web source say about {title}?"
    return f"What does the uploaded or indexed source {title} cover?"


def _category(sample: SourceSample) -> str:
    name = f"{sample.knowledge_base_name} {sample.source_space}".lower()
    if "sre" in name or "cvir" in name or " as" in f" {name} ":
        return "SRE"
    if "devops" in name or "devo" in name:
        return "DevOps"
    if "jira" in name:
        return "Jira analytics"
    if "web" in name:
        return "Web"
    return "Knowledge"


def _tags(sample: SourceSample, family: str) -> list[str]:
    tags = {family, _slug(sample.knowledge_base_name), _slug(sample.source_space)}
    if sample.status:
        tags.add(_slug(sample.status))
    return sorted(tag for tag in tags if tag)


def _family(source_type: str) -> str:
    normalized = source_type.lower()
    if "jira" in normalized:
        return "jira"
    if "confluence" in normalized:
        return "confluence"
    if "web" in normalized:
        return "web"
    return "upload"


def _clean_title(value: str) -> str:
    title = re.sub(r"\s+", " ", value).strip()
    if not title:
        return "this indexed source"
    return _trim_text(title, 120)


def _topic_from_chunk(value: str) -> str:
    lines = []
    for raw_line in value.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip(" -#:\t")
        if not line:
            continue
        if line.lower().startswith(("source:", "title:", "space:", "project:", "status:", "updated:", "section:")):
            continue
        if len(line) < 12:
            continue
        lines.append(line)
        if len(lines) >= 3:
            break
    if not lines:
        return ""
    topic = re.split(r"(?<=[.!?])\s+", lines[0], maxsplit=1)[0]
    return _trim_text(topic, 90)


def _meaningful_topic(topic: str, title: str, source_id: str) -> bool:
    if not topic:
        return False
    topic_norm = _normalize_text(topic)
    title_norm = _normalize_text(title)
    source_norm = _normalize_text(source_id)
    if len(topic_norm) < 12:
        return False
    if topic_norm in title_norm or title_norm in topic_norm:
        return False
    title_overlap = len(set(topic_norm.split()) & set(title_norm.split()))
    return not (source_norm and source_norm in topic_norm and title_overlap >= 4)


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _trim_text(value: str, max_length: int) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= max_length:
        return text
    cut = text[: max_length - 3].rstrip()
    word_cut = max(cut.rfind(" "), cut.rfind(" | "), cut.rfind(" - "))
    if word_cut >= max_length // 2:
        cut = cut[:word_cut].rstrip()
    cut = cut.rstrip("([{,:;/|- ")
    return f"{cut}..."


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:72] or "source"


def _source_counts(cases: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        for source in case["expected_source_types"]:
            counts[source] = counts.get(source, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
