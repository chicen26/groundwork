# Credits & disclosure

Groundwork discloses every library, dataset, external API, and AI-assisted tool it relies on. This
file mirrors the disclosure section of our Congressional App Challenge submission and is updated as
dependencies are added.

## Software libraries

| Library | Use | License |
|---|---|---|
| Expo / React Native | Mobile client | MIT |
| React | UI | MIT |
| TypeScript | Types for the client | Apache-2.0 |
| FastAPI | Backend HTTP framework | MIT |
| Pydantic / pydantic-settings | Request models and configuration | MIT |
| Uvicorn | ASGI server | BSD-3-Clause |
| pytest | Backend tests | MIT |
| Ruff | Backend lint + format | MIT |
| asyncpg | Postgres driver | Apache-2.0 |
| PostGIS | Spatial types and point-in-polygon queries | GPL-2.0 (server-side; not linked into our code) |
| PyJWT | Verifying Supabase-issued tokens | MIT |
| certifi | CA bundle for outbound HTTPS | MPL-2.0 |
| Pillow | Image decoding and EXIF stripping | MIT-CMU |
| Ultralytics YOLO11 | Architecture we fine-tune; training and inference runtime | AGPL-3.0 |

_Additional entries are appended as each step lands (Supabase client, turf.js, WeasyPrint/ReportLab)._

**On Ultralytics' licence.** YOLO11 is AGPL-3.0. Groundwork is a non-commercial student project and
its source is public, which is consistent with those terms. The architecture and training framework
are theirs; the dataset, the class taxonomy, the labelling, the trained weights, and every
evaluation artefact are ours.

## Datasets

| Dataset | Use | Terms |
|---|---|---|
| Groundwork defensible-space hazard dataset | Training data for our detection model | Collected and labeled by us; to be published openly with a dataset card |
| CAL FIRE Fire Hazard Severity Zones (SRA 2024, LRA 2025) | Zone lookup | Public CAL FIRE GIS data |
| WUCOLS V (UC Davis) | Plant water-use ratings | Public; attribution |
| Calscape (California Native Plant Society) | Native plant data | Non-commercial use with attribution; no public API — permission requested directly |
| UC ANR and fire safe council plant lists | Fire-wise plant guidance | Public documents, curated import |

## External APIs and data feeds

| Source | Use | Access |
|---|---|---|
| CAL FIRE FHSZ feature services (LRA 2025 v1, SRA 2023 v3) | Zone lookup | Public ArcGIS services; imported into our PostGIS and served from there |
| US Census Bureau geocoder | Address to coordinate | Free, no key; results cached |
| NWS `api.weather.gov` | Red Flag Warning banner | Free, no key; cached server-side |
| CAL FIRE incidents JSON | Nearby active incidents | Undocumented endpoint; cached, treated as unstable |
| NASA FIRMS | Optional hotspot context | Free key; cached |
| Genasys Protect | Evacuation-zone lookup deep link only | No API used; outbound link only |
| Supabase | Auth, Postgres, photo storage | Hosted service |

## AI-assisted development

- **Our model.** The hazard-detection model is a fine-tune of Ultralytics YOLO11 trained by us on a
  dataset we collected and labeled ourselves. Training configuration, evaluation metrics
  (mAP@50 per class, confusion matrix), and the dataset card live in [`ml/`](ml/).
- **AI coding assistance.** We used AI coding assistants (Claude) while writing parts of this
  codebase. All architecture, data collection, labeling, model training, evaluation, and product
  decisions are ours, and every generated line was reviewed by us before it was committed. AI does
  not constitute the entirety of the technical development.

## Attribution notes

- Calscape / CNPS data is used non-commercially with attribution, per their stated terms.
- No Google Street View imagery is used in training data, per their terms of service.
