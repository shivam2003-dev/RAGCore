"""Run Kimbal golden eval release gates.

Default mode validates the checked-in golden dataset. To enforce a live gate,
pass --api-base and --token, or set KIMBAL_EVALS_API_BASE and KIMBAL_EVALS_TOKEN.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals" / "golden" / "rag.jsonl"
MIN_GOLDEN_CASES = 100
REQUIRED_CATEGORIES = {"SRE", "DevOps", "Developer", "HR", "Web", "Blended"}
REQUIRED_SOURCE_TYPES = {"jira", "confluence", "upload", "web"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Kimbal RAG eval release gates")
    parser.add_argument("--dataset", default=str(DATASET), help="Golden JSONL dataset path")
    parser.add_argument("--api-base", default=os.getenv("KIMBAL_EVALS_API_BASE", ""))
    parser.add_argument("--token", default=os.getenv("KIMBAL_EVALS_TOKEN", ""))
    parser.add_argument("--min-cases", type=int, default=int(os.getenv("KIMBAL_EVALS_MIN_CASES", MIN_GOLDEN_CASES)))
    parser.add_argument("--strict-api", action="store_true", default=os.getenv("KIMBAL_EVALS_STRICT_API") == "1")
    args = parser.parse_args()

    cases = _load_dataset(Path(args.dataset))
    print(f"golden_dataset cases={len(cases)} path={args.dataset}")
    _validate_release_gate_coverage(cases, min_cases=args.min_cases)

    if args.api_base and args.token:
        return _run_api_gate(args.api_base.rstrip("/"), args.token)

    if args.strict_api:
        print("KIMBAL_EVALS_STRICT_API is set but no API credentials were supplied.", file=sys.stderr)
        return 2

    categories = sorted({case["category"] for case in cases})
    source_types = sorted({source for case in cases for source in case["expected_source_types"]})
    print(f"dataset_gate passed=true categories={','.join(categories)} source_types={','.join(source_types)}")
    print("live_gate skipped=true reason=no_api_base_or_token")
    return 0


def _load_dataset(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"Golden dataset not found: {path}")
    cases: list[dict] = []
    required = {"id", "category", "question", "expected_source_types", "expected_answer_traits"}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        missing = required - set(payload)
        if missing:
            raise SystemExit(f"{path}:{line_number} missing keys: {', '.join(sorted(missing))}")
        if not payload["expected_source_types"]:
            raise SystemExit(f"{path}:{line_number} must declare expected_source_types")
        cases.append(payload)
    if not cases:
        raise SystemExit(f"{path} has no eval cases")
    return cases


def _validate_release_gate_coverage(cases: list[dict], *, min_cases: int) -> None:
    if len(cases) < min_cases:
        raise SystemExit(f"Golden dataset has {len(cases)} cases; minimum required is {min_cases}")

    categories = {str(case["category"]) for case in cases}
    missing_categories = REQUIRED_CATEGORIES - categories
    if missing_categories:
        raise SystemExit(f"Golden dataset missing categories: {', '.join(sorted(missing_categories))}")

    source_types = {str(source) for case in cases for source in case["expected_source_types"]}
    missing_source_types = REQUIRED_SOURCE_TYPES - source_types
    if missing_source_types:
        raise SystemExit(f"Golden dataset missing source types: {', '.join(sorted(missing_source_types))}")

    duplicate_ids = _duplicate_ids(cases)
    if duplicate_ids:
        raise SystemExit(f"Golden dataset duplicate ids: {', '.join(duplicate_ids[:10])}")


def _duplicate_ids(cases: list[dict]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for case in cases:
        case_id = str(case["id"])
        if case_id in seen:
            duplicates.append(case_id)
        seen.add(case_id)
    return duplicates


def _run_api_gate(api_base: str, token: str) -> int:
    url = f"{api_base}/evals/offline" if api_base.endswith("/api/v1") else f"{api_base}/api/v1/evals/offline"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        print(f"live_gate error=unsupported_url_scheme scheme={parsed.scheme}", file=sys.stderr)
        return 2
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"live_gate error=http_{exc.code}", file=sys.stderr)
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 2
    except urllib.error.URLError as exc:
        print(f"live_gate error={exc.reason}", file=sys.stderr)
        return 2

    print(f"live_gate passed={str(payload.get('passed')).lower()} score={payload.get('display')}")
    for metric in payload.get("metrics", []):
        status = "pass" if metric.get("passed") else "fail"
        print(
            f"metric {metric.get('id')}={metric.get('display')} "
            f"threshold={metric.get('threshold')} status={status}"
        )
    for case in payload.get("failing_cases", [])[:5]:
        print(f"failing_case {case.get('id')} rationale={case.get('judge_rationale')}")
    return 0 if payload.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
