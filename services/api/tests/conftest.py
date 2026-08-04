"""Shared test fixtures.

Database tests run against a real Postgres with PostGIS — row-level security policies and CHECK
constraints cannot be meaningfully tested against a fake. When no database is configured (a fresh
checkout, or a contributor who has not installed PostGIS yet) those tests skip rather than fail, and
CI always provides one so they always run there.

Set GROUNDWORK_TEST_DATABASE_URL to point at a scratch database. Its schema is dropped and rebuilt
from the migrations for each test session.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio

from app.db.migrate import migrate

TEST_DSN = os.environ.get("GROUNDWORK_TEST_DATABASE_URL", "")

requires_db = pytest.mark.skipif(
    not TEST_DSN,
    reason="set GROUNDWORK_TEST_DATABASE_URL to run database tests",
)


async def _rebuild_schema(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        # A clean public schema means the migrations are exercised from zero every run — the same
        # path a new environment takes. The app role is cluster-wide and outlives the schema; it
        # owns nothing, so its grants disappear with the tables and migration 004 re-issues them.
        await conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        await conn.execute("CREATE SCHEMA public")
    finally:
        await conn.close()

    await migrate(dsn)


@pytest.fixture(scope="session")
def migrated_dsn() -> str:
    """Rebuild the test schema once per session, then hand back the DSN.

    Deliberately synchronous: a session-scoped *async* fixture runs on its own event loop, and the
    connections it opens cannot then be used by function-scoped tests. Doing the setup inside
    asyncio.run() keeps every async fixture on the loop of the test that asked for it.
    """
    if not TEST_DSN:
        pytest.skip("no test database configured")

    asyncio.run(_rebuild_schema(TEST_DSN))
    return TEST_DSN


@pytest_asyncio.fixture
async def db(migrated_dsn: str) -> AsyncIterator[asyncpg.Connection]:
    """A connection with no user identity set, for arranging fixtures and service-role checks."""
    conn = await asyncpg.connect(migrated_dsn)
    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def clean_db(db: asyncpg.Connection) -> AsyncIterator[asyncpg.Connection]:
    """Truncate user data between tests so ordering never matters."""
    await db.execute("TRUNCATE users, programs, plants, feed_cache, gis_layer_versions CASCADE")
    yield db
    await db.execute("TRUNCATE users, programs, plants, feed_cache, gis_layer_versions CASCADE")


async def create_user(conn: asyncpg.Connection, email: str | None = None) -> UUID:
    return await conn.fetchval(
        "INSERT INTO users (email) VALUES ($1) RETURNING id",
        email or f"{uuid4().hex[:12]}@example.test",
    )


async def create_property(
    conn: asyncpg.Connection,
    user_id: UUID,
    *,
    address: str = "1 Test Way, Danville, CA",
    lat: float = 37.8216,
    lng: float = -121.9999,
) -> UUID:
    return await conn.fetchval(
        """
        INSERT INTO properties (user_id, address, location)
        VALUES ($1, $2, ST_SetSRID(ST_MakePoint($3, $4), 4326)::geography)
        RETURNING id
        """,
        user_id,
        address,
        lng,
        lat,
    )
