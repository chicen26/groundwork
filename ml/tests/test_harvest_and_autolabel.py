"""Harvesting and auto-labelling tests.

Two invariants carry real consequences:

* An image without a recordable licence never lands. The dataset is going to be published, and one
  unattributable image would make that impossible.
* A machine proposal never becomes a label. `to_manifest` refuses while any box is unreviewed, so
  the machine/human split stays a fact rather than a claim.
"""

from __future__ import annotations

import pytest

from ml.autolabel import PROMPTS, CandidateBox, CandidateImage, review_summary, to_manifest
from ml.dataset import class_names
from ml.harvest import ACCEPTABLE_LICENCES, QUERIES, search_commons, search_openverse


# --------------------------------------------------------------------------- licensing


def test_only_republishable_licences_are_acceptable() -> None:
    """ND forbids derivatives, and cropping or augmenting for training is a derivative."""
    assert "by-nd" not in ACCEPTABLE_LICENCES
    assert "by-nc-nd" not in ACCEPTABLE_LICENCES
    assert {"cc0", "by"} <= ACCEPTABLE_LICENCES


def test_openverse_results_without_an_acceptable_licence_are_dropped(monkeypatch) -> None:
    import ml.harvest as harvest

    monkeypatch.setattr(
        harvest,
        "_get",
        lambda url, params: {
            "results": [
                {"id": "ok", "url": "https://x/1.jpg", "license": "cc0", "creator": "A"},
                {"id": "nd", "url": "https://x/2.jpg", "license": "by-nd", "creator": "B"},
                {"id": "none", "url": "https://x/3.jpg", "license": "", "creator": "C"},
            ]
        },
    )

    results = search_openverse("dead shrub", "dead_vegetation", 10)

    assert [meta.licence for _, meta in results] == ["cc0"]


def test_an_openverse_result_without_a_url_is_dropped(monkeypatch) -> None:
    import ml.harvest as harvest

    monkeypatch.setattr(
        harvest, "_get", lambda url, params: {"results": [{"id": "x", "license": "cc0"}]}
    )

    assert search_openverse("q", "dead_vegetation", 10) == []


def test_commons_results_keep_only_unambiguous_grants(monkeypatch) -> None:
    import ml.harvest as harvest

    monkeypatch.setattr(
        harvest,
        "_get",
        lambda url, params: {
            "query": {
                "pages": {
                    "1": {
                        "pageid": 1,
                        "title": "File:Good.jpg",
                        "imageinfo": [
                            {
                                "thumburl": "https://x/good.jpg",
                                "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}},
                            }
                        ],
                    },
                    "2": {
                        "pageid": 2,
                        "title": "File:Fair.jpg",
                        "imageinfo": [
                            {
                                "thumburl": "https://x/fair.jpg",
                                "extmetadata": {"LicenseShortName": {"value": "Fair use"}},
                            }
                        ],
                    },
                }
            }
        },
    )

    results = search_commons("q", "dead_vegetation", 10)

    assert len(results) == 1
    assert "cc by" in results[0][1].licence


def test_every_harvested_image_records_its_attribution(monkeypatch) -> None:
    import ml.harvest as harvest

    monkeypatch.setattr(
        harvest,
        "_get",
        lambda url, params: {
            "results": [
                {
                    "id": "a",
                    "url": "https://x/a.jpg",
                    "license": "by",
                    "license_url": "https://creativecommons.org/licenses/by/4.0/",
                    "creator": "Some Photographer",
                    "foreign_landing_url": "https://source/a",
                    "title": "A dead shrub",
                }
            ]
        },
    )

    _, meta = search_openverse("dead shrub", "dead_vegetation", 1)[0]

    assert meta.creator == "Some Photographer"
    assert meta.licence_url.startswith("https://")
    assert meta.source_url.startswith("https://")


def test_no_query_targets_a_prohibited_source() -> None:
    """Street View's terms forbid this outright, and using it would sink the dataset release."""
    everything = " ".join(q for queries in QUERIES.values() for q in queries).lower()

    assert "street view" not in everything
    assert "google" not in everything


def test_background_images_are_harvested_too() -> None:
    """Without tidy yards the model learns to find hazards in every garden it sees."""
    assert QUERIES["background"]


# --------------------------------------------------------------------------- proposals


def box(class_name: str = "dead_vegetation", **kwargs) -> CandidateBox:
    defaults = {
        "x": 0.5,
        "y": 0.5,
        "w": 0.2,
        "h": 0.2,
        "confidence": 0.4,
        "prompt": "a dead brown shrub",
    }
    return CandidateBox(class_name=class_name, **{**defaults, **kwargs})


def test_a_proposal_starts_unreviewed_and_unaccepted() -> None:
    """The default has to be the safe one: nothing counts until someone says it does."""
    proposed = box()

    assert proposed.reviewed is False
    assert proposed.accepted is False


def test_unreviewed_boxes_block_the_manifest() -> None:
    candidates = [CandidateImage(path="a.jpg", property_id="p1", boxes=[box()])]

    with pytest.raises(ValueError, match="not been reviewed"):
        to_manifest(candidates)


def test_a_reviewed_and_rejected_box_is_left_out() -> None:
    candidates = [
        CandidateImage(
            path="a.jpg",
            property_id="p1",
            boxes=[
                box(reviewed=True, accepted=True),
                box(reviewed=True, accepted=False),
            ],
        )
    ]

    manifest = to_manifest(candidates)

    assert len(manifest["images"][0]["boxes"]) == 1


def test_accepted_boxes_convert_to_taxonomy_indices() -> None:
    candidates = [
        CandidateImage(
            path="a.jpg",
            property_id="p1",
            boxes=[box("overhanging_limbs", reviewed=True, accepted=True)],
        )
    ]

    manifest = to_manifest(candidates)

    assert manifest["images"][0]["boxes"][0][0] == class_names().index("overhanging_limbs")


def test_an_image_reviewed_to_zero_boxes_is_still_a_background_image() -> None:
    """Rejecting every proposal means "nothing here", which is training signal, not a dropped row."""
    candidates = [
        CandidateImage(path="clean.jpg", property_id="p1", boxes=[box(reviewed=True)])
    ]

    manifest = to_manifest(candidates)

    assert manifest["images"][0]["boxes"] == []


def test_each_harvested_image_is_its_own_property() -> None:
    """Web images have no property to group by, so near-duplicates must not share a split key."""
    a = CandidateImage(path="x/a.jpg", property_id="harvested-a", boxes=[])
    b = CandidateImage(path="x/b.jpg", property_id="harvested-b", boxes=[])

    assert a.property_id != b.property_id


def test_the_review_summary_reports_what_is_outstanding() -> None:
    candidates = [
        CandidateImage(
            path="a.jpg",
            property_id="p1",
            boxes=[box(reviewed=True, accepted=True), box(reviewed=True), box()],
        )
    ]

    summary = review_summary(candidates)

    assert summary == {
        "images": 1,
        "proposed_boxes": 3,
        "reviewed_boxes": 2,
        "accepted_boxes": 1,
        "rejected_boxes": 1,
        "unreviewed_boxes": 1,
        "ready_to_train": False,
    }


def test_every_detectable_class_has_a_prompt() -> None:
    """A class with no prompt gets no proposals, so it silently falls back to manual labelling."""
    assert set(PROMPTS) == set(class_names())
