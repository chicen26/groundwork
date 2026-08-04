"""Fine-tune YOLO11-small on the Groundwork hazard dataset.

    python -m ml.train --data ml/data/prepared/data.yaml --epochs 100

Runs on a Colab or Kaggle GPU; inference then runs on CPU, which nano/small are fast enough for.
Ultralytics is imported inside the function so the rest of `ml/` — dataset assembly, the taxonomy,
the tests that guard against leakage — stays importable without torch installed.

Every run writes a `run_config.json` beside its weights. When a number from this model ends up in
the written submission, we need to be able to say exactly which data and settings produced it.
"""

from __future__ import annotations

import argparse
import json
import platform
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_MODEL = "yolo11s.pt"


@dataclass(frozen=True)
class TrainConfig:
    data: str
    model: str = DEFAULT_MODEL
    epochs: int = 100
    imgsz: int = 640
    batch: int = 16
    # Fixed so a rerun reproduces the run rather than merely resembling it.
    seed: int = 1337
    patience: int = 20
    project: str = "ml/runs"
    name: str = "hazards"
    # Yard photos are taken at varied times of day in a corridor of similar-looking houses, so
    # colour and geometry augmentation is doing real work against a homogeneous dataset.
    hsv_h: float = 0.015
    hsv_s: float = 0.6
    hsv_v: float = 0.4
    degrees: float = 5.0
    translate: float = 0.1
    scale: float = 0.4
    # Horizontal flips are safe here: a hazard is a hazard mirrored. Vertical flips are not — the
    # ground is always down, and "under a deck" depends on it.
    fliplr: float = 0.5
    flipud: float = 0.0
    mosaic: float = 1.0


def train(config: TrainConfig) -> Path:
    from ultralytics import YOLO  # imported here so ml/ stays usable without torch

    model = YOLO(config.model)
    results = model.train(
        data=config.data,
        epochs=config.epochs,
        imgsz=config.imgsz,
        batch=config.batch,
        seed=config.seed,
        patience=config.patience,
        project=config.project,
        name=config.name,
        hsv_h=config.hsv_h,
        hsv_s=config.hsv_s,
        hsv_v=config.hsv_v,
        degrees=config.degrees,
        translate=config.translate,
        scale=config.scale,
        fliplr=config.fliplr,
        flipud=config.flipud,
        mosaic=config.mosaic,
    )

    run_dir = Path(results.save_dir)
    (run_dir / "run_config.json").write_text(
        json.dumps(
            {
                "config": asdict(config),
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            indent=2,
        )
        + "\n"
    )
    return run_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="path to data.yaml from ml/dataset.py")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--name", default="hazards")
    args = parser.parse_args()

    run_dir = train(
        TrainConfig(
            data=args.data,
            model=args.model,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            seed=args.seed,
            name=args.name,
        )
    )
    print(f"weights and run_config.json in {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
