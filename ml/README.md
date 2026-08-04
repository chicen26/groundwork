# Groundwork ML

The hazard detector: its class taxonomy, the guide we label by, the dataset tooling, and the
training and evaluation scripts. The model is a fine-tune of Ultralytics YOLO11-small, trained on a
dataset we collect and label ourselves.

The code here is complete and tested. What it is waiting on is photographs — see
[LABELING_GUIDE.md](LABELING_GUIDE.md) for how to collect and label them.

## Layout

| File | What it does |
|---|---|
| [`taxonomy.json`](taxonomy.json) | The six classes, with include/exclude lists and sources. Single source of truth. |
| [`LABELING_GUIDE.md`](LABELING_GUIDE.md) | How to apply the taxonomy, photograph for the dataset, and run agreement checks. |
| [`dataset.py`](dataset.py) | Manifest validation, split-by-property, YOLO layout, `data.yaml`. |
| [`train.py`](train.py) | The fine-tune, with a `run_config.json` written beside every set of weights. |
| [`evaluate.py`](evaluate.py) | Held-out metrics, confusion matrix, and a `METRICS.md` we publish. |
| `tests/` | Guards, chiefly against leakage. Run on every push; need no torch. |

## The pipeline

```bash
# 1. Assemble. Validates boxes, splits by property, writes the YOLO layout.
python -m ml.dataset --manifest ml/data/manifest.json --out ml/data/prepared

# 2. Train (GPU: Colab or Kaggle).
pip install -e "ml[train]"
python -m ml.train --data ml/data/prepared/data.yaml --epochs 100

# 3. Evaluate on the held-out test set, once.
python -m ml.evaluate --weights ml/runs/hazards/weights/best.pt \
                      --data ml/data/prepared/data.yaml

# 4. Serve. The API's inference worker picks up queued photos.
export GROUNDWORK_DETECTOR_WEIGHTS=/path/to/best.pt
python -m app.inference.worker --once
```

## Classes

Six, chosen to be visually crisp and individually defensible, and written down before any labeling
began. Full definitions in [`taxonomy.json`](taxonomy.json).

| Class | Source |
|---|---|
| `dead_vegetation` | PRC 4291(a)(1); CSFS Home Ignition Zone |
| `veg_touching_structure` | IBHS Wildfire Prepared Home; draft Zone 0 |
| `overhanging_limbs` | PRC 4291(a)(4) |
| `combustible_mulch_z0` | Draft Zone 0 (pending final adoption) |
| `attached_wood_fence` | Draft Zone 0 (pending final adoption) |
| `combustibles_under_deck` | CSFS Home Ignition Zone; IBHS |

A test asserts this list, the rulebook's triggers, and the database's `hazard_class` enum all agree.
A class the model detects but no rule acts on is wasted labeling effort; a rule waiting on a class
the model never emits can never fire.

Any class that cannot clear a usable mAP@50 bar gets merged or dropped rather than shipped weak.
`evaluate.py` names those classes explicitly in its report.

## Splits are by property, never by image

This is the one thing the tooling refuses to let anyone get wrong. Every photo of one house lands in
one split, assigned by hashing the property id — so a rerun produces the same test set, and adding
photos next week does not reassign houses labeled last week.

If two photos of a yard straddled the train/test line, the model would be tested on a property it
had memorised, and the mAP in our written submission would be a number it could not reproduce on a
judge's own house. That is not a performance bug, it is a false claim, and it is why the leakage
guards run in CI on every push.

## Honesty about accuracy

We publish per-class mAP@50, a confusion matrix, and precision/recall curves — including for the
classes that do badly. `evaluate.py` writes `METRICS.md` for the repository and `metrics.json` for
the record.

The design assumes the model will miss things. Detections are advisory: below the rulebook's
confidence threshold they appear as "possible — confirm" and do not move the score at all, and the
checklist covers every rule independently, so a missed hazard cannot silently produce a clean plan.

When no weights are configured, inference jobs **fail** rather than returning nothing. An empty
result would be indistinguishable from "we looked and your yard is fine", which is the one lie this
product cannot afford.

## Privacy

Photographs of private property are sensitive. `ml/data/` is gitignored and raw imagery is never
committed. The published dataset is released separately, with a dataset card, explicit licence, and
only imagery we have permission to publish.
