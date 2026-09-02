# hcl-mcp end-to-end validation kit

Everything needed to test the hcl-mcp **through real chat tool-calls** — not scripts — from start to finish.

```
hcl_validation/
├── README.md                  ← you are here (orientation)
├── GUIDE.md                   ← ★ the detailed step-by-step: connect, run, BYO-data, drive every prompt
├── INPUT-DATA-CHECKLIST.md    ← Q1: complete list of input data for a full HCL run
├── TEST-PLAN.md               ← the ordered test matrix (every tool/prompt/resource)
├── inputs/                    ← input files; each subfolder has a README on what to drop in
│   ├── active_inputs.json     ← ★ selector: mostly "auto" — drop files by extension, no edit needed
│   ├── geometry/  office_room.obj/.mtl, office_room_blinds.obj/.mtl,
│   │              office_room_corner_window.obj/.mtl,
│   │              office_room_corner_window_blinds.obj/.mtl,
│   │              *_material_map.json (one per OBJ),
│   │              radiance/  ← hand-authored .rad scenes (materials.rad,
│   │                            luminaires_L09.rad, one <model>.rad each)  (+ README)
│   │              (all na=0, authored in true-north frame:
│   │               single window = south-facing; corner = south+west)
│   ├── weather/   GRC_Athens.167160_IWEC.epw                   (+ README)
│   │              (the .wea is derived on demand — not shipped)
│   ├── luminaires/ L09_cool.ies, L09_neutral.ies, L09_warm.ies (+ README)
│   ├── spd/       L09_cool.spd, L09_neutral.spd, L09_warm.spd  (+ README)
│   └── sensors/   office_room_grid.pts, observer_1.pts, observer_2.pts,
│                  sensor_1.pts, sensor_2.pts (single-window south model;
│                  regenerate for others; PNG previews no longer shipped)  (+ README)
└── results/                   ← created on first run; STRUCTURED one folder per workflow (see below)
    ├── VALIDATION-REPORT.md    ← top-level roll-up / index (links into each section)
    ├── W3-grid/                ← one folder per workflow; example expanded:
    │   ├── RESULTS.md          ← the actual metric values + PASS/FAIL per test
    │   ├── grid.csv            ← headline data at top (also *.hdr, manifest.json, report.html…)
    │   └── work/               ← intermediate/engine files (.rad .oct .pts .wea scripts logs)
    ├── W0-orientation/  W1-spectral/  W2-geometry/  W4-glare/  W5-electric/
    ├── W6-annual/  W7-spectral-sky/  W8-daysim-nvrd/  W9-studio/
    ├── N-negative/  X-cross-tool/  S-workflows/  E-energy/  G-arguments/
    ├── A-advisories/            ← the 6 advisory codes + 4 contract properties
    └── prompts/  resources/    ← RESULTS.md only (no simulation artifacts)
```
The validating agent lives at `../.claude/agents/hcl-mcp-tester.md`.

> **Server connection — you create it.** `../.mcp.json` is **git-ignored**, so a fresh clone has none: write
> it yourself from the config block in **[GUIDE.md](GUIDE.md) Part 1 / 1B** (same `command`/`args`/`env`
> for every client; only the filename differs). If the agent reports *"hcl-mcp server is not connected"*,
> this is the file it means.

### How results are organized (review outputs per workflow)
The agent writes **one folder per plan section** so you can open a single workflow and see everything it
produced, separated cleanly:

- **`<SEC>/RESULTS.md`** — the reviewable output: the **actual numbers** (mel-EDI / photopic / UGR / DGP /
  CCT / kWh tables, or the `{ran:false, commands[]}` emit plan) with the pass/fail verdict for each test.
- **`<SEC>/` top level** — the headline data files (`grid.csv`, `*.hdr` maps, `manifest.json`, the
  `hcl_studio` `report.md`/`report.html`, `preview_*.png`, `dosimetry.json`, …).
- **`<SEC>/work/`** — the intermediate/engine files (Radiance `.rad`/`.oct`/`.hdr`, `.cal`/scripts, `.pts`,
  `.wea`, `.smx`, logs) — the "temp" material you only open when you want to inspect *how* a number was made.

Sections map to the workflows in [TEST-PLAN.md](TEST-PLAN.md): `W0-orientation`, `W1-spectral`,
`W2-geometry`, `W3-grid`, `W4-glare`, `W5-electric`, `W6-annual`, `W7-spectral-sky`, `W8-daysim-nvrd`,
`W9-studio`, plus `N-negative`, `X-cross-tool`, `S-workflows`, `E-energy`, `G-arguments`, `A-advisories`,
`prompts`, `resources`. These are written when you run the kit — the shipped `results/` holds only its
own README. Once a run has generated them, start at `VALIDATION-REPORT.md` and click through to any
workflow's `RESULTS.md`.

