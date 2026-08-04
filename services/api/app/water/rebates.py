"""Rebate arithmetic.

This is money on a homeowner's screen, so every rule in governing principle 1 applies at once: it is
deterministic, it uses `Decimal` end to end, and no model output touches it. A wrong readiness score
is embarrassing; a wrong rebate figure is someone budgeting a project around a number we invented.

Three things this module refuses to do:

* Round in our favour. Payouts round **down** to the cent, the way a utility calculates them.
* Present an estimate as a promise. Every result carries the pre-approval warning and is labelled an
  estimate.
* Quietly ignore a minimum. A lawn below a programme's threshold returns zero with the reason, not a
  small number that will be rejected later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from functools import lru_cache
from pathlib import Path

PROGRAMS_PATH = Path(__file__).resolve().parents[2] / "programs" / "rebates.json"

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Tier:
    key: str
    label: str
    rate_per_sqft: Decimal
    requirements: str


@dataclass(frozen=True)
class RebateProgram:
    key: str
    agency: str
    agency_full: str
    name: str
    rate_per_sqft: Decimal
    cap_usd: Decimal
    minimum_sqft: int
    url: str
    tiers: tuple[Tier, ...]


@dataclass(frozen=True)
class RebateEstimate:
    program_key: str
    agency: str
    program_name: str
    tier_key: str | None
    tier_label: str | None
    area_sqft: Decimal
    rate_per_sqft: Decimal
    # What the rate alone would pay, before the cap. Shown when the cap bites, so someone can see
    # why a bigger lawn does not mean a bigger cheque.
    uncapped_usd: Decimal
    amount_usd: Decimal
    capped: bool
    cap_usd: Decimal
    eligible: bool
    # Populated when eligible is False. Always a reason, never a bare zero.
    ineligible_reason: str | None
    url: str
    warning: str

    def as_dict(self) -> dict:
        return {
            "program_key": self.program_key,
            "agency": self.agency,
            "program_name": self.program_name,
            "tier_key": self.tier_key,
            "tier_label": self.tier_label,
            "area_sqft": str(self.area_sqft),
            "rate_per_sqft": str(self.rate_per_sqft),
            "uncapped_usd": str(self.uncapped_usd),
            "amount_usd": str(self.amount_usd),
            "capped": self.capped,
            "cap_usd": str(self.cap_usd),
            "eligible": self.eligible,
            "ineligible_reason": self.ineligible_reason,
            "url": self.url,
            "warning": self.warning,
        }


@lru_cache
def _config(path: Path = PROGRAMS_PATH) -> dict:
    return json.loads(path.read_text())


def universal_warning() -> str:
    return _config()["universal_warning"]


@lru_cache
def load_programs(path: Path = PROGRAMS_PATH) -> tuple[RebateProgram, ...]:
    return tuple(
        RebateProgram(
            key=entry["key"],
            agency=entry["agency"],
            agency_full=entry["agency_full"],
            name=entry["name"],
            rate_per_sqft=Decimal(entry["rate_per_sqft"]),
            cap_usd=Decimal(entry["cap_usd"]),
            minimum_sqft=int(entry["minimum_sqft"]),
            url=entry["url"],
            tiers=tuple(
                Tier(
                    key=tier["key"],
                    label=tier["label"],
                    rate_per_sqft=Decimal(tier["rate_per_sqft"]),
                    requirements=tier["requirements"],
                )
                for tier in entry.get("tiers", [])
            ),
        )
        for entry in _config(path)["programs"]
    )


def program_for(agency: str | None) -> RebateProgram | None:
    """The programme for a utility, or None when we could not determine the utility.

    None is a real answer here. Walnut Creek and San Ramon are each split between two utilities, so
    guessing from a city name would hand someone the wrong rate and the wrong cap.
    """
    if not agency:
        return None
    return next((p for p in load_programs() if p.agency.upper() == agency.upper()), None)


def estimate(
    program: RebateProgram, area_sqft: Decimal | float | int, *, tier_key: str | None = None
) -> RebateEstimate:
    """What this programme would pay for this much lawn."""
    area = Decimal(str(area_sqft))

    tier = next((t for t in program.tiers if t.key == tier_key), None)
    rate = tier.rate_per_sqft if tier else program.rate_per_sqft

    # Truncate rather than round: a utility pays for the square feet you actually converted.
    uncapped = (area * rate).quantize(CENT, rounding=ROUND_DOWN)
    amount = min(uncapped, program.cap_usd)

    eligible = area >= program.minimum_sqft
    reason = (
        None
        if eligible
        else (
            f"{program.agency} requires at least {program.minimum_sqft} sq ft of lawn to be "
            f"converted; this area is {area} sq ft."
        )
    )

    return RebateEstimate(
        program_key=program.key,
        agency=program.agency,
        program_name=program.name,
        tier_key=tier.key if tier else None,
        tier_label=tier.label if tier else None,
        area_sqft=area,
        rate_per_sqft=rate,
        uncapped_usd=uncapped,
        amount_usd=amount if eligible else Decimal("0.00"),
        capped=eligible and uncapped > program.cap_usd,
        cap_usd=program.cap_usd,
        eligible=eligible,
        ineligible_reason=reason,
        url=program.url,
        warning=universal_warning(),
    )


def estimate_all(area_sqft: Decimal | float | int, *, tier_key: str | None = None) -> list[dict]:
    """Every programme's estimate, for when we could not determine the utility.

    Showing all three with their agencies named is more honest than picking one and being wrong.
    """
    return [
        estimate(program, area_sqft, tier_key=tier_key).as_dict() for program in load_programs()
    ]


def annual_gallons_saved(area_sqft: Decimal | float | int) -> Decimal:
    """Estimated annual water saving from converting this much lawn.

    Deliberately a whole number of gallons: implying precision past that would misrepresent a
    figure derived from a regional evapotranspiration average.
    """
    factor = Decimal(_config()["water_savings"]["gallons_per_sqft_per_year"])
    return (Decimal(str(area_sqft)) * factor).quantize(Decimal("1"), rounding=ROUND_DOWN)


def savings_basis() -> str:
    return _config()["water_savings"]["basis"]
