import asyncio
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import get_settings

MIGRATION_TEST_DATABASE_URL = os.getenv("MIGRATION_TEST_DATABASE_URL", "")


@pytest.mark.skipif(
    not MIGRATION_TEST_DATABASE_URL,
    reason="MIGRATION_TEST_DATABASE_URL must point to an explicit disposable database",
)
async def test_project_migration_upgrade_downgrade_round_trip():
    database_name = make_url(MIGRATION_TEST_DATABASE_URL).database or ""
    if "migration" not in database_name and "test" not in database_name:
        pytest.fail("Migration test refuses to use a database without migration/test in its name")

    before = await _counts(MIGRATION_TEST_DATABASE_URL)
    await asyncio.to_thread(_run_alembic, MIGRATION_TEST_DATABASE_URL, "downgrade", "0002")
    downgraded = await _schema_state(MIGRATION_TEST_DATABASE_URL)
    assert downgraded["revision"] == "0002"
    assert "projects" not in downgraded["tables"]
    assert "default_project_id" not in downgraded["user_columns"]
    assert downgraded["counts"] == before

    await asyncio.to_thread(_run_alembic, MIGRATION_TEST_DATABASE_URL, "upgrade", "0003")
    upgraded = await _schema_state(MIGRATION_TEST_DATABASE_URL)
    assert upgraded["revision"] == "0003"
    assert {
        "projects",
        "project_sources",
        "project_members",
        "source_access_grants",
    }.issubset(upgraded["tables"])
    assert "default_project_id" in upgraded["user_columns"]
    assert "project_id" in upgraded["conversation_columns"]
    assert upgraded["counts"] == before
    assert upgraded["project_count"] == before["organizations"]
    assert upgraded["project_source_count"] == before["knowledge_bases"]
    assert upgraded["project_member_count"] == before["users"]


def _run_alembic(database_url: str, action: str, revision: str) -> None:
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()
    try:
        config = Config("alembic.ini")
        if action == "upgrade":
            command.upgrade(config, revision)
        else:
            command.downgrade(config, revision)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()


async def _counts(database_url: str) -> dict[str, int]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT "
                        "(SELECT count(*) FROM organizations), "
                        "(SELECT count(*) FROM users), "
                        "(SELECT count(*) FROM knowledge_bases), "
                        "(SELECT count(*) FROM conversations)"
                    )
                )
            ).one()
            return {
                "organizations": int(row[0]),
                "users": int(row[1]),
                "knowledge_bases": int(row[2]),
                "conversations": int(row[3]),
            }
    finally:
        await engine.dispose()


async def _schema_state(database_url: str) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync_connection: set(inspect(sync_connection).get_table_names()))
            user_columns = await connection.run_sync(
                lambda sync_connection: {column["name"] for column in inspect(sync_connection).get_columns("users")}
            )
            conversation_columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"] for column in inspect(sync_connection).get_columns("conversations")
                }
            )
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            state: dict[str, object] = {
                "tables": tables,
                "user_columns": user_columns,
                "conversation_columns": conversation_columns,
                "revision": revision,
                "counts": await _counts(database_url),
                "project_count": 0,
                "project_source_count": 0,
                "project_member_count": 0,
            }
            if "projects" in tables:
                state["project_count"] = int(await connection.scalar(text("SELECT count(*) FROM projects")) or 0)
                state["project_source_count"] = int(
                    await connection.scalar(text("SELECT count(*) FROM project_sources")) or 0
                )
                state["project_member_count"] = int(
                    await connection.scalar(text("SELECT count(*) FROM project_members")) or 0
                )
            return state
    finally:
        await engine.dispose()
