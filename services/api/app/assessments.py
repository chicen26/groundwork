"""Turning a scan's evidence into a stored assessment and plan.

This is the seam between the database and the deterministic engine: it gathers what a scan knows,
hands it to `rules.engine`, and writes the result back as an immutable snapshot. The engine itself
never touches SQL, which is what keeps it testable without a database and reviewable as arithmetic.
"""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg

from app.rules.engine import Assessment, Evidence, build_plan, evaluate
from app.rules.rulebook import Rulebook

_EVIDENCE_QUERY = """
SELECT f.id::text AS finding_id,
       f.hazard::text AS hazard,
       f.source::text AS source,
       f.status::text AS status,
       f.confidence
FROM findings f
WHERE f.scan_id = $1
"""

_ANSWERS_QUERY = """
SELECT question_id, hazard_present
FROM checklist_answers
WHERE scan_id = $1
"""


async def gather_evidence(conn: asyncpg.Connection, scan_id: UUID) -> list[Evidence]:
    """Collect everything known about a scan, from the model and from the user."""
    evidence: list[Evidence] = []

    for row in await conn.fetch(_EVIDENCE_QUERY, scan_id):
        evidence.append(
            Evidence(
                key=row["hazard"],
                source=row["source"],
                confidence=float(row["confidence"]) if row["confidence"] is not None else None,
                confirmed=row["status"] == "confirmed",
                dismissed=row["status"] == "dismissed",
                resolved=row["status"] == "resolved",
                finding_id=row["finding_id"],
            )
        )

    for row in await conn.fetch(_ANSWERS_QUERY, scan_id):
        # Only a "yes" is evidence. A "no" is the absence of a hazard, which the engine represents
        # by there being nothing to trigger the rule.
        if row["hazard_present"]:
            evidence.append(Evidence(key=row["question_id"], source="checklist"))

    return evidence


async def assess_scan(
    conn: asyncpg.Connection, scan_id: UUID, *, rulebook: Rulebook, fhsz: str
) -> tuple[UUID, Assessment]:
    """Evaluate a scan and persist the result as a new assessment with its plan."""
    evidence = await gather_evidence(conn, scan_id)
    assessment = evaluate(rulebook, fhsz=fhsz, evidence=evidence)

    assessment_id = await conn.fetchval(
        """
        INSERT INTO assessments (scan_id, score, rulebook_version, breakdown)
        VALUES ($1, $2, $3, $4::jsonb) RETURNING id
        """,
        scan_id,
        assessment.score,
        assessment.rulebook_version,
        json.dumps(assessment.breakdown()),
    )

    plan_id = await conn.fetchval(
        "INSERT INTO plans (assessment_id) VALUES ($1) RETURNING id", assessment_id
    )

    for item in build_plan(assessment):
        await conn.execute(
            """
            INSERT INTO plan_items (
                plan_id, rank, kind, rule_id, finding_id, title, detail, citation,
                zone, severity, rule_status, caveat, effort_hours, cost_est_usd, score_if_done
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            """,
            plan_id,
            item.rank,
            item.kind,
            item.rule_id,
            # A plan item points at one finding for the before/after pairing; the rest stay linked
            # through the rule id.
            UUID(item.finding_ids[0]) if item.finding_ids else None,
            item.title,
            item.detail,
            item.citation,
            item.zone,
            item.severity.value,
            item.status.value,
            item.caveat,
            item.effort_hours,
            item.cost_est_usd,
            item.score_if_done,
        )

    return assessment_id, assessment
