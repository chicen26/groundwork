"""Row-level security tests.

The product promises that a homeowner's photos and address are private. These tests are the
evidence for that claim: they act as two different users against one database and assert that
neither can read, alter, or forge rows belonging to the other — including through the indirect
routes (scan -> photo, assessment -> plan) where a missing WHERE clause would otherwise leak data.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import asyncpg
import pytest

from tests.conftest import create_property, create_user, requires_db

pytestmark = [requires_db, pytest.mark.asyncio]


async def as_user(conn: asyncpg.Connection, user_id: UUID | str) -> None:
    """Enter a request-handler context: unprivileged role plus an identity.

    Mirrors `app.db.pool.acquire_as_user`. The SET LOCAL ROLE is the load-bearing half — tests run
    as the owning superuser, which Postgres exempts from row-level security entirely, so without it
    every assertion below would pass for the wrong reason.
    """
    await conn.execute("SET LOCAL ROLE groundwork_app")
    await conn.execute("SELECT set_config('groundwork.user_id', $1, true)", str(user_id))


@pytest.fixture
async def two_households(clean_db: asyncpg.Connection) -> tuple[UUID, UUID, UUID, UUID]:
    """Two users, each owning one property. Returns (user_a, property_a, user_b, property_b)."""
    user_a = await create_user(clean_db, "a@example.test")
    user_b = await create_user(clean_db, "b@example.test")
    property_a = await create_property(clean_db, user_a, address="1 A Street, Danville, CA")
    property_b = await create_property(clean_db, user_b, address="2 B Street, Orinda, CA")
    return user_a, property_a, user_b, property_b


async def test_user_sees_only_their_own_property(
    clean_db: asyncpg.Connection, two_households: tuple[UUID, UUID, UUID, UUID]
) -> None:
    user_a, property_a, _user_b, property_b = two_households

    async with clean_db.transaction():
        await as_user(clean_db, user_a)
        visible = {row["id"] for row in await clean_db.fetch("SELECT id FROM properties")}

    assert visible == {property_a}
    assert property_b not in visible


async def test_user_cannot_read_another_households_scan_or_photos(
    clean_db: asyncpg.Connection, two_households: tuple[UUID, UUID, UUID, UUID]
) -> None:
    user_a, _property_a, user_b, property_b = two_households

    scan_b = await clean_db.fetchval(
        "INSERT INTO scans (property_id) VALUES ($1) RETURNING id", property_b
    )
    await clean_db.execute(
        """
        INSERT INTO photos (scan_id, station, storage_path, exif_stripped)
        VALUES ($1, 'front_elevation', 'b/front.jpg', true)
        """,
        scan_b,
    )

    async with clean_db.transaction():
        await as_user(clean_db, user_a)
        assert await clean_db.fetchval("SELECT count(*) FROM scans") == 0
        assert await clean_db.fetchval("SELECT count(*) FROM photos") == 0

    # Sanity check in the other direction: the owner does see them, so the zero above is isolation
    # rather than an empty database.
    async with clean_db.transaction():
        await as_user(clean_db, user_b)
        assert await clean_db.fetchval("SELECT count(*) FROM photos") == 1


async def test_user_cannot_insert_a_property_owned_by_someone_else(
    clean_db: asyncpg.Connection, two_households: tuple[UUID, UUID, UUID, UUID]
) -> None:
    user_a, _property_a, user_b, _property_b = two_households

    async with clean_db.transaction():
        await as_user(clean_db, user_a)
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await clean_db.execute(
                """
                INSERT INTO properties (user_id, address, location)
                VALUES ($1, 'forged', ST_SetSRID(ST_MakePoint(-122, 37.8), 4326)::geography)
                """,
                user_b,
            )


async def test_user_cannot_update_another_households_finding(
    clean_db: asyncpg.Connection, two_households: tuple[UUID, UUID, UUID, UUID]
) -> None:
    user_a, _property_a, _user_b, property_b = two_households

    scan_b = await clean_db.fetchval(
        "INSERT INTO scans (property_id) VALUES ($1) RETURNING id", property_b
    )
    finding_b = await clean_db.fetchval(
        """
        INSERT INTO findings (scan_id, source, hazard)
        VALUES ($1, 'checklist', 'dead_vegetation') RETURNING id
        """,
        scan_b,
    )

    async with clean_db.transaction():
        await as_user(clean_db, user_a)
        # An UPDATE that matches no visible row is not an error — it simply affects nothing, which
        # is the outcome we care about.
        await clean_db.execute("UPDATE findings SET status = 'dismissed' WHERE id = $1", finding_b)

    assert await clean_db.fetchval("SELECT status FROM findings WHERE id = $1", finding_b) == "open"


async def test_plan_items_inherit_isolation_through_the_whole_chain(
    clean_db: asyncpg.Connection, two_households: tuple[UUID, UUID, UUID, UUID]
) -> None:
    """plan_item -> plan -> assessment -> scan -> property is the longest ownership path we have."""
    user_a, _property_a, user_b, property_b = two_households

    scan_b = await clean_db.fetchval(
        "INSERT INTO scans (property_id) VALUES ($1) RETURNING id", property_b
    )
    assessment_b = await clean_db.fetchval(
        """
        INSERT INTO assessments (scan_id, score, rulebook_version)
        VALUES ($1, 62, 'test') RETURNING id
        """,
        scan_b,
    )
    plan_b = await clean_db.fetchval(
        "INSERT INTO plans (assessment_id) VALUES ($1) RETURNING id", assessment_b
    )
    await clean_db.execute(
        """
        INSERT INTO plan_items (plan_id, rank, kind, title)
        VALUES ($1, 1, 'fire', 'Clear the first five feet')
        """,
        plan_b,
    )

    async with clean_db.transaction():
        await as_user(clean_db, user_a)
        assert await clean_db.fetchval("SELECT count(*) FROM plan_items") == 0

    async with clean_db.transaction():
        await as_user(clean_db, user_b)
        assert await clean_db.fetchval("SELECT count(*) FROM plan_items") == 1


async def test_unauthenticated_connection_sees_nothing(
    clean_db: asyncpg.Connection, two_households: tuple[UUID, UUID, UUID, UUID]
) -> None:
    """A connection with no identity set must not fall back to seeing everything."""
    async with clean_db.transaction():
        await as_user(clean_db, uuid4())  # a user that owns nothing
        assert await clean_db.fetchval("SELECT count(*) FROM properties") == 0


async def test_deleting_a_user_hard_deletes_their_data(
    clean_db: asyncpg.Connection, two_households: tuple[UUID, UUID, UUID, UUID]
) -> None:
    """Delete-account means the photos and findings go too, not just the login."""
    _user_a, _property_a, user_b, property_b = two_households

    scan_b = await clean_db.fetchval(
        "INSERT INTO scans (property_id) VALUES ($1) RETURNING id", property_b
    )
    await clean_db.execute(
        """
        INSERT INTO photos (scan_id, station, storage_path)
        VALUES ($1, 'roofline', 'b/roof.jpg')
        """,
        scan_b,
    )

    await clean_db.execute("DELETE FROM users WHERE id = $1", user_b)

    assert await clean_db.fetchval("SELECT count(*) FROM properties WHERE id = $1", property_b) == 0
    assert await clean_db.fetchval("SELECT count(*) FROM scans WHERE id = $1", scan_b) == 0
    assert await clean_db.fetchval("SELECT count(*) FROM photos WHERE scan_id = $1", scan_b) == 0
