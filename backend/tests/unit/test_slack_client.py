import httpx

from services.slack_client import SlackHttpClient


async def test_slack_client_retries_rate_limit_and_reads_complete_thread():
    calls: list[str] = []
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("conversations.replies") and calls.count("/api/conversations.replies") == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        if request.url.path.endswith("conversations.replies"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "messages": [
                        {"ts": "1.0", "user": "U1", "text": "Question"},
                        {
                            "ts": "2.0",
                            "thread_ts": "1.0",
                            "user": "U2",
                            "text": "Answer --force",
                            "reactions": [{"name": "white_check_mark", "count": 2}],
                        },
                    ],
                    "response_metadata": {"next_cursor": ""},
                },
            )
        return httpx.Response(
            200,
            json={"ok": True, "permalink": "https://example.slack.com/archives/C123/p100"},
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://slack.com/api")
    client = SlackHttpClient(bot_token="test-token", max_retries=2, http=http, sleep=sleep)
    try:
        thread = await client.fetch_thread(
            workspace_id="T123",
            channel_id="C123",
            channel_name="sre-help",
            thread_ts="1.0",
        )
    finally:
        await http.aclose()

    assert sleeps == [2.0]
    assert thread is not None
    assert len(thread.messages) == 2
    assert thread.messages[1].reactions == 2
    assert thread.thread_url.endswith("p100")


async def test_slack_client_treats_deleted_root_as_missing_thread():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "error": "thread_not_found"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://slack.com/api")
    client = SlackHttpClient(bot_token="test-token", http=http)
    try:
        thread = await client.fetch_thread(
            workspace_id="T123",
            channel_id="C123",
            channel_name="sre-help",
            thread_ts="1.0",
        )
    finally:
        await http.aclose()
    assert thread is None
