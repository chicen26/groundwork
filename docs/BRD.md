# Groundwork — Business Requirements Document

**Version:** 1.0 · **Date:** August 4, 2026 · **Team:** 2 developers
**Target:** 2026 Congressional App Challenge, CA-10 (Rep. Mark DeSaulnier) — submission deadline **Oct 26, 2026, 9:00 AM PT**

---

## 1. Product definition

**One-liner:** Groundwork scans your yard with a custom-trained AI model and turns California's conflicting fire-clearance and water-conservation rules into one personalized plan — what to remove, what to plant, what it saves, and the local rebates that pay for it.

**Problem.** California tells homeowners two contradictory things about the same yard: the pending Zone 0 regulation (draft April 2026, possibly effective late 2026) requires stripping vegetation, mulch, and combustibles from the 0–5 ft perimeter of homes in Very High fire hazard zones, while state and local water policy pays homeowners $1–$2/sq ft to *replace* lawns with plants. In February 2025, CAL FIRE's new hazard maps put Very High zones inside 12 Contra Costa cities (incl. Danville, Concord, Lafayette, Orinda). Insurers are non-renewing policies while the state's *Safer from Wildfires* regulation entitles homeowners to premium credits for documented mitigation. No tool exists that reconciles these: commercial defensible-space AI (ZestyAI, Verisk) serves insurers via aerial imagery; Fire Aside serves fire-department inspectors. **No consumer app lets a homeowner photograph their own property and get automated hazard detection.** (Verified market gap, Aug 2026.)

**Users.** Primary: homeowners in the Contra Costa / Tri-Valley wildland-urban interface. Secondary: fire districts and fire safe councils (as a resident self-assessment channel), insurance-shopping homeowners needing mitigation documentation.

**Goals.**
1. Win CA-10 by scoring on all three official judging criteria: idea originality (unclaimed intersection), implementation/UX (polished guided flow), coding skill (self-built dataset + self-trained model).
2. Real utility: ≥30 completed real-property assessments before submission; ≥1 letter/quote from a local fire agency, fire safe council, or CNPS.

**Non-goals (out of scope for v1).** Air-quality features (reserved as the "2.0" written answer). Evacuation guidance of any kind. Insurance price quotes. Commercial use. Android+iOS store release (Expo dev builds / TestFlight are sufficient for judging).

---

## 2. Selling points

**For judges:**
1. **First of its kind** — verified: no consumer photo-based defensible-space app exists; the capability is currently sold only to insurers and fire departments. We give it to homeowners for free.
2. **We built the AI, not borrowed it** — self-collected, self-labeled dataset (1,500–3,000 images) fine-tuning YOLO11; published openly as the first labeled defensible-space hazard dataset. Directly satisfies the CAC rule that AI "must not constitute the entirety of the technical development."
3. **Policy-perfect timing** — Zone 0 rulemaking is concluding during the build window; the Feb 2025 hazard maps just redrew our own district; the July 2026 Morgan Fire burned at the foot of Mount Diablo.
4. **One plan, two laws** — the unified fire+water plan is the creative thesis; nobody else reconciles Zone 0 with lawn-conversion rebates and the native-plant movement.
5. **Real money on screen** — per-utility rebate calculation (EBMUD $1–2/sq ft, CCWD $1, DSRSD $2) and insurance-credit documentation make impact tangible in the demo.
6. **Hyper-local credibility** — the resources screen names the judges' own agencies: SRVFPD, Con Fire, MOFD, Diablo Fire Safe Council.

**For users:** free inspector-grade guidance without waiting for an inspection; know your legal obligations before enforcement begins; find rebate money you didn't know existed; generate the paperwork your insurer wants.

---

## 3. Pros, cons, risks

**Pros:** unclaimed niche; strongest possible trained-AI narrative; regulatory tailwind; demo moments that film beautifully (live hazard boxes, score climbing after cleanup, "$1,840 rebate"); phase-able scope with a clean fallback (fire core + rebate calc, palette deferred).

