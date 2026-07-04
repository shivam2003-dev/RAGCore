from core.config import Settings
from services.confluence_service import ConfluenceClient


def test_confluence_v1_page_parser_preserves_source_link_and_version() -> None:
    client = ConfluenceClient(Settings(confluence_base_url="https://example.atlassian.net/wiki/spaces/DEV/overview"))

    page = client._parse_v1_page(
        {
            "id": "123",
            "title": "Runbook",
            "_links": {"webui": "/wiki/spaces/DEV/pages/123/Runbook"},
            "body": {"storage": {"value": "<p>Deploy safely</p>"}},
            "version": {"number": 7, "when": "2026-07-04T07:00:00.000Z"},
        }
    )

    assert page.id == "123"
    assert page.title == "Runbook"
    assert page.url == "https://example.atlassian.net/wiki/spaces/DEV/pages/123/Runbook"
    assert page.storage_html == "<p>Deploy safely</p>"
    assert page.version_number == 7
    assert page.version_created_at == "2026-07-04T07:00:00.000Z"
