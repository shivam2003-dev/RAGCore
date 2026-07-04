from services.discover_service import _parse_department_query_overrides, _parse_google_news_rss, department_catalog


def test_department_query_overrides_are_parsed_from_env_style_string() -> None:
    overrides = _parse_department_query_overrides("security=zero day CVE; devops=ArgoCD GitOps\nbad-entry")

    assert overrides == {"security": "zero day CVE", "devops": "ArgoCD GitOps"}
    departments = {item.id: item for item in department_catalog("security=zero day CVE")}
    assert departments["security"].query == "zero day CVE"
    assert departments["sre"].query


def test_google_news_rss_parser_returns_source_backed_rows() -> None:
    rss = """<?xml version="1.0" encoding="UTF-8" ?>
    <rss><channel><item>
      <title>Critical Kubernetes advisory released</title>
      <link>https://example.com/k8s-advisory</link>
      <source url="https://example.com">Example News</source>
      <pubDate>Sat, 04 Jul 2026 10:00:00 GMT</pubDate>
      <description><![CDATA[<p>Teams should review the patch guidance.</p>]]></description>
    </item></channel></rss>
    """

    rows = _parse_google_news_rss(rss, max_results=5)

    assert rows == [
        {
            "title": "Critical Kubernetes advisory released",
            "url": "https://example.com/k8s-advisory",
            "source": "Example News",
            "summary": "Teams should review the patch guidance.",
            "published_at": "2026-07-04T10:00:00+00:00",
            "score": 1.0,
        }
    ]
