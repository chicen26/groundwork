"""The detector interface, and the two implementations behind it.

Keeping this an interface is what lets the whole scan pipeline be tested — and demoed — without
torch installed. `YoloDetector` loads our fine-tuned weights; `NullDetector` stands in when no
weights are configured, and reports that honestly rather than pretending a clean yard.

Boxes come back normalised to [0, 1] so a finding survives whatever resizing the client does, which
is also the form the database CHECK constraints require.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Detection:
    hazard: str
    confidence: float
    # Normalised top-left corner plus size, matching the findings table.
    x: float
    y: float
    w: float
    h: float


class NoModelConfigured(RuntimeError):
    """No weights are available, so no detection can be attempted."""


class Detector(Protocol):
    @property
    def version(self) -> str: ...

    def detect(self, image_bytes: bytes) -> list[Detection]: ...


class NullDetector:
    """Stands in when no model is configured.

    It raises rather than returning an empty list on purpose. Silence would be indistinguishable
    from "we looked and your yard is fine", and the scan would show a clean result nobody earned.
    The job is marked failed, the client sees inference is unavailable, and the checklist still
    produces a complete plan.
    """

    version = "none"

    def detect(self, image_bytes: bytes) -> list[Detection]:
        raise NoModelConfigured("no detector weights configured")


class YoloDetector:
    """Our fine-tuned YOLO11 model, running on CPU."""

    def __init__(self, weights: Path, *, confidence_floor: float = 0.15) -> None:
        # Ultralytics and torch are a heavy optional dependency; import here so the API service can
        # run without them when inference is handled elsewhere.
        from ultralytics import YOLO

        self._model = YOLO(str(weights))
        self._weights = Path(weights)
        # Detections below this are not surfaced at all. The rulebook's higher threshold then
        # decides which of the survivors are stated as fact rather than offered for confirmation.
        self._confidence_floor = confidence_floor

    @property
    def version(self) -> str:
        return self._weights.stem

    def detect(self, image_bytes: bytes) -> list[Detection]:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as image:
            image = image.convert("RGB")
            width, height = image.size
            results = self._model.predict(image, conf=self._confidence_floor, verbose=False)

        detections: list[Detection] = []
        for result in results:
            names = result.names
            for box in result.boxes:
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
                # Clamp before normalising: a box a pixel past the edge is a rounding artefact, not
                # a reason to reject a real detection at the database constraint.
                x1, y1 = max(0.0, x1), max(0.0, y1)
                x2, y2 = min(float(width), x2), min(float(height), y2)
                if x2 <= x1 or y2 <= y1:
                    continue

                detections.append(
                    Detection(
                        hazard=names[int(box.cls)],
                        confidence=round(float(box.conf), 3),
                        x=round(x1 / width, 5),
                        y=round(y1 / height, 5),
                        w=round((x2 - x1) / width, 5),
                        h=round((y2 - y1) / height, 5),
                    )
                )
        return detections


def build_detector(weights_path: str | None) -> Detector:
    if not weights_path:
        return NullDetector()
    path = Path(weights_path)
    if not path.is_file():
        raise FileNotFoundError(f"detector weights not found: {path}")
    return YoloDetector(path)
