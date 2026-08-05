# Congressional App Challenge submission status

CA-10 (Rep. Mark DeSaulnier). Deadline **Oct 26, 2026, 9:00 AM PT**; our own target is to submit by
**Oct 23**.

## Eligibility and admin — not started, and only you can do these

- [ ] Both teammates enrolled in MS/HS on Oct 26, 2026
- [ ] Live or attend school in CA-10; at least half the team in-district
- [ ] Registration with personal emails; eligibility quiz completed
- [ ] Post-deadline exit questionnaire (both members)

## Code and disclosure — done

- [x] All code written after Oct 30, 2025 (this repository starts Aug 4, 2026)
- [x] Libraries documented in [CREDITS.md](../CREDITS.md)
- [x] AI-assisted development disclosed in CREDITS.md
- [x] Trained-model work documented as ours: taxonomy, labeling guide, dataset tooling, training
      and evaluation scripts all in [`ml/`](../ml/)
- [ ] **Commit attribution.** History is currently authored by one Git identity. If both teammates
      should appear as authors, that needs configuring — see the open questions below.

## App — buildable and testable now

- [x] Source runnable on demand: [README](../README.md) for setup, [RUNBOOK](RUNBOOK.md) for demo day
- [x] CI proves the API lints, tests against real PostGIS, builds a container, and that the
      container boots; the mobile app typechecks and bundles
- [ ] Expo dev build or TestFlight installed on the devices used for the video

## Blocked on work only you can do

| What | Why it is blocked | Roughly how long |
|---|---|---|
| 1,500–3,000 labeled photographs | Requires physically photographing properties | The Aug–Sep collection sprint in the BRD |
| Trained model + published metrics | Needs the dataset | A day of GPU time once labeled |
| Fire district / water utility boundaries | Not in Contra Costa's public ArcGIS folders | Ask the county GIS office directly |
| Plant palette content | WUCOLS bulk download, and CNPS permission for Calscape | Email CNPS early — their reply doubles as validation |
| 30+ real assessments | Needs testers | Sep–Oct recruiting push |
| Letter or quote from a local agency | Outreach | Start now; agencies are slow |
| Video (1–3 min, public) | Needs a working demo and the above | Week of Oct 13 |
| Written answers | Purpose, inspiration, technical difficulty, learnings, 2.0 | Week of Oct 13 |

## Written answers — source material already in the repository

- **Technical difficulty.** The determinism boundary ([D4](DECISIONS.md)) and why the score,
  rebate, and area math never touch model output. The leakage guards in `ml/tests/` and why
  split-by-property is a correctness property rather than a nicety.
- **Learnings.** Row-level security not applying to superusers — the isolation tests would have
  passed while proving nothing. The container that built fine and died on startup, which is why CI
  now boots it.
- **Inspiration.** Feb 2025 hazard maps redrawing 12 Contra Costa cities; the July 2026 Morgan Fire.
- **2.0.** Air-quality module and on-device inference, both deliberately out of scope for v1.

## What is honest to claim, and what is not

**Can claim:** first consumer photo-based defensible-space tool we could find; a self-collected and
self-labeled dataset with a taxonomy written before labeling; a deterministic rules engine with
published citations; rebate math that is exact and caveated.

**Cannot claim** until it is true: any accuracy number (no model trained yet), that Zone 0 is law
(it is a draft, and every rule derived from it says so), that the report certifies anything, or that
any rebate is guaranteed.
