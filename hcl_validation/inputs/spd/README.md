# inputs/spd — your spectral power distributions

> **Drop-and-run:** just copy a `<name>.spd` into this folder — it's auto-discovered by extension
> (no JSON editing). Filenames with `led/lamp/lum/3000k/4000k/5000k` are treated as the **luminaire**
> spectrum, others as the **daylight/surface** spectrum; one file is used for both roles. If both a
> sample and your file are present, yours wins. (Rules: `../active_inputs.json` → `_resolution`.)

## What to drop here
Plain-text **SPD** files: light-source spectra (lamps, daylight references) and/or measured surface spectra.

## Format (strict)
- **Two columns per line:** `wavelength_nm  value`. Delimiter may be space, tab, or comma.
- Comment / non-numeric lines are tolerated and skipped.
- Only **380–780 nm** is used; the parser resamples to a **1 nm grid** (401 points) by linear interpolation.
- **Relative SPD is fine** for ratio metrics (mel-DER, CCT, mel/photopic). **Absolute** (W·m⁻²·nm⁻¹) is
  needed only if you want absolute mel-EDI / lux *directly from the SPD* (a peak ≤ 1.5 triggers a
  `scale_warning` telling you it looks relative).

## Passing it to the tools
The MCP `spd` argument accepts **either a file path or the file contents** — pass `inputs/spd/my_lamp.spd`
directly (the tool reads it from disk, same as `ies`, `epw`, `wea`, the `.obj`, and `.pts` inputs), or paste
the rows as text. Inline rows always contain newlines, so a bare path is unambiguous; a path that doesn't
exist is parsed as text and yields a clear "no wavelength rows" error. A list of `[wavelength, value]` pairs
also works. For standard illuminants you don't need a file at all — use the `presets` tool (`D65`, `D50`,
`A`, `FL1..FL12`, plus illustrative LED models).

## Where to get one
Spectroradiometer measurement, manufacturer LED/lamp datasheets, or CIE illuminants via `presets`.

## How to bring your own
1. Copy your file here, e.g. `inputs/spd/my_lamp.spd`.
2. Set `"spd_luminaire"` (or `"spd_daylight"`) in `inputs/active_inputs.json` to its path.

## Provided (three measured tunable-white spectra — a comparison set)
Proxy SPDs (PhotoLED, EMPIR 15SIB07, CC BY 4.0) matching the three `../luminaires/L09_*.ies` CCTs — relative
power, 1 nm grid. Same fixture, different colour → the spectrum behind Scenarios S2/S3 in GUIDE.md Part 4.5:

- `L09_warm.spd` — ~2700 K (PhotoLED S130).
- `L09_neutral.spd` — ~4000 K (PhotoLED S982).  *(the base default)*
- `L09_cool.spd` — ~6500 K (PhotoLED S1402).

(These ship with a comment header line + a `wavelength_nm,relative_power` row, which the parser skips — only
the numeric rows are read. They were renamed from `.csv` to `.spd` so the auto-discovery glob finds them.)
