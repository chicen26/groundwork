# Groundwork ML

Home of the dataset taxonomy, labeling guide, training pipeline, and evaluation artifacts for the
Groundwork hazard-detection model. Populated in **Step 6**; this file records the plan and the rules
that constrain the work.

## Model

Fine-tune of Ultralytics YOLO11-small. Trained on GPU (Colab/Kaggle), served on CPU — nano/small is
fast enough for our inference budget. On-device export (CoreML/TFLite) is a post-P1 stretch.

## Classes

Six classes, chosen to be visually crisp and individually defensible:

| Class | Definition source |
|---|---|
| `veg_touching_structure` | IBHS Wildfire Prepared Home |
| `overhanging_limbs` | PRC 4291 / CSFS Home Ignition Zone |
| `combustible_mulch_z0` | Draft Zone 0 (pending final adoption) |
| `attached_wood_fence` | IBHS Wildfire Prepared Home |
| `combustibles_under_deck` | CSFS Home Ignition Zone |
| `dead_vegetation` | PRC 4291 |

Class definitions are written **before** any labeling begins, with positive and negative examples per
class in the labeling guide. Any class that cannot clear a usable mAP@50 bar gets merged or dropped
rather than shipped weak.

## Data rules

- 1,500–3,000 images: our own neighborhoods (with permission for close-ups), staged hazards, varied
  light and time of day, plus out-of-region photos to fight the homogeneity of corridor housing.
- **No Google Street View imagery in training data** — prohibited by their terms of service.
- Splits are **by property**, 70/15/15. Never split by image: two photos of the same yard in
  different splits is leakage.
- Photos of private property are sensitive. Raw imagery is not committed to this repository
  (`ml/data/` is gitignored); the published dataset is released separately with a dataset card and
  license.

## Evaluation artifacts (published, not just measured)

- Held-out test-set mAP@50, per class
- Confusion matrix
- Per-class precision/recall curves

These go in the repository and are cited in the written submission answers. Thresholds are tuned for
precision over recall in UI labeling: below-threshold detections surface as "possible hazard —
confirm," never as a stated fact.
