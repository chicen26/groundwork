"""Aggregate impact, honestly counted.

One public number set: how much ground Groundwork has actually covered, across every account.
Totals only, computed live from the same tables everything else uses — no per-user data leaves
this endpoint, and nothing is cached to look bigger than it is. Rebate dollars are recomputed
with the same calculators the lawn screen uses, counting each measured lawn's own utility
programme, so the headline number can never disagree with what any individual user was shown.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel

from app.db import pool
from app.water.rebates import annual_gallons_saved, estimate, program_for

router = APIRouter(prefix="/stats", tags=["stats"])


class Impact(BaseModel):
    properties: int
    assessments: int
    plan_items_done: int
    hazards_addressed: int
    lawn_sqft_measured: int
    annual_gallons_saved: int
    rebate_dollars_identified: int


@router.get("/impact", response_model=Impact)
async def impact() -> Impact:
    async with pool.acquire_service() as conn:
        counts = await conn.fetchrow(
            """
            SELECT
              (SELECT count(*) FROM properties)                                   AS properties,
              (SELECT count(*) FROM assessments)                                  AS assessments,
              (SELECT count(*) FROM plan_items WHERE done_at IS NOT NULL)         AS done_items,
              (SELECT count(*) FROM findings WHERE status IN ('confirmed', 'resolved'))
                                                                                  AS hazards,
              (SELECT COALESCE(sum(area_sqft), 0) FROM lawn_polygons)             AS lawn_sqft
            """
        )
        lawns = await conn.fetch(
            """
            SELECT l.area_sqft, p.water_utility
            FROM lawn_polygons l JOIN properties p ON p.id = l.property_id
            """
        )

    rebate_total = Decimal("0")
    for lawn in lawns:
        program = program_for(lawn["water_utility"])
        if program is None:
            continue
        result = estimate(program, lawn["area_sqft"])
        if result.eligible:
            rebate_total += result.amount_usd

    lawn_sqft = Decimal(str(counts["lawn_sqft"]))
    return Impact(
        properties=counts["properties"],
        assessments=counts["assessments"],
        plan_items_done=counts["done_items"],
        hazards_addressed=counts["hazards"],
        lawn_sqft_measured=int(lawn_sqft),
        annual_gallons_saved=int(annual_gallons_saved(lawn_sqft)),
        rebate_dollars_identified=int(rebate_total),
    )
