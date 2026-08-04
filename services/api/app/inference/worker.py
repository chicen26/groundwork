"""The inference worker: queued photographs in, findings out.

Runs as a separate process from the API so a slow model never delays an upload. It claims jobs with
`FOR UPDATE SKIP LOCKED`, so several workers can run at once without two of them detecting the same
photo twice.

    python -m app.inference.worker --once      # drain the queue and stop
    python -m app.inference.worker             # keep polling

Findings written here always land as `open`. Nothing the model produces is treated as confirmed —
that is the user's move (decision D4).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from pathlib import Path
from uuid import UUID

import asyncpg

from app.config import get_settings
from app.inference.detector import Detector, NoModelConfigured, build_detector
from app.storage import LocalPhotoStorage, PhotoStorage

logger = logging.getLogger("groundwork.inference")

MAX_ATTEMPTS = 3
IDLE_SLEEP_S = 2.0

# One job at a time, oldest first. SKIP LOCKED lets a second worker take the next one rather than
# blocking behind this transaction.
_CLAIM_JOB = """
UPDATE inference_jobs
SET status = 'running', attempts = attempts + 1, started_at = now()
WHERE id = (
    SELECT id FROM inference_jobs
    WHERE status = 'queued' AND attempts < $1
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING id, photo_id, attempts
"""


async def _photo(conn: asyncpg.Connection, photo_id: UUID) -> tuple[UUID, str]:
    row = await conn.fetchrow("SELECT scan_id, storage_path FROM photos WHERE id = $1", photo_id)
    if row is None:
        raise LookupError(f"photo {photo_id} vanished before inference")
    return row["scan_id"], row["storage_path"]


async def _record(
    conn: asyncpg.Connection,
    *,
    job_id: UUID,
    photo_id: UUID,
    scan_id: UUID,
    detections: list,
    model_version: str,
) -> None:
    for detection in detections:
        await conn.execute(
            """
            INSERT INTO findings (
                scan_id, photo_id, source, hazard, bbox_x, bbox_y, bbox_w, bbox_h,
                confidence, model_version, status
            )
            VALUES ($1, $2, 'model', $3::hazard_class, $4, $5, $6, $7, $8, $9, 'open')
            """,
            scan_id,
            photo_id,
            detection.hazard,
            detection.x,
            detection.y,
            detection.w,
            detection.h,
            detection.confidence,
            model_version,
        )

    await conn.execute(
        """
        UPDATE inference_jobs
        SET status = 'succeeded', finished_at = now(), model_version = $2, error = NULL
        WHERE id = $1
        """,
        job_id,
        model_version,
    )


async def _fail(conn: asyncpg.Connection, job_id: UUID, attempts: int, message: str) -> None:
    """Mark a job failed, or leave it queued for another attempt.

    A failed job is visible to the client as inference being unavailable for that photo. It never
    reads as "we looked and found nothing" — that distinction is the whole reason the null detector
    raises instead of returning an empty list.
    """
    final = attempts >= MAX_ATTEMPTS
    await conn.execute(
        """
        UPDATE inference_jobs
        SET status = $2::inference_status,
            error = $3,
            finished_at = CASE WHEN $2 = 'failed' THEN now() ELSE NULL END
        WHERE id = $1
        """,
        job_id,
        "failed" if final else "queued",
        message[:500],
    )


async def process_one(conn: asyncpg.Connection, detector: Detector, storage: PhotoStorage) -> bool:
    """Claim and process a single job. Returns False when the queue is empty."""
    async with conn.transaction():
        job = await conn.fetchrow(_CLAIM_JOB, MAX_ATTEMPTS)
        if job is None:
            return False

    job_id, photo_id, attempts = job["id"], job["photo_id"], job["attempts"]

    try:
        scan_id, path = await _photo(conn, photo_id)
        image_bytes = storage.get(path)
        detections = detector.detect(image_bytes)
    except NoModelConfigured as exc:
        logger.warning("job %s: %s", job_id, exc)
        await _fail(conn, job_id, MAX_ATTEMPTS, str(exc))  # no point retrying a missing model
        return True
    except Exception as exc:
        logger.exception("job %s failed", job_id)
        await _fail(conn, job_id, attempts, f"{type(exc).__name__}: {exc}")
        return True

    async with conn.transaction():
        await _record(
            conn,
            job_id=job_id,
            photo_id=photo_id,
            scan_id=scan_id,
            detections=detections,
            model_version=detector.version,
        )
    logger.info("job %s: %d detections", job_id, len(detections))
    return True


async def drain(conn: asyncpg.Connection, detector: Detector, storage: PhotoStorage) -> int:
    processed = 0
    while await process_one(conn, detector, storage):
        processed += 1
    return processed


async def run(*, once: bool = False) -> int:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("GROUNDWORK_DATABASE_URL is required to run the inference worker")

    detector = build_detector(settings.detector_weights or None)
    storage = LocalPhotoStorage(Path(settings.photo_storage_root))
    logger.info("inference worker starting, model=%s", detector.version)

    # The worker connects as the owning role, not groundwork_app: it writes findings across every
    # user's scans, which is exactly what row-level security exists to stop handlers doing.
    conn = await asyncpg.connect(settings.database_url)
    try:
        if once:
            return await drain(conn, detector, storage)

        processed = 0
        while True:
            did = await drain(conn, detector, storage)
            processed += did
            if did == 0:
                time.sleep(IDLE_SLEEP_S)
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="drain the queue and exit")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    processed = asyncio.run(run(once=args.once))
    print(f"processed {processed} job(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
