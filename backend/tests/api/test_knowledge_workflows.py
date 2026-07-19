import uuid
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import delete, select, update

from database.base import utcnow
from models import (
    Chunk,
    ConnectorState,
    Document,
    DocumentStatus,
    DocumentVersion,
    GitHubRepositoryMapping,
    Organization,
    Role,
    User,
)


async def _default_project(client, headers) -> dict:
    projects = (await client.get("/api/v1/projects", headers=headers)).json()
    return next(item for item in projects if item["slug"] == "all-knowledge")


async def _isolated_headers(client, db) -> tuple[dict[str, str], uuid.UUID]:
    suffix = uuid.uuid4().hex[:10]
    email = f"workflow-{suffix}@kimbal.io"
    password = "WorkflowTest123!"
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Workflow Test Admin",
            "organization_name": f"Workflow Test {suffix}",
        },
    )
    assert response.status_code == 201, response.text
    user = await db.scalar(select(User).where(User.email == email))
    assert user is not None
    user.role = Role.ADMIN
    await db.commit()
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return {"authorization": f"Bearer {login.json()['access_token']}"}, user.organization_id


@pytest_asyncio.fixture
async def workflow_auth(client, db):
    headers, organization_id = await _isolated_headers(client, db)
    yield headers
    await db.rollback()
    await db.execute(
        update(User).where(User.organization_id == organization_id).values(default_project_id=None)
    )
    await db.execute(delete(Organization).where(Organization.id == organization_id))
    await db.commit()


