async def test_metrics_overview_uses_live_database_counts(client, auth_headers):
    kb = await client.post(
        "/api/v1/knowledge-bases",
        json={"name": "Metrics Docs", "description": "test"},
        headers=auth_headers,
    )
    assert kb.status_code == 201, kb.text

    metrics = await client.get("/api/v1/metrics/overview", headers=auth_headers)
    assert metrics.status_code == 200, metrics.text
    body = metrics.json()
    assert body["knowledge_bases"] >= 1
    assert body["documents_total"] == 0
    assert body["questions_asked"] == 0
    assert body["feedback"]["total"] == 0
    assert body["sources"] == []


async def test_connector_status_endpoints_are_read_only_and_secret_safe(client, auth_headers):
    confluence = await client.get("/api/v1/confluence/status", headers=auth_headers)
    assert confluence.status_code == 200, confluence.text
    confluence_body = confluence.json()
    assert confluence_body["read_only"] is True
    assert confluence_body["configured"] is False
    assert "token" not in str(confluence_body.get("base_url", ""))

    jira = await client.get("/api/v1/jira/status", headers=auth_headers)
    assert jira.status_code == 200, jira.text
    jira_body = jira.json()
    assert jira_body["read_only"] is True
    assert jira_body["configured"] is False
    assert "token" not in str(jira_body.get("base_url", ""))


async def test_web_search_and_chat_capabilities_are_explicit(client, auth_headers):
    web = await client.get("/api/v1/web-search/status", headers=auth_headers)
    assert web.status_code == 200, web.text
    web_body = web.json()
    assert web_body["configured"] is True
    assert web_body["provider"] == "fake"

    chat = await client.get("/api/v1/chat/capabilities", headers=auth_headers)
    assert chat.status_code == 200, chat.text
    chat_body = chat.json()
    assert chat_body["answer_modes"] == ["fast", "council"]
    assert chat_body["council_configured"] is False
    assert "key" not in str(chat_body).lower()
