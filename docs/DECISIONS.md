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