### Advisories — read them before quoting a number
Any dict-shaped tool result may carry an `advisories` list of `{code, severity, message, field?}`; the key
is **absent** when nothing fires. `error` = probably not usable as-is · `warn` = usable but easy to
misreport · `info` = a default worth confirming. They attach at the tool-registration seam, so **all 46
tool functions** can carry them ([ADR-0005](../docs/adr/0005-advisories-attach-at-the-registration-seam.md)).
An advisory is **not** a FAIL — it tells you how to read the output — but quoting a number and *ignoring* its
advisory is a reporting defect, scored PARTIAL. Three fire on this kit's own shipped inputs and are
**expected**: `ALBEDO_NOT_MEASURED` on every Athens-IWEC sky call (that EPW writes a literal `0.000` albedo),
`GEOMETRY_HEALTH_UNCLEAN` on `office_room.obj` (1 × `NOT_ENCLOSED`), and `MEL_DER_BINNED` whenever channels
are passed without `spd=`. One documented gap: multi-point `circadian_metrics` returns a **list**, which
carries no advisories — check `mel_der_source` per point there. Section **A** of the plan tests all of it.

**Surface under test:** 46 unique tools / 50 entries incl. 4 aliases (get_reference, list_presets, import_weather, run_validation), 13 prompts, 14 resources (11 fixed + 3 templates). The 45th is `quality_presets` (named ambient-quality levels), registered 2026-07-23 after being found defined-but-unregistered — see TEST-PLAN **W0.5** / **DEF-QP-REG**. The 46th is **`check_geometry`** (standalone tier-1 geometry health audit): it was registered all along but appeared **nowhere** in this kit, which is why the head-count read 45/49 — corrected 2026-07-25 against the live server (`_list_tools()` → 50 names), with a test now at TEST-PLAN **W2.10**. The kit now also exercises `workplane_grid` (EN 12464-1 working-plane grid from OBJ, now with concave-room + footprint-clip support), `observer_points` (workstation eye sensors, now with a footprint check), `photosensors` (daylight-dimming reference sensors), `preview_scene` (matplotlib PNG scene previews), and the `place_sensors` / `visualize_scene` prompts. The spectral-sky tools (`atmosphere_from_epw` / `spectral_sky_from_epw` / `spectral_epw`) now carry **opt-in atmosphere refinements** — `ozone_mode` (van Heuklon 1979 climatology), `aerosol_g`, `aod_anchor_nm`, and `smarts_aerosol` — every default byte-identical, exercised in TEST-PLAN **G3.8**.

**Advisories (added to the kit 2026-07-30).** The `advisories` surface attaches at the tool-registration seam to all 46 tool functions and had **zero** coverage here — the same "registered but untested" hole as `check_geometry` and `quality_presets`. TEST-PLAN section **A** now covers the 6 codes plus 4 contract properties (absent-when-clean, the multi-point list gap, reporting-not-physics, alias naming); six are captured live. In the same pass the coverage ledger was corrected — it enumerated **44** tools and silently omitted `check_geometry` even after W2.10 was written for it, so **the ledger is now the declared authority** and is verified against `_list_tools()` rather than against prose head-counts.

> **New here? Open [GUIDE.md](GUIDE.md)** — it has the full connect → verify → run → bring-your-own-data →
> drive-the-prompts walkthrough. The sections below are the short version.

## How to run the validation

1. **Connect the server.** Register `hcl-mcp` with your AI client (Claude Code, Gemini CLI, or
   Antigravity) — the config (`command`/`args`/`env`) is the same everywhere; only the file differs.
   Then **restart the client in the project root** so the `hcl-mcp` tools load, and approve the server
   when prompted. Full per-client setup + the exact config block: **[GUIDE.md](GUIDE.md) Part 1 / 1B**.
   Sanity check: ask in chat "list hcl-mcp tools" or run `validate`.

2. **Launch the tester agent** from the main chat:
   > Use the **hcl-mcp-tester** agent to run the full validation against `hcl_validation/TEST-PLAN.md`.

   It acts as the user, calls every tool live, reads every resource, renders every prompt, judges each
   result (PASS / PASS(emit) / PARTIAL / FAIL / BLOCKED), and writes `results/VALIDATION-REPORT.md`.

3. **Drive the prompts yourself (human).** A subagent can't trigger slash-command prompts, so the agent
   validates prompt *text* by rendering it. To exercise them as a real user, type e.g.
   `/mcp__hcl-mcp__hcl_studio` or `/mcp__hcl-mcp__spectral_sky_from_epw` in the main chat. **Full
   prompt-by-prompt walkthrough is in [GUIDE.md](GUIDE.md) Part 5.**

### Use your own data — just drop files (auto-discovery)
The kit is **drop-and-run**: put a file with the right **extension** into the matching `inputs/` subfolder and
the tester picks it up automatically — **no JSON editing**:

