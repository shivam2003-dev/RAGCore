import uuid


async def test_register_login_refresh_me(client):
    email = f"flow-{uuid.uuid4().hex[:8]}@kimbal.io"
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "SuperSecret123!",
            "full_name": "Flow User",
            "organization_name": f"FlowOrg {uuid.uuid4().hex[:6]}",
        },
    )
    assert reg.status_code == 201
    tokens = reg.json()

    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "SuperSecret123!"}
    )
    assert login.status_code == 200

    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]

    # rotation: same refresh token unusable twice
    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert replay.status_code == 401

    me = await client.get(
        "/api/v1/auth/me", headers={"authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == email
    assert me.json()["role"] == "admin"  # first user in org


async def test_wrong_password_rejected(client, auth_headers):
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    email = me.json()["email"]
    resp = await client.post("/api/v1/auth/login", data={"username": email, "password": "nope-wrong"})
    assert resp.status_code == 401


async def test_protected_route_requires_auth(client):
    assert (await client.get("/api/v1/knowledge-bases")).status_code == 401


async def test_duplicate_email_conflict(client, auth_headers):
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": me.json()["email"],
            "password": "SuperSecret123!",
            "full_name": "Dup",
            "organization_name": "DupOrg",
        },
    )
    assert resp.status_code == 409


async def test_api_key_auth(client, auth_headers):
    created = await client.post(
        "/api/v1/auth/api-keys", json={"name": "ci-key"}, headers=auth_headers
    )
    assert created.status_code == 201
    raw = created.json()["key"]
    assert raw.startswith("kmb_")
    via_key = await client.get("/api/v1/auth/me", headers={"x-api-key": raw})
    assert via_key.status_code == 200


async def test_weak_password_rejected(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@kimbal.io",
            "password": "short",
            "full_name": "W",
            "organization_name": "WOrg",
        },
    )
    assert resp.status_code == 422
