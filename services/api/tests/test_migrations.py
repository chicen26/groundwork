"""Migration runner tests.

The runner is small, but it is the thing standing between us and a schema that differs between a
laptop, CI, and the deployed service in October. Two properties matter: migrations apply in a
defined order, and editing one that has already run is caught rather than silently ignored.
"""

from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from app.db.migrate import Migration, MigrationDriftError, discover, migrate, pending
from tests.conftest import requires_db


def test_migrations_are_discovered_in_filename_order() -> None:
    versions = [m.version for m in discover()]

    assert versions == sorted(versions), "numeric filename prefixes define apply order"
    assert versions[0].startswith("001"), "extensions must be created before anything uses them"


def test_pending_excludes_already_applied() -> None:
    migrations = discover()
    applied = {migrations[0].version: migrations[0].checksum}

    assert [m.version for m in pending(migrations, applied)] == [m.version for m in migrations[1:]]


def test_modifying_an_applied_migration_is_an_error(tmp_path: Path) -> None:
    """Editing an applied migration produces drift between environments — fail loudly instead."""
    migration = Migration(version="001_x", path=tmp_path / "001_x.sql", sql="SELECT 1;")
    applied_with_old_checksum = {"001_x": "a-checksum-from-before-the-edit"}

    with pytest.raises(MigrationDriftError, match="001_x"):
        pending([migration], applied_with_old_checksum)


@requires_db
async def test_migrations_are_idempotent(migrated_dsn: str) -> None:
    """Running the migrator against an up-to-date database applies nothing and does not error."""
    assert await migrate(migrated_dsn) == []


@requires_db
async def test_postgis_is_available(db: asyncpg.Connection) -> None:
    """Geo resolution is built on PostGIS; without it we would only find out in Step 3."""
    version = await db.fetchval("SELECT postgis_version()")

    assert version


@requires_db
async def test_core_tables_exist(db: asyncpg.Connection) -> None:
    rows = await db.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'",
    )
    tables = {row["tablename"] for row in rows}

    assert {
        "users",
        "properties",
        "scans",
        "photos",
        "findings",
        "lawn_polygons",
        "assessments",
        "plans",
        "plan_items",
        "plants",
        "programs",
        "feed_cache",
    } <= tables
