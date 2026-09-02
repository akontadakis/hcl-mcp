# inputs/luminaires — your photometry

> **Drop-and-run:** just copy a `<name>.ies` into this folder — it's auto-discovered by extension
> (no JSON editing). If both a sample and your file are present, yours wins. (Auto-discovery rules:
> `../active_inputs.json` → `_resolution`.)

## What to drop here
**IESNA LM-63** photometry files (`.ies`) for your fixtures. The IES carries geometry + intensity only — it
has **no color**. To make a luminaire spectral you pair it with an SPD (see below).

## Format
IESNA LM-63-1995 / 2002 text. Used by:
- `ies_analyze` → photometric report (lumens, watts, efficacy, beam/field, zonal flux)
- `ies_to_radiance` → `ies2rad` → a Radiance `.rad` you can place in the scene

## Pairing an SPD with the IES (to get circadian metrics from electric light)
- After `ies_to_radiance`, inject a 9-channel SPD triplet with `colored_luminaire(rad_path, channels9, count)`.
- Or, in `material_map.json`, give a `type:"luminaire"` group both `"ies"` and `"spd"` — the importer emits a
  drop-in `electric_lights` payload for `run_grid` / `run_image` / `glare_ugr`.

## Where to get one
Manufacturer product pages (download `.ies`), or lighting databases. Grab the lamp's SPD from the datasheet.

## How to bring your own
1. Copy your file here, e.g. `inputs/luminaires/my_troffer.ies`.
2. Set `"ies": "luminaires/my_troffer.ies"` in `inputs/active_inputs.json`.
3. (Optional) put the lamp SPD in `inputs/spd/` and reference it as `spd_luminaire`.

## Provided (one tunable-white fixture, three CCTs — a comparison set)
The **same** real luminaire — a Glamox C95-R600×600 LED 4800 (LM-63-1995) — at three colour temperatures,
each with a **matching measured SPD** in `../spd/`. Same photometry, different colour → isolates CCT's effect
on the body clock. See GUIDE.md **Part 4.5, Scenarios S2/S3**:

- `L09_warm.ies` — 2700 K (4467 lm)  ·  pair with `../spd/L09_warm.spd`
- `L09_neutral.ies` — 4000 K  ·  pair with `../spd/L09_neutral.spd`  *(the base default)*
- `L09_cool.ies` — 6500 K (4702 lm)  ·  pair with `../spd/L09_cool.spd`
