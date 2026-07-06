"""Canonical source metadata contract for indexed enterprise knowledge."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def normalize_source_metadata(
    metadata: dict[str, object] | None = None,
    *,
    source_type: str | None = None,
    title: str | None = None,
    source_id: str | None = None,
    source_url: str | None = None,
    source_space: str | None = None,
    source_version: str | int | None = None,
    updated_at: str | None = None,
    status: str | None = None,
    labels: list[str] | None = None,
    owner: str | None = None,
    acl: str | None = None,
    connector: str | None = None,
    connector_scope: str | None = None,
    source_sha256: str | None = None,
    filename: str | None = None,
    file_type: str | None = None,
) -> dict[str, object]:
    """Return metadata with stable fields used by retrieval, citations, and inventory.

    Connector-specific fields are preserved, but every source also gets a common
    shape: source_type, source_id, title, url, scope, freshness, ACL, and sync id.
    """

    result: dict[str, object] = dict(metadata or {})
    inferred_type = _clean(
        source_type
        or _str(result.get("source_type"))
        or _str(result.get("source"))
        or _str(result.get("source_system"))
        or "upload"
    ).lower()
    inferred_title = _clean(
        title
        or _str(result.get("source_title"))
        or _str(result.get("title"))
        or Path(filename or "Untitled document").name
    )
    inferred_url = _clean(
        source_url
        or _str(result.get("source_url"))
        or _str(result.get("url"))
        or _str(result.get("web_url"))
        or _str(result.get("jira_issue_url"))
        or _str(result.get("confluence_page_url"))
    )
    inferred_space = _clean(
        source_space
        or connector_scope
        or _str(result.get("source_space"))
        or _str(result.get("space"))
        or _str(result.get("space_key"))
        or _str(result.get("project"))
        or _str(result.get("project_key"))
        or _str(result.get("jira_project_key"))
        or _str(result.get("confluence_space_key"))
    )
    inferred_id = _clean(
        source_id
        or _str(result.get("source_id"))
        or _str(result.get("issue_key"))
        or _str(result.get("jira_issue_key"))
        or _str(result.get("page_id"))
        or _str(result.get("confluence_page_id"))
        or _str(result.get("web_url"))
        or source_sha256
        or _str(result.get("source_sha256"))
        or inferred_url
        or inferred_title
    )
    inferred_version = source_version or result.get("source_version") or result.get("updated_at")
    inferred_updated = _clean(
        updated_at
        or _str(result.get("source_updated_at"))
        or _str(result.get("updated_at"))
        or _str(result.get("jira_issue_updated_at"))
        or _str(result.get("confluence_version_created_at"))
    )
    normalized_labels = _labels(labels if labels is not None else result.get("labels"))
    normalized_owner = _clean(owner or _str(result.get("owner")) or _str(result.get("assignee")))
    normalized_connector = _clean(connector or _str(result.get("connector")) or inferred_type).lower()
    normalized_scope = _clean(connector_scope or inferred_space or ("uploads" if inferred_type == "upload" else "global"))
    normalized_acl = _clean(acl or _str(result.get("acl")) or ("user-upload" if inferred_type == "upload" else "connector-visible"))
    normalized_status = _clean(
        status
        or _str(result.get("status"))
        or _str(result.get("jira_issue_status"))
        or _str(result.get("status_category"))
        or "current"
    )

    if source_sha256:
        result["source_sha256"] = source_sha256
    elif "source_sha256" not in result and inferred_type == "upload":
        result["source_sha256"] = hashlib.sha256(inferred_id.encode("utf-8")).hexdigest()

    if filename:
        result["filename"] = filename
    if file_type:
        result["file_type"] = file_type

    result.update(
        {
            "source": inferred_type,
            "source_type": inferred_type,
            "source_family": inferred_type,
            "source_system": inferred_type,
            "source_id": inferred_id,
            "source_title": inferred_title,
            "source_url": inferred_url or None,
            "source_space": normalized_scope,
            "source_version": inferred_version,
            "source_updated_at": inferred_updated or _now_iso(),
            "space": normalized_scope if inferred_type == "confluence" else result.get("space", normalized_scope),
            "project": normalized_scope if inferred_type == "jira" else result.get("project", normalized_scope),
            "title": inferred_title,
            "url": inferred_url or result.get("url"),
            "updated_at": inferred_updated or _now_iso(),
            "status": normalized_status,
            "labels": normalized_labels,
            "owner": normalized_owner or None,
            "acl": normalized_acl,
            "connector": normalized_connector,
            "connector_scope": normalized_scope,
            "permission_state": _clean(_str(result.get("permission_state")) or "visible"),
        }
    )

    result["connector_sync_id"] = _clean(
        _str(result.get("connector_sync_id"))
        or f"{normalized_connector}:{normalized_scope}:{inferred_id}:{inferred_version or result.get('source_sha256') or 'v1'}"
    )
    result["source_inventory_key"] = f"{inferred_type}:{normalized_scope}:{inferred_id}"
    result["source_freshness_bucket"] = _freshness_bucket(_str(result.get("source_updated_at")))
    return result


def _labels(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _freshness_bucket(raw: str | None) -> str:
    if not raw:
        return "undated"
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return "undated"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    age_days = max(0, (datetime.now(UTC) - parsed).days)
    if age_days <= 30:
        return "fresh"
    if age_days <= 180:
        return "aging"
    return "stale"


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _clean(value: str | None) -> str:
    return " ".join(value.split()) if value else ""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