async def _create_kb(client, headers, name: str) -> str:
    response = await client.post(
        "/api/v1/knowledge-bases",
        headers=headers,
        json={"name": f"{name} {uuid.uuid4().hex[:7]}", "description": "workflow fixture"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _add_document(
    db,
    *,
    kb_id: str,
    title: str,
    content: str,
    metadata: dict,
    current_version: int = 1,
    status: DocumentStatus = DocumentStatus.READY,
) -> Document:
    document = Document(
        knowledge_base_id=uuid.UUID(kb_id),
        title=title,
        source_type="md",
        status=status,
        current_version=current_version,
        doc_metadata=metadata,
    )
    db.add(document)
    await db.flush()
    if status is DocumentStatus.READY:
        version = DocumentVersion(
            document_id=document.id,
            version=current_version,
            file_path="/dev/null",
            file_sha256=uuid.uuid4().hex * 2,
            file_size_bytes=len(content),
            created_at=utcnow(),
        )
        db.add(version)
        await db.flush()
        db.add(
            Chunk(
                knowledge_base_id=document.knowledge_base_id,
                document_id=document.id,
                document_version_id=version.id,
                ordinal=0,
                content=content,
                token_count=max(1, len(content.split())),
                chunk_metadata={"source": metadata.get("source")},
                created_at=utcnow(),
            )
        )
    await db.commit()
    return document


async def test_incident_experts_changes_and_freshness_use_cited_authorized_evidence(
    client,
    db,
    workflow_auth,
):
    auth_headers = workflow_auth
    project = await _default_project(client, auth_headers)
    now = datetime.now(UTC)
    jira_kb = await _create_kb(client, auth_headers, "Workflow Jira")
    slack_kb = await _create_kb(client, auth_headers, "Workflow Slack")
    confluence_kb = await _create_kb(client, auth_headers, "Workflow Confluence")
    github_kb = await _create_kb(client, auth_headers, "Workflow GitHub")

    jira = await _add_document(
        db,
        kb_id=jira_kb,
        title="CVIR-4242: Gateway retry exhaustion",
        content="CVIR-4242 gateway retry budget exhausted. Current status is Investigating.",
        metadata={
            "source": "jira",
            "source_id": "CVIR-4242",
            "source_url": "https://jira.example/browse/CVIR-4242",
            "source_updated_at": now.isoformat(),
            "source_inventory_key": "jira:CVIR-4242",
            "jira_issue_status": "Investigating",
            "jira_assignee": "Alice SRE",
            "jira_reporter": "Carol Ops",
        },
        current_version=2,
    )
    await _add_document(
        db,
        kb_id=slack_kb,
        title="CVIR-4242 public incident thread",
        content="CVIR-4242 gateway retry discussion and resolution validation.",
        metadata={
            "source": "slack",
            "source_id": "T1:C1:4242.1",
            "source_url": "https://example.slack.com/archives/C1/p42421",
            "source_updated_at": (now - timedelta(days=61)).isoformat(),
            "source_inventory_key": "slack:T1:C1:4242.1",
            "participants": [
                {"id": "U1", "display_name": "Alice SRE"},
                {"id": "U2", "display_name": "Bob Platform"},
            ],
        },
    )
    await _add_document(
        db,
        kb_id=confluence_kb,
        title="Gateway retry runbook",
        content="Gateway retry runbook for CVIR-4242: validate upstream health and retry budget.",
        metadata={
            "source": "confluence",
            "source_id": "page-4242",
            "source_url": "https://wiki.example/pages/4242",
            "source_updated_at": now.isoformat(),
            "source_inventory_key": "confluence:page-4242",
            "confluence_author": "Bob Platform",
        },
    )
    code = await _add_document(
        db,
        kb_id=github_kb,
        title="acme/gateway:src/retry.py",
        content="def gateway_retry_budget(): # CVIR-4242 gateway retry\n    return 3",
        metadata={
            "source": "github",
            "source_id": "acme/gateway:main:src/retry.py",
            "source_url": "https://github.com/acme/gateway/blob/abc/src/retry.py",
            "source_updated_at": now.isoformat(),
            "source_inventory_key": "github:acme/gateway:src/retry.py",
            "github_path": "src/retry.py",
            "github_codeowners": ["Alice SRE"],
            "github_contributors": ["Bob Platform"],
        },
    )
    await _add_document(
        db,
        kb_id=github_kb,
        title="acme/gateway:src/retry.py duplicate snapshot",
        content="gateway retry duplicate change record",
        metadata={
            "source": "github",
            "source_id": "acme/gateway:main:src/retry.py",
            "source_url": "https://github.com/acme/gateway/blob/def/src/retry.py",
            "source_updated_at": now.isoformat(),
            "source_inventory_key": "github:acme/gateway:src/retry.py",
        },
    )
    await _add_document(
        db,
        kb_id=jira_kb,
        title="Failed Jira fixture",
        content="",
        metadata={"source": "jira", "source_id": "CVIR-FAILED", "source_updated_at": now.isoformat()},
        status=DocumentStatus.FAILED,
    )

    incident = await client.post(
        "/api/v1/workflows/incident",
        headers=auth_headers,
        json={"project_id": project["id"], "issue_key": "cvir-4242"},
    )
    assert incident.status_code == 200, incident.text
    incident_body = incident.json()
    assert incident_body["issue_key"] == "CVIR-4242"
    assert incident_body["current_status"] == "Investigating"
    assert incident_body["owner"] == "Alice SRE"
    assert incident_body["timeline"]
    assert all(item["citation_identity"] for item in incident_body["timeline"])
    assert all("CVIR-4242" in item["label"] or "CVIR-4242" in item["detail"] for item in incident_body["timeline"])
    assert all(text.startswith("Fact [") for text in incident_body["facts"])
    assert all(text.startswith("Inference:") for text in incident_body["likely_next_actions"])
    assert any(item["source_type"] == "github" for item in incident_body["evidence"])
    assert "No authorized recent pull-request evidence was found." in incident_body["missing_evidence"]

    experts = await client.post(
        "/api/v1/workflows/experts",
        headers=auth_headers,
        json={"project_id": project["id"], "query": "CVIR-4242 gateway retry", "limit": 5},
    )
    assert experts.status_code == 200, experts.text
    expert_rows = experts.json()["experts"]
    assert expert_rows[0]["person"] == "Alice SRE"
    assert expert_rows[0]["score"] > expert_rows[1]["score"]
    assert expert_rows[0]["signals"]
    assert expert_rows[0]["citation_identity"]

    changes = await client.post(
        "/api/v1/workflows/changes",
        headers=auth_headers,
        json={
            "project_id": project["id"],
            "start_date": now.date().isoformat(),
            "end_date": now.date().isoformat(),
            "limit": 100,
        },
    )
    assert changes.status_code == 200, changes.text
    change_body = changes.json()
    assert change_body["changes"]
    assert change_body["deduplicated_count"] >= 1
    assert all(item["citation_identity"] for item in change_body["changes"])
    assert sum(change_body["source_counts"].values()) == len(change_body["changes"])

    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    user = await db.get(User, uuid.UUID(me.json()["id"]))
    state = await db.scalar(
        select(ConnectorState).where(
            ConnectorState.organization_id == user.organization_id,
            ConnectorState.kind == "github",
        )
    )
    if state is None:
        state = ConnectorState(
            organization_id=user.organization_id,
            created_by=user.id,
            kind="github",
            status="connected",
            config={},
            failure_count=0,
        )
        db.add(state)
        await db.flush()
    else:
        state.status = "connected"
    db.add(
        GitHubRepositoryMapping(
            organization_id=user.organization_id,
            connector_state_id=state.id,
            project_id=uuid.UUID(project["id"]),
            knowledge_base_id=uuid.UUID(github_kb),
            owner="acme",
            repository="gateway",
            branch="main",
            path_allowlist=[],
            path_denylist=[],
            is_enabled=True,
            status="configured",
        )
    )
    await db.commit()

    freshness = await client.get(
        "/api/v1/workflows/freshness",
        headers=auth_headers,
        params={"project_id": project["id"]},
    )
    assert freshness.status_code == 200, freshness.text
    health = freshness.json()
    assert health["stale_sources"] >= 1
    assert health["outdated_slack_resolutions"] >= 1
    assert health["failing_sources"] >= 1
    assert health["repository_branch_lag"] >= 1
    assert health["replaced_documents"] >= 1
    assert health["total_findings"] >= len(health["issues"])
    assert health["score"] < 100
    assert health["suggestions"]
    assert jira.id != code.id


async def test_incident_partial_sources_date_validation_and_project_authorization(
    client,
    db,
    workflow_auth,
):
    auth_headers = workflow_auth
    created = await client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": f"Partial incident {uuid.uuid4().hex[:6]}", "description": "Jira only"},
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    kb_id = await _create_kb(client, auth_headers, "Partial Jira")
    mapped = await client.put(
        f"/api/v1/projects/{project_id}/sources",
        headers=auth_headers,
        json={"knowledge_base_ids": [kb_id]},
    )
    assert mapped.status_code == 200, mapped.text
    await _add_document(
        db,
        kb_id=kb_id,
        title="CVIR-9000: Partial source incident",
        content="CVIR-9000 is Open and owned by Dana.",
        metadata={
            "source": "jira",
            "source_id": "CVIR-9000",
            "source_updated_at": datetime.now(UTC).isoformat(),
            "jira_issue_status": "Open",
            "jira_assignee": "Dana",
        },
    )
    incident = await client.post(
        "/api/v1/workflows/incident",
        headers=auth_headers,
        json={"project_id": project_id, "issue_key": "CVIR-9000"},
    )
    assert incident.status_code == 200, incident.text
    body = incident.json()
    assert body["partial"] is True
    assert body["current_status"] == "Open"
    assert any("Slack" in item for item in body["missing_evidence"])
    assert any("code" in item for item in body["missing_evidence"])

    invalid_range = await client.post(
        "/api/v1/workflows/changes",
        headers=auth_headers,
        json={"project_id": project_id, "start_date": "2026-07-20", "end_date": "2026-07-19"},
    )
    assert invalid_range.status_code == 422
    too_wide = await client.post(
        "/api/v1/workflows/changes",
        headers=auth_headers,
        json={"project_id": project_id, "start_date": "2024-01-01", "end_date": "2026-07-19"},
    )
    assert too_wide.status_code == 422

    missing_project = str(uuid.uuid4())
    for path, payload in (
        ("/api/v1/workflows/incident", {"project_id": missing_project, "issue_key": "CVIR-9000"}),
        ("/api/v1/workflows/experts", {"project_id": missing_project, "query": "gateway"}),
        (
            "/api/v1/workflows/changes",
            {"project_id": missing_project, "start_date": "2026-07-19", "end_date": "2026-07-19"},
        ),
    ):
        response = await client.post(path, headers=auth_headers, json=payload)
        assert response.status_code == 404
    freshness = await client.get(
        "/api/v1/workflows/freshness",
        headers=auth_headers,
        params={"project_id": missing_project},
    )
    assert freshness.status_code == 404
