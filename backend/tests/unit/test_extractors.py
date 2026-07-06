from ingestion.extractors.registry import HtmlExtractor


def test_html_extractor_preserves_headings_and_tables(tmp_path):
    path = tmp_path / "page.html"
    path.write_text(
        """
        <html>
          <head><title>HES Architecture</title></head>
          <body>
            <h1>HES Architecture</h1>
            <h2>Broker Flow</h2>
            <p>Broker receives meter events.</p>
            <table>
              <tr><th>Component</th><th>Owner</th></tr>
              <tr><td>Broker</td><td>SRE</td></tr>
            </table>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    extracted = HtmlExtractor().extract(path)

    assert "# HES Architecture" in extracted.text
    assert "## Broker Flow" in extracted.text
    assert "Component | Owner" in extracted.text
    assert extracted.metadata["headings"] == ["HES Architecture", "Broker Flow"]
    assert extracted.metadata["format"] == "html"
