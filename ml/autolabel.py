"""Pre-draw boxes so a human is correcting rather than starting from nothing.

    pip install -e "ml[autolabel]"
    python -m ml.autolabel --images ml/data/harvested/images --out ml/data/candidates.json

An open-vocabulary detector (OWLv2) is asked, in plain English, where "a dead brown shrub" or
"firewood stacked under a deck" is in each image. What comes back is a *proposal*: every box is
written with `reviewed: false`, and `ml/dataset.py` refuses to build a training set from unreviewed
boxes. Nothing here becomes a label until a person says so.

That is not ceremony. Two reasons it matters:

* **Accuracy.** OWLv2 has never seen our taxonomy. It does not know that bark mulch six feet from a
  wall is not a Zone 0 hazard, or that a fence must actually *meet* the house. A human is the only
  thing that knows the difference, and those distinctions are the product.
* **Honesty.** The Congressional App Challenge requires that AI not constitute the entirety of the
  technical work. Our labels being machine-suggested and human-decided is a fact we can state
  plainly — and the review counts are published with the dataset so nobody has to take our word.

Realistically this turns forty hours of drawing boxes into a few hours of judgement calls.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ml.dataset import class_names

# What to ask the detector, per class. Written as a description a person would recognise, because
# that is what an open-vocabulary model responds to.
PROMPTS: dict[str, list[str]] = {
    "dead_vegetation": [
        "a dead brown shrub",
        "dry dead grass",
        "a pile of dead leaves on the ground",
        "dead branches on a bush",
    ],
    "veg_touching_structure": [
        "a bush touching the wall of a house",
        "a vine growing up a house wall",
        "a hedge pressed against siding",
    ],
    "overhanging_limbs": [
        "a tree branch hanging over a roof",
        "tree limbs above a chimney",
    ],
    "combustible_mulch_z0": [
        "bark mulch next to a house foundation",
        "wood chips in a flower bed beside a wall",
    ],
    "attached_wood_fence": [
        "a wooden fence joined to a house wall",
        "a wooden gate attached to a building",
    ],
    "combustibles_under_deck": [
        "firewood stacked under a deck",
        "boxes and clutter stored under a porch",
    ],
}

# Deliberately low. Recall matters more than precision here: a spurious box costs one click to
# reject, whereas a missed hazard costs a human spotting it unaided, which is what we are avoiding.
DEFAULT_THRESHOLD = 0.12


@dataclass
class CandidateBox:
    """A proposed box. Not a label until `reviewed` is true and a person set `accepted`."""

    class_name: str
    # Normalised centre-format, matching what ml/dataset.py expects.
    x: float
    y: float
    w: float
    h: float
    confidence: float
    prompt: str
    reviewed: bool = False
    accepted: bool = False


@dataclass
class CandidateImage:
    path: str
    # Each source image is its own property, so near-duplicates cannot straddle a split.
    property_id: str
    boxes: list[CandidateBox]
    source: str = "harvested"


def _load_model(model_name: str):
    """Import inside the function so `ml/` stays usable without torch installed."""
    from transformers import Owlv2ForObjectDetection, Owlv2Processor

    processor = Owlv2Processor.from_pretrained(model_name)
    model = Owlv2ForObjectDetection.from_pretrained(model_name)
    model.eval()
    return processor, model


def propose(
    image_dir: Path,
    *,
    model_name: str = "google/owlv2-base-patch16-ensemble",
    threshold: float = DEFAULT_THRESHOLD,
    limit: int | None = None,
) -> list[CandidateImage]:
    import torch
    from PIL import Image

    processor, model = _load_model(model_name)

    prompts: list[str] = []
    prompt_to_class: dict[str, str] = {}
    for class_name in class_names():
        for prompt in PROMPTS.get(class_name, []):
            prompts.append(prompt)
            prompt_to_class[prompt] = class_name

    paths = sorted(p for p in Path(image_dir).iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if limit:
        paths = paths[:limit]

    candidates: list[CandidateImage] = []
    for index, path in enumerate(paths, start=1):
        try:
            with Image.open(path) as raw:
                image = raw.convert("RGB")
                width, height = image.size

                inputs = processor(text=[prompts], images=image, return_tensors="pt")
                with torch.no_grad():
                    outputs = model(**inputs)

                results = processor.post_process_grounded_object_detection(
                    outputs=outputs,
                    target_sizes=torch.tensor([[height, width]]),
                    threshold=threshold,
                )[0]
        except Exception as exc:  # noqa: BLE001 - one unreadable image must not end the run
            print(f"  skipped {path.name}: {exc}")
            continue

        boxes: list[CandidateBox] = []
        for score, label, box in zip(
            results["scores"], results["labels"], results["boxes"], strict=False
        ):
            prompt = prompts[int(label)]
            x1, y1, x2, y2 = (float(v) for v in box)
            x1, y1 = max(0.0, x1), max(0.0, y1)
            x2, y2 = min(float(width), x2), min(float(height), y2)
            if x2 <= x1 or y2 <= y1:
                continue

            boxes.append(
                CandidateBox(
                    class_name=prompt_to_class[prompt],
                    x=round(((x1 + x2) / 2) / width, 6),
                    y=round(((y1 + y2) / 2) / height, 6),
                    w=round((x2 - x1) / width, 6),
                    h=round((y2 - y1) / height, 6),
                    confidence=round(float(score), 4),
                    prompt=prompt,
                )
            )

        candidates.append(
            CandidateImage(path=str(path), property_id=f"harvested-{path.stem}", boxes=boxes)
        )
        if index % 25 == 0:
            print(f"  {index}/{len(paths)} images proposed")

    return candidates


def review_summary(candidates: list[CandidateImage]) -> dict:
    """Counts published with the dataset, so the machine/human split is on the record."""
    total = sum(len(c.boxes) for c in candidates)
    reviewed = sum(1 for c in candidates for b in c.boxes if b.reviewed)
    accepted = sum(1 for c in candidates for b in c.boxes if b.reviewed and b.accepted)
    return {
        "images": len(candidates),
        "proposed_boxes": total,
        "reviewed_boxes": reviewed,
        "accepted_boxes": accepted,
        "rejected_boxes": reviewed - accepted,
        "unreviewed_boxes": total - reviewed,
        "ready_to_train": total > 0 and reviewed == total,
    }


def to_manifest(candidates: list[CandidateImage]) -> dict:
    """Convert reviewed candidates into the manifest `ml/dataset.py` consumes.

    Only accepted boxes survive, and an unreviewed box is an error rather than an omission — a
    silently dropped proposal would mean training on a set nobody actually agreed to.
    """
    names = class_names()
    unreviewed = [b for c in candidates for b in c.boxes if not b.reviewed]
    if unreviewed:
        raise ValueError(
            f"{len(unreviewed)} boxes have not been reviewed. Every proposal needs a human "
            "decision before it can become training data."
        )

    return {
        "images": [
            {
                "path": candidate.path,
                "property_id": candidate.property_id,
                "source": candidate.source,
                "boxes": [
                    [names.index(box.class_name), box.x, box.y, box.w, box.h]
                    for box in candidate.boxes
                    if box.accepted
                ],
            }
            for candidate in candidates
        ]
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=Path("ml/data/candidates.json"))
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    candidates = propose(args.images, threshold=args.threshold, limit=args.limit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps([asdict(candidate) for candidate in candidates], indent=2) + "\n"
    )

    summary = review_summary(candidates)
    print(json.dumps(summary, indent=2))
    print(
        f"\n{summary['proposed_boxes']} boxes proposed across {summary['images']} images. "
        "Every one needs a yes or no from you before it counts as a label."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
