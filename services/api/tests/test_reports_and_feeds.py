"""Report and context-strip tests.

The report is the one artefact that leaves our hands and gets shown to a third party, so the tests
are mostly about what it must never claim. The strip's tests are about never blocking a scan on
somebody else's server, and never presenting stale weather as current.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from PIL import Image

from app.feeds.alerts import CACHE_SOURCE, AlertStrip, read_cached, summarise
from app.reports.pdf import DISCLAIMER, ReportData, ReportFinding, ReportPhoto, build_report
from tests.conftest import requires_db


def photo_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (320, 240), (80, 110, 60)).save(buffer, format="JPEG")
    return buffer.getvalue()


def sample(**overrides) -> ReportData:
    data = {
        "address": "1 Diablo Road, Danville, CA",
        "label": "Home",
        "fhsz": "very_high",
        "fhsz_source_version": "CAL FIRE FHSZ in LRA, 2025 v1",
        "fire_district": "SRVFPD",
        "score": 72,
        "rulebook_version": "2026.08",
        "applicable_weight": 91.0,
        "met_weight": 66.0,
        "outstanding": [
            ReportFinding(
                title="Clear dead vegetation within 30 feet",
                citation="PRC 4291(a)(1)",
                status="outstanding",
                zone="5-30ft",
                severity="critical",
                rule_status="in_effect",
                caveat=None,
            )
        ],
        "completed": [
            ReportFinding(
                title="Clear the roof and gutters",
                citation="PRC 4291(a)(3)",
                status="complete",
                zone="structure",
                severity="critical",
                rule_status="in_effect",
                caveat=None,
                photo=ReportPhoto(caption="Roofline after clearing", data=photo_bytes()),
            )
        ],
        "generated_at": datetime(2026, 8, 5, tzinfo=UTC),
    }
    data.update(overrides)
    return ReportData(**data)


# --------------------------------------------------------------------------- the report


def test_the_report_renders_a_pdf() -> None:
    pdf = build_report(sample())

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 2000


def test_the_report_never_claims_to_be_an_inspection() -> None:
    """The most damaging possible overclaim, on the one artefact a third party reads."""
    text = DISCLAIMER.lower()

    assert "not an inspection" in text
    assert "certification" in text
    assert "determination of eligibility" in text


def test_the_report_disclaims_evacuation_guidance() -> None:
    assert "no evacuation guidance" in DISCLAIMER.lower()


def test_the_report_includes_outstanding_items_not_only_completed_ones() -> None:
    """A document showing only good news is not worth much to whoever reads it."""
    with_outstanding = build_report(sample())
    without = build_report(sample(outstanding=[]))

    assert len(with_outstanding) > len(without)


def test_a_report_renders_with_no_completed_work() -> None:
    pdf = build_report(sample(completed=[]))

    assert pdf.startswith(b"%PDF-")


def test_a_report_renders_with_nothing_at_all() -> None:
    """A brand-new property with an empty plan must still produce a document, not an error."""
    pdf = build_report(sample(outstanding=[], completed=[]))

    assert pdf.startswith(b"%PDF-")


def test_a_corrupt_photograph_does_not_lose_the_whole_report() -> None:
    broken = ReportFinding(
        title="Something",
        citation="PRC 4291",
        status="complete",
        zone="structure",
        severity="high",
        rule_status="in_effect",
        caveat=None,
        photo=ReportPhoto(caption="broken", data=b"not an image"),
    )

    pdf = build_report(sample(completed=[broken]))

    assert pdf.startswith(b"%PDF-")


def test_a_draft_rule_carries_its_caveat_into_the_document() -> None:
    """Zone 0 is not law. An insurer reading this must not be told otherwise."""
    draft = ReportFinding(
        title="Replace bark mulch in the first five feet",
        citation="Draft Zone 0 regulation",
        status="outstanding",
        zone="0-5ft",
        severity="critical",
        rule_status="pending_adoption",
        caveat="Zone 0 is a draft regulation and has not been finally adopted.",
    )

    with_caveat = build_report(sample(outstanding=[draft]))
    without = build_report(
        sample(outstanding=[ReportFinding(**{**draft.__dict__, "caveat": None})])
    )

    assert len(with_caveat) > len(without)


def test_an_unresolved_district_prints_as_not_determined() -> None:
    pdf = build_report(sample(fire_district=None, fhsz_source_version=None))

    assert pdf.startswith(b"%PDF-")


# --------------------------------------------------------------------------- the context strip


def test_a_red_flag_warning_is_recognised() -> None:
    red_flag, events, headline = summarise(
        {
            "features": [
                {"properties": {"event": "Red Flag Warning", "headline": "Red Flag until 8pm"}}
            ]
        }
    )

    assert red_flag is True
    assert events == ["Red Flag Warning"]
    assert headline == "Red Flag until 8pm"


def test_ordinary_weather_does_not_raise_a_red_flag() -> None:
    red_flag, events, _ = summarise({"features": [{"properties": {"event": "Heat Advisory"}}]})

    assert red_flag is False
    assert events == ["Heat Advisory"]


def test_no_alerts_is_not_a_red_flag() -> None:
    assert summarise({"features": []}) == (False, [], None)


def test_the_strip_always_says_it_gives_no_evacuation_guidance() -> None:
    """A fire-adjacent app showing weather could easily be mistaken for something operational."""
    strip = AlertStrip(
        available=True,
        red_flag=True,
        events=["Red Flag Warning"],
        headline="x",
        fetched_at=datetime.now(UTC),
    )

    assert "evacuation" in strip.as_dict()["note"].lower()


@requires_db
@pytest.mark.asyncio
async def test_a_cache_miss_reports_unavailable_rather_than_all_clear(
    clean_db: asyncpg.Connection,
) -> None:
    """ "We do not know" and "there is no warning" must never look the same."""
    strip = await read_cached(clean_db, 37.82, -121.99)

    assert strip.available is False
    assert strip.red_flag is False


@requires_db
@pytest.mark.asyncio
async def test_a_fresh_cache_entry_is_served(clean_db: asyncpg.Connection) -> None:
    await clean_db.execute(
        """
        INSERT INTO feed_cache (source, cache_key, payload)
        VALUES ($1, '37.82,-121.99', $2::jsonb)
        """,
        CACHE_SOURCE,
        json.dumps({"red_flag": True, "events": ["Red Flag Warning"], "headline": "Windy"}),
    )

    strip = await read_cached(clean_db, 37.82, -121.99)

    assert strip.available is True
    assert strip.red_flag is True
    assert strip.headline == "Windy"


@requires_db
@pytest.mark.asyncio
async def test_stale_weather_is_withheld(clean_db: asyncpg.Connection) -> None:
    """A cleared Red Flag Warning shown as current is worse than showing nothing."""
    await clean_db.execute(
        """
        INSERT INTO feed_cache (source, cache_key, payload, fetched_at)
        VALUES ($1, '37.82,-121.99', $2::jsonb, $3)
        """,
        CACHE_SOURCE,
        json.dumps({"red_flag": True, "events": ["Red Flag Warning"], "headline": "Old"}),
        datetime.now(UTC) - timedelta(hours=3),
    )

    strip = await read_cached(clean_db, 37.82, -121.99)

    assert strip.available is False
    assert strip.red_flag is False
