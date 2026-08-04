"""Schema constraint tests.

The CHECK constraints in migration 002 encode product rules that must hold no matter which handler
writes the row: a model finding always points at the pixels that produced it, a bounding box always
lies inside its image, a confidence is always a probability, and money is never negative.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
import pytest

from tests.conftest import create_property, create_user, requires_db

pytestmark = requires_db


@pytest.fixture
async def scan_id(clean_db: asyncpg.Connection) -> UUID:
    user_id = await create_user(clean_db)
    property_id = await create_property(clean_db, user_id)
    return await clean_db.fetchval(
        "INSERT INTO scans (property_id) VALUES ($1) RETURNING id", property_id
    )


async def test_model_finding_requires_a_photo_and_a_box(
    clean_db: asyncpg.Connection, scan_id: UUID
) -> None:
    with pytest.raises(asyncpg.CheckViolationError, match="findings_model_shape"):
        await clean_db.execute(
            """
            INSERT INTO findings (scan_id, source, hazard, confidence)
            VALUES ($1, 'model', 'dead_vegetation', 0.9)
            """,
            scan_id,
        )


async def test_checklist_finding_may_not_carry_a_confidence(
    clean_db: asyncpg.Connection, scan_id: UUID
) -> None:
    """A user's answer has no model confidence; showing one would be a fabricated number."""
    with pytest.raises(asyncpg.CheckViolationError, match="findings_checklist_shape"):
        await clean_db.execute(
            """
            INSERT INTO findings (scan_id, source, hazard, confidence)
            VALUES ($1, 'checklist', 'dead_vegetation', 0.9)
            """,
            scan_id,
        )


async def test_bounding_box_must_lie_inside_the_image(
    clean_db: asyncpg.Connection, scan_id: UUID
) -> None:
    photo_id = await clean_db.fetchval(
        """
        INSERT INTO photos (scan_id, station, storage_path)
        VALUES ($1, 'front_elevation', 'a/front.jpg') RETURNING id
        """,
        scan_id,
    )

    with pytest.raises(asyncpg.CheckViolationError, match="findings_bbox_within_image"):
        await clean_db.execute(
            """
            INSERT INTO findings
                (scan_id, photo_id, source, hazard, bbox_x, bbox_y, bbox_w, bbox_h, confidence)
            VALUES ($1, $2, 'model', 'overhanging_limbs', 0.8, 0.1, 0.5, 0.2, 0.77)
            """,
            scan_id,
            photo_id,
        )


async def test_confidence_must_be_a_probability(
    clean_db: asyncpg.Connection, scan_id: UUID
) -> None:
    photo_id = await clean_db.fetchval(
        """
        INSERT INTO photos (scan_id, station, storage_path)
        VALUES ($1, 'roofline', 'a/roof.jpg') RETURNING id
        """,
        scan_id,
    )

    with pytest.raises(asyncpg.CheckViolationError, match="probability"):
        await clean_db.execute(
            """
            INSERT INTO findings
                (scan_id, photo_id, source, hazard, bbox_x, bbox_y, bbox_w, bbox_h, confidence)
            VALUES ($1, $2, 'model', 'overhanging_limbs', 0.1, 0.1, 0.2, 0.2, 1.4)
            """,
            scan_id,
            photo_id,
        )


async def test_score_must_be_within_zero_to_one_hundred(
    clean_db: asyncpg.Connection, scan_id: UUID
) -> None:
    with pytest.raises(asyncpg.CheckViolationError, match="assessments_score_range"):
        await clean_db.execute(
            """
            INSERT INTO assessments (scan_id, score, rulebook_version)
            VALUES ($1, 101, 'test')
            """,
            scan_id,
        )


async def test_completed_scan_must_carry_a_completion_time(
    clean_db: asyncpg.Connection, scan_id: UUID
) -> None:
    with pytest.raises(asyncpg.CheckViolationError, match="scans_completed_implies_timestamp"):
        await clean_db.execute("UPDATE scans SET status = 'complete' WHERE id = $1", scan_id)


async def test_lawn_area_must_be_positive(clean_db: asyncpg.Connection) -> None:
    """Area feeds rebate money directly; a zero or negative area is never a real measurement."""
    user_id = await create_user(clean_db)
    property_id = await create_property(clean_db, user_id)

    with pytest.raises(asyncpg.CheckViolationError, match="lawn_polygons_area_positive"):
        await clean_db.execute(
            """
            INSERT INTO lawn_polygons (property_id, geom, area_sqft)
            VALUES (
                $1,
                ST_GeomFromText(
                    'POLYGON((-122 37.8, -122 37.801, -121.999 37.801, -121.999 37.8, -122 37.8))',
                    4326
                )::geography,
                -5
            )
            """,
            property_id,
        )


async def test_updated_at_advances_on_update(clean_db: asyncpg.Connection) -> None:
    user_id = await create_user(clean_db)
    property_id = await create_property(clean_db, user_id)

    before = await clean_db.fetchval("SELECT updated_at FROM properties WHERE id = $1", property_id)
    await clean_db.execute("UPDATE properties SET label = 'Home' WHERE id = $1", property_id)
    after = await clean_db.fetchval("SELECT updated_at FROM properties WHERE id = $1", property_id)

    assert after > before
