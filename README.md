# Groundwork

**One scan of your yard. One plan that makes it fire-safe and water-wise — and shows the rebates that pay for it.**

Groundwork photographs a California property, runs a self-trained hazard-detection model over the
images, and reconciles two contradictory bodies of state policy — wildfire defensible-space rules
(PRC 4291, draft Zone 0) and water-conservation lawn-replacement rebates — into a single ranked
action plan with citations, cost estimates, and local program links.

Built for the 2026 Congressional App Challenge, CA-10.

> Groundwork provides educational guidance. It is **not** an official inspection, a safety
> guarantee, or insurance advice, and it contains no evacuation features.

---

## Repository layout

```
apps/mobile/      Expo + React Native (TypeScript) client
services/api/     FastAPI backend — geo, rules engine, rebates, inference orchestration
ml/               Dataset taxonomy, labeling guide, training + evaluation pipeline
infra/            Deployment config and GIS layer import scripts
docs/             BRD, architecture notes, decision log
```

## Architecture at a glance

```
[Expo React Native app]
   │ HTTPS/JSON
[FastAPI backend (single service)]
   ├── /auth ──────── Supabase (Postgres + auth + storage)
   ├── /assessments ─ inference worker (YOLO11 fine-tune, CPU) → findings
   ├── /rules ─────── rules engine (versioned JSON rulebooks)
   ├── /geo ───────── PostGIS point-in-polygon: FHSZ, fire district, water utility
   ├── /rebates ───── deterministic per-utility calculators
   ├── /plants ────── planting palette query
   ├── /reports ───── PDF generation
   └── /feeds ─────── cached NWS / CAL FIRE feeds (cron refresh)
```

### Governing principles

1. **Anything tied to law, money, or safety is deterministic.** The model proposes; the rules engine
   and the user dispose. No ML in area math, rebate math, or score arithmetic.
2. **The model is advisory and honest.** Confidence is always shown; metrics are published.
3. **No external call in the hot path.** Third-party feeds are cached server-side.
4. **Rulebooks are data, not code.** Versioned JSON, so a Zone 0 finalization is a content update.
5. **Everything disclosed.** See [CREDITS.md](CREDITS.md).

## Getting started

### Backend

```bash
cd services/api
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

API docs at `http://127.0.0.1:8000/docs`; health at `http://127.0.0.1:8000/v1/health`.

### Mobile

```bash
cd apps/mobile
npm install
npm start
```

### Checks

```bash
cd services/api && ruff check . && ruff format --check . && pytest
cd apps/mobile && npm run typecheck
```

## Documentation

- [Business requirements (BRD)](docs/BRD.md) — product definition, features, milestones
- [Decision log](docs/DECISIONS.md) — architectural decisions and their rationale
- [Submission status](docs/SUBMISSION.md) — what is done, and what is blocked on human work
- [Demo-day runbook](docs/RUNBOOK.md) — fallbacks, and what breaks looks like
- [Database](services/api/docs/DATABASE.md) — schema, migrations, and the privacy guarantee
- [Boundary layers](infra/gis/README.md) — which maps we host and how they are imported
- [ML pipeline](ml/README.md) · [labeling guide](ml/LABELING_GUIDE.md) · [dataset card](ml/DATASET_CARD.md)
- [Credits & disclosure](CREDITS.md) — every library, dataset, API, and AI-assisted tool

## License

Code is MIT ([LICENSE](LICENSE)). Third-party data retains its own license — see
[CREDITS.md](CREDITS.md).
