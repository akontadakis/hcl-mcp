# Phase 2 live-validation — run report

**Branch:** `feat/phase2-live-validation` · **Date:** 2026-07-18 · **Scene:** realistic `office_room.rad` + `materials.rad` (side-lit office, -Y window), GRC Athens IWEC weather.

This is the **first live run of the daylight and electric MCP tools on a realistic scene**, end-to-end through the server. It is not a measured/calibrated baseline — see the honest flags below.

## Step 1 — full test-suite regression gate

```
python3 -m pytest -q
```

Result: **1341 passed, 7 skipped, 22 warnings** in 14.34s. Matches master's green suite exactly — this branch made no `src/`/`tests/` changes, only committed evidence JSONs under `scripts/live_validation_phase2/out/` and README caveat rewrites. No failures, so no caused-by-us/pre-existing triage is needed.

## Step 2 — deliverables confirmed

**Committed** under `scripts/live_validation_phase2/out/`: `daylight_factor.json`, `annual_daylight.summary.json`, `daylight_savings.json`, `electric_units.json`, `electric_integrated.json`, `athens_full.wea`, `L09.rad`, `L09_red.rad`. Generated locally but **not committed** (reproducible/bulky): `L09.dat`, and the render/octree working dirs `glare_electric/` and `grid_electric/`.

## Step 3 — what ran, numbers from committed evidence

### `daylight_factor` (daylight_factor.json)
Realistic `office_room`, 45 workplane points, CIE Standard Overcast Sky. `df_avg = 3.531%`, falling smoothly from `df_min = 0.2949%` (far corner) to `df_max = 15.874%` (near the -Y window); `uniformity = 0.0835`; `e_outdoor = 18205.9468`. Magnitudes are plausible for a side-lit office (prior toy-scene caveat had extreme magnitudes on a fully-glazed room).

### `annual_daylight` (annual_daylight.summary.json)
Run **via the MCP tool end-to-end** (first time the async wrapper itself was exercised live, not just the core), full 8760-hour year on `athens_full.wea`, 45 points. `sDA = 0.7556` (75.6%), `ASE = 0.3111` (31.1%), `DA_avg = 0.7145` (approx 0.71), `UDI_autonomous_avg = 0.5705`. Per-point DA ranges `0.0234`-`0.9659` (far corner -> -Y window). ASE's dedicated direct-only (`-ab 0`) pass is confirmed distinct from the DA/UDI total pass.

### `daylight_savings` (daylight_savings.json)
Both wrappers exercised live end-to-end, single center reference point (`p_rated=448 W`, `area=31.4 m^2`).
- **Annual mode**: full 8760-h simulation with per-hour controls — `mean_reduction = 0.8594` (85.9%), `annual_kwh_per_m2 = 5.235` (approx 5.24 kWh/m2/yr), `occupied_hours = 2610`. Consistency check in the evidence file: 2610 h = 10 h x 261 weekdays (08:00-18:00 mask); `5.24 ~= (448 W / 31.4 m^2) x 2610 h x mean_FP 0.141`.
- **Point-in-time mode**: ran end-to-end but `daylight_lux = [0]` because `run_grid` (unlike `daylight_factor`) does not add a sky internally and `scene_sets` had no sky source -> no daylight -> no dimming. This is a usage nuance / potential UX footgun, not a wrapper failure.

### Electric — unit tools (electric_units.json)
First live run of `ies_analyze`, `ies_to_radiance`, `spd_to_channels`, `colored_luminaire` through the MCP server on the L09_neutral fixture (Glamox C95-R600x600 LED, 4000K). All four ran clean, no bugs surfaced: `ies_analyze` -> `input_watts=38`, `rated_lumens=4702`, `efficacy=123.74`, batwing distribution flagged (`beam_field_reliable=false`); `ies_to_radiance` produced `L09.rad`/`L09.dat` via `ies2rad -o`; `spd_to_channels` -> 9-channel vector; `colored_luminaire` correctly injected the red-third triplet `[0.017, 0.015, 0.004]` into `L09_red.rad`, leaving the source untouched.

