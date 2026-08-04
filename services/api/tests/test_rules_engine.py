"""Rules engine tests.

This is the arithmetic behind a number we show a homeowner next to statutory citations, so it gets
tested harder than anything else in the service. The properties that matter:

* The same inputs always produce the same score (no model output reaches the arithmetic).
* A rule that does not apply to a property never counts against it.
* Uncertain detections do not silently move the score.
* The "your score becomes X" preview cannot disagree with the score you actually get.
"""

from __future__ import annotations

import pytest

from app.rules.engine import Evidence, build_plan, evaluate, score_if_resolved
from app.rules.rulebook import Rulebook, RuleStatus

BASE_RULE = {
    "id": "test.rule",
    "title": "A rule",
    "rationale": "Because.",
    "citation": "PRC 4291(a)(1)",
    "authority": "Test authority",
    "status": "in_effect",
    "zone": "5-30ft",
    "severity": "critical",
    "weight": 10,
    "triggers": {"hazards": ["dead_vegetation"]},
    "action": {"title": "Do the thing"},
}


def make_rulebook(*rules: dict, confidence_threshold: float = 0.5) -> Rulebook:
    return Rulebook.model_validate(
        {
            "version": "test",
            "disclaimer": "Educational guidance, not an inspection.",
            "confidence_threshold": confidence_threshold,
            "rules": list(rules) or [BASE_RULE],
        }
    )


def model_evidence(key: str, confidence: float = 0.9, **kwargs) -> Evidence:
    return Evidence(key=key, source="model", confidence=confidence, **kwargs)


# --------------------------------------------------------------------------- scoring


def test_a_property_meeting_everything_scores_one_hundred() -> None:
    assessment = evaluate(make_rulebook(), fhsz="very_high", evidence=[])

    assert assessment.score == 100
    assert assessment.failures == []


def test_a_property_failing_everything_scores_zero() -> None:
    assessment = evaluate(
        make_rulebook(), fhsz="very_high", evidence=[model_evidence("dead_vegetation")]
    )

    assert assessment.score == 0


def test_score_is_the_proportion_of_applicable_weight_met() -> None:
    """Two rules weighted 10 and 30; failing the lighter one costs a quarter of the score."""
    heavy = {**BASE_RULE, "id": "heavy", "weight": 30, "triggers": {"checklist": ["heavy_q"]}}
    assessment = evaluate(
        make_rulebook(BASE_RULE, heavy),
        fhsz="very_high",
        evidence=[model_evidence("dead_vegetation")],
    )

    assert assessment.applicable_weight == 40
    assert assessment.met_weight == 30
    assert assessment.score == 75


def test_rules_that_do_not_apply_are_absent_from_both_sides_of_the_fraction() -> None:
    """A flat non-wildland lot is not marked down for a slope rule it can never trigger."""
    wildland_only = {
        **BASE_RULE,
        "id": "wildland.only",
        "applicability": {"fhsz_in": ["very_high"]},
    }
    everywhere = {
        **BASE_RULE,
        "id": "everywhere",
        "weight": 5,
        "triggers": {"checklist": ["gutters_full"]},
    }
    rulebook = make_rulebook(wildland_only, everywhere)

    assessment = evaluate(rulebook, fhsz="non_wildland", evidence=[])

    assert [outcome.rule.id for outcome in assessment.outcomes] == ["everywhere"]
    assert assessment.applicable_weight == 5


def test_a_property_with_no_applicable_rules_scores_one_hundred() -> None:
    rulebook = make_rulebook({**BASE_RULE, "applicability": {"fhsz_in": ["very_high"]}})

    assessment = evaluate(rulebook, fhsz="non_wildland", evidence=[])

    assert assessment.score == 100
    assert assessment.outcomes == ()


def test_scoring_is_deterministic() -> None:
    rulebook = make_rulebook()
    evidence = [model_evidence("dead_vegetation", confidence=0.62)]

    scores = {evaluate(rulebook, fhsz="high", evidence=evidence).score for _ in range(25)}

    assert scores == {0}


def test_score_rounds_half_up() -> None:
    """A property one point short of a threshold must not be displayed as having reached it."""
    rules = [
        {**BASE_RULE, "id": f"rule.{i}", "weight": 1, "triggers": {"checklist": [f"q{i}"]}}
        for i in range(8)
    ]
    # Five of eight equal-weight rules met is 62.5, which must present as 63 rather than 62.
    evidence = [Evidence(key=f"q{i}", source="checklist") for i in range(3)]

    assessment = evaluate(make_rulebook(*rules), fhsz="high", evidence=evidence)

    assert assessment.score == 63


