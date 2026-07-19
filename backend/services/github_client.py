import asyncio
import base64
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol, cast, overload
from urllib.parse import quote

import httpx

from core.exceptions import ProviderError

JsonDict = dict[str, object]
Sleep = Callable[[float], Awaitable[None]]


@dataclass(slots=True, frozen=True)
class GitHubBranchSnapshot:
    commit_sha: str
    tree_sha: str


@dataclass(slots=True, frozen=True)
class GitHubTreeEntry:
    path: str
    blob_sha: str
    size: int


@dataclass(slots=True, frozen=True)
class GitHubPullRequest:
    number: int
    title: str
    body: str
    state: str
    author: str
    url: str
    base_branch: str
    head_branch: str
    created_at: str
    updated_at: str
    merged_at: str | None
    draft: bool
    labels: list[str]


class GitHubReadClient(Protocol):
    async def branch(self, *, owner: str, repository: str, branch: str) -> GitHubBranchSnapshot: ...

    async def tree(self, *, owner: str, repository: str, tree_sha: str) -> list[GitHubTreeEntry]: ...

    async def blob(self, *, owner: str, repository: str, blob_sha: str) -> bytes: ...

    async def contributors(self, *, owner: str, repository: str) -> list[str]: ...

    async def recent_pull_requests(
        self,
        *,
        owner: str,
        repository: str,
        limit: int,
    ) -> list[GitHubPullRequest]: ...


class GitHubHttpClient:
    """Read-only GitHub REST client; it exposes no mutation methods."""

    def __init__(
        self,
        *,
        token: str,
        base_url: str = "https://api.github.com",
        api_version: str = "2026-03-10",
        timeout_seconds: float = 20.0,
        max_retries: int = 3,
        http: httpx.AsyncClient | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": api_version,
        }
        if token.strip():
            headers["Authorization"] = f"Bearer {token.strip()}"
        self._http = http or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers=headers,
        )
        self._owns_http = http is None
        self._max_retries = max(0, max_retries)
        self._sleep = sleep

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def branch(self, *, owner: str, repository: str, branch: str) -> GitHubBranchSnapshot:
        payload = await self._get(
            f"/repos/{_segment(owner)}/{_segment(repository)}/branches/{quote(branch, safe='')}",
        )
        commit = _dict(payload.get("commit"))
        nested_commit = _dict(commit.get("commit"))
        tree = _dict(nested_commit.get("tree"))
        commit_sha = _required_str(commit, "sha")
        tree_sha = _required_str(tree, "sha")
        return GitHubBranchSnapshot(commit_sha=commit_sha, tree_sha=tree_sha)

    async def tree(self, *, owner: str, repository: str, tree_sha: str) -> list[GitHubTreeEntry]:
        payload = await self._get(
            f"/repos/{_segment(owner)}/{_segment(repository)}/git/trees/{_segment(tree_sha)}",
            params={"recursive": "1"},
        )
        if payload.get("truncated") is True:
            raise ProviderError("GitHub recursive tree was truncated; narrow the configured path allowlist")
        entries: list[GitHubTreeEntry] = []
        for row in _list_of_dicts(payload.get("tree")):
            if row.get("type") != "blob":
                continue
            path = _str(row.get("path"))
            sha = _str(row.get("sha"))
            size = row.get("size")
            if path and sha and isinstance(size, int):
                entries.append(GitHubTreeEntry(path=path, blob_sha=sha, size=size))
        return entries

    async def blob(self, *, owner: str, repository: str, blob_sha: str) -> bytes:
        payload = await self._get(
            f"/repos/{_segment(owner)}/{_segment(repository)}/git/blobs/{_segment(blob_sha)}",
        )
        raw_content = payload.get("content")
        if not isinstance(raw_content, str):
            raise ProviderError("GitHub API response is missing content")
        content = raw_content.replace("\n", "")
        if payload.get("encoding") != "base64":
            raise ProviderError("GitHub blob response did not use base64 encoding")
        try:
            return base64.b64decode(content, validate=True)
        except ValueError as exc:
            raise ProviderError("GitHub blob response contained invalid base64") from exc

    async def contributors(self, *, owner: str, repository: str) -> list[str]:
        payload = await self._get(
            f"/repos/{_segment(owner)}/{_segment(repository)}/contributors",
            params={"per_page": "30", "anon": "false"},
            expect_list=True,
        )
        return [
            login
            for row in payload
            if (login := _str(row.get("login")))
        ][:30]

    async def recent_pull_requests(
        self,
        *,
        owner: str,
        repository: str,
        limit: int,
    ) -> list[GitHubPullRequest]:
        payload = await self._get(
            f"/repos/{_segment(owner)}/{_segment(repository)}/pulls",
            params={
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": str(max(1, min(limit, 100))),
            },
            expect_list=True,
        )
        return [_pull_request(row) for row in payload]

    @overload
    async def _get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        expect_list: Literal[False] = False,
    ) -> JsonDict: ...

    @overload
    async def _get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        expect_list: Literal[True],
    ) -> list[JsonDict]: ...

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        expect_list: bool = False,
    ) -> JsonDict | list[JsonDict]:
        for attempt in range(self._max_retries + 1):
            response = await self._http.get(path, params=params)
            rate_limited = response.status_code == 429 or (
                response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0"
            )
            if rate_limited:
                if attempt >= self._max_retries:
                    raise ProviderError("GitHub API remained rate limited after retries")
                await self._sleep(_retry_after(response, attempt))
                continue
            if response.status_code >= 500:
                if attempt >= self._max_retries:
                    raise ProviderError(f"GitHub API failed with HTTP {response.status_code}")
                await self._sleep(min(2**attempt, 8))
                continue
            if response.status_code >= 400:
                raise ProviderError(f"GitHub API read failed with HTTP {response.status_code}")
            raw: object = response.json()
            if expect_list:
                if not isinstance(raw, list):
                    raise ProviderError("GitHub API returned an unexpected response")
                return [cast(JsonDict, item) for item in raw if isinstance(item, dict)]
            if not isinstance(raw, dict):
                raise ProviderError("GitHub API returned an unexpected response")
            return cast(JsonDict, raw)
        raise ProviderError("GitHub API read failed")


