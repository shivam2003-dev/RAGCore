"""Full API-level RAG flow with fake providers: KB → upload → ingest → search → chat → feedback."""

import asyncio
import json
import uuid


async def _create_kb(client, headers) -> str:
    resp = await client.post(
        "/api/v1/knowledge-bases",
        json={"name": f"Docs {uuid.uuid4().hex[:8]}", "description": "test"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _upload_and_wait(client, headers, kb_id: str) -> str:
    content = (
        b"# Deploy Guide\n\nPush the image to harbor.kimbal.io registry. "
        b"Then create a pull request in infrastructure-configs and ArgoCD syncs it.\n"
    )
    resp = await client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": ("guide.md", content, "text/markdown")},
        data={"knowledge_base_id": kb_id},
    )
    assert resp.status_code == 202, resp.text
    doc_id = resp.json()["id"]
    for _ in range(20):  # background ingestion
        doc = (await client.get(f"/api/v1/documents/{doc_id}", headers=headers)).json()
        if doc["status"] in ("ready", "failed"):
            break
        await asyncio.sleep(0.2)
    assert doc["status"] == "ready", doc.get("error")
    return doc_id


async def test_full_rag_flow(client, auth_headers):
    kb_id = await _create_kb(client, auth_headers)
    doc_id = await _upload_and_wait(client, auth_headers, kb_id)

    # hybrid search
    search = await client.post(
        "/api/v1/search",
        json={"query": "how to deploy image registry", "knowledge_base_id": kb_id, "top_k": 3},
        headers=auth_headers,
    )
    assert search.status_code == 200
    hits = search.json()["hits"]
    assert hits and hits[0]["document_id"] == doc_id
    assert "timings_ms" in search.json()

    # conversation + streamed ask
    conv = await client.post(
        "/api/v1/conversations", json={"knowledge_base_id": kb_id}, headers=auth_headers
    )
    conv_id = conv.json()["id"]
    async with client.stream(
        "POST",
        f"/api/v1/conversations/{conv_id}/ask",
        json={"question": "How do I deploy?"},
        headers=auth_headers,
    ) as resp:
        assert resp.status_code == 200
        events: list[tuple[str, str]] = []
        current_event = ""
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                current_event = line[7:]
            elif line.startswith("data: "):
                events.append((current_event, line[6:]))
    event_types = [e for e, _ in events]
    assert event_types[0] == "sources"
    assert "delta" in event_types
    assert event_types[-1] == "done"
    done = json.loads(events[-1][1])
    assert done["usage"]["output_tokens"] >= 0
    assert done["latency_ms"] >= 0
    message_id = done["message_id"]

    # persisted history with citations (FakeLLM cites [1])
    messages = (
        await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)
    ).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["citations"], "fake LLM emits [n] markers"

    # conversational follow-up: backend rewrites before retrieval, then persists the new turn
    async with client.stream(
        "POST",
        f"/api/v1/conversations/{conv_id}/ask",
        json={"question": "Where do I push it?"},
        headers=auth_headers,
    ) as resp:
        assert resp.status_code == 200
        followup_events: list[tuple[str, str]] = []
        current_event = ""
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                current_event = line[7:]
            elif line.startswith("data: "):
                followup_events.append((current_event, line[6:]))
    followup_sources = json.loads(followup_events[0][1])
    assert followup_sources["standalone_question"] != "Where do I push it?"
    assert followup_events[-1][0] == "done"

    messages = (
        await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)
    ).json()
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]

    # feedback
    fb = await client.post(
        "/api/v1/feedback",
        json={"message_id": message_id, "rating": 1, "comment": "good"},
        headers=auth_headers,
    )
    assert fb.status_code == 201

    clear = await client.delete(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)
    assert clear.status_code == 204
    messages = (
        await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)
    ).json()
    assert messages == []


async def test_web_only_ask_streams_and_persists_citations(client, auth_headers):
    kb_id = await _create_kb(client, auth_headers)
    conv = await client.post(
        "/api/v1/conversations",
        json={"knowledge_base_id": kb_id, "title": "web search"},
        headers=auth_headers,
    )
    assert conv.status_code == 201, conv.text
    conv_id = conv.json()["id"]

    async with client.stream(
        "POST",
        f"/api/v1/conversations/{conv_id}/ask",
        json={"question": "What is current web context?", "source_mode": "web"},
        headers=auth_headers,
    ) as resp:
        assert resp.status_code == 200
        events: list[tuple[str, str]] = []
        current_event = ""
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                current_event = line[7:]
            elif line.startswith("data: "):
                events.append((current_event, line[6:]))

    event_types = [event_type for event_type, _payload in events]
    assert event_types[0] == "sources"
    assert "delta" in event_types
    assert event_types[-1] == "done"

    sources_payload = json.loads(events[0][1])
    assert sources_payload["source_mode"] == "web"
    assert sources_payload["sources"][0]["source_type"] == "web"
    assert sources_payload["sources"][0]["url"] == "https://example.com/kimbal-web-search"

    done = json.loads(events[-1][1])
    assert done["source_mode"] == "web"
    assert done["message_id"]

    messages = (
        await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=auth_headers)
    ).json()
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["citations"], "web chunks are persisted and citable"


async def test_upload_rejects_wrong_magic_bytes(client, auth_headers):
    kb_id = await _create_kb(client, auth_headers)
    resp = await client.post(
        "/api/v1/documents/upload",
        headers=auth_headers,
        files={"file": ("evil.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")},
        data={"knowledge_base_id": kb_id},
    )
    assert resp.status_code == 422


async def test_document_delete_removes_from_search(client, auth_headers):
    kb_id = await _create_kb(client, auth_headers)
    doc_id = await _upload_and_wait(client, auth_headers, kb_id)
    assert (
        await client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers)
    ).status_code == 204
    search = await client.post(
        "/api/v1/search",
        json={"query": "deploy image registry", "knowledge_base_id": kb_id},
        headers=auth_headers,
    )
    assert all(h["document_id"] != doc_id for h in search.json()["hits"])


async def test_rbac_viewer_cannot_upload(client, auth_headers):
    # register a second Kimbal user → viewer role
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    org_admin_email = me.json()["email"]
    org_name_resp = await client.get("/api/v1/knowledge-bases", headers=auth_headers)
    assert org_name_resp.status_code == 200
    _ = org_admin_email

    kb_id = await _create_kb(client, auth_headers)
    import uuid as _uuid

    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"viewer-{_uuid.uuid4().hex[:8]}@kimbal.io",
            "password": "SuperSecret123!",
            "full_name": "Viewer",
            "organization_name": "SharedOrgForRBAC",
        },
    )
    assert reg.status_code == 201
    assert reg.json()["access_token"]
    viewer_headers = {"authorization": f"Bearer {reg.json()['access_token']}"}
    resp = await client.post(
        "/api/v1/documents/upload",
        headers=viewer_headers,
        files={"file": ("x.txt", b"hello", "text/plain")},
        data={"knowledge_base_id": kb_id},
    )
    assert resp.status_code == 403
