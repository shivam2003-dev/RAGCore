import asyncio
import uuid


async def _create_user(client, headers, *, role: str) -> tuple[dict, str]:
    email = f"project-{role}-{uuid.uuid4().hex[:8]}@cvum.io"
    password = "SuperSecret123!"
    created = await client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": email,
            "password": password,
            "full_name": f"Project {role.title()}",
            "role": role,
        },
    )
    assert created.status_code == 201, created.text
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return created.json(), f"Bearer {token}"


async def _create_kb(client, headers, name: str) -> str:
    response = await client.post(
        "/api/v1/knowledge-bases",
        headers=headers,
        json={"name": f"{name} {uuid.uuid4().hex[:8]}", "description": "project ACL test"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["access_scope"] == "organization"
    return response.json()["id"]


async def _create_project(client, headers, name: str, source_ids: list[str]) -> dict:
    created = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": name, "description": f"Scope for {name}"},
    )
    assert created.status_code == 201, created.text
    project = created.json()
    mapped = await client.put(
        f"/api/v1/projects/{project['id']}/sources",
        headers=headers,
        json={"knowledge_base_ids": source_ids},
    )
    assert mapped.status_code == 200, mapped.text
    assert set(mapped.json()["source_ids"]) == set(source_ids)
    return mapped.json()


async def _upload_and_wait(client, headers, kb_id: str, filename: str, text: str) -> str:
    response = await client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": (filename, text.encode(), "text/plain")},
        data={"knowledge_base_id": kb_id},
    )
    assert response.status_code == 202, response.text
    document_id = response.json()["id"]
    for _ in range(30):
        document = await client.get(f"/api/v1/documents/{document_id}", headers=headers)
        assert document.status_code == 200, document.text
        if document.json()["status"] in {"ready", "failed"}:
            break
        await asyncio.sleep(0.1)
    assert document.json()["status"] == "ready", document.text
    return document_id


