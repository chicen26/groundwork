# Boundary layers

Groundwork hosts its own copies of the maps it resolves against. A homeowner opening the app must
not depend on CAL FIRE's ArcGIS server being reachable, and point-in-polygon against a local GIST
index costs milliseconds.

## Importing

```bash
export GROUNDWORK_DATABASE_URL=postgresql://localhost/groundwork_dev
python -m scripts.import_gis --all
```

Each import writes a new `gis_layer_versions` row and promotes it to active only after every
feature has loaded. A refresh that dies halfway leaves the previous map serving, and resolution
never sees half-loaded geometry.

Statewide layers are clipped on request to the CA-10 corridor (`CA10_BBOX` in `app/geo/sources.py`)
— roughly Contra Costa and Alameda counties with a margin. That is the difference between hosting
tens of megabytes and gigabytes we would never query.

## Layers currently configured

| Key | Source | Status |
|---|---|---|
| `fhsz_lra` | CAL FIRE, FHSZ in LRA 2025 v1 (`FHSALRA25_v1_All`) | Verified Aug 4, 2026 — 420 features in the corridor |
| `fhsz_sra` | CAL FIRE, FHSZ in SRA 2023 v3 (`FHSZSRA_23_3`) | Verified Aug 4, 2026 — 344 features in the corridor |

Verification means the imported copy was spot-checked against the live service at known
coordinates:

| Location | Zone | Responsibility |
|---|---|---|
| Lafayette | Moderate | LRA |
| Orinda hills | NonWildland | LRA |
| Danville centre | NonWildland | LRA |
| Blackhawk | High | SRA |
| Mount Diablo | Very High | SRA |

Where the two maps overlap, the local (LRA) designation governs; the state layer is the fallback
for unincorporated land.

## Not yet sourced

**Fire district and water utility boundaries.** These are published per-county and per-agency
rather than by one authority, and Contra Costa's district polygons are not in its public ArcGIS
folders (the `ConFire` folder is permission-restricted).

Until a source is confirmed, `resolve_point` returns `None` for these and the API reports them in
`unresolved`, so the client can say "we could not determine your fire district" rather than render
a blank field that reads like "you do not have one". Guessing would be worse than a gap: naming the
wrong district sends someone to the wrong agency for an inspection.

Still to find:

- SRVFPD / Con Fire / MOFD / ACFD service-area polygons
- EBMUD / CCWD / DSRSD service-area polygons. City-name lookup is **not** an acceptable substitute:
  Walnut Creek and San Ramon are each split between two utilities, and the utility decides which
  rebate rates and caps apply.

Adding either means adding a `LayerSource` entry to `app/geo/sources.py` — the importer is generic.

## Re-verification

Every URL here is in the verify-before-launch register. Publishers reorganise ArcGIS services
without notice; a URL that worked in August is not evidence it works in October. Re-run
`python -m scripts.import_gis --all --dry-run` before the submission video and confirm the feature
counts are in the same ballpark.
