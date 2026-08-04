"""The checklist and the rulebook must agree.

Two failure modes, both silent, both caught here:

* A question with no rule behind it wastes a homeowner's time in the guided walk.
* A rule whose only trigger is a checklist id nothing asks about can never fire, so the property is
  scored as meeting a requirement nobody checked.
"""

from __future__ import annotations

import pytest

from app.rules.checklist import CHECKLIST, QUESTIONS_BY_ID
from app.rules.rulebook import load_rulebook


@pytest.fixture(scope="module")
def rulebook():
    return load_rulebook("2026.08")


def test_every_question_drives_at_least_one_rule(rulebook) -> None:
    triggers = {key for rule in rulebook.rules for key in rule.triggers.checklist}
    orphans = set(QUESTIONS_BY_ID) - triggers

    assert not orphans, f"questions asked but never used: {sorted(orphans)}"


def test_every_checklist_trigger_has_a_question(rulebook) -> None:
    triggers = {key for rule in rulebook.rules for key in rule.triggers.checklist}
    missing = triggers - set(QUESTIONS_BY_ID)

    assert not missing, f"rules waiting on questions nobody asks: {sorted(missing)}"


def test_question_ids_are_unique() -> None:
    ids = [question.id for question in CHECKLIST]

    assert len(ids) == len(set(ids))


def test_questions_are_phrased_so_yes_means_hazard_present() -> None:
    """The answer the user gives and the value the engine scores are the same, with no polarity."""
    for question in CHECKLIST:
        assert question.prompt.strip().endswith("?"), question.id
        assert question.help_text, question.id


def test_every_question_belongs_to_a_photo_station() -> None:
    from app.routers.scans import STATIONS

    for question in CHECKLIST:
        assert question.station in STATIONS, question.id