def _pull_request(row: JsonDict) -> GitHubPullRequest:
    user = _dict(row.get("user"))
    base = _dict(row.get("base"))
    head = _dict(row.get("head"))
    labels = [label for item in _list_of_dicts(row.get("labels")) if (label := _str(item.get("name")))]
    number = row.get("number")
    if not isinstance(number, int):
        raise ProviderError("GitHub pull request response is missing number")
    return GitHubPullRequest(
        number=number,
        title=_required_str(row, "title"),
        body=_str(row.get("body")) or "",
        state=_required_str(row, "state"),
        author=_str(user.get("login")) or "unknown",
        url=_required_str(row, "html_url"),
        base_branch=_str(base.get("ref")) or "",
        head_branch=_str(head.get("ref")) or "",
        created_at=_required_str(row, "created_at"),
        updated_at=_required_str(row, "updated_at"),
        merged_at=_str(row.get("merged_at")),
        draft=row.get("draft") is True,
        labels=labels,
    )


def _retry_after(response: httpx.Response, attempt: int) -> float:
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return max(0.0, min(float(raw), 300.0))
        except ValueError:
            pass
    return float(min(2**attempt, 8))


def _segment(value: str) -> str:
    cleaned = value.strip()
    if not cleaned or "/" in cleaned or cleaned in {".", ".."}:
        raise ProviderError("GitHub owner, repository, branch, or SHA is invalid")
    return quote(cleaned, safe="")


def _dict(value: object) -> JsonDict:
    return cast(JsonDict, value) if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[JsonDict]:
    if not isinstance(value, list):
        return []
    return [cast(JsonDict, item) for item in value if isinstance(item, dict)]


def _str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _required_str(row: JsonDict, key: str) -> str:
    value = _str(row.get(key))
    if not value:
        raise ProviderError(f"GitHub API response is missing {key}")
    return value
