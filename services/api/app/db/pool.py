"""Database connections and the identity that constrains them.

Two ways to reach the database, and the difference matters:

* `acquire_as_user(user_id)` — sets `groundwork.user_id` on the connection, so every row-level
  security policy in migration 003 applies. This is what request handlers use.
* `acquire_service()` — no identity set, used only by background jobs that legitimately work across
  users: feed refresh, GIS imports, the inference worker writing findings.

The setting is applied with SET LOCAL inside a transaction, so it cannot leak to the next borrower
of a pooled connection.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import asyncpg

_pool: asyncpg.Pool | None = None


async def init_pool(dsn: str, *, min_size: int = 1, max_size: int = 10) -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("database pool is not initialised; call init_pool() during startup")
    return _pool


@asynccontextmanager
async def acquire_as_user(user_id: UUID | str) -> AsyncIterator[asyncpg.Connection]:
    """Yield a connection scoped to one user, inside a transaction with RLS in force.

    Everything the caller does is part of that transaction: it commits on clean exit and rolls back
    on exception, which is the behaviour a request handler wants anyway.
    """
    pool = get_pool()
    async with pool.acquire() as conn, conn.transaction():
        # Drop to the unprivileged role first. Postgres never applies row-level security to a
        # superuser, so connecting as the owner would silently disable every policy.
        await conn.execute("SET LOCAL ROLE groundwork_app")
        # set_config with is_local=true is the parameterised form of SET LOCAL; string
        # interpolation here would be an injection point on a value that decides data access.
        await conn.execute("SELECT set_config('groundwork.user_id', $1, true)", str(user_id))
        yield conn


@asynccontextmanager
async def acquire_service() -> AsyncIterator[asyncpg.Connection]:
    """Yield a connection with no user identity, for cross-user background work only."""
    pool = get_pool()
    async with pool.acquire() as conn:
        yield conn
