from core.config import Settings
from services.confluence_service import ConfluenceClient, ConfluencePage, ConfluenceSpace, _page_metadata


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


def test_confluence_metadata_includes_canonical_source_fields() -> None:
    space = ConfluenceSpace(
        id="space-1",
        key="SRE",
        name="SRE",
        url="https://example.atlassian.net/wiki/spaces/SRE/overview",
    )
    page = ConfluencePage(
        id="123",
        title="HES Architecture",
        url="https://example.atlassian.net/wiki/spaces/SRE/pages/123/HES+Architecture",
        storage_html="<p>Architecture content</p>",
        version_number=7,
        version_created_at="2026-07-04T07:00:00.000Z",
    )

    metadata = _page_metadata(space=space, page=page)

    assert metadata["source"] == "confluence"
    assert metadata["source_type"] == "confluence"
    assert metadata["space"] == "SRE"
    assert metadata["page_id"] == "123"
    assert metadata["title"] == "HES Architecture"
    assert metadata["url"] == page.url
    assert metadata["updated_at"] == "2026-07-04T07:00:00.000Z"
    assert metadata["source_updated_at"] == "2026-07-04T07:00:00.000Z"
    assert metadata["acl"] == "connector-visible"
    assert metadata["connector_sync_id"] == "confluence:SRE:123:7"
    assert metadata["chunk_strategy_version"] == "confluence-heading-context-v2"
