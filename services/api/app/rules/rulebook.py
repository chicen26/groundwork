"""Rulebooks: the law, as data.

A rulebook is a versioned JSON document describing what a property is required or advised to do,
where each requirement comes from, and how heavily it counts. Nothing here is code, which is the
point (decision D3): Zone 0 is still a draft regulation, and its adoption should be a content
update rather than a refactor.

Two invariants the loader enforces, because both are ways we could mislead someone about the law:

* Every rule cites something. A finding without a citation is an assertion the user cannot check.
* A rule that is not yet in force is explicitly marked `pending_adoption` and carries the caveat
  text shown next to it in the app.
"""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

RULEBOOK_DIR = Path(__file__).resolve().parents[2] / "rulebooks"


class Severity(StrEnum):
    """How much a failure matters. Weights come from the rulebook, not from this ordering."""

    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


class RuleStatus(StrEnum):
    IN_EFFECT = "in_effect"
    # Drafted and published but not yet adopted — shown to the user, never stated as an obligation.
    PENDING_ADOPTION = "pending_adoption"
    # Not law at all: a recognised standard we recommend (IBHS, fire safe council guidance).
    ADVISORY = "advisory"


class Zone(StrEnum):
    """Defensible-space zones, named as the public materials name them."""

    ZONE_0 = "0-5ft"
    ZONE_1 = "5-30ft"
    ZONE_2 = "30-100ft"
    STRUCTURE = "structure"


class Applicability(BaseModel):
    """When a rule applies to a property at all."""

    # Empty means "every property", which is right for advisory items but wrong for statutory ones:
    # PRC 4291 applies in hazard zones, not to a flat lot in a non-wildland area.
    fhsz_in: list[str] = Field(default_factory=list)
    # Two-letter state codes this rule is law in. Empty means it is not tied to a jurisdiction —
    # true of recognised standards like IBHS, which are good practice in any state.
    states: list[str] = Field(default_factory=list)

    def applies_to(self, fhsz: str, state: str | None = None) -> bool:
        if self.fhsz_in and fhsz not in self.fhsz_in:
            return False
        return not (self.states and (state or "").upper() not in self.states)


class Triggers(BaseModel):
    """What evidence puts a rule into a failing state."""

    # Detector classes whose presence indicates this rule is not met.
    hazards: list[str] = Field(default_factory=list)
    # Checklist question ids answered in the affirmative-for-hazard direction.
    checklist: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def must_be_triggerable(self) -> Triggers:
        if not self.hazards and not self.checklist:
            raise ValueError("a rule needs at least one trigger, or it can never be evaluated")
        return self


class Action(BaseModel):
    """What the homeowner would actually do about it."""

    title: str
    detail: str = ""
    effort_hours: float | None = Field(default=None, ge=0)
    cost_est_usd: float | None = Field(default=None, ge=0)
    # Links this action to a rebate, chipping, or cost-share program by its key.
    program_key: str | None = None


class Rule(BaseModel):
    id: str = Field(min_length=3)
    title: str
    # Why this is being asked of the user, in their words rather than the statute's.
    rationale: str
    citation: str = Field(min_length=3)
    authority: str
    status: RuleStatus
    zone: Zone
    severity: Severity
    # Relative contribution to the score. Higher means a failure costs more.
    weight: float = Field(gt=0)
    applicability: Applicability = Field(default_factory=Applicability)
    triggers: Triggers
    action: Action
    # Shown verbatim beside any finding from a rule that is not yet law.
    caveat: str = ""
    # Rules this one replaces where both would apply. A state requirement supersedes the national
    # advisory version of the same hazard, so a Californian is not marked down twice for one bush.
    supersedes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def pending_rules_must_carry_their_caveat(self) -> Rule:
        """A draft regulation stated without qualification would misinform someone about the law."""
        if self.status == RuleStatus.PENDING_ADOPTION and not self.caveat:
            raise ValueError(f"rule {self.id} is pending adoption but has no caveat text")
        return self

    @property
    def is_binding(self) -> bool:
        return self.status == RuleStatus.IN_EFFECT


class Rulebook(BaseModel):
    version: str
    description: str = ""
    # Model detections below this confidence are surfaced as "possible — confirm" and do not move
    # the score until the user confirms them. The model proposes; the user disposes (decision D4).
    confidence_threshold: float = Field(default=0.5, ge=0, le=1)
    disclaimer: str
    rules: list[Rule]

    @model_validator(mode="after")
    def superseded_rules_exist(self) -> Rulebook:
        """A rule cannot replace one that is not here — that would silently drop coverage."""
        known = {rule.id for rule in self.rules}
        for rule in self.rules:
            missing = [rule_id for rule_id in rule.supersedes if rule_id not in known]
            if missing:
                raise ValueError(f"rule {rule.id} supersedes unknown rules: {missing}")
        return self

    @model_validator(mode="after")
    def rule_ids_are_unique(self) -> Rulebook:
        seen = [rule.id for rule in self.rules]
        duplicates = {rule_id for rule_id in seen if seen.count(rule_id) > 1}
        if duplicates:
            raise ValueError(f"duplicate rule ids: {sorted(duplicates)}")
        return self

    def applicable(self, fhsz: str, state: str | None = None) -> list[Rule]:
        """Rules in force for this property, with superseded duplicates removed.

        Order matters to the caller only for readability; the engine sorts its own output. What
        matters here is that a hazard covered by both a national advisory rule and a stricter state
        requirement is counted once, under the stricter one.
        """
        in_force = [rule for rule in self.rules if rule.applicability.applies_to(fhsz, state)]
        replaced = {rule_id for rule in in_force for rule_id in rule.supersedes}
        return [rule for rule in in_force if rule.id not in replaced]

    def by_id(self, rule_id: str) -> Rule | None:
        return next((rule for rule in self.rules if rule.id == rule_id), None)


def available_versions(directory: Path = RULEBOOK_DIR) -> list[str]:
    return sorted(path.stem for path in directory.glob("*.json"))


@lru_cache
def load_rulebook(version: str, directory: Path = RULEBOOK_DIR) -> Rulebook:
    """Load and validate one rulebook. Cached: rulebooks are immutable once published."""
    path = directory / f"{version}.json"
    if not path.is_file():
        known = ", ".join(available_versions(directory)) or "none"
        raise FileNotFoundError(f"no rulebook {version!r}; available: {known}")
    return Rulebook.model_validate(json.loads(path.read_text()))
