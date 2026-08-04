# Labeling guide

Read this before drawing a single box. It was written before labeling began, deliberately: deciding
what counts as a hazard *while* labeling means the definition drifts to fit whatever is on screen,
and two people end up labeling different datasets.

Class definitions, with include/exclude lists and the source each comes from, live in
[`taxonomy.json`](taxonomy.json). This document covers how to apply them.

## The rules that matter most

**When in doubt, do not label.** A missed hazard costs recall. A wrong one puts a red box on
somebody's house and tells them they are breaking a rule they are not. The app pairs every scan with
a checklist precisely so that recall is not the only thing standing between a user and a correct
plan — so we can afford to be conservative, and we should be.

**Label what is visible, not what you know.** If you took the photo and remember the mulch continues
around the corner, that is not in the frame. Label the frame.

**One box per distinct instance.** Three separate dead shrubs are three boxes. A continuous bed of
bark mulch along one wall is one box.

**Boxes are tight.** Include the hazard and nothing else. A box with half a lawn in it teaches the
model that lawns are hazards.

**Do not label through obstruction.** If a car covers the base of the wall, the mulch behind it is
not labeled. Absence of evidence is not evidence of clearance — that phrasing is in the taxonomy for
`combustibles_under_deck` for the same reason.

## The five-foot problem

Two classes (`combustible_mulch_z0`, and the Zone 0 reading of `veg_touching_structure`) depend on a
distance the camera does not record. Use visible reference objects:

| Object | Typical size |
|---|---|
| Exterior door | ~36 in wide, ~80 in tall |
| Siding course (lap siding) | 6–8 in |
| Standard brick | ~8 in long |
| Concrete walkway | 36–48 in wide |
| Garage door (single) | ~96 in wide |

If no reference is in frame and the band is not obvious, skip the photo for that class. A guess
scaled from nothing is worse than an unlabeled image.

## Photographing for the dataset

- **Vary the light.** Morning, midday, overcast, and late afternoon. A model trained only on 2pm
  sun learns shadows, not hazards.
- **Vary the distance.** Full elevation, mid-range, and close-up of the 0–5 ft band.
- **Stage hazards deliberately.** Our own corridor is homogeneous and mostly well-maintained, so
  rare classes will not appear often enough on their own. Staged examples are legitimate training
  data and should be recorded as staged in the manifest notes.
- **Get out-of-region photos** from relatives and friends elsewhere in California. Homogeneity is
  the biggest threat to this dataset (risk R2).
- **No Google Street View imagery.** Prohibited by their terms of service. This is not negotiable
  and would compromise the dataset release.
- **Permission for close-ups.** Public-street angles of visible frontage are fine; anything closer
  needs the owner's agreement.

## Background images matter

Photograph clean yards too, and label them with an empty file. A detector that has never seen a
well-maintained 0–5 ft band will invent hazards in one. Aim for roughly 10–15% background images.

## Agreement checks

Both of us label, and we spot-check each other weekly:

1. Pick 20 images the other person labeled.
2. Label them independently, without looking at the existing boxes.
3. Compare. Any class where we disagree more than about one time in five gets its definition
   tightened in `taxonomy.json` — and the previously labeled images for that class get revisited.

Record each check in `ml/agreement/YYYY-MM-DD.md` with the disagreements found. These notes are
evidence of method for the written submission, and the honest place to admit which classes were
hard.

## Splits are automatic — do not sort by hand

`ml/dataset.py` assigns every property to train, val, or test by hashing its id. Never move images
between splits manually, and never let two photos of one house end up in different splits: the model
would be tested on a property it had already memorised, and the mAP we publish would be a number it
cannot reproduce on a judge's yard. Tests enforce this; the honesty of our metrics depends on it.

## Manifest format

```json
{
  "images": [
    {
      "path": "raw/2026-08-10/danville-01/front.jpg",
      "property_id": "danville-01",
      "staged": false,
      "boxes": [[0, 0.412, 0.688, 0.180, 0.140]]
    }
  ]
}
```

Boxes are YOLO format: `[class_index, x_centre, y_centre, width, height]`, all normalised to 0–1.
`property_id` is required — it is the unit of splitting, and without it leakage cannot be prevented,
only hoped for.
