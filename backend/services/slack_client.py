import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol, cast

import httpx

from core.exceptions import ProviderError
from services.slack_normalizer import SlackMessage, SlackThread

JsonDict = dict[str, object]
Sleep = Callable[[float], Awaitable[None]]


class SlackReadClient(Protocol):
    async def fetch_thread(
        self,
        *,
        workspace_id: str,
        channel_id: str,
        channel_name: str,
        thread_ts: str,
    ) -> SlackThread | None: ...

    async def list_thread_roots(self, *, channel_id: str, limit: int) -> list[str]: ...


class SlackHttpClient:
    """Small GET-only Slack Web API client with bounded 429/5xx retries."""

    def __init__(
        self,
        *,
        bot_token: str,
        timeout_seconds: float = 20.0,
        max_retries: int = 3,
        page_limit: int = 15,
        http: httpx.AsyncClient | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._bot_token = bot_token
        self._max_retries = max(0, max_retries)
        self._page_limit = max(1, min(page_limit, 200))
        self._http = http or httpx.AsyncClient(
            base_url="https://slack.com/api",
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {bot_token}"},
        )
        self._owns_http = http is None
        self._sleep = sleep

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def list_thread_roots(self, *, channel_id: str, limit: int) -> list[str]:
        payload = await self._request(
            "conversations.history",
            params={"channel": channel_id, "limit": str(max(1, min(limit, self._page_limit)))},
        )
        roots: list[str] = []
        for row in _list_of_dicts(payload.get("messages")):
            ts = _str(row.get("thread_ts")) or _str(row.get("ts"))
            if ts and ts not in roots:
                roots.append(ts)
        return roots

    async def fetch_thread(
        self,
        *,
        workspace_id: str,
        channel_id: str,
        channel_name: str,
        thread_ts: str,
    ) -> SlackThread | None:
        messages: list[SlackMessage] = []
        cursor = ""
        while True:
            params = {
                "channel": channel_id,
                "ts": thread_ts,
                "limit": str(self._page_limit),
            }
            if cursor:
                params["cursor"] = cursor
            try:
                payload = await self._request("conversations.replies", params=params)
            except ProviderError as exc:
                if "thread_not_found" in str(exc) or "message_not_found" in str(exc):
                    return None
                raise
            messages.extend(_message(row) for row in _list_of_dicts(payload.get("messages")))
            metadata = _dict(payload.get("response_metadata"))
            cursor = (_str(metadata.get("next_cursor")) or "").strip()
            if not cursor:
                break

        if not messages:
            return None
        permalink_payload = await self._request(
            "chat.getPermalink",
            params={"channel": channel_id, "message_ts": thread_ts},
        )
        permalink = _str(permalink_payload.get("permalink")) or ""
        return SlackThread(
            workspace_id=workspace_id,
            channel_id=channel_id,
            channel_name=channel_name,
            thread_ts=thread_ts,
            thread_url=permalink,
            messages=messages,
        )

    async def _request(self, method: str, *, params: dict[str, str]) -> JsonDict:
        for attempt in range(self._max_retries + 1):
            response = await self._http.get(f"/{method}", params=params)
            if response.status_code == 429:
                if attempt >= self._max_retries:
                    raise ProviderError(f"Slack {method} remained rate limited after retries")
                retry_after = _retry_after_seconds(response)
                await self._sleep(retry_after)
                continue
            if response.status_code >= 500:
                if attempt >= self._max_retries:
                    raise ProviderError(f"Slack {method} failed with HTTP {response.status_code}")
                await self._sleep(min(2**attempt, 8))
                continue
            response.raise_for_status()
            payload = cast(JsonDict, response.json())
            if payload.get("ok") is not True:
                error = _str(payload.get("error")) or "unknown_error"
                raise ProviderError(f"Slack {method} failed: {error}")
            return payload
        raise ProviderError(f"Slack {method} failed")


def _message(row: JsonDict) -> SlackMessage:
    reactions = sum(
        int(item.get("count") or 0)
        for item in _list_of_dicts(row.get("reactions"))
        if isinstance(item.get("count"), int)
    )
    edited = _dict(row.get("edited"))
    return SlackMessage(
        ts=_str(row.get("ts")) or "0",
        user_id=_str(row.get("user")) or _str(row.get("bot_id")) or "unknown",
        display_name=_str(row.get("username")) or "",
        text=_str(row.get("text")) or "",
        reactions=reactions,
        edited_at=_str(edited.get("ts")),
    )


def _retry_after_seconds(response: httpx.Response) -> float:
    try:
        return max(0.0, min(float(response.headers.get("Retry-After", "1")), 300.0))
    except ValueError:
        return 1.0


def _dict(value: object) -> JsonDict:
    return cast(JsonDict, value) if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[JsonDict]:
    if not isinstance(value, list):
        return []
    return [cast(JsonDict, item) for item in value if isinstance(item, dict)]


def _str(value: object) -> str | None:
    return value if isinstance(value, str) else None
