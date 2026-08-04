"""The guided checklist.

The model flags what it can see; the checklist covers what a photograph cannot answer — whether
gutters are full, whether vents are screened, what the far end of the property looks like. Together
they are the input to one rules engine, which is why every question id here must match a trigger in
the rulebook. A question with no rule behind it wastes the user's time, and a rule with no way to be
triggered can never be evaluated. A test asserts both directions.

Questions are phrased so that "yes" always means the hazard is present. That keeps the answer a
homeowner gives and the value the engine scores identical, with no polarity to get backwards.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.rules.rulebook import Zone


@dataclass(frozen=True)
class Question:
    id: str
    prompt: str
    # What the user should look for, in the language of the thing itself rather than the statute.
    help_text: str
    zone: Zone
    # Which photo station this question belongs beside in the guided walk.
    station: str


CHECKLIST: tuple[Question, ...] = (
    Question(
        id="dead_vegetation_present",
        prompt="Is there dead or dried-out vegetation within 30 feet of the house?",
        help_text="Dead shrubs, dried grass, fallen leaves, or dead branches still on the plant.",
        zone=Zone.ZONE_1,
        station="front_elevation",
    ),
    Question(
        id="roof_debris_present",
        prompt="Are there leaves or pine needles sitting on the roof?",
        help_text="Look along the valleys and where the roof meets a wall — debris collects there.",
        zone=Zone.STRUCTURE,
        station="roofline",
    ),
    Question(
        id="gutters_full",
        prompt="Are the gutters holding debris?",
        help_text="Needles and leaves in a gutter hold fire directly against the roof edge.",
        zone=Zone.STRUCTURE,
        station="roofline",
    ),
    Question(
        id="limbs_near_chimney",
        prompt="Are any tree limbs within 10 feet of the chimney or stovepipe?",
        help_text="Measure from the outlet, not from the roof surface.",
        zone=Zone.STRUCTURE,
        station="roofline",
    ),
    Question(
        id="vents_unscreened",
        prompt=(
            "Are any attic or crawlspace vents unscreened, "
            "or screened with mesh wider than 1/8 inch?"
        ),
        help_text="Embers pulled through an open vent start a fire inside the walls, out of sight.",
        zone=Zone.STRUCTURE,
        station="left_side",
    ),
    Question(
        id="vegetation_against_walls",
        prompt="Is anything planted or growing against the exterior walls?",
        help_text="Shrubs, vines, or hedges touching the siding.",
        zone=Zone.ZONE_0,
        station="perimeter_0_5ft",
    ),
    Question(
        id="combustible_mulch_present",
        prompt="Is there bark or wood mulch in the first five feet around the house?",
        help_text="Gravel, stone, and bare soil are fine; shredded bark is what we mean here.",
        zone=Zone.ZONE_0,
        station="perimeter_0_5ft",
    ),
    Question(
        id="wood_fence_attached",
        prompt="Does a wooden fence or gate attach directly to the house?",
        help_text="A fence meeting the wall carries fire straight to the structure.",
        zone=Zone.ZONE_0,
        station="perimeter_0_5ft",
    ),
    Question(
        id="storage_under_deck",
        prompt="Is anything stored under a deck or porch?",
        help_text="Firewood, furniture, bins — anything that would smoulder out of sight.",
        zone=Zone.ZONE_0,
        station="deck_porch",
    ),
    Question(
        id="firewood_near_house",
        prompt="Is firewood or lumber stacked within 30 feet of the house?",
        help_text="Include stacks against a fence or shed that touches the house.",
        zone=Zone.ZONE_1,
        station="rear_elevation",
    ),
    Question(
        id="outer_zone_fuels_dense",
        prompt="Between 30 and 100 feet out, are shrubs and trees growing into each other?",
        help_text="Continuous fuel lets fire climb from the ground into tree canopies.",
        zone=Zone.ZONE_2,
        station="rear_elevation",
    ),
    Question(
        id="grass_over_four_inches",
        prompt="Is any grass on the property taller than four inches?",
        help_text="Annual grasses cure and carry fire quickly once dry.",
        zone=Zone.ZONE_2,
        station="rear_elevation",
    ),
)

QUESTIONS_BY_ID: dict[str, Question] = {question.id: question for question in CHECKLIST}


def questions_for_station(station: str) -> list[Question]:
    return [question for question in CHECKLIST if question.station == station]
