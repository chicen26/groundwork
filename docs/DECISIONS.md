# Decision log

Short, dated records of architectural decisions and why we made them. New entries append; entries
are amended rather than deleted so the reasoning stays auditable for the submission write-up.

---

### D1 — Monorepo with one backend service · Aug 4, 2026

**Decision.** One repository containing `apps/mobile`, `services/api`, and `ml`, with a single
deployable FastAPI service rather than per-domain microservices.

**Why.** Two developers over twelve weeks. A monorepo means one CI pipeline, one place for judges to
read the source, and no cross-repo version drift between the client and the API contract. Splitting
services would buy scaling we do not need and cost us integration time we do not have.

---

### D2 — Versioned API prefix (`/v1`) from the first endpoint · Aug 4, 2026

**Decision.** All routers mount under `/v1`.

**Why.** Testers will be running installed Expo dev builds during the recruiting push (30+ real
assessments). Those builds cannot be force-updated, so the contract they pinned has to keep working
while we continue shipping.

---

### D3 — Rulebooks are versioned data, not code · Aug 4, 2026

**Decision.** Fire and water rules live in versioned JSON documents. The active version is an
environment setting and is exposed on `/v1/health` and on every assessment.

**Why.** Zone 0 is still a draft regulation during the build window and may be finalized before the
October deadline. Encoding the rules as data means adoption is a content update, not a refactor. It
also means any finding we show can name the exact rulebook that produced it — necessary for the
"pending final adoption" labeling we promised in the risk register (R3).

---

### D4 — Determinism boundary · Aug 4, 2026

**Decision.** The model only proposes findings. Score arithmetic, rebate math, and area computation
are deterministic backend code with unit tests, never model output.

**Why.** Those numbers are legal, financial, and safety claims. A false positive in a bounding box is
recoverable and is labeled "flagged for review"; a wrong rebate figure or readiness score is not.

---

### D5 — Docker image built in CI from the start · Aug 4, 2026

**Decision.** CI builds the API image on every push.

**Why.** Demo-day fallback is a laptop-hosted backend behind a tunnel. That fallback is only real if
the image is known to build; discovering a broken Dockerfile in October is not a risk worth carrying.

---

### D6 — Boundary layers are imported and versioned, never queried live · Aug 4, 2026

**Decision.** CAL FIRE's FHSZ maps are imported into our PostGIS as versioned snapshots. An import
promotes itself to active only after every feature has loaded, and resolution reads only the active
version.

**Why.** Governing principle 3 — no external call in the hot path. Beyond uptime, a homeowner's zone
is a claim about a specific published map, so we store which edition produced it and show that with
the answer. Versioning also makes a bad refresh recoverable rather than a live outage.

---

### D7 — An unresolved layer is reported, not guessed · Aug 4, 2026

**Decision.** Where no polygon contains a property, the API returns the layer in `unresolved` rather
than falling back to a nearest match or a city-name lookup.

**Why.** Naming the wrong fire district sends someone to the wrong agency for an inspection, and
Walnut Creek and San Ramon are each split between two water utilities, which changes the rebate rate
and cap. A visible gap is honest and fixable; a confident wrong answer is neither.

---

### D8 — Tokens are verified locally against a public JWKS · Aug 4, 2026, revised Aug 5

**Decision.** Supabase issues JWTs and we verify them ourselves, against the project's **public**
JWKS (ES256) rather than a shared secret. The service therefore holds no secret capable of minting a
token. Algorithms are allowlisted to ES256/RS256, and issuer and audience are both checked. A
development-only `X-Groundwork-User` header exists and is refused whenever the environment is
production or auth is configured. A bearer token presented while auth is unconfigured returns 503
rather than being accepted, and a JWKS fetch failure returns 503 rather than 401 — telling someone
their credentials are wrong when our own fetch failed is a lie.

**Why.** Building the scan flow should not require a Supabase project, but a convenience header that
could survive into a deployment is a hole. Both failure modes resolve toward refusing access.

---

### D9 — Areas and rebate figures are computed server-side, in Decimal · Aug 5, 2026

**Decision.** The client draws the lawn polygon; the server computes its geodesic area with PostGIS
and every rebate figure with `Decimal`, rounding **down** to the cent. Where the water utility could
not be determined, all three programmes are shown with their agencies named rather than one being
guessed.

**Why.** People budget projects around these numbers. A float rounding error or a client-side area
computed on a slow phone becomes a promise we cannot keep. Rounding down matches how a utility pays
— for the square feet actually converted — and showing three named agencies is more useful than one
confident wrong rate, particularly in Walnut Creek and San Ramon where the city is split between two
utilities.

Every estimate carries the pre-approval warning, because work started before the inspection is
ineligible no matter how good the finished yard is.

