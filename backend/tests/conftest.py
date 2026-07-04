"""Test bootstrap: point the app at kimbal_test + fake providers BEFORE any
app module import creates engines or caches settings."""

import os

os.environ.update(
    DATABASE_URL="postgresql+asyncpg://kimbal:kimbal_dev_password@localhost:5433/kimbal_test",
    REDIS_URL="redis://localhost:6379/1",
    LLM_PROVIDER="fake",
    EMBEDDING_PROVIDER="fake",
    APP_SECRET_KEY="test-secret-key-for-tests-only-abcdef123456",
    UPLOAD_DIR="var/test-uploads",
    RATE_LIMIT_PER_MINUTE="10000",
    CONFLUENCE_BASE_URL="",
    CONFLUENCE_API_TOKEN="",
    CONFLUENCE_EMAIL="",
    JIRA_BASE_URL="",
    JIRA_API_TOKEN="",
    JIRA_EMAIL="",
    JIRA_BOARD_ID="0",
    WEB_SEARCH_PROVIDER="fake",
    WEB_SEARCH_API_KEY="",
    WEB_SEARCH_BASE_URL="",
    LLM_COUNCIL_ENABLED="false",
    LLM_COUNCIL_MODELS="",
)

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from database.session import engine
from models import Base


@pytest.fixture(scope="session", autouse=True)
def _quiet_logs():
    from core.logging import configure_logging

    configure_logging()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db():
    from database.session import SessionFactory

    async with SessionFactory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client():
    from api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    import uuid as _uuid

    email = f"user-{_uuid.uuid4().hex[:10]}@kimbal.io"
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "SuperSecret123!",
            "full_name": "Test User",
            "organization_name": f"Org {_uuid.uuid4().hex[:6]}",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"authorization": f"Bearer {token}"}