# --------------------------------------------------------------------------- evidence handling


def test_low_confidence_detections_do_not_move_the_score() -> None:
    """Below threshold is "possible — confirm", not a fact we score against."""
    assessment = evaluate(
        make_rulebook(confidence_threshold=0.5),
        fhsz="very_high",
        evidence=[model_evidence("dead_vegetation", confidence=0.31)],
    )

    assert assessment.score == 100
    assert len(assessment.needs_confirmation) == 1
    assert assessment.needs_confirmation[0].unconfirmed[0].confidence == 0.31


def test_a_confirmed_low_confidence_detection_does_count() -> None:
    """The user's confirmation is what makes it a fact — the model only proposed it."""
    assessment = evaluate(
        make_rulebook(confidence_threshold=0.5),
        fhsz="very_high",
        evidence=[model_evidence("dead_vegetation", confidence=0.2, confirmed=True)],
    )

    assert assessment.score == 0


def test_dismissed_and_resolved_evidence_is_ignored() -> None:
    rulebook = make_rulebook()

    dismissed = evaluate(
        rulebook, fhsz="high", evidence=[model_evidence("dead_vegetation", dismissed=True)]
    )
    resolved = evaluate(
        rulebook, fhsz="high", evidence=[model_evidence("dead_vegetation", resolved=True)]
    )

    assert dismissed.score == 100
    assert resolved.score == 100
    assert dismissed.needs_confirmation == []


def test_a_checklist_answer_always_counts() -> None:
    """A user's own answer carries no confidence, and needs none."""
    rule = {**BASE_RULE, "triggers": {"checklist": ["dead_vegetation_present"]}}

    assessment = evaluate(
        make_rulebook(rule),
        fhsz="high",
        evidence=[Evidence(key="dead_vegetation_present", source="checklist")],
    )

    assert assessment.score == 0


def test_either_kind_of_evidence_can_trigger_one_rule() -> None:
    rule = {
        **BASE_RULE,
        "triggers": {"hazards": ["dead_vegetation"], "checklist": ["dead_vegetation_present"]},
    }

    from_model = evaluate(
        make_rulebook(rule), fhsz="high", evidence=[model_evidence("dead_vegetation")]
    )
    from_user = evaluate(
        make_rulebook(rule),
        fhsz="high",
        evidence=[Evidence(key="dead_vegetation_present", source="checklist")],
    )

    assert from_model.score == from_user.score == 0


# --------------------------------------------------------------------------- explanation


def test_the_breakdown_arithmetic_adds_up() -> None:
    heavy = {**BASE_RULE, "id": "heavy", "weight": 30, "triggers": {"checklist": ["heavy_q"]}}
    assessment = evaluate(
        make_rulebook(BASE_RULE, heavy),
        fhsz="very_high",
        evidence=[model_evidence("dead_vegetation", finding_id="f-1")],
    )
    breakdown = assessment.breakdown()

    assert breakdown["applicable_weight"] == 40
    assert sum(rule["weight_lost"] for rule in breakdown["rules"]) == 10
    assert breakdown["met_weight"] + sum(r["weight_lost"] for r in breakdown["rules"]) == 40


def test_every_reported_rule_carries_its_citation() -> None:
    """A finding the user cannot check the source of is an assertion, not guidance."""
    assessment = evaluate(
        make_rulebook(), fhsz="very_high", evidence=[model_evidence("dead_vegetation")]
    )

    for rule in assessment.breakdown()["rules"]:
        assert rule["citation"]
        assert rule["authority"]


def test_binding_failures_are_distinguished_from_draft_ones() -> None:
    draft = {
        **BASE_RULE,
        "id": "draft.rule",
        "status": "pending_adoption",
        "caveat": "Not yet adopted.",
        "triggers": {"checklist": ["draft_q"]},
    }
    assessment = evaluate(
        make_rulebook(BASE_RULE, draft),
        fhsz="very_high",
        evidence=[
            model_evidence("dead_vegetation"),
            Evidence(key="draft_q", source="checklist"),
        ],
    )

    assert len(assessment.failures) == 2
    assert [outcome.rule.id for outcome in assessment.binding_failures] == ["test.rule"]


