"""Dataset assembly for the hazard detector.

The one rule this module exists to enforce: **splits are by property, never by image**. Two photos
of the same yard land in the same split or the dataset is lying to us. A model that has seen a house
from the front and is then tested on the same house from the side will report a mAP it cannot
reproduce on a judge's property, and that number would end up in our written submission.

Also here: the manifest format, deterministic assignment so a rerun does not reshuffle the test set,
and the data.yaml Ultralytics expects.

    python -m ml.dataset --manifest ml/data/manifest.json --out ml/data/prepared
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

TAXONOMY_PATH = Path(__file__).resolve().parent / "taxonomy.json"

# 70/15/15, as planned before any labelling began.
DEFAULT_SPLIT = (0.70, 0.15, 0.15)
SPLITS = ("train", "val", "test")


def load_taxonomy(path: Path = TAXONOMY_PATH) -> list[dict]:
    data = json.loads(path.read_text())
    classes = sorted(data["classes"], key=lambda c: c["index"])
    if [c["index"] for c in classes] != list(range(len(classes))):
        raise ValueError("taxonomy class indices must be contiguous and start at zero")
    return classes


def class_names(path: Path = TAXONOMY_PATH) -> list[str]:
    return [c["name"] for c in load_taxonomy(path)]


@dataclass(frozen=True)
class Image:
    """One labelled photograph."""

    path: str
    # The property it was taken at. This is the unit of splitting, and the reason the manifest
    # requires it: without it we cannot prevent leakage, only hope for its absence.
    property_id: str
    # YOLO-format boxes: (class_index, x_centre, y_centre, width, height), all normalised.
    boxes: tuple[tuple[int, float, float, float, float], ...] = ()

    def validate(self, class_count: int) -> None:
        for index, (cls, x, y, w, h) in enumerate(self.boxes):
            where = f"{self.path} box {index}"
            if not 0 <= cls < class_count:
                raise ValueError(f"{where}: unknown class index {cls}")
            if not (0 < w <= 1 and 0 < h <= 1):
                raise ValueError(f"{where}: box size out of range")
            if not (0 <= x <= 1 and 0 <= y <= 1):
                raise ValueError(f"{where}: box centre outside the image")
            # A centre plus half a width landing outside the frame means the box was written in
            # corner format by mistake — a silent, model-poisoning error worth catching early.
            if x - w / 2 < -1e-6 or x + w / 2 > 1 + 1e-6:
                raise ValueError(f"{where}: box extends beyond the image horizontally")
            if y - h / 2 < -1e-6 or y + h / 2 > 1 + 1e-6:
                raise ValueError(f"{where}: box extends beyond the image vertically")


@dataclass
class Dataset:
    images: list[Image] = field(default_factory=list)

    @classmethod
    def from_manifest(cls, path: Path) -> Dataset:
        payload = json.loads(Path(path).read_text())
        return cls(
            images=[
                Image(
                    path=entry["path"],
                    property_id=str(entry["property_id"]),
                    boxes=tuple(tuple(box) for box in entry.get("boxes", [])),
                )
                for entry in payload["images"]
            ]
        )

    @property
    def properties(self) -> list[str]:
        return sorted({image.property_id for image in self.images})

    def validate(self, class_count: int) -> None:
        if not self.images:
            raise ValueError("manifest contains no images")
        for image in self.images:
            image.validate(class_count)

    def class_counts(self) -> Counter:
        return Counter(box[0] for image in self.images for box in image.boxes)


def _bucket(property_id: str, salt: str) -> float:
    """Deterministically map a property onto [0, 1).

    Hashing rather than shuffling means a rerun, or a run on another machine, produces the same test
    set. Adding photos later moves nobody between splits, so a mAP from last week stays comparable.
    """
    digest = hashlib.sha256(f"{salt}:{property_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def split_by_property(
    dataset: Dataset,
    ratios: tuple[float, float, float] = DEFAULT_SPLIT,
    salt: str = "groundwork-v1",
) -> dict[str, list[Image]]:
    """Partition images into train/val/test, keeping every property whole."""
    if abs(sum(ratios) - 1.0) > 1e-9:
        raise ValueError("split ratios must sum to 1")

    train_ratio, val_ratio, _ = ratios
    assignment: dict[str, str] = {}
    for property_id in dataset.properties:
        position = _bucket(property_id, salt)
        if position < train_ratio:
            assignment[property_id] = "train"
        elif position < train_ratio + val_ratio:
            assignment[property_id] = "val"
        else:
            assignment[property_id] = "test"

    result: dict[str, list[Image]] = {name: [] for name in SPLITS}
    for image in dataset.images:
        result[assignment[image.property_id]].append(image)
    return result


def leaked_properties(splits: dict[str, list[Image]]) -> set[str]:
    """Properties appearing in more than one split. Must always be empty."""
    seen: dict[str, str] = {}
    leaked: set[str] = set()
    for split_name, images in splits.items():
        for image in images:
            previous = seen.setdefault(image.property_id, split_name)
            if previous != split_name:
                leaked.add(image.property_id)
    return leaked


def summarise(splits: dict[str, list[Image]], classes: list[dict]) -> dict:
    """Per-split image, property, and per-class box counts — published with the dataset card."""
    names = {c["index"]: c["name"] for c in classes}
    summary: dict = {"splits": {}, "leaked_properties": sorted(leaked_properties(splits))}
    for split_name, images in splits.items():
        counts = Counter(box[0] for image in images for box in image.boxes)
        summary["splits"][split_name] = {
            "images": len(images),
            "properties": len({image.property_id for image in images}),
            "boxes": sum(counts.values()),
            "by_class": {names[i]: counts.get(i, 0) for i in sorted(names)},
        }
    return summary


def write_yolo_dataset(
    splits: dict[str, list[Image]],
    out_dir: Path,
    classes: list[dict],
    *,
    source_root: Path | None = None,
    copy_images: bool = True,
) -> Path:
    """Lay out images and labels the way Ultralytics expects, and write data.yaml."""
    out_dir = Path(out_dir)
    for split_name in SPLITS:
        (out_dir / "images" / split_name).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / split_name).mkdir(parents=True, exist_ok=True)

    for split_name, images in splits.items():
        for image in images:
            source = Path(source_root or ".") / image.path
            target = out_dir / "images" / split_name / Path(image.path).name
            if copy_images and source.is_file():
                shutil.copy2(source, target)

            label_lines = [
                f"{cls} {x:.6f} {y:.6f} {w:.6f} {h:.6f}" for cls, x, y, w, h in image.boxes
            ]
            label_path = out_dir / "labels" / split_name / f"{Path(image.path).stem}.txt"
            # An empty label file is meaningful: it declares a background image with no hazards,
            # which the model needs in order to learn what a clean yard looks like.
            label_path.write_text("\n".join(label_lines) + ("\n" if label_lines else ""))

    data_yaml = out_dir / "data.yaml"
    names_block = "\n".join(f"  {c['index']}: {c['name']}" for c in classes)
    data_yaml.write_text(
        "# Generated by ml/dataset.py — do not edit by hand.\n"
        f"path: {out_dir.resolve()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        f"nc: {len(classes)}\n"
        "names:\n"
        f"{names_block}\n"
    )
    return data_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--salt", default="groundwork-v1")
    parser.add_argument("--no-copy", action="store_true", help="write labels only")
    args = parser.parse_args()

    classes = load_taxonomy()
    dataset = Dataset.from_manifest(args.manifest)
    dataset.validate(len(classes))

    splits = split_by_property(dataset, salt=args.salt)
    leaked = leaked_properties(splits)
    if leaked:
        # Unreachable by construction, checked anyway: this is the assumption the published metrics
        # rest on, and an assertion is cheaper than a retracted number.
        raise SystemExit(f"property leakage across splits: {sorted(leaked)}")

    data_yaml = write_yolo_dataset(
        splits, args.out, classes, source_root=args.source_root, copy_images=not args.no_copy
    )
    summary = summarise(splits, classes)
    (Path(args.out) / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(json.dumps(summary, indent=2))
    print(f"\nwrote {data_yaml}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
