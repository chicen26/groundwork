"""Tests for the rulebook we actually ship.

The engine tests use synthetic rules to prove the arithmetic. These check the real content: that
every shipped rule is honest about its legal status, that the six detector classes all connect to
something, and that a homeowner in a Very High zone with a messy yard gets a plan that leads with
the law rather than with a draft regulation.
"""

from __future__ import annotations

import pytest

from app.rules.engine import Evidence, build_plan, evaluate
from app.rules.rulebook import RuleStatus, available_versions, load_rulebook

# Kept in lockstep with the hazard_class enum in migration 002 and with ml/README.md.
DETECTOR_CLASSES = {
    "veg_touching_structure",
    "overhanging_limbs",
    "combustible_mulch_z0",
    "attached_wood_fence",
    "combustibles_under_deck",
    "dead_vegetation",
}


@pytest.fixture(scope="module")
def rulebook():
    return load_rulebook("2026.08")


def test_at_least_one_rulebook_ships() -> None:
    assert available_versions()


def test_every_rule_cites_a_source(rulebook) -> None:
    for rule in rulebook.rules:
        assert rule.citation, rule.id
        assert rule.authority, rule.id
        assert rule.rationale, rule.id


def test_draft_rules_are_marked_and_caveated(rulebook) -> None:
    """Zone 0 is not law yet. Every rule derived from it must say so."""
    zone0_rules = [rule for rule in rulebook.rules if rule.id.startswith("zone0.")]

    assert zone0_rules, "the draft Zone 0 rules are the creative thesis; they should exist"
    for rule in zone0_rules:
        assert rule.status is RuleStatus.PENDING_ADOPTION, rule.id
        assert "draft" in rule.caveat.lower(), rule.id
        assert "not" in rule.caveat.lower(), rule.id


def test_statutory_rules_are_marked_in_effect(rulebook) -> None:
    for rule in (r for r in rulebook.rules if r.id.startswith("prc4291.")):
        assert rule.status is RuleStatus.IN_EFFECT, rule.id
        assert "PRC 4291" in rule.citation, rule.id


def test_advisory_rules_are_not_presented_as_law(rulebook) -> None:
    for rule in (r for r in rulebook.rules if r.id.startswith("ibhs.")):
        assert rule.status is RuleStatus.ADVISORY, rule.id


def test_every_detector_class_drives_at_least_one_rule(rulebook) -> None:
    """A class we train the model to detect but never act on is wasted labelling effort."""
    triggered = {hazard for rule in rulebook.rules for hazard in rule.triggers.hazards}

    assert triggered >= DETECTOR_CLASSES, f"unused classes: {DETECTOR_CLASSES - triggered}"


def test_no_rule_triggers_on_an_unknown_hazard_class(rulebook) -> None:
    """A typo in a rulebook trigger would silently make that rule unreachable."""
    triggered = {hazard for rule in rulebook.rules for hazard in rule.triggers.hazards}

    assert triggered <= DETECTOR_CLASSES, f"unknown classes: {triggered - DETECTOR_CLASSES}"


def test_statutory_rules_do_not_apply_outside_hazard_zones(rulebook) -> None:
    """PRC 4291 is a wildland requirement; applying it to a city lot would be a false obligation."""
    for rule in (r for r in rulebook.rules if r.id.startswith(("prc4291.", "zone0."))):
        assert rule.applicability.fhsz_in, rule.id
        assert "non_wildland" not in rule.applicability.fhsz_in, rule.id


def test_a_clean_property_in_a_very_high_zone_scores_full_marks(rulebook) -> None:
    assessment = evaluate(rulebook, fhsz="very_high", evidence=[], state="CA")

    assert assessment.score == 100
    assert build_plan(assessment) == []


def test_a_messy_very_high_property_is_led_by_binding_law(rulebook) -> None:
    """The demo case: every detector fires, and the plan opens with what is required today."""
    evidence = [
        Evidence(key=hazard, source="model", confidence=0.9, finding_id=f"f-{hazard}")
        for hazard in DETECTOR_CLASSES
    ]

    assessment = evaluate(rulebook, fhsz="very_high", evidence=evidence, state="CA")
    plan = build_plan(assessment)

    assert assessment.score < 60
    assert plan[0].status is RuleStatus.IN_EFFECT
    # Draft items still appear — they are the point of the product — but below the binding ones.
    statuses = [item.status for item in plan]
    assert statuses.index(RuleStatus.IN_EFFECT) < statuses.index(RuleStatus.PENDING_ADOPTION)


