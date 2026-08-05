# Groundwork defensible-space hazard dataset

> **Status: not yet published.** This card is written in advance so that collection and labeling
> happen against a stated plan rather than being described after the fact. Fill in the counts and
> metrics from `ml/data/prepared/summary.json` and `ml/metrics/metrics.json` before release, and
> delete this notice.

## What it is

Photographs of California residential properties, labeled with six wildfire-hazard classes visible
from the ground. Collected and labeled by the two of us for the 2026 Congressional App Challenge.

As far as we could establish in August 2026, no open labeled dataset of defensible-space hazards
exists — the capability is sold to insurers and fire departments rather than published.

## Classes

Six, defined in [`taxonomy.json`](taxonomy.json) with include/exclude lists and a source per class,
written **before** any labeling began: `dead_vegetation`, `veg_touching_structure`,
`overhanging_limbs`, `combustible_mulch_z0`, `attached_wood_fence`, `combustibles_under_deck`.

## Collection

- Contra Costa and Alameda counties, plus out-of-region photographs from family and friends
  elsewhere in California to fight the homogeneity of corridor housing.
- Varied light and time of day.
- Hazards staged deliberately where rare classes would not otherwise appear often enough. Staged
  images are marked as such in the manifest.
- Public-street angles of visible frontage; anything closer taken with the owner's permission.
- **No Google Street View imagery** — prohibited by their terms of service.

## Splits

70/15/15 **by property**, assigned by hashing the property id. Every photograph of one house lands
in one split. Splitting by image would test the model on properties it had memorised and inflate the
metrics we publish. Tests in `ml/tests/` enforce this and run in CI.

## Known limitations

State these plainly at release; a dataset card that lists no weaknesses is not credible.

- **Geographic concentration.** Mostly one corridor of similar housing stock. Expect worse
  performance on other architecture, other vegetation, other terrain.
- **Staged examples.** Some hazards were arranged rather than found. Staging is honest for training
  but is not the same distribution as neglect.
- **Two labelers.** Weekly agreement checks are recorded in `ml/agreement/`, but two people share
  blind spots that a larger pool would not.
- **Ambiguous distance.** Two classes depend on a five-foot band the camera does not measure.
  Labelers use reference objects and skip the frame when no reference is visible.
- **Seasonality.** Collected across one summer. Cured grass looks different in April.

## Ethics and privacy

Photographs of private property. Images are published only where we have permission to publish them;
faces, licence plates, and house numbers are excluded or obscured. No addresses or coordinates are
included in the release. Users of the Groundwork app are separate from this dataset — their photos
are private to their account and are never added to it.

## Licence

To be stated at release. Intended: permissive for the images we own outright, with the class
definitions and labeling guide released alongside so the labels can be reproduced or disputed.

## Citation

To be added on release.
