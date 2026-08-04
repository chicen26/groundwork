"""Inference worker tests.

Two things matter most here, and neither is about accuracy:

* A photograph that could not be processed must never look like a photograph that came back clean.
  Silence would show a homeowner a safe-looking scan nobody earned.
* Nothing the model produces arrives confirmed. The model proposes, the user disposes (decision D4).
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest
from PIL import Image

from app.inference.detector import Detection, NoModelConfigured, NullDetector
from app.inference.worker import MAX_ATTEMPTS, drain, process_one
from app.storage import LocalPhotoStorage
from tests.conftest import TEST_DSN, requires_db

pytestmark = [requires_db, pytest.mark.asyncio]


class StubDetector:
    """A detector with fixed opinions, so the pipeline can be tested without torch."""

    version = "stub-v1"

    def __init__(self, detections: list[Detection] | None = None, *, boom: bool = False) -> None:
        self._detections = detections or []
        self._boom = boom
        self.calls = 0

    def detect(self, image_bytes: bytes) -> list[Detection]:
        self.calls += 1
        if self._boom:
            raise RuntimeError("the model fell over")
        return list(self._detections)


def jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (320, 240), (70, 100, 60)).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
async def queued(clean_db: asyncpg.Connection, tmp_path: Path):
    """A scan with one uploaded photo and one queued inference job."""
    storage = LocalPhotoStorage(tmp_path)
    user_id = await clean_db.fetchval(
        "INSERT INTO users (email) VALUES ($1) RETURNING id", f"{uuid4().hex[:8]}@example.test"
    )
    property_id = await clean_db.fetchval(
        """
        INSERT INTO properties (user_id, address, location, fhsz)
        VALUES ($1, '1 Test Way', ST_SetSRID(ST_MakePoint(-121.99, 37.82), 4326)::geography,
                'very_high')
        RETURNING id
        """,
        user_id,
    )
    scan_id = await clean_db.fetchval(
        "INSERT INTO scans (property_id) VALUES ($1) RETURNING id", property_id
    )
    path = storage.put(scan_id, jpeg())
    photo_id = await clean_db.fetchval(
        """
        INSERT INTO photos (scan_id, station, storage_path, width_px, height_px, exif_stripped)
        VALUES ($1, 'perimeter_0_5ft', $2, 320, 240, true) RETURNING id
        """,
        scan_id,
        path,
    )
    job_id = await clean_db.fetchval(
        "INSERT INTO inference_jobs (photo_id) VALUES ($1) RETURNING id", photo_id
    )
    return {
        "conn": clean_db,
        "storage": storage,
        "scan_id": scan_id,
        "photo_id": photo_id,
        "job_id": job_id,
    }


async def test_a_detection_becomes_an_open_finding(queued) -> None:
    conn, storage = queued["conn"], queued["storage"]
    detector = StubDetector(
        [Detection(hazard="combustible_mulch_z0", confidence=0.82, x=0.1, y=0.2, w=0.3, h=0.25)]
    )

    assert await process_one(conn, detector, storage) is True

    finding = await conn.fetchrow(
        "SELECT hazard::text AS hazard, status::text AS status, confidence, bbox_x, bbox_w,"
        " model_version FROM findings WHERE scan_id = $1",
        queued["scan_id"],
    )
    assert finding["hazard"] == "combustible_mulch_z0"
    # Never 'confirmed': the model only proposes.
    assert finding["status"] == "open"
    assert float(finding["confidence"]) == pytest.approx(0.82)
    assert float(finding["bbox_x"]) == pytest.approx(0.1)
    assert finding["model_version"] == "stub-v1"


async def test_a_successful_job_is_marked_succeeded(queued) -> None:
    conn, storage = queued["conn"], queued["storage"]

    await process_one(conn, StubDetector(), storage)

    job = await conn.fetchrow(
        "SELECT status::text AS status, model_version, finished_at"
        " FROM inference_jobs WHERE id = $1",
        queued["job_id"],
    )
    assert job["status"] == "succeeded"
    assert job["model_version"] == "stub-v1"
    assert job["finished_at"] is not None


async def test_a_photo_with_no_hazards_succeeds_with_no_findings(queued) -> None:
    """A genuinely clean photo is a success with zero findings — distinct from a failure."""
    conn, storage = queued["conn"], queued["storage"]

    await process_one(conn, StubDetector([]), storage)

    status = await conn.fetchval(
        "SELECT status::text FROM inference_jobs WHERE id = $1", queued["job_id"]
    )
    assert status == "succeeded"
    assert await conn.fetchval("SELECT count(*) FROM findings") == 0


async def test_no_model_configured_fails_the_job_rather_than_reporting_a_clean_yard(
    queued,
) -> None:
    """The distinction the product rests on: "could not look" is not "looked, and it is fine"."""
    conn, storage = queued["conn"], queued["storage"]

    await process_one(conn, NullDetector(), storage)

    job = await conn.fetchrow(
        "SELECT status::text AS status, error FROM inference_jobs WHERE id = $1", queued["job_id"]
    )
    assert job["status"] == "failed"
    assert "no detector weights" in job["error"]
    assert await conn.fetchval("SELECT count(*) FROM findings") == 0


async def test_a_missing_model_is_not_retried(queued) -> None:
    """Retrying a model that does not exist just burns the queue."""
    conn, storage = queued["conn"], queued["storage"]

    await process_one(conn, NullDetector(), storage)

    assert await process_one(conn, NullDetector(), storage) is False


async def test_a_crashing_model_is_retried_then_given_up_on(queued) -> None:
    conn, storage = queued["conn"], queued["storage"]
    detector = StubDetector(boom=True)

    for _ in range(MAX_ATTEMPTS + 2):
        await process_one(conn, detector, storage)

    job = await conn.fetchrow(
        "SELECT status::text AS status, attempts, error FROM inference_jobs WHERE id = $1",
        queued["job_id"],
    )
    assert job["status"] == "failed"
    assert job["attempts"] == MAX_ATTEMPTS
    assert "the model fell over" in job["error"]
    # It stopped being retried rather than looping forever.
    assert detector.calls == MAX_ATTEMPTS


async def test_one_bad_photo_does_not_stop_the_queue(clean_db, tmp_path) -> None:
    """A worker that dies on one corrupt file leaves every later scan unprocessed."""
    storage = LocalPhotoStorage(tmp_path)
    user_id = await clean_db.fetchval(
        "INSERT INTO users (email) VALUES ($1) RETURNING id", f"{uuid4().hex[:8]}@example.test"
    )
    property_id = await clean_db.fetchval(
        """
        INSERT INTO properties (user_id, address, location)
        VALUES ($1, '1 Test Way', ST_SetSRID(ST_MakePoint(-121.99, 37.82), 4326)::geography)
        RETURNING id
        """,
        user_id,
    )
    scan_id = await clean_db.fetchval(
        "INSERT INTO scans (property_id) VALUES ($1) RETURNING id", property_id
    )
    for station in ("front_elevation", "roofline"):
        photo_id = await clean_db.fetchval(
            """
            INSERT INTO photos (scan_id, station, storage_path, exif_stripped)
            VALUES ($1, $2::photo_station, $3, true) RETURNING id
            """,
            scan_id,
            station,
            storage.put(scan_id, jpeg()),
        )
        await clean_db.execute("INSERT INTO inference_jobs (photo_id) VALUES ($1)", photo_id)

    # Fails the first photo, succeeds on every one after it.
    class FlakyDetector:
        version = "flaky-v1"

        def __init__(self) -> None:
            self.calls = 0

        def detect(self, image_bytes: bytes):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("corrupt file")
            return [Detection("dead_vegetation", 0.7, 0.1, 0.1, 0.2, 0.2)]

    processed = await drain(clean_db, FlakyDetector(), storage)

    assert processed >= 2, "the failure must not have ended the drain"
    # The queue empties: the second photo went through, and the first was requeued and picked up
    # again rather than being abandoned or blocking the ones behind it.
    queued_left = await clean_db.fetchval(
        "SELECT count(*) FROM inference_jobs WHERE status = 'queued'"
    )
    assert queued_left == 0
    assert (
        await clean_db.fetchval("SELECT count(*) FROM inference_jobs WHERE status = 'succeeded'")
        == 2
    )


async def test_an_empty_queue_reports_nothing_to_do(clean_db, tmp_path) -> None:
    assert await process_one(clean_db, StubDetector(), LocalPhotoStorage(tmp_path)) is False


async def test_two_workers_do_not_process_the_same_photo(queued) -> None:
    """SKIP LOCKED is what lets a second worker help rather than duplicate."""
    storage = queued["storage"]
    detector_a, detector_b = StubDetector(), StubDetector()

    other = await asyncpg.connect(TEST_DSN)
    try:
        results = await asyncio.gather(
            process_one(queued["conn"], detector_a, storage),
            process_one(other, detector_b, storage),
        )
    finally:
        await other.close()

    assert sorted(results) == [False, True], "exactly one worker should have claimed the job"
    assert detector_a.calls + detector_b.calls == 1


async def test_the_null_detector_refuses_rather_than_returning_nothing() -> None:
    with pytest.raises(NoModelConfigured):
        NullDetector().detect(jpeg())


async def test_findings_from_the_worker_move_the_score(queued) -> None:
    """The full chain: a detection becomes evidence the deterministic engine acts on."""
    from app.assessments import gather_evidence

    conn, storage = queued["conn"], queued["storage"]
    await process_one(
        conn,
        StubDetector([Detection("dead_vegetation", 0.91, 0.2, 0.2, 0.3, 0.3)]),
        storage,
    )

    evidence = await gather_evidence(conn, UUID(str(queued["scan_id"])))

    assert [e.key for e in evidence] == ["dead_vegetation"]
    assert evidence[0].source == "model"
    assert evidence[0].confirmed is False