**Cons / risks → mitigations:**
| # | Risk | Mitigation |
|---|------|-----------|
| R1 | Model false negatives embarrass demo (judge tries own house) | Frame detections as "flagged for review," pair with manual checklist so plans are complete without the model; publish mAP + confusion matrix as honesty |
| R2 | Dataset diversity — corridor housing is homogeneous | Stage hazards deliberately; vary light/time; out-of-region photos from relatives; 6 crisp classes only |
| R3 | Zone 0 still draft — misstating law | All Zone 0 items labeled "pending final adoption"; re-verify at bof.fire.ca.gov before video (if final by Oct → upgrade copy) |
| R4 | Rebate misuse — utilities void rebates if lawn removed before pre-approval | Rebate screen leads with "Apply BEFORE you dig," deep-links utility application; never say "guaranteed" |
| R5 | Safety overclaim | Persistent disclaimer: educational guidance, not an official inspection or safety guarantee; no evacuation features |
| R6 | Scope creep ("two apps" perception) | Fire assessment is the core loop; water modules are P1 additions; hard cut-line defined in §6 |
| R7 | Calscape licensing (no API; non-commercial with attribution) | Attribute per their FAQ; email CNPS early — their reply doubles as community validation |
| R8 | External feeds unstable (CAL FIRE API undocumented) | All third-party data proxied + cached server-side; demo never depends on a live external call |
| R9 | Low organic adoption window | Recruit via neighbors, school clubs, Nextdoor, fire safe council; target = 30+ assessments, not installs |

---

## 4. Feature requirements

Priorities: **P0** = must ship (core demo), **P1** = ship for full pitch, **P2** = stretch.

### F1. Address setup & zone resolution — P0
Enter address → geocode → resolve and display: (a) Fire Hazard Severity Zone via point-in-polygon on CAL FIRE 2025 LRA/SRA GIS layers; (b) fire district (SRVFPD / Con Fire / MOFD / ACFD boundaries); (c) water utility (EBMUD / CCWD / DSRSD / city — incl. split-city handling for Walnut Creek & San Ramon). Copy: "Your home was designated **Very High** in Feb 2025."

### F2. Guided yard scan — P0
Structured photo walk with per-station framing hints: front elevation, each side, deck/porch, roofline, 0–5 ft perimeter. Photos upload per-station; scan resumable; works with camera or library.

### F3. AI hazard detection — P0
Backend inference with our fine-tuned YOLO11-small. Six classes: `veg_touching_structure`, `overhanging_limbs`, `combustible_mulch_z0`, `attached_wood_fence`, `combustibles_under_deck`, `dead_vegetation`. Bounding boxes rendered on user photos; per-detection confidence; below-threshold = "possible hazard — confirm." Segmentation (turf/vegetation cover) is **P1** for palette + verification support.

### F4. Rules engine & Readiness Score — P0
Deterministic engine (no LLM). Inputs: detections + user-confirmed checklist answers + FHSZ + lawn data. Rulebooks encoded as versioned JSON: PRC 4291 Zones 1–2, draft Zone 0 (flagged pending), IBHS Wildfire Prepared Home. Output: 0–100 score (transparent severity-weighted formula) + findings list, each with citation, zone, severity, rationale.

### F5. Action plan — P0
Ranked to-do list merging fire and water items with effort estimate, cost/savings estimate, citation, and linked program (chipping, cost-share, rebate). Check-off with score preview ("clearing this raises your score to 71").

### F6. Lawn measurement & rebate calculator — P1
User outlines lawn polygon(s) on satellite basemap → geodesic area → utility-specific rebate math (EBMUD standard $1/sf & Super $2/sf w/ native requirement, cap $2,000; CCWD $1/sf cap $2,000; DSRSD $2/sf cap $3,000) + estimated gal/yr saved (area × local ET-based factor). Always shows "pre-approval required before removal" + application link. Money math is 100% deterministic.

### F7. Planting palette — P1
Recommendation engine over our joined dataset: WUCOLS V water ratings × UC ANR/fire-safe-council fire-wise lists × Calscape native data (with attribution). Filters: yard zone (0–5 ft = noncombustible/hardscape only per draft Zone 0; 5–30 ft; 30+ ft), sun, native-only toggle (Super Rebate eligibility). Each plant: water need, fire notes, native status, rebate-qualifying flag.

### F8. Fix & verify — P1
Re-scan a station → model + user confirmation clears findings → score updates → before/after pairs saved (feeds F9 documentation).

### F9. Insurance & documentation report — P1
One-tap PDF: property, date, geotag, FHSZ, score, findings with photos, completed mitigations with before/after, mapped to *Safer from Wildfires* credit categories. Footer disclaimer (educational, not an inspection).

### F10. Local resources — P1
District-aware directory (data-driven JSON): MOFD free chipping/vent mesh, Diablo FSC chipping + $3,500 cost-share, Con Fire weed-abatement deadlines, SRVFPD inspections, Genasys evacuation-zone deep link (protect.genasys.com — lookup only, no evac features).

### F11. Context strip — P2
Red Flag Warning banner (NWS `api.weather.gov/alerts/active`), active incidents within 30 mi (CAL FIRE incidents JSON via our cache; NASA FIRMS optional). Deliberately minimal — one strip, no map screen. Never blocks core flows if feeds are down.

