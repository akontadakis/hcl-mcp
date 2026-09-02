# physical_sky live-validation — run report

Branch `feat/physical-sky-live-validation`. This closes out the plan whose goal was to take the
`annual_nvrd(physical_sky=True)` Daysim/DDS flip from "correct-by-construction + unit-tested" to
**first live execution against real Daysim + Radiance binaries**. This is a **first live execution,
not a measured-spectra baseline** — nothing here was checked against measured sky spectra.

## What ran

Scene: `office_room` (built-in test geometry). Weather: `GRC_Athens.167160_IWEC.epw`. Channels: 3.
Engines: real Daysim `ds_shortterm` + Radiance 6.1a (not mocked, not capability-skipped). Driver:
`scripts/physical_sky_live/run_physical_sky_live.py` (+ `run_physical_sky_live.sh` wrapper).

Two phases were executed, both with `physical_sky=True` on the production `annual_nvrd` path
(`_channel_provider=None` — the real seam, not a monkeypatch):

### Phase A — coarse proof run

From `out/phaseA_coarse.summary.json`:

| field | value |
|---|---|
| `ran` | `true` |
| `n_timesteps` | 35040 (15-min timestep) |
| `coverage.n_physical` | 17532 |
| `coverage.n_template` | 17508 |
| `coverage.coverage_pct` | 50.034246575342465 |
| `has_enhanced_solar_note` | `false` |
| `rd_series_divergence.mean_abs` | 0.0012477116669189475 |
| `rd_series_divergence.max_abs` | 0.03371785690061546 |
| `rd_series_divergence.final_cum_pct` | 0.27368798556468593 |
| `wall_clock_s` | 283.9 (≈4.73 min) |
| `rad_params` | `-ab 1 -ad 256 -aa 0.2 -ar 32` |

### Phase B — representative run at default ambient parameters

From `out/phaseB_default.summary.json`:

| field | value |
|---|---|
| `ran` | `true` |
| `n_timesteps` | 87600 (6-min timestep) |
| `coverage.n_physical` | 43830 |
| `coverage.n_template` | 43770 |
| `coverage.coverage_pct` | 50.034246575342465 |
| `has_enhanced_solar_note` | `false` |
| `rd_series_divergence.mean_abs` | 0.0010810387288447704 |
| `rd_series_divergence.max_abs` | 0.03405121605416217 |
| `rd_series_divergence.final_cum_pct` | 0.2388224805523978 |
| `wall_clock_s` | 458.4 (≈7.64 min) |
| `rad_params` | `-ab 2 -ad 512 -aa 0.1 -ar 64` (tool default) |

**Phase-B run-vs-skip decision:** Phase B was RUN, not skipped. The plan's gate was "run Phase B
only if Phase A wall-clock ≤ 15 min"; Phase A's captured `wall_clock_s` (283.9 s ≈ 4.73 min) is well
under that gate, so Phase B proceeded at the tool's default (finer) ambient parameters and a finer
6-min timestep.

## Coverage interpretation

`coverage_pct` is **50.034246575342465%** in both phases — identical because both scenes/weather
files/years are the same and coverage is a daylight-vs-night split, not a simulation-quality knob.
This is the **fraction of timesteps that received the physical EPW-derived sky/sun spectral shape**
(`n_physical`), with the remainder (`n_template`, night / zero-irradiance timesteps) legitimately
falling back to the reference-sky/air-mass-sun template by design — there is no daylight to
physically reconstruct at night. **This is not a defect and not "half the coverage failed"** — it is
the expected daylight-fraction split for a full annual run at this latitude, and it is consistent
between the 15-min (17532/35040 physical) and 6-min (43830/87600 physical) timestep runs.

## Sun time-resolution

`has_enhanced_solar_note` is **`false`** in both phase summaries. This field is set when the
constant-30°-zenith colored-sun fallback fires (i.e. per-timestep solar zeniths were unavailable).
Its absence across both the 35,040-step and 87,600-step runs means the Daysim sub-hourly adapter
supplied real per-timestep solar zeniths throughout — the air-mass reddening was **time-resolved**,
not the constant-30° fallback, in this live production-path execution.

## Full-suite regression gate

```
python3 -m pytest -q
```

Result: **1341 passed, 7 skipped, 0 failed** (20 warnings, all pre-existing `colour`-library
`ColourRuntimeWarning`s unrelated to this branch). The only shipped-code change on this branch is
Task 4's one-line note reword in `src/hcl_radiance/annual_nvrd.py` (commit `cf54175`), covered by
its companion assertion added to `tests/test_annual_nvrd.py`, and it is green in this run.

## Doc changes (Task 5, commit `817938a`)

```
docs: physical_sky flip caveats updated to first-live-execution (evidence-backed)

 README.md                     |  6 +++---
 docs/spectral-sky-as-built.md | 37 ++++++++++++++++++++++++-------------
 2 files changed, 27 insertions(+), 16 deletions(-)
```

`README.md` — two caveat passages reworded from "wired-but-unexercised" / "never executed against a
real binary" to cite the 2026-07-18 first live execution (physical-spectral-sky feature bullet near
the top of the file, and the "Physical spectral-sky pipeline" caveat block under
`## Validation & Accuracy Caveats`), plus the separate constant-30°-zenith bullet softened to
describe a conditional fallback (fires only when solar zeniths are unavailable) rather than a
blanket "constant-zenith in production" claim.

`docs/spectral-sky-as-built.md` — six locations updated: the Phase-implementation status table row
for "Live-DDS physical-sky flip" (was "NOT live-validated", now cites the 2026-07-18 execution +
50.03% coverage + time-resolved sun); the `physical_sky` docstring-adjacent prose describing the
`note` field (now scoped to "describes THIS run's transport," not a global claim, with a pointer to
§3septies); the §3septies live-wiring narrative (D-16/D-17 downgrade discussion) updated with a
"2026-07-18" execution paragraph; the D-16/D-17/D-23 phase-summary paragraph near the SMARTS/native-
Radiance summary; and two "Known Limitations"-style paragraphs (one enumerating what's still
"never-run-live", one closing out the "remaining external-path gap") both updated to record the
first live execution while explicitly preserving the still-open, still-unverified `.wea` hour-
convention assumption (D-23) — the live runs exercised coverage/timing, not that assumption.

## Honest scope note

This is a **first live execution** of the `physical_sky` Daysim/DDS flip against real binaries,
proving the seam runs end-to-end on real Daysim + Radiance output and produces sane coverage/
divergence numbers. It is **not** a calibrated baseline against measured sky spectra, and it does
not touch or resolve the still-open `.wea` hour-convention caveat (D-23), which neither phase
exercised.
