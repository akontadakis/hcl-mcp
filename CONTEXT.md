# CONTEXT

Orientation for anyone — human or agent — working in this repo. Read this before changing physics.

## What this is

`hcl-mcp` exposes a spectral / human-centric-lighting toolkit as an MCP server: sky and luminaire
spectra, CIE S 026 alpha-opic metrics, Radiance-driven daylight simulation, and circadian compliance
scoring. It derives from Lark Spectral Lighting; the BSD attribution in `THIRD-PARTY-NOTICES.md` and
the "port of Lark" provenance must stay.

## Layers — the boundary is load-bearing

| Layer | Package | Rule |
|---|---|---|
| Pure math | `hcl_core` | Never imports the layers above; no Radiance command knowledge. Testable with no binaries — every binary path is capability-gated. Two audited exceptions to "no subprocesses": the generic step-runner `proc.py` (the single implementation behind `hcl_radiance.runner.run_sequence`) and the opt-in SMARTS oracle (`spectral_engine/smarts.py`, gated on `$SMARTSPATH`). Text formats the physics itself is defined on (SPD, IES LM-63, EPW, Klems XML) are parsed here. |
| Adapter | `hcl_radiance`, `hcl_daysim` | Builds commands, parses outputs. Owns all engine knowledge. |
| Protocol | `hcl_mcp` | Thin. Argument plumbing, docstrings, and result-side advisories; no physics. |

`hcl_platform` holds OS/path/exe helpers. Physics that leaks upward into `hcl_mcp`, or Radiance
knowledge that leaks down into `hcl_core`, is a defect regardless of whether tests pass — the
import direction is enforced by `tests/test_module_layering.py`, which fails the suite on any
import above a module's layer.

## Domain traps that have each cost real debugging time

- **`melanopic_lux` is NOT mel-EDI.** It is larger by D65's own melanopic/photopic ratio (~1.0997 on
  the 9-bin route). Every circadian standard is written in mel-EDI, so substituting one silently
  relaxes the threshold. Use `mel_edi`; `mel_der_source` records whether it came from a full SPD
  (`spd_transported`) or binned channels alone (`binned_channels`, approximate).
- **mel-DER belongs to the point, not the lamp.** A source SPD is exact only where the source IS
  the point. After light crosses a spectrally selective surface the source figure is wrong by the
  size of the spectral shift (measured up to 12.7%), and the "exact" label makes it look more
  trustworthy than the approximate route it beats only at the source. See ADR-0006.
- **An "electric-only" octree is only as good as its sky detection.** Basename heuristics leak;
  a sky named for its condition rather than the word "sky" put daylight into an electric result
  (1662 lx reported as 17705 lx). Detect by content, and bound the answer by
  sum(lumens)/area — the bound is free and catches the whole class. See ADR-0007.
- **Radiance polygons are TWO-SIDED.** A face normal pointing "the wrong way" is not a physics
  defect and must never be reported as one.
- **Native `.smx` spectral bands are stored DESCENDING** (red -> blue). Reverse before use. Relatedly,
  `rcomb -c M` yields EML, ~1.081x mel-EDI — pass explicit numeric coefficients instead.
- **Every geometry tolerance is absolute metres.** Anything comparing a length or area against a
  constant must receive the model's unit scale, or it breaks both ways: missing real defects in a
  millimetre model *and* hard-failing valid geometry.
- **A floor's bounding box is not its footprint.** On a concave (L/T/U) plan the extent covers the
  notch, which is open exterior — points there read HIGH and inflate sDA/ASE. Clip to
  `footprint.floor_polygons`.
- **EPW "no data" is not always the documented sentinel.** IWEC/TMY2 write a literal `0.000` albedo
  for every hour instead of `999.0`. Sub-physical values are missing data, not measurements.
- **A sample's duration is its own timestep**, never the gap to the next sample. Analysis periods are
  gapped (daylit hours only, and `weather.decompose` repeats a window across months), so a forward
  difference charges one sample the whole night — or the whole inter-month gap.
- **MCP tool params that take a list or dict need an explicit annotation.** An untyped parameter gets
  stringified or emits an empty schema.

## Advisories — the traps above, raised automatically

Most of the traps in this list are silent-wrong-number failures, so several are now also surfaced on
the result itself. `hcl_mcp/advisories.py` holds nine pure rules; every dict-shaped tool result may
carry an `advisories` list of `{code, severity, message, field?}`, absent entirely when nothing fires.

This does **not** breach the layer rule above. A rule reads a field `hcl_core` already computed and
phrases a caution about it — that is reporting, not physics. A rule that recomputes a physical
quantity, reads a file, or shells out is a defect. Add new rules there, with one test proving the
rule fires and one proving it stays silent on a clean result, and build the fixtures from the real
producer rather than by hand: `GEOMETRY_HEALTH_UNCLEAN` shipped broken because both its tests used a
`skipped` shape production never emits. See `docs/adr/0005-advisories-attach-at-the-registration-seam.md`.

## Provenance discipline

Every atmospheric and photometric constant carries a source: `override` > measured/`epw` > documented
`default`. A value the code substituted must never be reported as one an instrument measured — the
provenance is part of the result, not decoration. Approximations are labelled with their measured
error (see `docs/hcl-methodology.md`).

## Working here

- Tests: `PYTHONPATH=src .venv/bin/python -m pytest -q` (no `timeout` on macOS — it is not installed).
- Green tests are necessary, not sufficient: every defect found in the 2026-07-25 review passed the
  suite. The gaps were all *boundary* cases the tests never reached.
- Live Radiance/Daysim runs are gated behind env vars and skip cleanly when absent.
- ADR conventions: `docs/adr/`. Issue-tracking and triage-label notes moved out of the
  published repo (2026-08-10) and now live at `../_data/docs/agents/`.
