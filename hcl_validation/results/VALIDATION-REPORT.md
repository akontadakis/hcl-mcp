# Validation report — post-reconnect live run

**Date:** 2026-08-06 · **Server:** hcl-mcp, reconnected on the current tree
**Engines:** Radiance 6.1a (`/usr/local/radiance/bin`) LIVE · Daysim (`/usr/local/daysim/bin`) LIVE
**Model:** `office_room.obj` (4.3 × 7.3 × 3.4 m, single south window, aperture 4.86 m²)
**Sky:** `GRC_Athens.167160_IWEC.epw`

This run's purpose was to confirm, over MCP, the fixes made while the previous server
process held stale code. Every one is verified live below.

## Fixes confirmed live

| Fix | Before | Now |
|---|---|---|
| `colored_sky` missing irradiance | `no solar RGB line ('3 R G B') found in gendaylit output` — blamed the parser | names the missing `direct`/`diffuse` and the channels-vs-magnitudes distinction |
| SPD scale warning | told users a genuinely absolute Athens SPD's EDIs were "shape indicators, not lux-scale EDIs" | reports the scale as INDETERMINATE; mel-EDI **7740 lx** returned as a usable value |
| negative zone weight | `weights=[-0.075, 1.075]` → **−18.7 W consumed, 107.5 % saved** | rejected, naming the weight and the geometric cause |

## Workflow results

| ID | Workflow | Result |
|---|---|---|
| W0 | `validate` self-test | **PASS** — `ok:true`; the single `passed:false` is the by-design `channel_vs_spd_alpha_opic` check (non-gating, documented) |
| W0 | `radiance_status` / `daysim_status` | **PASS** — both available, 0 missing binaries |
| W2 | `import_geometry` (+ derived sensors) | **PASS** — 84 grid points (0 dropped), 16 observers at 1.2/1.6 m, 4 luminaires placed, `health.ok:true` |
| W3 | `daylight_factor` (45-pt grid, CIE overcast) | **PASS** — df_avg **3.51 %**, df_min 0.28 %, df_max 16.42 %, uniformity 0.080, e_outdoor 18145 lx |
| W7 | `spectral_sky_from_epw` (Jun 21 12:00) | **PASS** — 401-pt 1 nm spectra, Kt 0.640, zenith 18.8°, CCM `fig11-faithful` |
| W7 | `spectral_sky_from_epw` (Dec 21 09:00) | **PASS** — winter overcast edge case: Kt 0.292, zenith 82.3°, air mass 7.1; spectra positive, bridge residuals ~1e-15 |
| W3 | `colored_sky` + `run_grid` (9-channel) | **PASS** — eye-level **mel-EDI 551.3 lx**, photopic 508.5 lx, mel-DER 1.084 |
| W5 | `lighting_controls` (3-zone gradient) | **PASS** — 75.7 W consumed, 174.3 W saved, 69.7 % reduction; power rises monotonically as illuminance falls |

## Notes on the numbers

- **DF** 3.51 % here vs 3.49 % pre-reconnect vs 3.53 % in the docs: Radiance stochastic sampling on
  the same 45-point grid. The kit asserts BEHAVIOUR (`df_min ≤ df_avg`, DF falling with distance
  from the window), and all of it holds.
- **mel-EDI 551.3** vs 547.5 pre-reconnect: same, within sampling noise. Quote `mel_edi`, never
  `melanopic_lux` (606.2 here — 10 % higher, and not the quantity any standard is written in).
- `mel_der_source` is `binned_channels` on the daylit eye, which the tool labels itself; that route
  is ~0.1 % on daylight.

## Advisories seen (all correct)

- `GEOMETRY_HEALTH_UNCLEAN` — `NOT_ENCLOSED`, 20 boundary edges on the glazing/luminaire groups.
  Expected for inset surfaces in this model; `health.ok` is still true.
- `ALBEDO_NOT_MEASURED` — the Athens EPW writes a `0.000` placeholder in the albedo field, so the
  documented ρ = 0.20 default is substituted. Fires on both spectral-sky calls, as designed.

## Not exercised

W4 glare, W6/W8 annual (`run_annual`, `annual_nvrd`, Daysim path), W9 studio, and the
negative/cross-tool/prompt sections. Nothing blocked them — this run was scoped to confirming the
fixes plus the core daylight and melanopic chain.
