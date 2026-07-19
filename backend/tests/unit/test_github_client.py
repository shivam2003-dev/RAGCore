import httpx

from services.github_client import GitHubHttpClient


async def test_recent_pull_request_normalization_and_read_only_request():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "number": 42,
                    "title": "Harden retry handling",
                    "body": "Adds bounded retry logic.",
                    "state": "closed",
                    "user": {"login": "octocat"},
                    "html_url": "https://github.com/acme/service/pull/42",
                    "base": {"ref": "main"},
                    "head": {"ref": "retry-hardening"},
                    "created_at": "2026-07-01T00:00:00Z",
                    "updated_at": "2026-07-02T00:00:00Z",
                    "merged_at": "2026-07-02T00:00:00Z",
                    "draft": False,
                    "labels": [{"name": "reliability"}],
                }
            ],
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com")
    client = GitHubHttpClient(token="fixture", http=http)
    try:
        rows = await client.recent_pull_requests(owner="acme", repository="service", limit=10)
    finally:
        await http.aclose()

    assert rows[0].number == 42
    assert rows[0].author == "octocat"
    assert rows[0].labels == ["reliability"]
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/repos/acme/service/pulls"


async def test_empty_blob_is_valid_base64_content():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/repos/acme/service/git/blobs/abc123"
        return httpx.Response(200, json={"content": "", "encoding": "base64"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.github.com")
    client = GitHubHttpClient(token="fixture", http=http)
    try:
        content = await client.blob(owner="acme", repository="service", blob_sha="abc123")
    finally:
        await http.aclose()

    assert content == b""