### F12. Accounts & persistence — P0
Email auth (Supabase). Properties, scans, findings, progress persist. Data private by default; delete-account = hard delete of photos + records. Photos EXIF-stripped on upload (location stored only as our own fields with consent).

---

## 5. Backend directrix (architecture & governing principles)

### Governing principles
1. **Anything tied to law, money, or safety is deterministic.** The model proposes; the rules engine + user confirmation disposes. No ML in area math, rebate math, or score arithmetic.
2. **The model is advisory and honest.** Confidence shown; thresholds tuned for precision over recall in UI labeling; metrics published.
3. **No external call in the hot path.** Every third-party feed (CAL FIRE, NWS, FIRMS) is fetched by a scheduled job into our DB and served from cache. GIS lookups run on layers we host.
4. **Rulebooks are data, not code.** Versioned JSON documents so a Zone 0 finalization is a content update, not a refactor.
5. **Everything disclosed.** `CREDITS.md` lists every library, dataset, API, and any AI-assisted tooling — mirrors the CAC submission's disclosure section.

### System shape
```
[Expo React Native app]
   │ HTTPS/JSON
[FastAPI backend (single service)]
   ├── /auth ──────────── Supabase (Postgres + auth + storage)
   ├── /assessments ───── inference worker (YOLO11 .pt, CPU) → findings
   ├── /rules ─────────── rules engine (versioned JSON rulebooks)
   ├── /geo ───────────── PostGIS point-in-polygon: FHSZ, fire district, utility
   ├── /rebates ───────── deterministic calculators (per-utility config JSON)
   ├── /plants ────────── palette query over joined plant dataset (Postgres)
   ├── /reports ──────── PDF generation (WeasyPrint/ReportLab)
   └── /feeds ─────────── cached NWS / CAL FIRE / FIRMS (cron refresh)
```

### Stack
- **App:** React Native + Expo, TypeScript. Camera flow via `expo-camera`; satellite polygon via `react-native-maps` + turf.js for geodesic area (server re-computes authoritative value).
- **API:** Python 3.12, FastAPI + Pydantic. Single deployable service; inference in a worker process/queue so uploads never block.
- **ML:** Ultralytics YOLO11-small fine-tune; train on Colab/Kaggle GPUs; inference on CPU (nano/small is fast enough); export to CoreML/TFLite only as post-P1 stretch.
- **Data:** Supabase Postgres (+ PostGIS) — auth, rows, photo storage. GIS layers imported once: CAL FIRE FHSZ (SRA + 2025 LRA), fire-district and utility boundaries.
- **Hosting:** Render/Fly free-or-cheap tier; Dockerfile from day one. Demo-day fallback: laptop-hosted backend + tunnel.

### Core data model
```
users(id, email, created_at)
properties(id, user_id, address, lat, lng, fhsz_class, fire_district, water_utility)
scans(id, property_id, started_at, completed_at, status)
photos(id, scan_id, station, storage_path, exif_stripped bool)
findings(id, scan_id, photo_id, class, bbox, confidence, source enum(model|checklist),
         status enum(open|confirmed|dismissed|resolved), rule_ids[])
lawn_polygons(id, property_id, geojson, area_sqft, computed_at)
assessments(id, scan_id, score, rulebook_version, breakdown jsonb)
plans(id, assessment_id) / plan_items(id, plan_id, rank, kind enum(fire|water),
         rule_id, finding_id?, cost_est, savings_est, program_id?, done_at)
plants(id, name, sci_name, wucols_rating, fire_notes, native bool, zones_allowed[], sources[])
programs(id, agency, type enum(rebate|chipping|cost_share|inspection), config jsonb)
feed_cache(id, source, payload jsonb, fetched_at)
```

### Key API endpoints
```
POST /auth/*                       (Supabase-delegated)
POST /properties                   → geo resolution runs here
POST /scans  /scans/{id}/photos    → enqueue inference; returns finding stream
GET  /scans/{id}/findings
POST /findings/{id}/status         (confirm/dismiss/resolve)
POST /properties/{id}/lawn         → area + rebate + savings
GET  /assessments/{id}             → score + breakdown
GET  /plans/{id}                   POST /plan-items/{id}/complete
GET  /plants?zone=&sun=&native=
GET  /programs?district=&utility=
GET  /feeds/alerts?lat=&lng=       (cached)
POST /reports/{assessment_id}      → PDF URL
```

