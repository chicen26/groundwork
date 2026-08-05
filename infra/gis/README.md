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

The default import covers **all of California** (~28k polygons; CAL FIRE's maps are statewide, so
serving the whole state is a bounding box, not a feature). `--extent ca10` keeps dev imports fast.
Verified statewide Aug 5, 2026: Pacific Palisades and Paradise resolve Very High, Fresno centre
Non-Wildland.

## Layers currently configured

| Key | Source | Status |
|---|---|---|
| `fhsz_lra` | CAL FIRE, FHSZ in LRA 2025 v1 (`FHSALRA25_v1_All`) | Verified Aug 4, 2026 — 420 features in the corridor |
| `fhsz_sra` | CAL FIRE, FHSZ in SRA 2023 v3 (`FHSZSRA_23_3`) | Verified Aug 4, 2026 — 344 features in the corridor |
| `fire_districts` | CAL FIRE, California Local Fire Districts (`California_Local_Fire_Districts`) | Verified Aug 5, 2026 — 671 features statewide; Danville resolves San Ramon Valley FPD (FDID 07035) |
| `water_utilities` | SWRCB, Drinking Water System Area Boundaries (SABL), Water Service Area polygons only | Verified Aug 5, 2026 — 4,953 features statewide; Danville resolves EBMUD (CA0110005) |

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

## District and utility boundaries: sourced

The gap this section used to describe is closed. Two statewide authorities publish exactly what
the per-county search never found:

- **Fire districts** — CAL FIRE's *California Local Fire Districts* compilation (updated yearly
  against the State Fire Marshal's FDID register), hosted in the same ArcGIS org as the FHSZ
  layers.
- **Water utilities** — the State Water Board's *Drinking Water System Area Boundaries* (SABL).
  We import **Water Service Area** polygons only; jurisdictional boundaries overstate who a
  system actually serves. This satisfies the split-city requirement: Walnut Creek and San Ramon
  resolve to the utility that actually serves the point, not a city-name guess.

Names are canonicalised at import (`_DISTRICT_CANONICAL`, `_UTILITY_CANONICAL` in
`app/geo/sources.py`) so `resources.json` district matching and `rebates.json` agency matching
keep working: the CAL FIRE layer says "SAN RAMON VALLEY FPD", the resources file says
"San Ramon Valley Fire Protection District", and SABL says "EAST BAY MUD" where the rebate
programme says "EBMUD".

A point outside every polygon still resolves to `None` and is reported in `unresolved` — the
honest gap survives; it is just much rarer now.

## Re-verification

Every URL here is in the verify-before-launch register. Publishers reorganise ArcGIS services
without notice; a URL that worked in August is not evidence it works in October. Re-run
`python -m scripts.import_gis --all --dry-run` before the submission video and confirm the feature
counts are in the same ballpark.