| Drop into… | Extension | Becomes |
|------------|-----------|---------|
| `inputs/geometry/` | `<name>.obj` (+ `<name>.mtl`) | the room model |
| `inputs/weather/`  | `<name>.epw` | the climate (the `.wea` is derived for you if absent) |
| `inputs/luminaires/` | `<name>.ies` | the fixture |
| `inputs/spd/` | `<name>.spd` | a daylight/lamp spectrum |
| `inputs/sensors/` | `<name>.pts` | sensor points (optional — else auto-derived from the room). **Name it by role:** `*grid*`/`*workplane*` → the work-plane grid, `*observer*`/`*eye*` → vertical eye sensors, `*sensor*`/`*photo*` → daylight-dimming sensors |

**How the tester detects your file.** Some paths in `inputs/active_inputs.json` are `"auto"` (`epw`, `wea`,
`material_map`); the fields that ship with more than one candidate (`geometry_obj`, `ies`,
`spd_daylight`, `spd_luminaire`, and — since 2026-07-30 — `points` / `points_observer` /
`points_photosensor`) name a default so the multi-file scenario set stays unambiguous. Following that
file's `_resolution` rules, the agent globs each subfolder by extension and uses the single match. `_sample_files`
is now empty — the old throwaway demos were removed and every present file competes on equal footing — so when a
class has several files the base default disambiguates and the agent warns on any leftover ambiguity. Drop a
single file of your own into a folder and `"auto"` becomes unambiguous again. It echoes the chosen files in a
`resolved inputs` banner at the top of the report.

> **⚠️ Classes with `roles` resolve by role, not by sort order** (`spd`, and `points` since 2026-07-30).
> Five `.pts` ship, and plain alphabetical resolution picked `observer_1.pts` — a **single vertical eye
> point** — as the work-plane input ahead of the 45-point `office_room_grid.pts`. That silently degenerates
> sDA/ASE to 0%/100%, averages DF over the wrong plane, and leaves EN 12464-1 uniformity undefined. A `.pts`
> is not one interchangeable class; roles now split it and always win over sort order.

**Geometry just works too.** You no longer have to hand-write `material_map.json`. If no on-disk map covers your
OBJ's groups, the tester **auto-generates** one from the OBJ + its `.mtl` (reflectances inferred from group
names and `.mtl` `Kd`) so a bare `<name>.obj` + `<name>.mtl` runs end-to-end — flagged **illustrative** in the
report. To control the materials exactly, drop a `geometry/<name>_material_map.json` whose keys match your
groups (the agent prefers it over auto-generation). Full detail: [GUIDE.md](GUIDE.md) Part 4 and each
subfolder's `README.md`.

> Prefer explicit control? You can still set any field in `active_inputs.json` to a specific path — an explicit,
> existing path always wins over auto-discovery.

## Live vs. emit — the simulation engines are optional
The pure-Python spectral core always runs. The simulation tools call external engines; **whichever you
have installed run live, the rest emit the exact command plan** (`{"ran": false, "commands":[…]}`) — a
valid, capability-gated result scored **PASS(emit)**, not FAIL. Run `validate`, `radiance_status`,
`daysim_status` first and the report records the actual state. Engines (all optional, all cross-platform —
**macOS / Linux / Windows**):

| Engine | Powers | Get it |
|--------|--------|--------|
| **Radiance** (6.x for native spectral) | grid, image, annual, glare, native spectral sky, `ies2rad`, `epw2wea` | [github.com/LBNL-ETA/Radiance/releases/latest](https://github.com/LBNL-ETA/Radiance/releases/latest) |
| **Daysim** | `generate_subhourly_wea`, live `annual_nvrd` transport (`timestep_min` ∈ {1,2,3,4,5,6,10,12,15,20,30}) | [github.com/MITSustainableDesignLab/Daysim](https://github.com/MITSustainableDesignLab/Daysim) (build, or `build_daysim`) |
| **`reinsrc.cal`** (Radiance lib helper) | live 2-phase DDS for `run_annual` / `annual_nvrd` | ships in the Radiance/Daysim source; copy into the Radiance `lib` |
| **SMARTS 2.9.5** | `engine="smarts"` (optional; `spectrl2` pure-Python is default) | [nrel.gov/grid/solar-resource/smarts.html](https://www.nrel.gov/grid/solar-resource/smarts.html) |

> Each engine is found via an `env` path in your client config (`HCL_RADIANCE_BIN`, `HCL_DAYSIM_BIN`,
> `SMARTSPATH`, `RAYPATH`). **Install steps with the exact build/copy commands for macOS / Linux /
> Windows are in [GUIDE.md Appendix A](GUIDE.md#a--installing-the-engines-optional--for-live-simulation).**

## Scope / honesty notes baked into the plan
- Geometry is OBJ-only (no inline mesh); the importer still hard-fails on an unmapped group (tested on purpose
  in W2.2), but the tester shields you from that by **auto-generating** a complete map when you don't supply one
  (illustrative reflectances — see "Use your own data").
- `recommend_fixtures` sizing and the surface library are **illustrative / first-principles**, not measured —
  treat their numbers as plausibility checks, not ground truth.
- nvRD `R_D` is **relative**, not absolute.
