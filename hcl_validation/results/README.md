# results/ — validation outputs, one folder per workflow

This folder is written by the **hcl-mcp-tester** agent (or by you, following
[TEST-PLAN.md](../TEST-PLAN.md)). It is **structured so you can review the outputs of each workflow on its
own** — not one flat pile of files.

## Layout

```
results/
├── VALIDATION-REPORT.md     ← START HERE. Top-level roll-up: capability banner, resolved inputs,
│                              the full results matrix, coverage, defects, verdict. Every row links
│                              into the section folder below that produced it.
├── W0-orientation/          ← self-test (validate, radiance_status, daysim_status, reference)
├── W1-spectral/             ← spectral analysis of one SPD (prompt spd_to_circadian)
├── W2-geometry/             ← OBJ import + sensor/observer/photosensor grids + scene preview
├── W3-grid/                 ← point-in-time daylight grid (prompt hcl_grid_study)
├── W4-glare/                ← fisheye eye image & glare (prompt fisheye_eye_analysis)
├── W5-electric/             ← electric lighting design + energy (prompt electric_lighting_design)
├── W6-annual/               ← annual circadian dose (prompt annual_circadian_dose)
├── W7-spectral-sky/         ← physical spectral sky from EPW (prompt spectral_sky_from_epw)
├── W8-daysim-nvrd/          ← annual alertness / nvRD, Daysim path (prompt annual_alertness)
├── W9-studio/               ← study brief & report glue (prompt hcl_studio)
├── N-negative/              ← negative / edge / expected-error cases
├── X-cross-tool/            ← cross-tool consistency checks
├── S-workflows/             ← full workflow chains (S1 blinds A/B, S5 studio end-to-end)
├── E-energy/                ← energy & daylight-responsive controls
├── G-arguments/             ← argument / mode / error-path depth coverage
├── prompts/                 ← rendered prompt-text checks (RESULTS.md only)
└── resources/               ← resource reads (RESULTS.md only)
```

## What's inside each `<SEC>/` folder

| File / dir | What it is |
|------------|------------|
| **`RESULTS.md`** | The reviewable output: the **actual metric values** observed (mel-EDI, photopic lux, UGR, DGP, CCT, kWh tables — or the `{ran:false, commands[]}` emit plan) with the pass/fail verdict for every test in that workflow. |
| **headline data at the top** | The workflow's final data artifacts: `grid.csv`, glare `*.hdr` maps + `rgb.txt`, the room `manifest.json` + `*.pts` + `preview_*.png`, the studio `report.md`/`report.html`, `dosimetry.json`, … |
| **`work/`** | Intermediate & engine files — Radiance `.rad`/`.oct`/`.hdr`, `.cal`/scripts, `.pts`, `.wea`, `.smx`, logs. Open only when you want to inspect *how* a number was produced. |

`prompts/` and `resources/` run no simulation, so they hold a `RESULTS.md` only (no `work/`).

## Scoring key (used in every `RESULTS.md`)

- **PASS** — ran; output present and within the Assert bounds.
- **PASS(emit)** — returned `{ran:false, commands[]}` because a simulation engine is absent. This is the
  correct, capability-gated result, **not** a failure.
- **PARTIAL** — ran, keys present, but a value is off.
- **FAIL** — error / missing keys / wrong typed failure on a negative case.
- **BLOCKED** — couldn't attempt (says why).