def test_the_same_yard_is_judged_less_harshly_outside_a_hazard_zone(rulebook) -> None:
    """Zone 0 and PRC 4291 do not apply in a non-wildland area, so the score should reflect that."""
    evidence = [Evidence(key=hazard, source="model", confidence=0.9) for hazard in DETECTOR_CLASSES]

    very_high = evaluate(rulebook, fhsz="very_high", evidence=evidence, state="CA")
    non_wildland = evaluate(rulebook, fhsz="non_wildland", evidence=evidence, state="CA")

    assert non_wildland.score > very_high.score


def test_an_unknown_zone_still_yields_advisory_guidance(rulebook) -> None:
    """When we cannot determine the zone, the user still gets the advice that applies anywhere."""
    assessment = evaluate(
        rulebook,
        fhsz="unknown",
        evidence=[Evidence(key="storage_under_deck", source="checklist")],
    )

    assert assessment.outcomes, "advisory rules apply regardless of zone"
    assert assessment.score < 100
    assert assessment.binding_failures == []


def test_the_disclaimer_travels_with_every_assessment(rulebook) -> None:
    assessment = evaluate(rulebook, fhsz="very_high", evidence=[], state="CA")

    assert "not an official inspection" in assessment.disclaimer.lower()
    assert "evacuation" in assessment.disclaimer.lower()


# --------------------------------------------------------------------------- jurisdiction


def test_a_homeowner_outside_california_still_gets_a_real_assessment(rulebook) -> None:
    """The national advisory base is the floor. Nobody sees an empty screen because of geography."""
    evidence = [Evidence(key=h, source="model", confidence=0.9) for h in DETECTOR_CLASSES]

    colorado = evaluate(rulebook, fhsz="unknown", evidence=evidence, state="CO")
    plan = build_plan(colorado)

    assert colorado.outcomes, "the advisory rules apply in every state"
    assert colorado.score < 100
    assert plan, "a failing advisory rule still produces something to do"
    for item in plan:
        assert item.citation


def test_california_law_does_not_apply_outside_california(rulebook) -> None:
    """PRC 4291 is California code. Citing it to someone in Texas would be a false obligation."""
    evidence = [Evidence(key=h, source="model", confidence=0.9) for h in DETECTOR_CLASSES]

    texas = evaluate(rulebook, fhsz="unknown", evidence=evidence, state="TX")

    assert texas.binding_failures == [], "no state statute is in force for a Texas property"
    assert not [o for o in texas.outcomes if o.rule.id.startswith(("prc4291.", "zone0."))]


def test_a_californian_is_not_counted_twice_for_one_hazard(rulebook) -> None:
    """Both an advisory rule and a stricter state rule cover mulch. Only the stricter one counts."""
    evidence = [Evidence(key="combustible_mulch_z0", source="model", confidence=0.9)]

    california = evaluate(rulebook, fhsz="very_high", evidence=evidence, state="CA")
    triggered = [o.rule.id for o in california.failures]

    assert "zone0.combustible_mulch" in triggered
    assert "ibhs.zone0_noncombustible" not in triggered


def test_the_advisory_rule_covers_the_gap_outside_california(rulebook) -> None:
    """The same mulch is still a finding in Colorado, just advisory rather than statutory."""
    evidence = [Evidence(key="combustible_mulch_z0", source="model", confidence=0.9)]

    colorado = evaluate(rulebook, fhsz="unknown", evidence=evidence, state="CO")
    triggered = [o.rule.id for o in colorado.failures]

    assert "ibhs.zone0_noncombustible" in triggered


def test_every_detector_class_is_actionable_in_any_state(rulebook) -> None:
    """A class we detect but no national rule acts on is dead weight outside California."""
    national = [r for r in rulebook.rules if not r.applicability.states]
    covered = {hazard for rule in national for hazard in rule.triggers.hazards}

    assert covered >= DETECTOR_CLASSES, f"no national rule for: {DETECTOR_CLASSES - covered}"


def test_state_specific_rules_declare_their_state(rulebook) -> None:
    for rule in rulebook.rules:
        if rule.id.startswith(("prc4291.", "zone0.")):
            assert rule.applicability.states == ["CA"], rule.id


def test_an_unknown_state_falls_back_to_the_national_base(rulebook) -> None:
    """A dropped pin we cannot place still yields advice, never a blank result."""
    evidence = [Evidence(key="dead_vegetation", source="model", confidence=0.9)]

    assessment = evaluate(rulebook, fhsz="unknown", evidence=evidence, state=None)

    assert assessment.outcomes
    assert assessment.score < 100