async def test_project_crud_default_persistence_and_role_matrix(client, auth_headers):
    editor, editor_token = await _create_user(client, auth_headers, role="editor")
    viewer, viewer_token = await _create_user(client, auth_headers, role="viewer")
    editor_headers = {"authorization": editor_token}
    viewer_headers = {"authorization": viewer_token}

    viewer_create = await client.post(
        "/api/v1/projects",
        headers=viewer_headers,
        json={"name": "Viewer forbidden"},
    )
    assert viewer_create.status_code == 403

    created = await client.post(
        "/api/v1/projects",
        headers=editor_headers,
        json={"name": f"Editor Project {uuid.uuid4().hex[:6]}", "description": "managed"},
    )
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["user_project_role"] == "manager"

    kb_id = await _create_kb(client, auth_headers, "Editor source")
    editor_map = await client.put(
        f"/api/v1/projects/{project['id']}/sources",
        headers=editor_headers,
        json={"knowledge_base_ids": [kb_id]},
    )
    assert editor_map.status_code == 200, editor_map.text

    editor_member_write = await client.put(
        f"/api/v1/projects/{project['id']}/members",
        headers=editor_headers,
        json={"members": [{"user_id": editor["id"], "project_role": "manager"}]},
    )
    assert editor_member_write.status_code == 403

    admin_members = await client.put(
        f"/api/v1/projects/{project['id']}/members",
        headers=auth_headers,
        json={
            "members": [
                {"user_id": editor["id"], "project_role": "manager"},
                {"user_id": viewer["id"], "project_role": "member"},
            ]
        },
    )
    assert admin_members.status_code == 200, admin_members.text

    viewer_map = await client.put(
        f"/api/v1/projects/{project['id']}/sources",
        headers=viewer_headers,
        json={"knowledge_base_ids": [kb_id]},
    )
    assert viewer_map.status_code == 403

    selected = await client.put(
        "/api/v1/users/me/default-project",
        headers=viewer_headers,
        json={"project_id": project["id"]},
    )
    assert selected.status_code == 200, selected.text
    me = await client.get("/api/v1/auth/me", headers=viewer_headers)
    assert me.status_code == 200
    assert me.json()["default_project_id"] == project["id"]

    updated = await client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=editor_headers,
        json={"description": "updated by manager"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "updated by manager"

    deleted = await client.delete(
        f"/api/v1/projects/{project['id']}",
        headers=editor_headers,
    )
    assert deleted.status_code == 204
    invisible = await client.get(f"/api/v1/projects/{project['id']}", headers=viewer_headers)
    assert invisible.status_code == 404


async def test_project_scope_and_restricted_source_grants_are_enforced(client, auth_headers):
    viewer, viewer_token = await _create_user(client, auth_headers, role="viewer")
    viewer_headers = {"authorization": viewer_token}
    kb_alpha = await _create_kb(client, auth_headers, "Alpha ACL")
    kb_beta = await _create_kb(client, auth_headers, "Beta ACL")
    alpha_document = await _upload_and_wait(
        client,
        auth_headers,
        kb_alpha,
        "alpha.txt",
        "The shared lookup phrase resolves to alpha-only deployment guidance.",
    )
    beta_document = await _upload_and_wait(
        client,
        auth_headers,
        kb_beta,
        "beta.txt",
        "The shared lookup phrase resolves to beta-only incident guidance.",
    )
    project_alpha = await _create_project(client, auth_headers, "Alpha Project", [kb_alpha])
    project_beta = await _create_project(client, auth_headers, "Beta Project", [kb_beta])

    for project in (project_alpha, project_beta):
        membership = await client.put(
            f"/api/v1/projects/{project['id']}/members",
            headers=auth_headers,
            json={"members": [{"user_id": viewer["id"], "project_role": "member"}]},
        )
        assert membership.status_code == 200, membership.text

    restricted = await client.put(
        f"/api/v1/knowledge-bases/{kb_beta}/permissions",
        headers=auth_headers,
        json={"access_scope": "restricted", "user_ids": []},
    )
    assert restricted.status_code == 200, restricted.text

    membership_does_not_grant = await client.post(
        "/api/v1/search",
        headers=viewer_headers,
        json={
            "query": "shared lookup phrase",
            "knowledge_base_id": kb_beta,
            "project_id": project_beta["id"],
        },
    )
    assert membership_does_not_grant.status_code == 404

    cross_project = await client.post(
        "/api/v1/search",
        headers=viewer_headers,
        json={
            "query": "shared lookup phrase",
            "knowledge_base_id": kb_alpha,
            "project_id": project_beta["id"],
        },
    )
    assert cross_project.status_code == 404

    granted = await client.put(
        f"/api/v1/knowledge-bases/{kb_beta}/permissions",
        headers=auth_headers,
        json={"access_scope": "restricted", "user_ids": [viewer["id"]]},
    )
    assert granted.status_code == 200, granted.text

    viewer_project = await client.get(
        f"/api/v1/projects/{project_beta['id']}",
        headers=viewer_headers,
    )
    assert viewer_project.status_code == 200
    assert viewer_project.json()["authorized_source_ids"] == [kb_beta]

    direct_document_denied = await client.get(
        f"/api/v1/documents/{beta_document}",
        headers=auth_headers,
    )
    assert direct_document_denied.status_code == 404
    filtered_document_list = await client.get("/api/v1/documents", headers=auth_headers)
    assert filtered_document_list.status_code == 200
    assert beta_document not in {item["id"] for item in filtered_document_list.json()["items"]}

    alpha = await client.post(
        "/api/v1/search",
        headers=viewer_headers,
        json={
            "query": "shared lookup phrase",
            "knowledge_base_id": kb_alpha,
            "project_id": project_alpha["id"],
        },
    )
    assert alpha.status_code == 200, alpha.text
    assert alpha.json()["hits"][0]["document_id"] == alpha_document
    assert alpha.json()["trace"] is None

    beta = await client.post(
        "/api/v1/search",
        headers=viewer_headers,
        json={
            "query": "shared lookup phrase",
            "knowledge_base_id": kb_beta,
            "project_id": project_beta["id"],
        },
    )
    assert beta.status_code == 200, beta.text
    assert beta.json()["hits"][0]["document_id"] == beta_document
    assert all(hit["document_id"] != alpha_document for hit in beta.json()["hits"])

    conversation = await client.post(
        "/api/v1/conversations",
        headers=viewer_headers,
        json={
            "knowledge_base_id": kb_beta,
            "project_id": project_beta["id"],
            "title": "Beta-scoped conversation",
        },
    )
    assert conversation.status_code == 201, conversation.text
    assert conversation.json()["project_id"] == project_beta["id"]

    revoked = await client.put(
        f"/api/v1/knowledge-bases/{kb_beta}/permissions",
        headers=auth_headers,
        json={"access_scope": "restricted", "user_ids": []},
    )
    assert revoked.status_code == 200
    denied_after_revoke = await client.post(
        "/api/v1/search",
        headers=viewer_headers,
        json={
            "query": "shared lookup phrase",
            "knowledge_base_id": kb_beta,
            "project_id": project_beta["id"],
        },
    )
    assert denied_after_revoke.status_code == 404

    direct_kb_denied = await client.get(
        f"/api/v1/knowledge-bases/{kb_beta}",
        headers=viewer_headers,
    )
    assert direct_kb_denied.status_code == 404

    collections_denied = await client.get(
        f"/api/v1/knowledge-bases/{kb_beta}/collections",
        headers=viewer_headers,
    )
    assert collections_denied.status_code == 404


async def test_cross_organization_project_is_not_discoverable(client, auth_headers, db):
    from core.security import hash_password
    from models import Organization, Project, ProjectMember, ProjectRole, Role, User

    other_org = Organization(name="Other Organization", slug=f"other-{uuid.uuid4().hex[:8]}")
    db.add(other_org)
    await db.flush()
    other_user = User(
        organization_id=other_org.id,
        email=f"other-{uuid.uuid4().hex[:8]}@cvum.io",
        password_hash=hash_password("SuperSecret123!"),
        full_name="Other Admin",
        role=Role.ADMIN,
    )
    db.add(other_user)
    await db.flush()
    other_project = Project(
        organization_id=other_org.id,
        name="Other Private Project",
        slug="other-private",
        description="must not be visible",
    )
    db.add(other_project)
    await db.flush()
    db.add(
        ProjectMember(
            organization_id=other_org.id,
            project_id=other_project.id,
            user_id=other_user.id,
            project_role=ProjectRole.MANAGER,
        )
    )
    await db.commit()

    response = await client.get(f"/api/v1/projects/{other_project.id}", headers=auth_headers)
    assert response.status_code == 404
