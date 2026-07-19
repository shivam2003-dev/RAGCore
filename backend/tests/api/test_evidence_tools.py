import asyncio
import json
import uuid

from core.config import get_settings


async def _upload_fixture(client, headers, kb_id: str) -> str:
    response = await client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={
            "file": (
                "evidence-runbook.md",
                b"# Gateway retry runbook\n\nCVIR-4242 uses retry budget ALPHA-EVIDENCE-42.",
                "text/markdown",
            )
        },
        data={"knowledge_base_id": kb_id},
    )
    assert response.status_code == 202, response.text
    document_id = response.json()["id"]
    for _ in range(30):
        document = await client.get(f"/api/v1/documents/{document_id}", headers=headers)
        if document.json()["status"] in {"ready", "failed"}:
            break
        await asyncio.sleep(0.1)
    assert document.json()["status"] == "ready", document.text
    return document_id


async def test_evidence_rest_contract_project_authorization_and_planned_ask(
    client,
    auth_headers,
    monkeypatch,
):
    kb = await client.post(
        "/api/v1/knowledge-bases",
        headers=auth_headers,
        json={"name": f"Evidence tools {uuid.uuid4().hex[:8]}", "description": "phase 5"},
    )
    assert kb.status_code == 201, kb.text
    kb_id = kb.json()["id"]
    document_id = await _upload_fixture(client, auth_headers, kb_id)
    projects = (await client.get("/api/v1/projects", headers=auth_headers)).json()
    project_id = next(item["id"] for item in projects if item["slug"] == "all-knowledge")

    capabilities = await client.get("/api/v1/tools/capabilities", headers=auth_headers)
    assert capabilities.status_code == 200
    assert capabilities.json()["read_only"] is True
    assert len(capabilities.json()["tools"]) == 7

    result = await client.post(
        "/api/v1/tools/search_knowledge",
        headers=auth_headers,
        json={"query": "ALPHA-EVIDENCE-42 retry budget", "project_id": project_id, "limit": 5},
    )
    assert result.status_code == 200, result.text
    evidence = result.json()["evidence"]
    assert evidence and evidence[0]["document_id"] == document_id
    assert evidence[0]["project_id"] == project_id
    assert evidence[0]["permission_context"]["project_id"] == project_id
    assert evidence[0]["permission_context"]["decision"] == "authorized"
    assert evidence[0]["citation_identity"]
    assert "ALPHA-EVIDENCE-42" in evidence[0]["content"]

    missing_project = await client.post(
        "/api/v1/tools/search_knowledge",
        headers=auth_headers,
        json={"query": "ALPHA-EVIDENCE-42", "project_id": str(uuid.uuid4())},
    )
    assert missing_project.status_code == 404

    plan = await client.post(
        "/api/v1/tools/plan",
        headers=auth_headers,
        json={"query": "Investigate CVIR-4242 with Slack, runbook and code", "project_id": project_id},
    )
    assert plan.status_code == 200, plan.text
    assert plan.json()["strategy"] == "deterministic"
    assert len(plan.json()["selections"]) <= 5

    settings = get_settings()
    monkeypatch.setattr(settings, "knowledge_planner_enabled", True)
    conversation = await client.post(
        "/api/v1/conversations",
        headers=auth_headers,
        json={"knowledge_base_id": kb_id, "project_id": project_id},
    )
    assert conversation.status_code == 201, conversation.text
    async with client.stream(
        "POST",
        f"/api/v1/conversations/{conversation.json()['id']}/ask",
        headers=auth_headers,
        json={"question": "What is ALPHA-EVIDENCE-42?"},
    ) as response:
        assert response.status_code == 200
        events: list[tuple[str, dict]] = []
        event_name = ""
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                event_name = line[7:]
            elif line.startswith("data: "):
                events.append((event_name, json.loads(line[6:])))
    sources = events[0][1]
    assert sources["query_classification"] == "planned_evidence"
    assert sources["retrieval_trace"]["planner"]["selected_tools"] == ["search_knowledge"]
    assert sources["sources"][0]["document_id"] == document_id
    assert events[-1][0] == "done"

    cleared = await client.delete(
        f"/api/v1/conversations/{conversation.json()['id']}/messages",
        headers=auth_headers,
    )
    assert cleared.status_code == 204
    deleted_conversation = await client.delete(
        f"/api/v1/conversations/{conversation.json()['id']}",
        headers=auth_headers,
    )
    assert deleted_conversation.status_code == 204
    deleted_document = await client.delete(
        f"/api/v1/documents/{document_id}",
        headers=auth_headers,
    )
    assert deleted_document.status_code == 204


async def test_evidence_tool_request_rejects_direct_scope_override(client, auth_headers):
    projects = (await client.get("/api/v1/projects", headers=auth_headers)).json()
    project_id = next(item["id"] for item in projects if item["slug"] == "all-knowledge")
    response = await client.post(
        "/api/v1/tools/search_knowledge",
        headers=auth_headers,
        json={
            "query": "bypass",
            "project_id": project_id,
            "user_id": str(uuid.uuid4()),
            "knowledge_base_ids": [str(uuid.uuid4())],
        },
    )
    assert response.status_code == 422
