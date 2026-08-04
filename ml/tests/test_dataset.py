"""Dataset assembly tests.

The leakage tests are the reason this file exists. If two photos of one house end up on opposite
sides of the train/test line, the model gets tested on a property it has already memorised, and the
mAP we publish in the submission is a number it cannot reproduce on a judge's yard. That is not a
performance bug; it is a false claim.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml.dataset import (
    Dataset,
    Image,
    class_names,
    leaked_properties,
    load_taxonomy,
    split_by_property,
    summarise,
    write_yolo_dataset,
)

CLASSES = load_taxonomy()


def image(path: str, property_id: str, *boxes) -> Image:
    return Image(path=path, property_id=property_id, boxes=tuple(boxes))


def many_properties(count: int, per_property: int = 3) -> Dataset:
    return Dataset(
        images=[
            image(f"p{p}_{i}.jpg", f"property-{p}", (0, 0.5, 0.5, 0.2, 0.2))
            for p in range(count)
            for i in range(per_property)
        ]
    )


# --------------------------------------------------------------------------- leakage


def test_no_property_appears_in_two_splits() -> None:
    splits = split_by_property(many_properties(120))

    assert leaked_properties(splits) == set()


def test_every_photo_of_one_property_lands_together() -> None:
    """The specific failure this guards: front and side shots of one house split apart."""
    dataset = Dataset(
        images=[
            image("front.jpg", "the-house"),
            image("side.jpg", "the-house"),
            image("rear.jpg", "the-house"),
        ]
    )

    splits = split_by_property(dataset)
    holding = [name for name, images in splits.items() if images]

    assert len(holding) == 1
    assert len(splits[holding[0]]) == 3


def test_leak_detection_actually_catches_a_leak() -> None:
    """Guard the guard: a leakage checker that never fires proves nothing."""
    leaked = leaked_properties(
        {
            "train": [image("a.jpg", "shared")],
            "val": [],
            "test": [image("b.jpg", "shared")],
        }
    )

    assert leaked == {"shared"}


# --------------------------------------------------------------------------- determinism


def test_splitting_is_deterministic() -> None:
    """A rerun must not reshuffle the test set, or last week's mAP stops being comparable."""
    dataset = many_properties(60)

    first = split_by_property(dataset)
    second = split_by_property(dataset)

    assert {k: [i.path for i in v] for k, v in first.items()} == {
        k: [i.path for i in v] for k, v in second.items()
    }


def test_adding_photos_does_not_move_existing_properties() -> None:
    """Collection continues for weeks; a new batch must not silently reassign old houses."""
    before = split_by_property(many_properties(40))
    placement_before = {
        img.property_id: name for name, images in before.items() for img in images
    }

    after = split_by_property(many_properties(80))
    placement_after = {img.property_id: name for name, images in after.items() for img in images}

    for property_id, split_name in placement_before.items():
        assert placement_after[property_id] == split_name


def test_the_ratios_are_roughly_honoured() -> None:
    splits = split_by_property(many_properties(400, per_property=1))
    total = sum(len(images) for images in splits.values())

    assert total == 400
    assert 0.60 < len(splits["train"]) / total < 0.80
    assert len(splits["test"]) > 20


def test_ratios_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        split_by_property(many_properties(10), ratios=(0.5, 0.3, 0.3))


# --------------------------------------------------------------------------- validation


def test_a_box_outside_the_image_is_rejected() -> None:
    """Boxes written in corner format instead of centre format poison training silently."""
    dataset = Dataset(images=[image("a.jpg", "p", (0, 0.9, 0.5, 0.4, 0.2))])

    with pytest.raises(ValueError, match="beyond the image"):
        dataset.validate(len(CLASSES))


def test_an_unknown_class_index_is_rejected() -> None:
    dataset = Dataset(images=[image("a.jpg", "p", (99, 0.5, 0.5, 0.2, 0.2))])

    with pytest.raises(ValueError, match="unknown class"):
        dataset.validate(len(CLASSES))


def test_a_zero_sized_box_is_rejected() -> None:
    dataset = Dataset(images=[image("a.jpg", "p", (0, 0.5, 0.5, 0.0, 0.2))])

    with pytest.raises(ValueError, match="box size"):
        dataset.validate(len(CLASSES))


def test_an_empty_manifest_is_rejected() -> None:
    with pytest.raises(ValueError, match="no images"):
        Dataset().validate(len(CLASSES))


def test_a_valid_dataset_passes() -> None:
    Dataset(images=[image("a.jpg", "p", (0, 0.5, 0.5, 0.3, 0.3))]).validate(len(CLASSES))


# --------------------------------------------------------------------------- taxonomy


def test_taxonomy_indices_are_contiguous() -> None:
    assert [c["index"] for c in CLASSES] == list(range(len(CLASSES)))


def test_every_class_defines_what_to_include_and_exclude() -> None:
    """Ambiguity between two labellers is the cheapest way to ruin a small dataset."""
    for entry in CLASSES:
        assert entry["definition"], entry["name"]
        assert entry["include"], entry["name"]
        assert entry["exclude"], entry["name"]
        assert entry["source"], entry["name"]


def test_the_taxonomy_matches_the_rulebook_and_the_database() -> None:
    """One list of classes, three consumers. Drift here means a detection nothing acts on."""
    api = Path(__file__).resolve().parents[2] / "services" / "api"
    rulebook = json.loads((api / "rulebooks" / "2026.08.json").read_text())
    migration = (api / "migrations" / "002_core_schema.sql").read_text()

    names = set(class_names())
    triggered = {h for rule in rulebook["rules"] for h in rule["triggers"].get("hazards", [])}

    assert triggered == names, "rulebook triggers and taxonomy disagree"
    for name in names:
        assert f"'{name}'" in migration, f"{name} missing from the hazard_class enum"


# --------------------------------------------------------------------------- output


def test_the_yolo_layout_is_written(tmp_path: Path) -> None:
    splits = split_by_property(many_properties(30))

    data_yaml = write_yolo_dataset(splits, tmp_path, CLASSES, copy_images=False)

    text = data_yaml.read_text()
    assert f"nc: {len(CLASSES)}" in text
    assert "0: dead_vegetation" in text
    for split_name in ("train", "val", "test"):
        assert (tmp_path / "labels" / split_name).is_dir()


def test_a_background_image_gets_an_empty_label_file(tmp_path: Path) -> None:
    """Clean yards are training signal: the model has to learn what "no hazard" looks like."""
    splits = {"train": [image("clean.jpg", "p")], "val": [], "test": []}

    write_yolo_dataset(splits, tmp_path, CLASSES, copy_images=False)

    assert (tmp_path / "labels" / "train" / "clean.txt").read_text() == ""


def test_the_summary_reports_per_class_counts(tmp_path: Path) -> None:
    """Published with the dataset card, so a rare class cannot hide behind a headline number."""
    splits = split_by_property(many_properties(30))

    summary = summarise(splits, CLASSES)

    assert summary["leaked_properties"] == []
    assert set(summary["splits"]) == {"train", "val", "test"}
    assert "dead_vegetation" in summary["splits"]["train"]["by_class"]