### ML pipeline (the schedule-critical path)
1. **Taxonomy:** class definitions written from IBHS Wildfire Prepared Home standard + CSFS Home Ignition Zone guide before any labeling.
2. **Collection:** 1,500–3,000 photos — own neighborhoods (permissioned close-ups; public-street angles), staged hazards, varied light/time; NO Street View in training (TOS).
3. **Labeling:** Label Studio or CVAT (free/private); label guide doc with positive/negative examples per class; both teammates label, weekly agreement spot-checks.
4. **Training:** 70/15/15 split by *property* (no leakage); augmentation; iterate weekly. Track mAP@50 per class; drop/merge any class that can't clear a usable bar.
5. **Evaluation artifact:** held-out test set, confusion matrix, per-class PR — published in repo + cited in written answers.
6. **Release:** dataset published (first open defensible-space hazard dataset) with cards/licenses.

### External data dependencies (verified Aug 2026)
| Source | Use | Access |
|---|---|---|
| CAL FIRE FHSZ GIS (SRA 2024 + LRA 2025) | F1 zone lookup | Downloadable GeoJSON/SHP → self-hosted PostGIS |
| NWS alerts `api.weather.gov` | F11 Red Flag | Free, no key → cached |
| CAL FIRE incidents `incidents.fire.ca.gov/.../List` | F11 | Undocumented JSON → cached, treat as unstable |
| NASA FIRMS | F11 optional | Free MAP_KEY → cached |
| WUCOLS V (4,100+ taxa, Mar 2025) | F7 | Downloadable xlsx → imported |
| Calscape (CNPS) | F7 native data | Non-commercial w/ attribution; no API — email CNPS |
| UC ANR / fire-safe-council plant lists | F7 fire-wise | Public PDFs → curated import |
| Utility rebate terms (EBMUD/CCWD/DSRSD) | F6 | Encoded as config JSON; re-verify pre-launch |
| Genasys Protect | F10 deep link only | No public API |

### Privacy & security
Photos of private property = sensitive: EXIF stripped, storage bucket private, signed URLs, hard delete on request, no third-party analytics, minors' accounts fine (no public sharing features). HTTPS everywhere; secrets in env; rate-limit uploads.

---

## 6. Milestones (Aug 4 → Oct 26)

| Weeks | Deliverable | Cut-line check |
|---|---|---|
| 1–2 (Aug 4–17) | Taxonomy + label guide; collection sprint ≥800 photos; repo, CI, Expo skeleton, Supabase, geo import | — |
| 3–5 (Aug 18–Sep 7) | ≥1,500 labeled; model v1 trained; rules engine v1; P0 loop end-to-end (scan→boxes→score→plan) | **P0 demo works or scope cut** |
| 6–7 (Sep 8–21) | F6 rebates, F7 palette, F8 verify, F10 resources; model v2 | Palette slips → 2.0 answer |
| 8 (Sep 22–28) | F9 PDF, polish, F11 strip; freeze features | **Feature freeze** |
| 9–10 (Sep 29–Oct 12) | 30+ real assessments; outreach (Diablo FSC, SRVFPD, MOFD, CNPS); dataset published | — |
| 11 (Oct 13–19) | Video shot+cut; written answers drafted; Zone 0 status re-verified | — |
| 12 (Oct 20–26) | Buffer; submit ≥3 days early | **Submit by Oct 23** |

## 7. CAC compliance checklist
- [ ] Both teammates eligible (enrolled MS/HS on Oct 26, 2026; live or attend school in CA-10; ≥half of team in-district)
- [ ] Registration with personal emails; eligibility quiz done
- [ ] All code written after Oct 30, 2025; all coding by us; libraries documented in CREDITS.md
- [ ] AI tools fully disclosed; trained-model work documented as ours
- [ ] Video 1–3 min, public YouTube/Vimeo: names, app name, one-sentence purpose, target audience, tools/languages, functionality demo
- [ ] Written answers: purpose / inspiration / technical difficulty / learnings / 2.0 (= air-quality module + on-device inference)
- [ ] App + source runnable on demand for judges
- [ ] Post-deadline exit questionnaire (both members)

## 8. Verify-before-launch register
1. Zone 0 adoption status (bof.fire.ca.gov) — recheck monthly + before video
2. Rebate terms/caps for all three utilities (EBMUD/CCWD/DSRSD pages) — now encoded in `services/api/programs/rebates.json`; re-verify every figure there before the video
3. WUCOLS bulk download link (site blocked automated fetch)
4. CNPS/Calscape attribution email sent + response
5. CAL FIRE incidents endpoint stability (fallback: NIFC ArcGIS feeds)
6. DeSaulnier office 2026 submission specifics (press release / (925) 933-2660)
7. Tri-Valley/Dublin–San Ramon program overlap check (ACFD programs, Dublin FHSZ status, Firewise communities) — open research item from prior session
