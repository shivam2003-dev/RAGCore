import uuid

from database.base import utcnow
from models import Document, DocumentStatus, DocumentVersion, Feedback, Message, User


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
    assert body["connector_runs"] == []


async def test_document_lineage_exposes_source_provenance(client, auth_headers, db):
    kb = await client.post(
        "/api/v1/knowledge-bases",
        json={"name": "Lineage Docs", "description": "test"},
        headers=auth_headers,
    )
    assert kb.status_code == 201, kb.text
    kb_id = uuid.UUID(kb.json()["id"])

    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me.status_code == 200, me.text
    user_id = uuid.UUID(me.json()["id"])
    doc = Document(
        knowledge_base_id=kb_id,
        collection_id=None,
        uploaded_by=user_id,
        title="SRE Runbook",
        source_type="html",
        status=DocumentStatus.READY,
        current_version=1,
        is_deleted=False,
        doc_metadata={
            "source": "confluence",
            "confluence_page_id": "12345",
            "confluence_page_url": "https://example.atlassian.net/wiki/spaces/SRE/pages/12345",
            "confluence_version": 7,
            "source_sha256": "a" * 64,
        },
    )
    db.add(doc)
    await db.flush()
    db.add(
        DocumentVersion(
            document_id=doc.id,
            version=1,
            file_path="/tmp/sre.html",
            file_sha256="b" * 64,
            file_size_bytes=128,
            created_at=utcnow(),
        )
    )
    await db.commit()

    resp = await client.get(f"/api/v1/documents/{doc.id}/lineage", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source_system"] == "confluence"
    assert body["source_id"] == "12345"
    assert body["source_url"].startswith("https://example.atlassian.net/wiki")
    assert body["source_version"] == 7
    assert body["versions"][0]["version"] == 1
    assert "api_key" not in str(body).lower()


async def test_evals_overview_uses_persisted_answer_data(client, auth_headers, db):
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me.status_code == 200, me.text
    user_id = uuid.UUID(me.json()["id"])
    user = await db.get(User, user_id)
    assert user is not None

    kb = await client.post(
        "/api/v1/knowledge-bases",
        json={"name": "Eval Docs", "description": "test"},
        headers=auth_headers,
    )
    assert kb.status_code == 201, kb.text

    conversation = await client.post(
        "/api/v1/conversations",
        json={"knowledge_base_id": kb.json()["id"], "title": "Eval question"},
        headers=auth_headers,
    )
    assert conversation.status_code == 201, conversation.text
    conversation_id = uuid.UUID(conversation.json()["id"])

    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content="How do I deploy a Kubernetes service?",
        input_tokens=None,
        output_tokens=None,
        latency_ms=None,
        timings={},
        model=None,
        created_at=utcnow(),
    )
    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content="Deploy the service with a manifest, run validation, then let ArgoCD sync the release.",
        input_tokens=30,
        output_tokens=80,
        latency_ms=1240,
        timings={"llm": 1100},
        model="fake-eval-model",
        created_at=utcnow(),
    )
    db.add_all([user_message, assistant_message])
    await db.flush()
    db.add(
        Feedback(
            message_id=assistant_message.id,
            user_id=user.id,
            rating=1,
            comment=None,
            created_at=utcnow(),
        )
    )
    await db.commit()

    resp = await client.get("/api/v1/evals/overview", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answers_total"] == 1
    assert body["sample_size"] == 1
    assert body["benchmark"]["label"] == "Kimbal Benchmark"
    assert body["benchmark"]["display"].endswith("/100")
    assert body["benchmark"]["sample_size"] == 1
    assert body["golden_dataset"]["cases"] >= 8
    assert body["golden_dataset"]["benchmark_ready"] is True
    assert {component["id"] for component in body["benchmark"]["components"]} >= {
        "groundedness",
        "citation_coverage",
        "answer_relevance",
        "success_rate",
    }
    assert body["feedback"]["helpful"] == 1
    assert body["latency"]["avg_ms"] == 1240
    assert body["models"][0]["model"] == "fake-eval-model"
    assert {score["id"] for score in body["scores"]} >= {
        "groundedness",
        "answer_relevance",
        "citation_coverage",
    }
    assert "api_key" not in str(body).lower()

    benchmark = await client.get("/api/v1/evals/benchmark", headers=auth_headers)
    assert benchmark.status_code == 200, benchmark.text
    assert benchmark.json()["display"].endswith("/100")

    golden = await client.get("/api/v1/evals/golden", headers=auth_headers)
    assert golden.status_code == 200, golden.text
    assert golden.json()["dataset_path"] == "evals/golden/rag.jsonl"


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
    assert isinstance(chat_body["council_available_models"], list)
    assert "key" not in str(chat_body).lower()


async def test_discover_feed_returns_live_shape_without_secret_material(client, auth_headers):
    resp = await client.get("/api/v1/discover/feed?department=security", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider"] == "fake"
    assert body["department"] == "security"
    assert body["departments"]
    assert body["lead"]["url"].startswith("https://")
    assert body["board_pulse"]["jira_documents"] == 0
    assert "api_key" not in str(body).lower()


async def test_role_prompt_generation_uses_configured_llm(client, auth_headers):
    resp = await client.post(
        "/api/v1/chat/roles/generate",
        json={
            "name": "Security Architect",
            "goal": "triage zero-day risk and produce remediation plans",
            "source_focus": "security Jira, Confluence advisories, and web alerts",
            "output_style": "risk summary, evidence, next actions",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Security Architect"
    assert "zero-day risk" in body["prompt"]
    assert "source-grounding" in body["prompt"]
