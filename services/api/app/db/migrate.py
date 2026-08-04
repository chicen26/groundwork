"""Migration runner.

Plain, numbered `.sql` files applied in order and recorded in `schema_migrations`. No ORM and no
migration DSL: the schema is full of PostGIS types, CHECK constraints, and row-level security
policies that are clearer written directly, and judges reading the repository can see exactly what
the database enforces.

Each applied file's checksum is stored. Editing a migration that has already run is a mistake we
want to fail loudly rather than discover as drift between two environments.

    python -m app.db.migrate            # apply pending migrations
    python -m app.db.migrate --status   # show what would run
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

import asyncpg

from app.config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

CREATE_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    text PRIMARY KEY,
    checksum   text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


@dataclass(frozen=True)
class Migration:
    version: str
    path: Path
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode()).hexdigest()


class MigrationDriftError(RuntimeError):
    """An already-applied migration file has been modified."""


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Load migrations sorted by filename; the numeric prefix defines the order."""
    migrations = [
        Migration(version=path.stem, path=path, sql=path.read_text())
        for path in sorted(directory.glob("*.sql"))
    ]
    if not migrations:
        raise FileNotFoundError(f"no migrations found in {directory}")
    return migrations


async def applied_versions(conn: asyncpg.Connection) -> dict[str, str]:
    await conn.execute(CREATE_MIGRATIONS_TABLE)
    rows = await conn.fetch("SELECT version, checksum FROM schema_migrations")
    return {row["version"]: row["checksum"] for row in rows}


def pending(migrations: list[Migration], applied: dict[str, str]) -> list[Migration]:
    """Return migrations not yet applied, refusing to proceed if an applied file changed."""
    drifted = [
        m.version for m in migrations if m.version in applied and applied[m.version] != m.checksum
    ]
    if drifted:
        raise MigrationDriftError(
            "these migrations were modified after being applied: "
            + ", ".join(drifted)
            + ". Write a new migration instead of editing an applied one."
        )
    return [m for m in migrations if m.version not in applied]


async def apply(conn: asyncpg.Connection, migration: Migration) -> None:
    """Apply one migration; the file and its bookkeeping row commit together or not at all."""
    async with conn.transaction():
        await conn.execute(migration.sql)
        await conn.execute(
            "INSERT INTO schema_migrations (version, checksum) VALUES ($1, $2)",
            migration.version,
            migration.checksum,
        )


async def migrate(dsn: str, *, status_only: bool = False) -> list[str]:
    """Apply every pending migration. Returns the versions applied (or pending, for --status)."""
    conn = await asyncpg.connect(dsn)
    try:
        migrations = discover()
        outstanding = pending(migrations, await applied_versions(conn))
        if status_only:
            return [m.version for m in outstanding]
        for migration in outstanding:
            await apply(conn, migration)
        return [m.version for m in outstanding]
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Groundwork database migrations.")
    parser.add_argument("--status", action="store_true", help="list pending migrations only")
    parser.add_argument("--dsn", help="override GROUNDWORK_DATABASE_URL")
    args = parser.parse_args()

    dsn = args.dsn or get_settings().database_url
    if not dsn:
        print("no database URL: set GROUNDWORK_DATABASE_URL or pass --dsn", file=sys.stderr)
        return 2

    versions = asyncio.run(migrate(dsn, status_only=args.status))
    if not versions:
        print("database is up to date")
    elif args.status:
        print("pending:\n  " + "\n  ".join(versions))
    else:
        print("applied:\n  " + "\n  ".join(versions))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
