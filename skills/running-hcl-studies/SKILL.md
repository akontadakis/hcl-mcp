---
name: running-hcl-studies
description: Use when running daylight, melanopic, circadian, or Radiance simulations through the hcl-mcp tools — daylight factor, sDA/ASE, annual daylight, mel-EDI, nvRD, spectral sky from EPW, glare/UGR, IES luminaires, or lighting-control savings. Covers tool ordering, the absolute-path rule, which quantity to report, and how to read the `advisories` field. Not for developing the hcl-mcp codebase itself.
---

# Running hcl-mcp studies

## The ladder

1. **Geometry** — `import_geometry` (or `check_geometry` first: no binaries, no scene, cheap to re-run). Read the health report before anything else: `check_geometry` returns it at the top level (`ok`, `counts`, `findings`, `skipped`), `import_geometry` embeds the same report under `result["health"]`. `skipped` categories are not clean ones.
2. **Sensors** — `workplane_grid` (EN 12464-1), `observer_points` (eye positions), `photosensors` (daylight-dimming zones), or `sensors` to save a named reusable set.
3. **Sky** — `import_weather`, then `colored_sky` / `spectral_sky_from_epw` / `spectral_sky_native`.
4. **Run** — `run_grid`, `run_annual`, `annual_daylight`, `lm83_daylight`, `annual_nvrd`, `daylight_savings`.
5. **Report** — see below.

### sDA and ASE: which tool

`annual_daylight` computes the *arithmetic* of sDA/ASE on whatever shading the scene
contains. `lm83_daylight` runs LM-83-12's *method*: a three-phase engine per window group
with an hourly blind that closes on §2.2.6's direct-sun trigger, and a blinds-retracted
zero-bounce ASE pass. Ask for LM-83 sDA/ASE and you want `lm83_daylight`; `annual_daylight`
reports `sDA_basis.lm83_conformant: false` unless the caller asserts a shading model no code
path can produce.

Neither is a submission on its own: `lm83_daylight`'s `lm83_method_conformant` is **always
false**, because §2.2.8–§2.2.11's model-input clauses (dirt depreciation, frame occlusion,
reveals, obstructions, interior reflectance, furniture) are out of scope. Glazing runs at its
raw `tvis`, which biases sDA upward. Read `metrics.conditions.departures` before quoting.

## Paths

Every file-shaped argument resolves against the server's working directory, not your shell's.
Pass absolute paths. A relative path usually surfaces as a misleading parse error, not a
file-not-found — check the path before debugging the file.

## What to report

- **mel-EDI (`mel_edi`)**, never `melanopic_lux`. They differ by ~1.0997x on the 9-bin
  route and every standard is written in mel-EDI.
- mel-DER is reported **at the point**, never at the lamp. Check `mel_der_source`:
  `spd_transported` keeps the source spectrum's within-bin detail and recovers the per-bin
  transport from the channels; `binned_channels` is inferred from the channel averages alone
  and can run ~8% high on narrow-band sources.
- On `spd_transported` results, `source_mel_der` is the luminaire's own figure and
  `transport_ratio` is the shift the room imposed. A datasheet quotes the source value; do
  not "correct" `mel_der` toward it.
- On an `electric` block, read `lumen_bound` before quoting anything: `mean_lux` above
  `ceiling_lux` means the block counts light the luminaires never emitted (classically, a sky
  that reached the electric-only octree). Pass `sky_files=` to `run_grid` to name skies exactly.
- Never report a substituted default as a measured value. Provenance ranks
  `override` > `epw` > `default`.
- Radiance polygons are two-sided — a normal pointing "the wrong way" is not a defect.

## Advisories

Any dict-shaped result may carry `advisories`: a list of `{code, severity, message, field?}`.

| severity | meaning |
|---|---|
| `error` | the result is probably not usable as-is |
| `warn` | usable, but easy to misreport |
| `info` | a default worth confirming |

Tools returning a LIST rather than a dict carry no advisories. The only one is
`circadian_metrics` with multi-point input — inspect `mel_der_source` per point there.

Current codes: `MEL_DER_BINNED`, `SPECTRAL_TRANSPORT_SHIFT`, `ELECTRIC_EXCEEDS_LUMEN_BOUND`,
`ALBEDO_NOT_MEASURED`, `DOSE_THRESHOLD_IS_DEFAULT`, `ZONE_WEIGHT_REMAINDER`,
`GEOMETRY_HEALTH_UNCLEAN`, `NVRD_ZERO_DIVERGENCE`, `RADIANCE_DROPS_IES_CANDELA_SCALE`
(error — the Radiance build dropped the ies2rad A1 candela scale; electric numbers are per-luminaire
low and must be RE-RUN with `HCL_RADIANCE_SHIM=1`, never rescaled).

An absent `advisories` key means no rule fired. It does not mean the model is right.

## Going deeper

- Method and validated error bounds: `docs/hcl-methodology.md`
- Operating the tools end to end: `docs/operating-guide.md`
- Decisions and their rationale: `docs/adr/`
