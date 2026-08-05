# Demo-day runbook

What to do when something breaks in front of judges. Written now, calmly, rather than in October
holding a phone.

## The fallback, in order

1. **Deployed backend** (Render/Fly), app pointed at it via `apiBaseUrl` in `app.json`.
2. **Laptop-hosted backend behind a tunnel.** The image is known to build and boot — CI runs the
   container and asks it for `/v1/health` on every push, so this fallback is real rather than
   assumed.
3. **Laptop backend on the local network**, phone on the same wifi, `apiBaseUrl` set to the laptop's
   LAN address.
4. **Pre-recorded video.** Shot in advance regardless; the submission needs it anyway.

## Bring the backend up from nothing

```bash
cd services/api
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export GROUNDWORK_DATABASE_URL=postgresql://localhost/groundwork_dev
python -m app.db.migrate
python -m scripts.import_gis --all       # hazard layers, ~10 minutes
export GROUNDWORK_DETECTOR_WEIGHTS=/path/to/best.pt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

In a second terminal:

```bash
python -m app.inference.worker
```

Check it is alive: `curl http://127.0.0.1:8000/v1/health` should report `status: ok` and name the
rulebook version.

## Things that will go wrong, and what they look like

| Symptom | Cause | What to do |
|---|---|---|
| Startup dies naming a rulebook | `GROUNDWORK_RULEBOOK_VERSION` points at a file that is not there | Set it to a version in `rulebooks/`, or unset it for the default |
| Startup dies on a permission error | Photo storage directory not writable | `mkdir -p var/photos`, or set `GROUNDWORK_PHOTO_STORAGE_ROOT` somewhere writable |
| Every zone comes back "Not determined" | GIS layers not imported, or import half-finished | `python -m scripts.import_gis --all`; an interrupted import leaves the previous version active, so re-running is safe |
| Photos upload but no findings appear | The inference worker is not running, or no weights configured | Start the worker. With no weights, jobs **fail** rather than returning nothing — check `inference_jobs.error` |
| Scan works, plan is empty | Nothing triggered a rule — a genuinely clean property scores 100 | Use the staged-hazard property for the demo |
| App cannot reach the API | `apiBaseUrl` still on 127.0.0.1 while running on a phone | Point it at the tunnel or LAN address and restart the bundler |

## Demo path that always works

The checklist alone produces a complete plan without the model, because every rule is triggerable by
a question. If inference is down, walk the checklist and the score, findings, and plan all still
work. Say so out loud rather than hiding it — the model being advisory is a design decision, not an
excuse.

## Before the video

- [ ] Re-verify Zone 0 adoption status at bof.fire.ca.gov and update the rulebook if it has been
      adopted
- [ ] Re-verify every rebate rate and cap in `services/api/programs/rebates.json`
- [ ] Re-run `python -m scripts.import_gis --all --dry-run` and confirm feature counts are sane
- [ ] Re-check every URL in `programs/resources.json` still resolves
- [ ] Confirm `ml/METRICS.md` reflects the model actually shipped
- [ ] Delete-account tested once on a throwaway account, files confirmed gone
