"""Scans: the guided walk, the photographs, the findings, and the resulting plan.

The flow this serves: start a scan on a property, photograph each station, answer the questions a
photograph cannot answer, confirm or dismiss what the model flagged, then ask for an assessment.

Uploads never wait on the model. A photograph is sanitised, stored, and queued, and the client polls
findings as they appear — a homeowner walking their yard should not be watching a spinner.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Path, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.assessments import assess_scan
from app.auth import CurrentUser
from app.db import pool
from app.routers.rules import active_rulebook
from app.rules.checklist import CHECKLIST, QUESTIONS_BY_ID
from app.storage import UnsupportedImage, get_storage, sanitize

router = APIRouter(tags=["scans"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

STATIONS = (
    "front_elevation",
    "left_side",
    "right_side",
    "rear_elevation",
    "deck_porch",
    "roofline",
    "perimeter_0_5ft",
)


# ------------------------------------------------------------------------------ models


class ScanSummary(BaseModel):
    id: UUID
    property_id: UUID
    status: str
    stations_photographed: list[str]
    stations_remaining: list[str]
    questions_answered: int
    questions_total: int
    open_findings: int
    photos_pending_inference: int


class FindingResponse(BaseModel):
    id: UUID
    photo_id: UUID | None
    hazard: str
    source: str
    status: str
    confidence: float | None
    bbox: dict[str, float] | None
    model_version: str | None
    # False when the detection is too uncertain to state as fact; the client labels these
    # "possible — confirm" rather than asserting them.
    needs_confirmation: bool


class FindingStatusUpdate(BaseModel):
    status: str = Field(pattern="^(confirmed|dismissed|resolved|open)$")


class ChecklistAnswer(BaseModel):
    question_id: str
    hazard_present: bool


class ChecklistSubmission(BaseModel):
    answers: list[ChecklistAnswer]


class QuestionResponse(BaseModel):
    id: str
    prompt: str
    help_text: str
    zone: str
    station: str


class PlanItemResponse(BaseModel):
    id: UUID
    rank: int
    title: str
    detail: str
    citation: str
    zone: str | None
    severity: str | None
    rule_status: str | None
    caveat: str | None
    effort_hours: float | None
    cost_est_usd: float | None
    score_if_done: int | None
    done: bool


class AssessmentResponse(BaseModel):
    id: UUID
    scan_id: UUID
    score: int
    rulebook_version: str
    breakdown: dict
    disclaimer: str
    plan: list[PlanItemResponse]


# ------------------------------------------------------------------------------ helpers


async def _owned_scan(conn, scan_id: UUID) -> dict:
    """Fetch a scan the caller owns, or 404.

    Row-level security means another household's scan is simply invisible, so "not found" is honest
    and leaks nothing about whether the id exists.
    """
    row = await conn.fetchrow(
        """
        SELECT s.id, s.property_id, s.status::text AS status, p.fhsz::text AS fhsz,
               p.state_code
        FROM scans s JOIN properties p ON p.id = s.property_id
        WHERE s.id = $1
        """,
        scan_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="scan not found")
    return dict(row)


# ------------------------------------------------------------------------------ checklist catalog


@router.get("/checklist", response_model=list[QuestionResponse], tags=["rules"])
def get_checklist() -> list[QuestionResponse]:
    """The questions the guided walk asks. Served so the app and the engine cannot drift apart."""
    return [
        QuestionResponse(
            id=question.id,
            prompt=question.prompt,
            help_text=question.help_text,
            zone=question.zone.value,
            station=question.station,
        )
        for question in CHECKLIST
    ]


# ------------------------------------------------------------------------------ scans


@router.post(
    "/properties/{property_id}/scans",
    response_model=ScanSummary,
    status_code=status.HTTP_201_CREATED,
)
async def start_scan(user_id: CurrentUser, property_id: Annotated[UUID, Path()]) -> ScanSummary:
    """Start a scan, or hand back the one already in progress.

    Resuming rather than starting a second scan is the point: the walk is long enough that people
    put their phone down partway through.
    """
    async with pool.acquire_as_user(user_id) as conn:
        owns = await conn.fetchval("SELECT 1 FROM properties WHERE id = $1", property_id)
        if not owns:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="property not found")

        scan_id = await conn.fetchval(
            "SELECT id FROM scans WHERE property_id = $1 AND status = 'in_progress' LIMIT 1",
            property_id,
        )
        if scan_id is None:
            scan_id = await conn.fetchval(
                "INSERT INTO scans (property_id) VALUES ($1) RETURNING id", property_id
            )

        return await _summarise(conn, scan_id)


@router.get("/scans/{scan_id}", response_model=ScanSummary)
async def get_scan(user_id: CurrentUser, scan_id: Annotated[UUID, Path()]) -> ScanSummary:
    async with pool.acquire_as_user(user_id) as conn:
        await _owned_scan(conn, scan_id)
        return await _summarise(conn, scan_id)


async def _summarise(conn, scan_id: UUID) -> ScanSummary:
    scan = await conn.fetchrow(
        "SELECT id, property_id, status::text AS status FROM scans WHERE id = $1", scan_id
    )
    photographed = [
        row["station"]
        for row in await conn.fetch(
            "SELECT DISTINCT station::text AS station FROM photos WHERE scan_id = $1", scan_id
        )
    ]
    answered = await conn.fetchval(
        "SELECT count(*) FROM checklist_answers WHERE scan_id = $1", scan_id
    )
    open_findings = await conn.fetchval(
        "SELECT count(*) FROM findings WHERE scan_id = $1 AND status = 'open'", scan_id
    )
    pending = await conn.fetchval(
        """
        SELECT count(*) FROM inference_jobs j
        JOIN photos p ON p.id = j.photo_id
        WHERE p.scan_id = $1 AND j.status IN ('queued', 'running')
        """,
        scan_id,
    )

    return ScanSummary(
        id=scan["id"],
        property_id=scan["property_id"],
        status=scan["status"],
        stations_photographed=sorted(photographed),
        stations_remaining=[s for s in STATIONS if s not in photographed],
        questions_answered=answered,
        questions_total=len(CHECKLIST),
        open_findings=open_findings,
        photos_pending_inference=pending,
    )


# ------------------------------------------------------------------------------ photos


@router.post("/scans/{scan_id}/photos", status_code=status.HTTP_202_ACCEPTED)
async def upload_photo(
    user_id: CurrentUser,
    scan_id: Annotated[UUID, Path()],
    station: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> dict:
    """Accept one station photograph: sanitise it, store it, and queue inference.

    202 rather than 201 is deliberate — the photo is stored, but the findings it will produce do not
    exist yet.
    """
    if station not in STATIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown station {station!r}",
        )

    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="that photo is too large",
        )

    try:
        # Metadata is stripped before anything is written, never after: a file that briefly exists
        # with GPS coordinates in it has already been a file with GPS coordinates in it.
        clean, width, height = sanitize(raw)
    except UnsupportedImage as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    async with pool.acquire_as_user(user_id) as conn:
        await _owned_scan(conn, scan_id)

        path = get_storage().put(scan_id, clean)
        photo_id = await conn.fetchval(
            """
            INSERT INTO photos (scan_id, station, storage_path, width_px, height_px, exif_stripped)
            VALUES ($1, $2::photo_station, $3, $4, $5, true) RETURNING id
            """,
            scan_id,
            station,
            path,
            width,
            height,
        )
        await conn.execute("INSERT INTO inference_jobs (photo_id) VALUES ($1)", photo_id)

    return {"photo_id": str(photo_id), "station": station, "inference": "queued"}


@router.get("/photos/{photo_id}/content")
async def get_photo(user_id: CurrentUser, photo_id: Annotated[UUID, Path()]) -> Response:
    """Serve a photograph to the person it belongs to.

    Bytes go through an authenticated endpoint rather than a public URL, so possession of a link is
    never possession of a photograph of somebody's house.
    """
    async with pool.acquire_as_user(user_id) as conn:
        path = await conn.fetchval("SELECT storage_path FROM photos WHERE id = $1", photo_id)

    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="photo not found")

    return Response(
        content=get_storage().get(path),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


# ------------------------------------------------------------------------------ findings


@router.get("/scans/{scan_id}/findings", response_model=list[FindingResponse])
async def list_findings(
    user_id: CurrentUser, scan_id: Annotated[UUID, Path()]
) -> list[FindingResponse]:
    threshold = active_rulebook().confidence_threshold

    async with pool.acquire_as_user(user_id) as conn:
        await _owned_scan(conn, scan_id)
        rows = await conn.fetch(
            """
            SELECT id, photo_id, hazard::text AS hazard, source::text AS source,
                   status::text AS status, confidence, bbox_x, bbox_y, bbox_w, bbox_h,
                   model_version
            FROM findings WHERE scan_id = $1
            ORDER BY confidence DESC NULLS LAST, created_at
            """,
            scan_id,
        )

    return [
        FindingResponse(
            id=row["id"],
            photo_id=row["photo_id"],
            hazard=row["hazard"],
            source=row["source"],
            status=row["status"],
            confidence=float(row["confidence"]) if row["confidence"] is not None else None,
            bbox=(
                {
                    "x": float(row["bbox_x"]),
                    "y": float(row["bbox_y"]),
                    "w": float(row["bbox_w"]),
                    "h": float(row["bbox_h"]),
                }
                if row["bbox_x"] is not None
                else None
            ),
            model_version=row["model_version"],
            needs_confirmation=(
                row["source"] == "model"
                and row["status"] == "open"
                and (row["confidence"] is None or float(row["confidence"]) < threshold)
            ),
        )
        for row in rows
    ]


@router.post("/findings/{finding_id}/status", response_model=FindingResponse)
async def update_finding_status(
    user_id: CurrentUser,
    finding_id: Annotated[UUID, Path()],
    payload: FindingStatusUpdate,
) -> FindingResponse:
    """Confirm, dismiss, or resolve a finding: the user disposing of what the model proposed."""
    async with pool.acquire_as_user(user_id) as conn:
        row = await conn.fetchrow(
            """
            UPDATE findings SET status = $2::finding_status WHERE id = $1
            RETURNING id, scan_id, photo_id, hazard::text AS hazard, source::text AS source,
                      status::text AS status, confidence, bbox_x, bbox_y, bbox_w, bbox_h,
                      model_version
            """,
            finding_id,
            payload.status,
        )

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="finding not found")

    return FindingResponse(
        id=row["id"],
        photo_id=row["photo_id"],
        hazard=row["hazard"],
        source=row["source"],
        status=row["status"],
        confidence=float(row["confidence"]) if row["confidence"] is not None else None,
        bbox=(
            {
                "x": float(row["bbox_x"]),
                "y": float(row["bbox_y"]),
                "w": float(row["bbox_w"]),
                "h": float(row["bbox_h"]),
            }
            if row["bbox_x"] is not None
            else None
        ),
        model_version=row["model_version"],
        needs_confirmation=False,
    )


# ------------------------------------------------------------------------------ checklist answers


@router.put("/scans/{scan_id}/checklist", response_model=ScanSummary)
async def submit_checklist(
    user_id: CurrentUser, scan_id: Annotated[UUID, Path()], payload: ChecklistSubmission
) -> ScanSummary:
    unknown = [a.question_id for a in payload.answers if a.question_id not in QUESTIONS_BY_ID]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown checklist questions: {unknown}",
        )

    async with pool.acquire_as_user(user_id) as conn:
        await _owned_scan(conn, scan_id)
        for answer in payload.answers:
            await conn.execute(
                """
                INSERT INTO checklist_answers (scan_id, question_id, hazard_present)
                VALUES ($1, $2, $3)
                ON CONFLICT (scan_id, question_id)
                DO UPDATE SET hazard_present = EXCLUDED.hazard_present, answered_at = now()
                """,
                scan_id,
                answer.question_id,
                answer.hazard_present,
            )
        return await _summarise(conn, scan_id)


# ------------------------------------------------------------------------------ assessment


@router.post(
    "/scans/{scan_id}/assess",
    response_model=AssessmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_assessment(
    user_id: CurrentUser, scan_id: Annotated[UUID, Path()]
) -> AssessmentResponse:
    """Score the scan and build its plan.

    Re-assessable on purpose: confirming a finding or completing a task changes the evidence,
    and the user should be able to watch the number move.
    """
    rulebook = active_rulebook()

    async with pool.acquire_as_user(user_id) as conn:
        scan = await _owned_scan(conn, scan_id)
        assessment_id, assessment = await assess_scan(
            conn, scan_id, rulebook=rulebook, fhsz=scan["fhsz"], state=scan["state_code"]
        )
        await conn.execute(
            """
            UPDATE scans SET status = 'complete', completed_at = now()
            WHERE id = $1 AND status <> 'complete'
            """,
            scan_id,
        )
        plan = await _plan_for(conn, assessment_id)

    return AssessmentResponse(
        id=assessment_id,
        scan_id=scan_id,
        score=assessment.score,
        rulebook_version=assessment.rulebook_version,
        breakdown=assessment.breakdown(),
        disclaimer=assessment.disclaimer,
        plan=plan,
    )


@router.get("/assessments/{assessment_id}", response_model=AssessmentResponse)
async def get_assessment(
    user_id: CurrentUser, assessment_id: Annotated[UUID, Path()]
) -> AssessmentResponse:
    async with pool.acquire_as_user(user_id) as conn:
        row = await conn.fetchrow(
            "SELECT id, scan_id, score, rulebook_version, breakdown FROM assessments WHERE id = $1",
            assessment_id,
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="assessment not found"
            )
        plan = await _plan_for(conn, assessment_id)

    import json

    breakdown = row["breakdown"]
    return AssessmentResponse(
        id=row["id"],
        scan_id=row["scan_id"],
        score=row["score"],
        rulebook_version=row["rulebook_version"],
        breakdown=json.loads(breakdown) if isinstance(breakdown, str) else breakdown,
        disclaimer=active_rulebook().disclaimer,
        plan=plan,
    )


async def _plan_for(conn, assessment_id: UUID) -> list[PlanItemResponse]:
    rows = await conn.fetch(
        """
        SELECT i.id, i.rank, i.title, i.detail, i.citation, i.zone, i.severity,
               i.rule_status, i.caveat, i.effort_hours, i.cost_est_usd, i.score_if_done,
               i.done_at
        FROM plan_items i JOIN plans p ON p.id = i.plan_id
        WHERE p.assessment_id = $1
        ORDER BY i.rank
        """,
        assessment_id,
    )
    return [
        PlanItemResponse(
            id=row["id"],
            rank=row["rank"],
            title=row["title"],
            detail=row["detail"] or "",
            citation=row["citation"] or "",
            zone=row["zone"],
            severity=row["severity"],
            rule_status=row["rule_status"],
            caveat=row["caveat"],
            effort_hours=float(row["effort_hours"]) if row["effort_hours"] is not None else None,
            cost_est_usd=float(row["cost_est_usd"]) if row["cost_est_usd"] is not None else None,
            score_if_done=row["score_if_done"],
            done=row["done_at"] is not None,
        )
        for row in rows
    ]


@router.post("/plan-items/{item_id}/complete", response_model=PlanItemResponse)
async def complete_plan_item(
    user_id: CurrentUser, item_id: Annotated[UUID, Path()]
) -> PlanItemResponse:
    """Tick off a task, and resolve the evidence it was raised for.

    Resolving the evidence is what makes the next assessment reflect the work — otherwise the
    score would sit still while the yard got safer. Evidence lives in two places, and both are
    resolved: model findings for this rule's hazards, and checklist answers for its questions.
    """
    async with pool.acquire_as_user(user_id) as conn:
        row = await conn.fetchrow(
            """
            UPDATE plan_items SET done_at = now() WHERE id = $1
            RETURNING id, rank, rule_id, title, detail, citation, zone, severity, rule_status,
                      caveat, effort_hours, cost_est_usd, score_if_done, done_at, finding_id,
                      (SELECT a.scan_id FROM plans p JOIN assessments a ON a.id = p.assessment_id
                       WHERE p.id = plan_items.plan_id) AS scan_id
            """,
            item_id,
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan item not found")

        rule = next(
            (r for r in active_rulebook().rules if r.id == row["rule_id"]),
            None,
        )
        if rule and row["scan_id"]:
            if rule.triggers.checklist:
                await conn.execute(
                    """
                    UPDATE checklist_answers SET resolved_at = now()
                    WHERE scan_id = $1 AND question_id = ANY($2) AND hazard_present
                    """,
                    row["scan_id"],
                    rule.triggers.checklist,
                )
            if rule.triggers.hazards:
                # Dismissed stays dismissed: the user said it was never real, which is a different
                # statement from "it was real and I fixed it".
                await conn.execute(
                    """
                    UPDATE findings SET status = 'resolved'
                    WHERE scan_id = $1 AND hazard::text = ANY($2) AND status <> 'dismissed'
                    """,
                    row["scan_id"],
                    rule.triggers.hazards,
                )
        elif row["finding_id"]:
            await conn.execute(
                "UPDATE findings SET status = 'resolved' WHERE id = $1", row["finding_id"]
            )

    return PlanItemResponse(
        id=row["id"],
        rank=row["rank"],
        title=row["title"],
        detail=row["detail"] or "",
        citation=row["citation"] or "",
        zone=row["zone"],
        severity=row["severity"],
        rule_status=row["rule_status"],
        caveat=row["caveat"],
        effort_hours=float(row["effort_hours"]) if row["effort_hours"] is not None else None,
        cost_est_usd=float(row["cost_est_usd"]) if row["cost_est_usd"] is not None else None,
        score_if_done=row["score_if_done"],
        done=True,
    )
