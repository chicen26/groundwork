"""Report and feed endpoints."""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, Response, status

from app.auth import CurrentUser
from app.db import pool
from app.feeds.alerts import read_cached
from app.reports.pdf import ReportData, ReportFinding, ReportPhoto, build_report
from app.storage import get_storage

router = APIRouter(tags=["reports"])


@router.get("/feeds/alerts")
async def alerts(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
) -> dict:
    """The context strip, from cache only. Never blocks on the National Weather Service."""
    async with pool.acquire_service() as conn:
        strip = await read_cached(conn, lat, lng)
    return strip.as_dict()


@router.post("/assessments/{assessment_id}/report")
async def create_report(user_id: CurrentUser, assessment_id: Annotated[UUID, Path()]) -> Response:
    """Render this assessment as a PDF the homeowner can hand to an insurer."""
    async with pool.acquire_as_user(user_id) as conn:
        assessment = await conn.fetchrow(
            """
            SELECT a.id, a.score, a.rulebook_version, a.breakdown,
                   p.address, p.label, p.fhsz::text AS fhsz, p.fhsz_source_version,
                   p.fire_district
            FROM assessments a
            JOIN scans s ON s.id = a.scan_id
            JOIN properties p ON p.id = s.property_id
            WHERE a.id = $1
            """,
            assessment_id,
        )
        if assessment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="assessment not found"
            )

        items = await conn.fetch(
            """
            SELECT i.title, i.citation, i.zone, i.severity, i.rule_status, i.caveat, i.done_at,
                   f.photo_id, ph.storage_path
            FROM plan_items i
            JOIN plans pl ON pl.id = i.plan_id
            LEFT JOIN findings f ON f.id = i.finding_id
            LEFT JOIN photos ph ON ph.id = f.photo_id
            WHERE pl.assessment_id = $1
            ORDER BY i.rank
            """,
            assessment_id,
        )

    storage = get_storage()

    def to_finding(row) -> ReportFinding:
        photo = None
        if row["storage_path"]:
            try:
                photo = ReportPhoto(
                    caption=f"Photographed during the scan · {row['zone'] or ''}".strip(" ·"),
                    data=storage.get(row["storage_path"]),
                )
            except OSError:
                # A missing file must not cost someone the whole document.
                photo = None
        return ReportFinding(
            title=row["title"],
            citation=row["citation"] or "",
            status="complete" if row["done_at"] else "outstanding",
            zone=row["zone"] or "",
            severity=row["severity"] or "",
            rule_status=row["rule_status"] or "",
            caveat=row["caveat"],
            photo=photo,
        )

    breakdown = assessment["breakdown"]
    breakdown = json.loads(breakdown) if isinstance(breakdown, str) else breakdown

    pdf = build_report(
        ReportData(
            address=assessment["address"],
            label=assessment["label"],
            fhsz=assessment["fhsz"],
            fhsz_source_version=assessment["fhsz_source_version"],
            fire_district=assessment["fire_district"],
            score=assessment["score"],
            rulebook_version=assessment["rulebook_version"],
            applicable_weight=float(breakdown.get("applicable_weight", 0)),
            met_weight=float(breakdown.get("met_weight", 0)),
            outstanding=[to_finding(r) for r in items if not r["done_at"]],
            completed=[to_finding(r) for r in items if r["done_at"]],
        )
    )

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="groundwork-{assessment_id}.pdf"',
            # Someone's address and photographs of their home: never cached by an intermediary.
            "Cache-Control": "private, no-store",
        },
    )
