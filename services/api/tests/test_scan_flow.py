"""End-to-end scan flow tests.

The whole product loop, over a real database: start a scan, upload a photograph, answer the
checklist, confirm what the model flagged, get a score and a plan, do a task, watch the score move.
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import Iterator
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import get_settings
from app.main import create_app
from tests.conftest import TEST_DSN, requires_db

pytestmark = requires_db

DANVILLE = {"address": "1 Test Way, Danville, CA", "lat": 37.8216, "lng": -121.9999}


def photo_bytes(colour: tuple[int, int, int] = (80, 110, 60)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (640, 480), colour).save(buffer, format="JPEG")
    return buffer.getvalue()


async def _seed(dsn: str) -> UUID:
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("TRUNCATE users, gis_layer_versions, feed_cache CASCADE")
        user_id = await conn.fetchval(
            "INSERT INTO users (email) VALUES ($1) RETURNING id", f"{uuid4().hex[:8]}@example.test"
        )
        version_id = await conn.fetchval(
            """
            INSERT INTO gis_layer_versions (layer, source_url, source_version, is_active)
            VALUES ('fhsz_lra', 'https://example.test', 'CAL FIRE FHSZ in LRA, 2025 v1', true)
            RETURNING id
            """
        )
        await conn.execute(
            """
            INSERT INTO fhsz_zones (layer_version_id, responsibility, fhsz, geom)
            VALUES ($1, 'LRA', 'very_high',
                    ST_Multi(ST_MakeEnvelope(-122.1, 37.7, -121.9, 37.9, 4326)))
            """,
            version_id,
        )
        return user_id
    finally:
        await conn.close()


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[tuple[TestClient, dict]]:
    monkeypatch.setenv("GROUNDWORK_DATABASE_URL", TEST_DSN)
    monkeypatch.setenv("GROUNDWORK_ENVIRONMENT", "development")
    monkeypatch.setenv("GROUNDWORK_PHOTO_STORAGE_ROOT", str(tmp_path / "photos"))
    monkeypatch.delenv("GROUNDWORK_SUPABASE_JWT_SECRET", raising=False)
    get_settings.cache_clear()

    user_id = asyncio.run(_seed(TEST_DSN))
    with TestClient(create_app()) as client:
        yield client, {"X-Groundwork-User": str(user_id)}

    get_settings.cache_clear()


@pytest.fixture
def scan(api, migrated_dsn: str) -> tuple[TestClient, dict, str]:
    client, headers = api
    property_id = client.post("/v1/properties", json=DANVILLE, headers=headers).json()["id"]
    scan_id = client.post(f"/v1/properties/{property_id}/scans", headers=headers).json()["id"]
    return client, headers, scan_id


# ------------------------------------------------------------------------------ scan lifecycle


def test_starting_a_scan_lists_the_stations_still_to_photograph(scan) -> None:
    client, headers, scan_id = scan

    body = client.get(f"/v1/scans/{scan_id}", headers=headers).json()

    assert body["status"] == "in_progress"
    assert "perimeter_0_5ft" in body["stations_remaining"]
    assert body["stations_photographed"] == []


def test_starting_a_scan_twice_resumes_the_first(scan) -> None:
    """The walk is long enough that people put the phone down partway through."""
    client, headers, scan_id = scan
    property_id = client.get(f"/v1/scans/{scan_id}", headers=headers).json()["property_id"]

    again = client.post(f"/v1/properties/{property_id}/scans", headers=headers).json()

    assert again["id"] == scan_id


def test_uploading_a_photo_records_the_station_and_queues_inference(scan) -> None:
    client, headers, scan_id = scan

    response = client.post(
        f"/v1/scans/{scan_id}/photos",
        data={"station": "perimeter_0_5ft"},
        files={"file": ("yard.jpg", photo_bytes(), "image/jpeg")},
        headers=headers,
    )

    assert response.status_code == 202, response.text
    assert response.json()["inference"] == "queued"

    summary = client.get(f"/v1/scans/{scan_id}", headers=headers).json()
    assert summary["stations_photographed"] == ["perimeter_0_5ft"]
    assert summary["photos_pending_inference"] == 1


def test_uploaded_photos_are_recorded_as_exif_stripped(scan, db_check) -> None:
    client, headers, scan_id = scan
    client.post(
        f"/v1/scans/{scan_id}/photos",
        data={"station": "roofline"},
        files={"file": ("roof.jpg", photo_bytes(), "image/jpeg")},
        headers=headers,
    )

    stripped = db_check("SELECT bool_and(exif_stripped) FROM photos WHERE scan_id = $1", scan_id)

    assert stripped is True


def test_an_unknown_station_is_refused(scan) -> None:
    client, headers, scan_id = scan

    response = client.post(
        f"/v1/scans/{scan_id}/photos",
        data={"station": "the_neighbours_garden"},
        files={"file": ("x.jpg", photo_bytes(), "image/jpeg")},
        headers=headers,
    )

    assert response.status_code == 422


def test_a_non_image_upload_is_refused(scan) -> None:
    client, headers, scan_id = scan

    response = client.post(
        f"/v1/scans/{scan_id}/photos",
        data={"station": "roofline"},
        files={"file": ("notes.txt", b"just some text", "text/plain")},
        headers=headers,
    )

    assert response.status_code == 422


def test_a_photo_is_only_served_to_its_owner(scan) -> None:
    client, headers, scan_id = scan
    photo_id = client.post(
        f"/v1/scans/{scan_id}/photos",
        data={"station": "front_elevation"},
        files={"file": ("front.jpg", photo_bytes(), "image/jpeg")},
        headers=headers,
    ).json()["photo_id"]

    mine = client.get(f"/v1/photos/{photo_id}/content", headers=headers)
    stranger = client.get(
        f"/v1/photos/{photo_id}/content", headers={"X-Groundwork-User": str(uuid4())}
    )

    assert mine.status_code == 200
    assert mine.headers["content-type"] == "image/jpeg"
    assert stranger.status_code == 404


def test_another_households_scan_is_not_reachable(scan) -> None:
    client, _headers, scan_id = scan

    response = client.get(f"/v1/scans/{scan_id}", headers={"X-Groundwork-User": str(uuid4())})

    assert response.status_code == 404


# ------------------------------------------------------------------------------ checklist


def test_the_checklist_is_served_for_the_guided_walk(api, migrated_dsn: str) -> None:
    client, headers = api

    questions = client.get("/v1/checklist", headers=headers).json()

    assert questions
    for question in questions:
        assert question["prompt"].endswith("?")
        assert question["help_text"]


def test_answering_the_checklist_counts_progress(scan) -> None:
    client, headers, scan_id = scan

    body = client.put(
        f"/v1/scans/{scan_id}/checklist",
        json={
            "answers": [
                {"question_id": "gutters_full", "hazard_present": True},
                {"question_id": "vents_unscreened", "hazard_present": False},
            ]
        },
        headers=headers,
    ).json()

    assert body["questions_answered"] == 2


def test_changing_an_answer_replaces_it(scan) -> None:
    client, headers, scan_id = scan
    answer = {"answers": [{"question_id": "gutters_full", "hazard_present": True}]}
    client.put(f"/v1/scans/{scan_id}/checklist", json=answer, headers=headers)

    body = client.put(
        f"/v1/scans/{scan_id}/checklist",
        json={"answers": [{"question_id": "gutters_full", "hazard_present": False}]},
        headers=headers,
    ).json()

    assert body["questions_answered"] == 1


def test_an_unknown_question_is_refused(scan) -> None:
    client, headers, scan_id = scan

    response = client.put(
        f"/v1/scans/{scan_id}/checklist",
        json={"answers": [{"question_id": "do_you_own_a_dragon", "hazard_present": True}]},
        headers=headers,
    )

    assert response.status_code == 422


# ------------------------------------------------------------------------------ assessment


def test_a_scan_with_a_hazard_scores_below_a_clean_one(scan) -> None:
    client, headers, scan_id = scan
    client.put(
        f"/v1/scans/{scan_id}/checklist",
        json={"answers": [{"question_id": "roof_debris_present", "hazard_present": True}]},
        headers=headers,
    )

    assessment = client.post(f"/v1/scans/{scan_id}/assess", headers=headers).json()

    assert assessment["score"] < 100
    assert assessment["plan"], "a failing rule must produce something to do about it"
    assert assessment["disclaimer"]


def test_every_plan_item_carries_its_citation(scan) -> None:
    """A task we ask someone to do must say what is asking for it."""
    client, headers, scan_id = scan
    client.put(
        f"/v1/scans/{scan_id}/checklist",
        json={
            "answers": [
                {"question_id": "roof_debris_present", "hazard_present": True},
                {"question_id": "combustible_mulch_present", "hazard_present": True},
            ]
        },
        headers=headers,
    )

    plan = client.post(f"/v1/scans/{scan_id}/assess", headers=headers).json()["plan"]

    for item in plan:
        assert item["citation"]
        if item["rule_status"] == "pending_adoption":
            assert item["caveat"], "a draft rule must say it is not law yet"


def test_binding_law_is_ranked_above_a_draft_regulation(scan) -> None:
    client, headers, scan_id = scan
    client.put(
        f"/v1/scans/{scan_id}/checklist",
        json={
            "answers": [
                {"question_id": "combustible_mulch_present", "hazard_present": True},
                {"question_id": "roof_debris_present", "hazard_present": True},
            ]
        },
        headers=headers,
    )

    plan = client.post(f"/v1/scans/{scan_id}/assess", headers=headers).json()["plan"]

    assert plan[0]["rule_status"] == "in_effect"


def test_the_breakdown_explains_the_score(scan) -> None:
    client, headers, scan_id = scan
    client.put(
        f"/v1/scans/{scan_id}/checklist",
        json={"answers": [{"question_id": "gutters_full", "hazard_present": True}]},
        headers=headers,
    )

    breakdown = client.post(f"/v1/scans/{scan_id}/assess", headers=headers).json()["breakdown"]

    assert breakdown["applicable_weight"] > 0
    lost = sum(rule["weight_lost"] for rule in breakdown["rules"])
    assert breakdown["met_weight"] + lost == breakdown["applicable_weight"]


def test_completing_a_task_raises_the_score_to_its_preview(scan) -> None:
    """The demo moment, and the one place a wrong number would be most visible."""
    client, headers, scan_id = scan
    client.put(
        f"/v1/scans/{scan_id}/checklist",
        json={
            "answers": [
                {"question_id": "roof_debris_present", "hazard_present": True},
                {"question_id": "gutters_full", "hazard_present": True},
            ]
        },
        headers=headers,
    )
    first = client.post(f"/v1/scans/{scan_id}/assess", headers=headers).json()
    item = first["plan"][0]
    predicted = item["score_if_done"]

    client.post(f"/v1/plan-items/{item['id']}/complete", headers=headers)
    # Completing a checklist-driven task also means answering that question the other way.
    client.put(
        f"/v1/scans/{scan_id}/checklist",
        json={"answers": [{"question_id": "roof_debris_present", "hazard_present": False}]},
        headers=headers,
    )
    second = client.post(f"/v1/scans/{scan_id}/assess", headers=headers).json()

    assert second["score"] == predicted
    assert second["score"] > first["score"]


def test_an_assessment_can_be_fetched_again(scan) -> None:
    client, headers, scan_id = scan
    created = client.post(f"/v1/scans/{scan_id}/assess", headers=headers).json()

    fetched = client.get(f"/v1/assessments/{created['id']}", headers=headers).json()

    assert fetched["score"] == created["score"]
    assert fetched["rulebook_version"] == created["rulebook_version"]


def test_another_household_cannot_read_an_assessment(scan) -> None:
    client, headers, scan_id = scan
    created = client.post(f"/v1/scans/{scan_id}/assess", headers=headers).json()

    response = client.get(
        f"/v1/assessments/{created['id']}", headers={"X-Groundwork-User": str(uuid4())}
    )

    assert response.status_code == 404


def test_assessing_marks_the_scan_complete(scan) -> None:
    client, headers, scan_id = scan
    client.post(f"/v1/scans/{scan_id}/assess", headers=headers)

    assert client.get(f"/v1/scans/{scan_id}", headers=headers).json()["status"] == "complete"


# ------------------------------------------------------------------------------ findings


def test_confirming_a_low_confidence_finding_makes_it_count(scan, db_exec) -> None:
    """Below threshold the model only proposes; the user's confirmation is what makes it a fact."""
    client, headers, scan_id = scan
    photo_id = client.post(
        f"/v1/scans/{scan_id}/photos",
        data={"station": "perimeter_0_5ft"},
        files={"file": ("p.jpg", photo_bytes(), "image/jpeg")},
        headers=headers,
    ).json()["photo_id"]
    finding_id = db_exec(
        """
        INSERT INTO findings
            (scan_id, photo_id, source, hazard, bbox_x, bbox_y, bbox_w, bbox_h, confidence,
             model_version)
        VALUES ($1, $2, 'model', 'combustible_mulch_z0', 0.1, 0.1, 0.3, 0.3, 0.22, 'test-v0')
        RETURNING id
        """,
        scan_id,
        UUID(photo_id),
    )

    before = client.post(f"/v1/scans/{scan_id}/assess", headers=headers).json()["score"]
    findings = client.get(f"/v1/scans/{scan_id}/findings", headers=headers).json()
    assert findings[0]["needs_confirmation"] is True

    client.post(f"/v1/findings/{finding_id}/status", json={"status": "confirmed"}, headers=headers)
    after = client.post(f"/v1/scans/{scan_id}/assess", headers=headers).json()["score"]

    assert before == 100
    assert after < before