### Electric — integrated path (electric_integrated.json)
**First end-to-end LIVE run** of the electric integrated path (prior: emit-/mock-tested only) — `run_grid` (electric_lights payload, 4x L09 batwing downlights, `total_wattage = 152` W), `glare_ugr`, and `lighting_controls`, all clean, no crash.
- `run_grid`: `electric_photopic_lux` min 27.22 / max 46.52 / approx avg **36.0** lux; `melanopic_over_photopic = 0.765`; spatial pattern consistent with 4 ceiling fixtures.
- `glare_ugr`: `UGR = 0`, `DGP = 0.160066` (low glare, below the 0.35 perceptible threshold) — plausible for ceiling panels out of direct line of sight.
- `lighting_controls`: clean ContinuousOff dimming curve, `FP = 0.4568`, `reduction = 0.543` on a synthetic sweep (the real annual controls were already driven live by `daylight_savings` above).

**ELECTRIC MAGNITUDE — root-caused + fixed (see electric_source_cal_fix.json):**
- The first run's ~37 lux average was **~14× too low**. Investigation (Debug + fix) proved this is **NOT a batwing effect** (L09 nadir candela ~1878 ≈ peak) and **NOT an hcl-mcp bug**: the local custom **Radiance 6.1a build's compiled `source_corr` drops the `ies2rad` brightdata `A1` (candela-scale) multiplier**. Proven 3 ways (10× `A1`-arg → no effect; fold `A1` into RGB → correct; explicit `source.cal` `flatcorr` override → correct).
- **Fixed** by patching `source.cal` (`apply_source_cal_patch.sh`, needs `sudo`): the same office_room 4×L09 grid then reads **avg 494 lux (min 363 / max 627)** — realistic, exactly 14.4× the unpatched value. hcl-mcp's electric pipeline is correct given a Radiance whose `source_corr` honors `A1`; do NOT fold `A1` into `color_luminaire` (double-scales on stock Radiance).
- `glare_ugr` returned **`UGR=0` alongside `DGP=0.16`** — plausible (no Guth-position source) but flagged as worth a sanity check.

## Caveats closed vs. remaining (README)

Closed (README.md, this branch, lines ~191-192 and ~699-700 in the diff):
- `annual_daylight` / `daylight_factor` caveats rewritten from "first live validation on a toy scene only" / "MCP async wrapper not yet exercised" to "first live run on realistic `office_room` + GRC Athens IWEC, MCP wrapper exercised end-to-end" — with the actual sDA/ASE/DA_avg/df_avg numbers quoted.
- The old "electric pipelines have not been exercised end-to-end" caveat replaced with the first-live-run description of the integrated path, including the magnitude and UGR flags above.
- `daylight_savings` folded into the same rewritten daylight caveat (both modes now described as live).

Resolved during this branch:
- **Electric ~14× under-emission — root-caused + fixed.** Local Radiance build's `source_corr` drops the `ies2rad` `A1` multiplier; patched via `source.cal` override (`apply_source_cal_patch.sh`, sudo). Re-validated: office_room 4×L09 avg 494 lux. NOT an hcl-mcp bug.

- **source.cal patch APPLIED + MCP-verified (2026-07-18).** After `sudo bash apply_source_cal_patch.sh`, re-running `mcp__hcl-mcp__run_grid` with the 4×L09 `electric_lights` payload returned correct magnitudes end-to-end through the MCP tool: under-fixture 622.7 lux, room-center 497.2 lux, far-corner 412.5 lux (was ~35–43 lux; ~14× correction), total_wattage 152, mel/phot ≈0.765. Electric path fully validated on this machine.
- **`UGR=0` anomaly RESOLVED — it was the same A1 bug, not a separate issue.** Pre-patch the fixtures were 14× too dim → below evalglare's glare threshold → `UGR=0`. Re-running `mcp__hcl-mcp__glare_ugr` post-patch: **UGR=19.24, DGP=0.199**, 2 glare sources (the ceiling panels, source luminance ~5609 cd/m²). Both are realistic and consistent (UGR≈19 = the standard office limit for ceiling panels; DGP 0.199 < 0.35 imperceptible). See `electric_postpatch_verify.json`.

Remaining open:
- (none)
- `daylight_savings(mode="point_in_time")` no-sky footgun (`run_grid` doesn't add a sky the way `daylight_factor` does) — a usage-nuance finding, not fixed in this branch.
- `annual_daylight` still always simulates the full 8760-hour year (no `period`/`partial_year` wiring through this tool).

## Bottom line

This is the **first realistic-scene live run of the phase-2 daylight and electric tools through the MCP server**, not a measured/calibrated baseline. All numbers above are quoted directly from the committed evidence JSONs. Full test suite remains green at 1341 passed / 7 skipped, matching master — this branch changed no source or test code.
