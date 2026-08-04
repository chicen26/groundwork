"""Rebate arithmetic tests.

These numbers appear on a homeowner's screen next to a utility's name, and people budget projects
around them. So: exact decimal arithmetic, rounding that never favours us, caps that bite, minimums
that refuse with a reason, and the pre-approval warning present on every single result — a rebate
is void if the lawn comes out before the inspection, no matter how good the finished yard is.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.water.rebates import (
    annual_gallons_saved,
    estimate,
    estimate_all,
    load_programs,
    program_for,
    universal_warning,
)

EBMUD = program_for("EBMUD")
CCWD = program_for("CCWD")
DSRSD = program_for("DSRSD")


def test_the_configured_utilities_are_the_ones_we_serve() -> None:
    assert {p.agency for p in load_programs()} == {"EBMUD", "CCWD", "DSRSD"}


# --------------------------------------------------------------------------- the arithmetic


def test_a_straightforward_rebate() -> None:
    result = estimate(CCWD, 500)

    assert result.amount_usd == Decimal("500.00")
    assert result.rate_per_sqft == Decimal("1.00")
    assert result.capped is False


def test_the_higher_rate_utility_pays_double() -> None:
    assert estimate(DSRSD, 500).amount_usd == Decimal("1000.00")


def test_the_cap_bites_and_says_so() -> None:
    """A bigger lawn does not mean a bigger cheque, and the screen should be able to explain why."""
    result = estimate(CCWD, 5000)

    assert result.uncapped_usd == Decimal("5000.00")
    assert result.amount_usd == Decimal("2000.00")
    assert result.capped is True
    assert result.cap_usd == Decimal("2000.00")


def test_dsrsds_higher_cap_is_honoured() -> None:
    result = estimate(DSRSD, 5000)

    assert result.amount_usd == Decimal("3000.00")
    assert result.capped is True


def test_money_is_exact_not_floating_point() -> None:
    """0.1 + 0.2 problems in a dollar figure are the sort of bug nobody forgives."""
    result = estimate(CCWD, Decimal("333.33"))

    assert result.amount_usd == Decimal("333.33")
    assert isinstance(result.amount_usd, Decimal)


def test_payouts_round_down_to_the_cent() -> None:
    """Round in the utility's favour, not ours: they pay for the square feet actually converted."""
    result = estimate(CCWD, Decimal("100.999"))

    assert result.amount_usd == Decimal("100.99")


def test_the_super_tier_uses_its_own_rate() -> None:
    standard = estimate(EBMUD, 400)
    super_tier = estimate(EBMUD, 400, tier_key="super")

    assert standard.amount_usd == Decimal("400.00")
    assert super_tier.amount_usd == Decimal("800.00")
    assert super_tier.tier_label == "Super Rebate"


def test_an_unknown_tier_falls_back_to_the_base_rate() -> None:
    result = estimate(EBMUD, 400, tier_key="platinum-deluxe")

    assert result.rate_per_sqft == EBMUD.rate_per_sqft
    assert result.tier_key is None


# --------------------------------------------------------------------------- refusing honestly


def test_a_lawn_under_the_minimum_pays_nothing_and_explains_why() -> None:
    """A small number the utility will later reject is worse than a clear zero."""
    result = estimate(CCWD, 50)

    assert result.eligible is False
    assert result.amount_usd == Decimal("0.00")
    assert "at least 100 sq ft" in result.ineligible_reason
    assert "50" in result.ineligible_reason


def test_exactly_the_minimum_is_eligible() -> None:
    result = estimate(CCWD, 100)

    assert result.eligible is True
    assert result.amount_usd == Decimal("100.00")


def test_an_unknown_utility_yields_no_programme() -> None:
    """Walnut Creek and San Ramon are split between utilities; guessing gets the rate wrong."""
    assert program_for(None) is None
    assert program_for("Some Other Water Company") is None


def test_when_the_utility_is_unknown_every_programme_is_shown() -> None:
    results = estimate_all(500)

    assert len(results) == 3
    assert {r["agency"] for r in results} == {"EBMUD", "CCWD", "DSRSD"}
    for result in results:
        assert result["warning"]


# --------------------------------------------------------------------------- the warning


def test_every_estimate_carries_the_pre_approval_warning() -> None:
    """Removing the lawn before approval voids the rebate. This cannot be a footnote elsewhere."""
    for program in load_programs():
        result = estimate(program, 400)
        assert result.warning
        assert "BEFORE" in result.warning


def test_the_warning_says_what_happens_if_you_start_early() -> None:
    warning = universal_warning().lower()

    assert "before" in warning
    assert "not eligible" in warning or "void" in warning


def test_every_programme_links_to_its_own_application_page() -> None:
    for program in load_programs():
        assert program.url.startswith("https://")


# --------------------------------------------------------------------------- water savings


def test_water_saving_scales_with_area() -> None:
    assert annual_gallons_saved(1000) == Decimal("30000")
    assert annual_gallons_saved(500) == Decimal("15000")


def test_water_saving_is_a_whole_number_of_gallons() -> None:
    """Decimals here would imply a precision a regional ET average does not have."""
    result = annual_gallons_saved(Decimal("333.33"))

    assert result == result.to_integral_value()


def test_zero_area_saves_nothing() -> None:
    assert annual_gallons_saved(0) == Decimal("0")


# --------------------------------------------------------------------------- determinism


@pytest.mark.parametrize("area", [100, 500, 1234, 5000, Decimal("2500.55")])
def test_the_same_lawn_always_produces_the_same_figure(area) -> None:
    amounts = {estimate(EBMUD, area).amount_usd for _ in range(20)}

    assert len(amounts) == 1