def test_dismissing_a_finding_leaves_the_score_alone(scan, db_exec) -> None:
    client, headers, scan_id = scan
    photo_id = client.post(
        f"/v1/scans/{scan_id}/photos",
        data={"station": "front_elevation"},
        files={"file": ("p.jpg", photo_bytes(), "image/jpeg")},
        headers=headers,
    ).json()["photo_id"]
    finding_id = db_exec(
        """
        INSERT INTO findings
            (scan_id, photo_id, source, hazard, bbox_x, bbox_y, bbox_w, bbox_h, confidence)
        VALUES ($1, $2, 'model', 'dead_vegetation', 0.1, 0.1, 0.2, 0.2, 0.95)
        RETURNING id
        """,
        scan_id,
        UUID(photo_id),
    )

    triggered = client.post(f"/v1/scans/{scan_id}/assess", headers=headers).json()["score"]
    client.post(f"/v1/findings/{finding_id}/status", json={"status": "dismissed"}, headers=headers)
    dismissed = client.post(f"/v1/scans/{scan_id}/assess", headers=headers).json()["score"]

    assert triggered < 100
    assert dismissed == 100


def test_findings_carry_their_box_and_model_version(scan, db_exec) -> None:
    """The client draws the box, and the report has to name the model that drew it."""
    client, headers, scan_id = scan
    photo_id = client.post(
        f"/v1/scans/{scan_id}/photos",
        data={"station": "front_elevation"},
        files={"file": ("p.jpg", photo_bytes(), "image/jpeg")},
        headers=headers,
    ).json()["photo_id"]
    db_exec(
        """
        INSERT INTO findings
            (scan_id, photo_id, source, hazard, bbox_x, bbox_y, bbox_w, bbox_h, confidence,
             model_version)
        VALUES ($1, $2, 'model', 'dead_vegetation', 0.25, 0.5, 0.2, 0.1, 0.81, 'yolo11s-v1')
        RETURNING id
        """,
        scan_id,
        UUID(photo_id),
    )

    finding = client.get(f"/v1/scans/{scan_id}/findings", headers=headers).json()[0]

    assert finding["bbox"] == {"x": 0.25, "y": 0.5, "w": 0.2, "h": 0.1}
    assert finding["model_version"] == "yolo11s-v1"
    assert finding["needs_confirmation"] is False
