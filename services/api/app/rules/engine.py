"""The rules engine and the Readiness Score.

Deterministic by design (decision D4). Given a property's hazard zone, the findings on its scan, and
the user's checklist answers, this produces the same score and the same explanation every time. No
model output reaches the arithmetic: detections decide which rules are *triggered*, and everything
after that is fixed weights over a fixed rulebook.

The score is a proportion, not a curve:

    score = 100 * (weight of applicable rules met) / (weight of all applicable rules)

That makes it explainable in one sentence — "you are meeting 68 out of 91 points of what applies to
your property" — and it means the breakdown adds up. A rule that does not apply to a property is
absent from both sides of the fraction, so a flat lot in a non-wildland area is not marked down for
failing to clear a slope it does not have.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.rules.rulebook import Rule, Rulebook, RuleStatus, Severity


@dataclass(frozen=True)
class Evidence:
    """One piece of evidence about a property, from the model or from the user."""

    # A detector class name, or a checklist question id.
    key: str
    source: str  # 'model' | 'checklist'
    confidence: float | None = None
    # Set once the user has confirmed or dismissed a model detection.
    confirmed: bool = False
    dismissed: bool = False
    # Cleared by a re-scan or a completed action.
    resolved: bool = False
    finding_id: str | None = None

    def counts(self, threshold: float) -> bool:
        """Whether this evidence should move the score.

        Dismissed and resolved evidence never counts. A user's own answer always counts. A model
        detection counts once confirmed, or while its confidence clears the rulebook's threshold —
        below that it is shown as "possible, confirm this" and left out of the arithmetic rather
        than quietly assumed.
        """
        if self.dismissed or self.resolved:
            return False
        if self.source == "checklist" or self.confirmed:
            return True
        return self.confidence is not None and self.confidence >= threshold


@dataclass(frozen=True)
class RuleOutcome:
    """One applicable rule and how the property fared against it."""

    rule: Rule
    met: bool
    # Evidence that triggered this rule, empty when met.
    evidence: tuple[Evidence, ...] = ()
    # Evidence too uncertain to count yet — surfaced so the user can confirm it.
    unconfirmed: tuple[Evidence, ...] = ()
    # Evidence that once triggered this rule and has since been resolved by doing the work. The
    # rule is met, but the plan should still show the task — as done, not as vanished.
    resolved_evidence: tuple[Evidence, ...] = ()

    @property
    def weight_lost(self) -> float:
        return 0.0 if self.met else self.rule.weight


@dataclass(frozen=True)
class Assessment:
    """The whole answer: a score, the arithmetic behind it, and what to do next."""

    score: int
    rulebook_version: str
    outcomes: tuple[RuleOutcome, ...]
    disclaimer: str
    applicable_weight: float = 0.0
    met_weight: float = 0.0

    @property
    def failures(self) -> list[RuleOutcome]:
        """Unmet rules, worst first — the order the action plan is built in."""
        return sorted(
            (outcome for outcome in self.outcomes if not outcome.met),
            key=lambda outcome: (-outcome.rule.weight, outcome.rule.id),
        )

    @property
    def needs_confirmation(self) -> list[RuleOutcome]:
        """Rules resting on detections the user has not confirmed yet."""
        return [outcome for outcome in self.outcomes if outcome.unconfirmed]

    @property
    def binding_failures(self) -> list[RuleOutcome]:
        """Unmet rules that are actually law today, as opposed to draft or advisory."""
        return [outcome for outcome in self.failures if outcome.rule.is_binding]

    def breakdown(self) -> dict:
        """Serialisable arithmetic, stored on the assessment so a score can always show its work."""
        return {
            "formula": "100 * met_weight / applicable_weight",
            "applicable_weight": round(self.applicable_weight, 3),
            "met_weight": round(self.met_weight, 3),
            "rules": [
                {
                    "rule_id": outcome.rule.id,
                    "title": outcome.rule.title,
                    "citation": outcome.rule.citation,
                    "authority": outcome.rule.authority,
                    "status": outcome.rule.status.value,
                    "zone": outcome.rule.zone.value,
                    "severity": outcome.rule.severity.value,
                    "weight": outcome.rule.weight,
                    "met": outcome.met,
                    "weight_lost": outcome.weight_lost,
                    "caveat": outcome.rule.caveat,
                    "evidence": [
                        {"key": e.key, "source": e.source, "finding_id": e.finding_id}
                        for e in outcome.evidence
                    ],
                    "unconfirmed": [
                        {"key": e.key, "confidence": e.confidence, "finding_id": e.finding_id}
                        for e in outcome.unconfirmed
                    ],
                }
                for outcome in self.outcomes
            ],
        }


def _score_from_weights(met_weight: float, applicable_weight: float) -> int:
    """Round half up, so a property one point short of 70 is never displayed as 70."""
    if applicable_weight <= 0:
        # No rule applies. That is a complete answer, not a failure, so it scores full marks —
        # and the client shows the empty rule list rather than a bare 100.
        return 100
    ratio = Decimal(str(met_weight)) / Decimal(str(applicable_weight))
    return int((ratio * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def evaluate(
    rulebook: Rulebook,
    *,
    fhsz: str,
    evidence: list[Evidence],
    state: str | None = None,
) -> Assessment:
    """Evaluate a property against a rulebook.

    `state` decides which statutory rules are in force. Outside a state we hold law for, the
    nationally-recognised advisory rules still apply, so a homeowner anywhere gets a real score and
    a real plan — just without the citations that only exist in one state's code.
    """
    by_key: dict[str, list[Evidence]] = {}
    for item in evidence:
        by_key.setdefault(item.key, []).append(item)

    outcomes: list[RuleOutcome] = []
    applicable_weight = 0.0
    met_weight = 0.0

    for rule in rulebook.applicable(fhsz, state):
        triggering: list[Evidence] = []
        unconfirmed: list[Evidence] = []
        resolved: list[Evidence] = []

        for key in [*rule.triggers.hazards, *rule.triggers.checklist]:
            for item in by_key.get(key, []):
                if item.counts(rulebook.confidence_threshold):
                    triggering.append(item)
                elif item.resolved:
                    resolved.append(item)
                elif not item.dismissed:
                    unconfirmed.append(item)

        met = not triggering
        applicable_weight += rule.weight
        if met:
            met_weight += rule.weight

        outcomes.append(
            RuleOutcome(
                rule=rule,
                met=met,
                evidence=tuple(triggering),
                unconfirmed=tuple(unconfirmed),
                resolved_evidence=tuple(resolved),
            )
        )

    return Assessment(
        score=_score_from_weights(met_weight, applicable_weight),
        rulebook_version=rulebook.version,
        outcomes=tuple(outcomes),
        disclaimer=rulebook.disclaimer,
        applicable_weight=applicable_weight,
        met_weight=met_weight,
    )


def score_if_resolved(assessment: Assessment, rule_ids: set[str]) -> int:
    """What the score becomes once these rules are met.

    Powers "clearing this raises your score to 71" on the action plan. Same arithmetic as `evaluate`
    rather than an approximation, so the preview cannot disagree with the score the user gets after
    doing the work.
    """
    met_weight = assessment.met_weight + sum(
        outcome.rule.weight
        for outcome in assessment.outcomes
        if not outcome.met and outcome.rule.id in rule_ids
    )
    return _score_from_weights(met_weight, assessment.applicable_weight)


@dataclass
class PlanItem:
    """One ranked thing to do, carrying the reason it is being asked for."""

    rank: int
    kind: str  # 'fire' | 'water'
    rule_id: str
    title: str
    detail: str
    citation: str
    zone: str
    severity: Severity
    status: RuleStatus
    caveat: str
    effort_hours: float | None
    cost_est_usd: float | None
    program_key: str | None
    finding_ids: list[str] = field(default_factory=list)
    # What the score becomes if only this item is completed.
    score_if_done: int = 0
    # True for work already finished: the rule is met because its evidence was resolved.
    done: bool = False


def build_plan(assessment: Assessment) -> list[PlanItem]:
    """Turn unmet rules into a ranked list of actions, keeping finished work on the list.

    Ordering is by weight, and binding law outranks a draft regulation of equal weight: what someone
    is required to do today should sit above what they may be required to do later. Rules met by
    *resolving* their evidence — the user did the work — stay on the plan marked done, so a
    re-assessment reads as progress rather than amnesia.
    """
    ranked = sorted(
        assessment.failures,
        key=lambda outcome: (
            not outcome.rule.is_binding,
            -outcome.rule.weight,
            outcome.rule.id,
        ),
    )
    completed = sorted(
        (o for o in assessment.outcomes if o.met and o.resolved_evidence),
        key=lambda outcome: (-outcome.rule.weight, outcome.rule.id),
    )

    def item(index: int, outcome: RuleOutcome, *, done: bool) -> PlanItem:
        return PlanItem(
            rank=index,
            kind="fire",
            rule_id=outcome.rule.id,
            title=outcome.rule.action.title,
            detail=outcome.rule.action.detail or outcome.rule.rationale,
            citation=outcome.rule.citation,
            zone=outcome.rule.zone.value,
            severity=outcome.rule.severity,
            status=outcome.rule.status,
            caveat=outcome.rule.caveat,
            effort_hours=outcome.rule.action.effort_hours,
            cost_est_usd=outcome.rule.action.cost_est_usd,
            program_key=outcome.rule.action.program_key,
            finding_ids=[
                e.finding_id
                for e in (outcome.evidence if not done else outcome.resolved_evidence)
                if e.finding_id
            ],
            # A finished item's score is already in the number; promising more would be a lie.
            score_if_done=(
                assessment.score if done else score_if_resolved(assessment, {outcome.rule.id})
            ),
            done=done,
        )

    plan = [item(index, outcome, done=False) for index, outcome in enumerate(ranked, start=1)]
    plan.extend(
        item(index, outcome, done=True)
        for index, outcome in enumerate(completed, start=len(plan) + 1)
    )
    return plan