# --------------------------------------------------------------------------- plan


def test_the_plan_ranks_law_above_a_draft_of_equal_weight() -> None:
    draft = {
        **BASE_RULE,
        "id": "draft.rule",
        "status": "pending_adoption",
        "caveat": "Not yet adopted.",
        "triggers": {"checklist": ["draft_q"]},
    }
    assessment = evaluate(
        make_rulebook(draft, BASE_RULE),
        fhsz="very_high",
        evidence=[
            model_evidence("dead_vegetation"),
            Evidence(key="draft_q", source="checklist"),
        ],
    )

    plan = build_plan(assessment)

    assert [item.rule_id for item in plan] == ["test.rule", "draft.rule"]
    assert [item.rank for item in plan] == [1, 2]


def test_a_draft_plan_item_carries_its_caveat() -> None:
    draft = {
        **BASE_RULE,
        "id": "draft.rule",
        "status": "pending_adoption",
        "caveat": "Zone 0 has not been finally adopted.",
        "triggers": {"checklist": ["draft_q"]},
    }
    assessment = evaluate(
        make_rulebook(draft), fhsz="very_high", evidence=[Evidence("draft_q", "checklist")]
    )

    item = build_plan(assessment)[0]

    assert item.status is RuleStatus.PENDING_ADOPTION
    assert item.caveat == "Zone 0 has not been finally adopted."


def test_score_preview_matches_the_score_after_doing_the_work() -> None:
    """The preview and the real recomputation must never disagree."""
    heavy = {**BASE_RULE, "id": "heavy", "weight": 30, "triggers": {"checklist": ["heavy_q"]}}
    rulebook = make_rulebook(BASE_RULE, heavy)
    evidence = [
        model_evidence("dead_vegetation"),
        Evidence(key="heavy_q", source="checklist"),
    ]
    before = evaluate(rulebook, fhsz="very_high", evidence=evidence)

    previewed = score_if_resolved(before, {"heavy"})
    after = evaluate(
        rulebook,
        fhsz="very_high",
        evidence=[
            model_evidence("dead_vegetation"),
            Evidence(key="heavy_q", source="checklist", resolved=True),
        ],
    )

    assert previewed == after.score == 75


def test_plan_items_preview_their_own_completion() -> None:
    heavy = {**BASE_RULE, "id": "heavy", "weight": 30, "triggers": {"checklist": ["heavy_q"]}}
    assessment = evaluate(
        make_rulebook(BASE_RULE, heavy),
        fhsz="very_high",
        evidence=[
            model_evidence("dead_vegetation"),
            Evidence(key="heavy_q", source="checklist"),
        ],
    )

    plan = build_plan(assessment)

    assert {item.rule_id: item.score_if_done for item in plan} == {"heavy": 75, "test.rule": 25}


def test_plan_items_link_back_to_the_findings_that_caused_them() -> None:
    assessment = evaluate(
        make_rulebook(),
        fhsz="very_high",
        evidence=[model_evidence("dead_vegetation", finding_id="finding-123")],
    )

    assert build_plan(assessment)[0].finding_ids == ["finding-123"]


def test_a_property_meeting_everything_has_an_empty_plan() -> None:
    assessment = evaluate(make_rulebook(), fhsz="very_high", evidence=[])

    assert build_plan(assessment) == []


# --------------------------------------------------------------------------- rulebook validation


def test_a_pending_rule_without_a_caveat_is_rejected() -> None:
    """Stating a draft regulation without qualification would misinform someone about the law."""
    with pytest.raises(ValueError, match="caveat"):
        make_rulebook({**BASE_RULE, "status": "pending_adoption"})


def test_a_rule_with_no_triggers_is_rejected() -> None:
    with pytest.raises(ValueError, match="trigger"):
        make_rulebook({**BASE_RULE, "triggers": {}})


def test_a_rule_without_a_citation_is_rejected() -> None:
    with pytest.raises(ValueError):
        make_rulebook({**BASE_RULE, "citation": ""})


def test_duplicate_rule_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        make_rulebook(BASE_RULE, dict(BASE_RULE))


def test_zero_or_negative_weights_are_rejected() -> None:
    with pytest.raises(ValueError):
        make_rulebook({**BASE_RULE, "weight": 0})
