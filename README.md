# hcl-mcp — Human-Centric Lighting MCP Server

A literature-grounded human-centric-lighting (HCL) engine exposed as a local
**[Model Context Protocol](https://modelcontextprotocol.io)** server. It computes CIE S 026 α-opic
and circadian metrics, reconstructs a physical spectral sky from an EPW, drives the per-channel
**Radiance** daylight/electric/glare pipeline, and estimates light-driven alertness — all callable
from any MCP client in natural language.

The spectral and circadian methods implement published models directly: Bird & Riordan 1986
(SPECTRL2 clear sky), Nann & Riordan 1991 (SEDES1 cloud modifier), CIE S 026:2018 (α-opic action
spectra), Amundadottir 2016 (nvRD alertness), Inanici, Brennan & Clark 2015 (3-/9-channel).
Full citation map and grounding-status index: [`docs/literature-bibliography.md`](docs/literature-bibliography.md).

> **Version** 0.1.0 · **Python** ≥ 3.11 · **License** MIT
> **Optional engines** Radiance 6.1a (daylight / electric / glare / native spectral) · Daysim (sub-hourly weather) · SMARTS (spectral oracle)

The pure-Python spectral core has **zero runtime dependency on Radiance or Daysim** — it always
runs. The simulation layers follow a strict **run-or-emit** contract: if the binary is present they
execute; if not, they return the exact command sequence they *would* have run.

## Install in two lines

In Claude Code:

```
/plugin marketplace add akontadakis/hcl-mcp
/plugin install hcl-mcp@hcl-mcp
```

Restart Claude Code and the 47 tools are live, together with the `running-hcl-studies` skill. You
need [`uv`](https://docs.astral.sh/uv/) on your `PATH`; Radiance stays optional. Other hosts and
the manual route are under [Installation](#installation).

---

<details open>
<summary><strong>Table of Contents</strong></summary>

- [Key Features](#key-features)
- [What It Computes](#what-it-computes)
- [Installation](#installation)
- [The run/emit contract](#the-runemit-contract)
- [Capabilities](#capabilities)
- [Usage Examples](#usage-examples)
- [Architecture](#architecture)
- [Dataflow](#dataflow)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [External Engines](#external-engines)
- [Troubleshooting](#troubleshooting)
- [Validation & Accuracy Caveats](#validation--accuracy-caveats)
- [Documentation](#documentation)
- [References & License](#references--license)

</details>

---

## Key Features

- 🌈 **Spectral foundation** — SPD → 3-/9-channel bins; the full **CIE S 026** α-opic suite (S/M/L-cone, rhodopic, melanopic E / ELR / EDI), photopic / melanopic / neuropic equivalent illuminance, CCT + Duv, mel-DER, EML.
- 🌌 **Physical spectral sky from EPW** — radiative transfer instead of CIE-D-series templates: a pure-Python **Bird SPECTRL2** clear-sky engine plus the **SEDES1** cloud bridge, driven by EPW-derived atmosphere (AOD / PWV / ozone) and solar geometry, resampled to 1 nm over 380–780 nm. The clear-sky engine is selectable (`engine="spectrl2"` default | `"smarts"`), and Radiance 6.x `gensdaymtx` is exposed as its own native tool. Four atmospheric refinements are opt-in and every default reproduces the base physics byte-for-bit.
- ☀️ **Spectral daylight simulation** — colored Perez sky/sun plus the per-channel **Radiance** pipeline: point-in-time grids, fisheye eye-level images, 2-phase annual **Daylight-Coefficient (DDS)** runs with circadian dosimetry, climate-based metrics (DA/cDA/UDI, sDA/ASE), CIE-overcast Daylight Factor, and **LM-83-12** sDA/ASE with blinds actually operated.
- 💡 **Electric lighting** — IESNA **LM-63** photometry, `ies2rad` conversion, **EnergyPlus**-faithful daylight-responsive controls and energy savings, glare via **evalglare** (UGR/DGP), and **EN 12464-1** task interpretation.
- 🧠 **Circadian alertness** — the **nvRD** non-visual direct-response model (Amundadottir 2016) with an automatic annual → alertness bridge driven by Daysim sub-hourly weather.
- ✅ **Compliance** — mel-EDI / EML verdicts against **WELL v2 L03**, **Brown 2022**, **ISO/CIE 8995-1:2025** and **EN 17037**, plus **EN 12464-1:2021** task lighting. Each verdict carries its threshold, citation and measurement convention.
- 📐 **OBJ/CAD geometry import** — a real Wavefront `.obj` room becomes a per-channel Radiance scene with per-group spectral materials, true-north orientation, derived sensors (work-plane grid, seated **and** standing eye observers, DGP views), a ground↔sky albedo bridge, drop-in luminaires, and a provenance manifest. Unmapped groups **hard-fail** — no silent generic material.
- 🧭 **Guided studio journey** — `hcl_studio` runs a full study end to end (goal → fixture design via `recommend_fixtures` → simulate → `build_report`) with a resumable brief.
- 🔬 **Verifiable** — a built-in `validate()` self-test anchors constants against CIE S 026 published values, and every constant is documented against the source line it came from.

---

## What It Computes

| Domain | Quantities |
| --- | --- |
| **α-opic (CIE S 026)** | Melanopic / S-/M-/L-cone / rhodopic irradiance (E_α), efficacy of luminous radiation (ELR), Equivalent Daylight Illuminance (EDI), D65-normalized `K_D65` |
| **Circadian** | Photopic lux; **mel-EDI** and **`melanopic_lux`** — *two different quantities*, differing by D65's own melanopic/photopic ratio (~1.0997× on the 9-bin route). Thresholds are `≥`, so substituting the larger `melanopic_lux` silently manufactures compliance: score against `mel_edi` only ([ADR-0001](docs/adr/0001-mel-edi-is-the-circadian-quantity.md)). Plus neuropic lux, mel-DER, EML |
| **Color** | CCT (Ohno 2013) + Duv |
| **Daylight** | Point-in-time grid HCL metrics, fisheye FOV-weighted melanopic luminance, annual mel-EDI series, hours-above-threshold dosimetry, DA/cDA/UDI, sDA/ASE, CIE-overcast Daylight Factor, named sensor sets |
| **Spectral sky** | EPW-hour atmospheric state (AOD, PWV, ozone, pressure, albedo), solar geometry, SPECTRL2 + SEDES1 cloud-modified 1 nm direct-normal and sky-diffuse irradiance (380–780 nm), spectral ground glow, annual sky artifacts (SPD set / band matrix / spectral `.wea` / sidecar) |
| **Electric** | Rated lumens / efficacy / LOR / beam & field angles, zonal flux, daylight-control power fraction, energy savings (kWh/m²·yr) |
| **Alertness** | Relative non-visual direct response `R_D(t)` and cumulative dose |
| **Fixture design** | Lumen method reconciled with a CIE S 026 mel-DER solve: required flux, fixture count and spacing-to-height layout, target CCT band, power density, binding constraint (visual vs circadian) |
| **Compliance** | Pass/fail verdicts with thresholds, citations, and measurement conventions |

---

## Installation

**→ Full manual for macOS / Windows / Linux across five clients: [`INSTALL.md`](INSTALL.md).** The summary below is the short version.

### Requirements

| Requirement | Version | Notes |
| --- | --- | --- |
| **Python** | ≥ 3.11 | from [`pyproject.toml`](pyproject.toml) |
| **[`uv`](https://docs.astral.sh/uv/)** | current | installs deps and launches the server |
| **MCP client** | protocol 2026-07-28 or 2025-11-25 | the server answers both: per-request metadata, or the older `initialize` handshake |
| `fastmcp` · `fastmcp-tasks` · `pydantic` · `colour-science` · `matplotlib` | ≥ 4.2, < 5 · ≥ 4.2, < 5 · ≥ 2 · ≥ 0.4.4 · ≥ 3.7 | installed automatically; all five are hard dependencies |

External engines are optional — see [External Engines](#external-engines).

### Claude Code — plugin (two lines)

This repository is also a Claude Code plugin marketplace, so one install registers the server *and*
the `running-hcl-studies` skill:

```
/plugin marketplace add akontadakis/hcl-mcp
/plugin install hcl-mcp@hcl-mcp
```

Restart Claude Code and check with `/mcp`. The plugin launches
`uvx --from git+https://github.com/akontadakis/hcl-mcp hcl-mcp` and declares no environment
variables — the server inherits your shell's, so put `HCL_RADIANCE_BIN` / `RAYPATH` in your shell
profile, or use the CLI method below, which takes `--env`. Manage it later with `/plugin`.

### Claude Code (CLI)

```bash
claude mcp add hcl-mcp -- uvx --from git+https://github.com/akontadakis/hcl-mcp hcl-mcp
```

`uvx` fetches, builds and caches the server on first run. Add variables with `--env` (repeatable),
e.g. `--env HCL_RADIANCE_BIN=/usr/local/radiance/bin`. Use `-s user` to register globally.

### Claude Desktop / other MCP clients

```jsonc
{
  "mcpServers": {
    "hcl-mcp": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/akontadakis/hcl-mcp", "hcl-mcp"],
      "env": {
        "HCL_WORK_ROOT": "/ABSOLUTE/PATH/TO/work",        // optional: where sim files are written
        "HCL_RADIANCE_BIN": "/usr/local/radiance/bin",    // optional: Radiance bin dir if not on PATH
        "HCL_DAYSIM_BIN": "/ABSOLUTE/PATH/TO/daysim/bin"  // optional: Daysim bin dir
      }
    }
  }
}
```

> Remove the `//` comments — JSON does not allow them. VS Code uses `servers` (not `mcpServers`) and needs `"type": "stdio"`; see [`INSTALL.md`](INSTALL.md).

> **⚠️ Running from a local clone?** Use `uv tool install .` (the launch command is then just `hcl-mcp`), **not** `uv run --directory …`. `uv run`'s implicit sync can leave the editable install in a state where the bare interpreter cannot import the `src/`-layout packages, and the server dies with `ModuleNotFoundError: hcl_core`. See [`INSTALL.md`](INSTALL.md) Method B.

### Development setup

```bash
uv sync --extra dev      # runtime + pytest
uv run pytest -q         # full test suite
```

---

## The run/emit contract

Every tool that touches Radiance or Daysim takes `run: bool = True` and behaves identically:

- **`run=True` and the binary is available** → it **executes** and returns results.
- **`run=False`, or the binary is missing** → it does **not** execute and returns
  `{"ran": false, "commands": [ ...exact ordered shell lines... ], "reason": ...}`.

So you can design and inspect a full pipeline — sky generation, octree compilation, ray tracing,
matrix multiplication — on any machine, then run the identical commands where an engine exists.
Call `validate()`, `radiance_status()` and `daysim_status()` first to see which layers will execute.

---

## Long runs: progress, cancel, background tasks

A simulation tool call is a *job*. The engine runs on a worker thread, so the server keeps
answering other requests while Radiance works.

| What the client does | What the server does |
| --- | --- |
| Sends a `progressToken` | Reports each pipeline step as `notifications/progress`: a running count and a message such as `rtrace (3/15)` |
| Cancels the request (`notifications/cancelled`), times out, or goes away | Kills the command it is waiting on, together with the children that command started (`rfluxmtx`, `rtrace -n`), and runs no further step |
| Declares the tasks extension (`io.modelcontextprotocol/tasks`, MCP 2026-07-28) | Returns a task handle at once for the eight long tools; `tasks/get` shows the current step, `tasks/cancel` stops the run, the result is kept for 24 h |
| Honours cache hints (MCP 2026-07-28) | Marks its tool, prompt and resource lists and its reference texts `ttlMs` = 1 h, `cacheScope` = `public` |

The eight long tools are `run_annual`, `annual_daylight`, `lm83_daylight`, `daylight_savings`,
`annual_nvrd`, `spectral_epw`, `spectral_sky_native` and `build_daysim`. A client that does not
declare the tasks extension gets the same tools as plain calls, with progress and cancellation.
Tasks live in the server process (no Redis, nothing to install): they end when the server does.
Simulations take turns: a second one waits for the first, because engines write fixed file names
into the work directory. Status calls, task polling and cancellation are answered meanwhile.

Four of those tools ask *"this takes minutes to hours, proceed?"* first, when the client can show
a form. Answering no, declining or cancelling returns the command plan instead of running.

## Capabilities

**47 tools · 14 resources · 13 prompts.** The server registers 51 tool names: the 47 plus four
verb-object aliases (`get_reference`, `list_presets`, `import_weather`, `run_validation`) for
clearer AI tool selection.

| Group | Runs | Tools |
| --- | --- | --- |
| 🌈 **Spectral core** | always (pure Python) | `spd_to_channels` `circadian_metrics` `alpha_opic` `spectral_metrics` `compliance` `presets` `glass_transmissivity` `write_material` `validate` `reference` `recommend_fixtures` |
| ☀️ **Daylight simulation** | run-or-emit | `radiance_status` `quality_presets` `colored_sky` `run_grid` `run_image` `run_annual` `annual_daylight` `lm83_daylight` `daylight_factor` `weather` |
| 📐 **Geometry & sensors** | mixed | `import_geometry` `check_geometry` `workplane_grid` `observer_points` `sensors` `photosensors` `preview_scene` |
| 🌌 **Physical spectral sky** | pure Python (`spectral_sky_native` run-or-emit) | `atmosphere_from_epw` `spectral_sky_from_epw` `spectral_epw` `spectral_sky_native` |
| 💡 **Electric lighting** | mixed | `ies_analyze` `ies_to_radiance` `colored_luminaire` `lighting_controls` `daylight_savings` `glare_ugr` |
| 🧠 **Circadian alertness** | pure Python | `nvrd` `reconstruct_spectrum` `annual_nvrd` |
| 🗓️ **Daysim** | run-or-emit | `daysim_status` `build_daysim` `generate_subhourly_wea` |
| 🧭 **Studio journey** | always | `save_brief` `load_brief` `build_report` |

**→ Every tool with its full signature, semantics and honesty notes: [`docs/operating-guide.md`](docs/operating-guide.md) §4. Resources and prompts: §5.**

Two things worth knowing before you read any result:

- **`quality_presets`** makes the ambient-accuracy/runtime trade-off explicit rather than inherited. `low` (`-ab 0`) has no interreflection, so DA/sDA/UDI are meaningless there while ASE stays exact; `high` (`-ab 3`) is the floor for anything reportable. On one validated annual run the preview-grade default returned sDA **77.78%** where a converged solve returned **100.00%** on identical geometry — hence the `convergence_warning` that `annual_daylight` now attaches.
- **Advisories.** Any tool returning a dict may carry an `advisories` list — absent entirely when there is nothing to flag. Each entry is `{code, severity, message, field?}` with severity `error` (result probably unusable), `warn` (usable but easy to misreport) or `info` (a default was applied). They are **reporting, not physics**: each rule re-reads a field the tool already computed. The nine codes are `MEL_DER_BINNED`, `SPECTRAL_TRANSPORT_SHIFT`, `ELECTRIC_EXCEEDS_LUMEN_BOUND`, `ALBEDO_NOT_MEASURED`, `DOSE_THRESHOLD_IS_DEFAULT`, `ZONE_WEIGHT_REMAINDER`, `GEOMETRY_HEALTH_UNCLEAN`, `NVRD_ZERO_DIVERGENCE` and `RADIANCE_DROPS_IES_CANDELA_SCALE`; each is defined in [`docs/operating-guide.md`](docs/operating-guide.md) and [`docs/technical-reference.md`](docs/technical-reference.md), and [ADR-0005](docs/adr/0005-advisories-attach-at-the-registration-seam.md) explains why they attach at the registration seam. **Known v1 gap:** advisories attach only to dict results, so multi-point `circadian_metrics` (which returns a list) carries none — check `mel_der_source` per point by hand there.

---

## Usage Examples

> These show the underlying tool calls. In an MCP client you just ask in natural language (*"What's the melanopic EDI of D65 and does it pass WELL v2?"*) and the model picks the tools. `channel_type`: **0 = 3-channel, 1 = 9-channel**. `spd` accepts a `.spd` **file path**, SPD text, or `(wavelength, value)` rows.

**1 · SPD → circadian metrics + compliance** *(pure Python — no engine needed)*

```json
{ "tool": "presets",          "arguments": { "name": "D65" } }
{ "tool": "spd_to_channels",  "arguments": { "spd": "<SPD data from step 1>", "channel_type": 1 } }
{ "tool": "alpha_opic",       "arguments": { "channels": [0.10,0.12,0.20,0.30,0.35,0.33,0.25,0.18,0.12], "channel_type": 1 } }
{ "tool": "compliance",       "arguments": { "mel_edi": 250, "standard": "well_v2_l03" } }
```

**2 · Annual climate-based daylight metrics** *(reuse one named sensor set across the daylight tools)*

```json
{ "tool": "sensors", "arguments": {
    "action": "create", "name": "wp",
    "grid": { "interior": [0.25, 5.75, 0.25, 3.75], "floor_z": 0.0, "workplane_h": 0.8 } } }
{ "tool": "annual_daylight", "arguments": {
    "channel_scenes": [{ "materials": "materials.rad", "geometry": "room.rad", "sky_color": [0.9, 0.95, 1.0] }],
    "wea": "athens.wea", "sensor_set": "wp", "channel_type": 0,
    "da_threshold": 300, "sda_da_fraction": 0.5, "ase_threshold": 1000, "ase_hours": 250, "run": true } }
{ "tool": "daylight_factor", "arguments": {
    "scene_sets": ["materials.rad", "room.rad"], "sensor_set": "wp", "run": true } }
```

> `annual_daylight` returns per-point DA/cDA/UDI plus spatial sDA/ASE (ASE via its own direct-only `-ab 0` pass — the two lux matrices are **not** interchangeable); `daylight_factor` adds the CIE-overcast DF %.

**3 · Guided studio journey — design the fixtures, then grade the result** *(the front door)*

Say *"design human-centric lighting for a 6×4×3 m office targeting WELL mel-EDI 250 and run a
study."* The `hcl_studio` prompt conducts all 8 phases; the design and reporting steps are pure
Python and always run.

```json
{ "tool": "recommend_fixtures", "arguments": {
    "length_m": 6, "width_m": 4, "height_m": 3, "mount_height_m": 2.8,
    "target_em_lux": 500, "target_mel_edi": 250 } }
{ "tool": "build_report", "arguments": { "study": "office_a", "brief": "<accumulated brief>" } }
```

**→ Colored sky + grid, annual circadian dose, electric design + glare, and the full studio walkthrough: [`docs/operating-guide.md`](docs/operating-guide.md) §3.**

---

## Architecture

Five modules in four layers. Imports point **downward** only, so knowing which layer a tool lives
in tells you what it needs to run.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  hcl_mcp/      Thin FastMCP server — 47 tools, 14 resources, 13 prompts. │  ← pure protocol
│                Maps tools onto the modules below; no business logic.     │
├─────────────────────────────────┬────────────────────────────────────────┤
│  hcl_radiance/                  │  hcl_daysim/                           │  ← ONE layer, two peers
│  Radiance adapter: detect       │  Daysim adapter (ds_shortterm /        │    (not stacked)
│  binaries → build commands →    │  epw2wea). Sub-hourly weather for      │    each needs its own
│  run-or-emit → parse. Native    │  the alertness bridge.                 │    engine; Daysim is
│  gensdaymtx · OBJ import.       │  Build-from-source.                    │    build-from-source
│              └───── annual nvRD borrows the .wea generator ─────┘        │  ← the one lateral edge
├─────────────────────────────────┴────────────────────────────────────────┤
│  hcl_core/     Pure-Python spectral math (≤401-pt arrays, plain loops).  │  ← always runs,
│                CIE S 026 α-opic, channels, circadian metrics,            │     zero engine deps
│                compliance, nvRD model, spectral reconstruction, and the  │
│                physical EPW→spectral-sky pipeline (SPECTRL2 + SEDES1).   │
├──────────────────────────────────────────────────────────────────────────┤
│  hcl_platform/ Cross-platform path, text-I/O and executable resolution.  │  ← stdlib only
└──────────────────────────────────────────────────────────────────────────┘
```

The separation is **enforced, not conventional**: `tests/test_module_layering.py` walks `src/` and
fails the suite on any import above a module's layer. `hcl_core` has zero dependency on the
Radiance/Daysim binaries — the property that makes the spectral core portable. The one caveat is
the optional **SMARTS oracle** (`hcl_core/spectral_engine/smarts.py`), the single core path that
shells out, capability-gated on `$SMARTSPATH`. All Radiance/Daysim subprocess transport lives in
`hcl_radiance` / `hcl_daysim`; the MCP layer holds no business logic.

---

## Dataflow

Every tool is a node in one of six pipelines. All inputs reduce to a small set of canonical
artifacts — an **SPD**, a **channel vector**, a Radiance **scene**, an **EPW**, an **IES**
luminaire — and the pipelines converge on circadian metrics, a compliance verdict, or a report.

```
  A · SPECTRAL CORE   (hcl_core — pure Python, always runs)
  SPD ─┬─ spd_to_channels ─► channels[3|9] ─┬─ alpha_opic ───────► α-opic E/ELR/EDI, mel-EDI ─┐
  preset┘  (or exact SPD ─────────────────► )├─ circadian_metrics ► photopic/melanopic lux, EML ├─► compliance
                                             └─ spectral_metrics ─► CCT/Duv, mel-DER, EML↔EDI ┘   └─► PASS/FAIL + citations

  B · DAYLIGHT SIMULATION   (hcl_radiance — run-or-emit)
  channels ─► colored_sky ─► sky.rad ─┐
  scene (.rad materials + geometry) ──┼─► run_grid  ─► oconv → rtrace -I ×channel ─► grid HCL metrics
                                      ├─► run_image ─► rpict ×channel ───────────► melanopic luminance maps
  weather (.wea) ─────────────────────┴─► run_annual ─► 2-phase DDS ─────────────► annual mel-EDI ─► dosimetry

  C · PHYSICAL SPECTRAL SKY   (hcl_core; native variant run-or-emit)
  EPW + (m,d,h) ─► atmosphere + solar geometry ─► SPECTRL2 + SEDES1 ─► SpectralSkyRecord
                                                  ─► channels · reconstruction · emitters · α-opic

  D · ELECTRIC LIGHTING   (hcl_core analysis + hcl_radiance render)
  IES (LM-63) ─┬─ ies_analyze ──────────────────────► photometric report
               └─ ies_to_radiance ─► colored_luminaire ─┐
  scene + sky ──────────────────────────────────────────┴─► glare_ugr ─► UGR/DGP + glare sources
  illuminance @ points ─► lighting_controls ─► daylight_savings ──────► savings (kWh/m²·yr)

  E · CIRCADIAN ALERTNESS   (hcl_daysim sub-hourly → hcl_core nvRD)
  EPW ─► generate_subhourly_wea ─► .wea ─► annual_nvrd ─┬─ reconstruct_spectrum ─► per-nm SPD
                                                        └─ nvrd ─► R_D(t) + cumulative dose

  F · GUIDED STUDIO JOURNEY   (hcl_studio prompt orchestrates)
  goal ─► recommend_fixtures ─► save_brief ─► [run B / D sims] ─► build_report ─► report.{md,html}
```

Three properties hold across all six: the **core path always runs**; the **simulation paths
run-or-emit**; and **physics is computed once, then consumed** — the `SpectralSkyRecord` is frozen
sky-truth and nothing downstream recomputes it.

**→ Pipeline C stage by stage, with boundary data structures and per-symbol source map: [`docs/spectral-sky-methodology.md`](docs/spectral-sky-methodology.md) §3 and [`docs/spectral-sky-as-built.md`](docs/spectral-sky-as-built.md).**

---

## Project Structure

```
hcl-mcp/
├── src/
│   ├── hcl_core/         # Pure-Python spectral math (the verifiable asset)
│   │                     #   α-opic integrals · action spectra · SPD binning · CCT/Duv
│   │                     #   compliance · nvRD · spectral reconstruction · daylight metrics
│   │                     #   LM-83 + Klems · IES · lighting controls · fixture design
│   │                     #   EPW → atmosphere/solar geometry → SPECTRL2 + SEDES1 → sky record
│   │   └── spectral_engine/   # pluggable clear-sky engines: spectrl2 (pure Python) · smarts (gated)
│   ├── hcl_radiance/     # Radiance adapter: detect → build commands → run-or-emit → parse
│   │                     #   grid · image · annual DDS · three-phase LM-83 · OBJ import
│   │                     #   sensors · glare · native gensdaymtx
│   ├── hcl_daysim/       # Daysim adapter: epw2wea, ds_shortterm, build-from-source
│   ├── hcl_mcp/          # FastMCP server: tools, resources, prompts, advisories, studio
│   └── hcl_platform/     # Cross-platform paths, text I/O, executable resolution (stdlib only)
├── tests/                # Unit + layering + capability-gated live tests
├── hcl_validation/       # End-to-end validation kit driven through real chat tool-calls
├── docs/                 # Methodology, technical reference, ADRs, engine build guides
├── skills/               # running-hcl-studies (auto-loaded by the Claude Code plugin)
├── .claude-plugin/       # Plugin marketplace + plugin manifest
└── .mcp.json             # Server declaration used by the plugin
```

[`hcl_validation/`](hcl_validation/) is the complement to `tests/`: `tests/` verifies the Python
math in isolation, the kit exercises the whole MCP surface the way a user drives it — every tool
called live, every resource read, every prompt rendered. Start at its
[`README.md`](hcl_validation/README.md), then [`GUIDE.md`](hcl_validation/GUIDE.md) and
[`TEST-PLAN.md`](hcl_validation/TEST-PLAN.md).

---

## Configuration

All environment variables are optional.

| Variable | Purpose | Default |
| --- | --- | --- |
| `HCL_WORK_ROOT` | Directory where simulation files are written | first MCP client root, else `~/hcl_work` |
| `HCL_RADIANCE_BIN` | Radiance `bin` directory, if not on `PATH` | auto-discovered on `PATH` |
| `HCL_DAYSIM_BIN` | Daysim `bin` directory (`ds_shortterm`, `epw2wea`) | auto-discovered on `PATH` |
| `SMARTSPATH` | SMARTS executable — **the file, not its directory** | unset (SMARTS engine unavailable) |
| `PYTHONPATH` | Only for a local clone launched from source — set to the `src` dir | — |

**work_dir precedence:** explicit tool argument → `HCL_WORK_ROOT` → first MCP client root → `~/hcl_work`.

---

## External Engines

| Layer | Needs | Notes |
| --- | --- | --- |
| **Spectral core** | nothing | Pure Python — always runs. |
| **Daylight / electric / glare + native spectral** | [Radiance](https://www.radiance-online.org/) **6.1a** | One build is a superset of the old `≥ 5.4` floor: `oconv`, `rtrace`, `rpict`, `gendaylit`, `gendaymtx`, `rfluxmtx`, `rcontrib`, `dctimestep`, `ies2rad`, `evalglare`, `obj2rad`, `xform`, and the spectral `gensdaymtx` / `rcomb`. **Not bundled.** Without it, tools emit their command plans. |
| **Sub-hourly weather** | [Daysim](https://github.com/MITSustainableDesignLab/Daysim) | `ds_shortterm` + `epw2wea`. Source-available (NRC / Fraunhofer ISE), **not bundled** — build via `build_daysim`. Only the `annual_nvrd` alertness bridge needs it. |
| **Spectral oracle** | [SMARTS](https://www.nrel.gov/grid/solar-resource/smarts.html) 2.9.5 | Optional; only for `engine="smarts"`. Needs `$SMARTSPATH`. The default `engine="spectrl2"` needs nothing. |

**→ Get-source → build → set-env → verify checklist for all three: [`docs/engines-install.md`](docs/engines-install.md).**

---

## Troubleshooting

| Symptom | Cause & fix |
| --- | --- |
| **Server won't start / `ModuleNotFoundError: hcl_core`** | The `src/`-layout packages aren't importable. Use `uvx` or `uv tool install .` rather than `uv run --directory`; see [`INSTALL.md`](INSTALL.md). |
| **A simulation tool returns `{"ran": false, "commands": […]}`** | Working as designed — the engine isn't found, so the tool **emits** its command plan. Run `radiance_status()` / `daysim_status()`, install the engine or set `HCL_RADIANCE_BIN` / `HCL_DAYSIM_BIN`, then re-call with `run=true`. |
| **`alpha_opic` raises "no integer-wavelength rows…"** | `spd` must resolve to SPD rows — a readable `.spd` path, SPD text, or `(λ, value)` rows. A preset *name* is not an SPD: fetch it with `presets(name=…)` first. |
| **`compliance(standard="en_12464_1")` returns `"incomplete"`** | EN 12464-1 is judged on task parameters, not a `mel_edi` — pass `task` plus measured `em`/`ugr`/`uo`/`ra`. With none, the verdict is `"incomplete"` by design, never a vacuous pass. |
| **A relative file path fails oddly** | Every file-shaped argument resolves against the **server's** working directory, not your shell's. Pass absolute paths — a bad relative path can surface as a parse error rather than "missing". |
| **Files written somewhere unexpected** | Output goes to `work_dir`: explicit arg → `HCL_WORK_ROOT` → first MCP client root → `~/hcl_work`. |

---

## Validation & Accuracy Caveats

This toolkit is **honest about what is proven versus what is latent.** Read this before trusting a
live run. Canonical wording lives in [`docs/spectral-sky-as-built.md`](docs/spectral-sky-as-built.md) §9
and [`docs/technical-reference.md`](docs/technical-reference.md) §12–13.

**Verified**

- ✅ **The spectral math.** `validate()` anchors `K_D65` against CIE S 026 published values (within 0.05%), checks weight-sum and scale-invariance properties, and confirms mel-DER(D65) ≈ 1.0. Two deliberate fixes over the Lark source are applied (Python-2 integer division; a 3-channel bin-ordering misalignment).
- ✅ **The grid daylight pipeline.** A unit-radiance hemisphere reproduces `562.345 lux = 179 × π` on both the 3- and 9-channel paths under live Radiance.
- ✅ **OBJ geometry import** — live-checked on Radiance 6.1a: the `obj2rad → xform → oconv → rtrace` round-trip, a north-rotation round-trip, an IES-luminaire octree build, and the colored-by-material `annotate` render.
- ✅ **The offline spectral stack.** EPW → atmosphere/solar geometry → SPECTRL2 → SEDES1 → `SpectralSkyRecord` → artifacts is unit-tested end to end; the SPECTRL2 constants are transcribed verbatim from the NREL `spectrl2_2.c` source.

**First live runs, not calibrated baselines**

- ⚠️ **`gensdaymtx` and SMARTS.** SMARTS agrees with the Python SPECTRL2 engine to ~2% direct / ~7% diffuse, r≈0.99 ([`docs/spectral-engine-comparison.md`](docs/spectral-engine-comparison.md)). Neither is validated against *measured* sky spectra.
- ⚠️ **The `physical_sky` flip.** First live execution 2026-07-18 measured **50.03% physical coverage** — daylight timesteps carry EPW-derived spectra, night timesteps fall back to the template by design — with a time-resolved sun throughout.
- ⚠️ **`annual_daylight` / `daylight_factor` / `daylight_savings` / `sensors`.** All ran live on a realistic office plus Athens IWEC. Two identical preview-grade runs gave sDA **66.7%** and **82.2%** — Radiance's ambient calculation is stochastic, so preview-grade sDA is not reproducible. **ASE was bit-identical** across runs, since its direct-only pass has no ambient sampling. Use `quality="high"` for anything you intend to quote.
- ⚠️ **The electric path.** First end-to-end live run 2026-07-18. It exposed a **Radiance build defect, not an hcl-mcp one**: a custom 6.1a build's compiled `source_corr` dropped the `ies2rad` `A1` candela-scale multiplier, so IES luminaires under-emitted ~14×, which also collapsed UGR to 0. Patching `source.cal` gave a realistic 494 lux average and UGR 19.24 / DGP 0.199. Do **not** fold `A1` into `colored_luminaire` — that double-scales on a stock Radiance. Sky paths are unaffected.

**Known limits**

- ⚠️ **`R_D` (alertness) is relative only.** The nvRD intensity response was fit from nighttime electric-light studies; daytime adaptation is unvalidated, and an unexplained channel→irradiance constant biases the absolute value (it cancels in ELR/EDI ratios but not in the nonlinear sigmoid).
- ⚠️ **The SEDES1 cloud CCM carries real spectral-shape uncertainty.** Only the always-on energy rescale is exact. Per-wavelength regression uncertainty is surfaced as `ccm_sigma`; the CCM can be locally re-fit ([`docs/recalibrating-cloud-ccm.md`](docs/recalibrating-cloud-ccm.md)). The opt-in **SEDES2** tabulated alternative closes the *digitization* caveat but remains a German-site fit, and its independent variable is NGH, not `Kt` — it is not a drop-in.
- ⚠️ **Spectral physics is opt-in.** Without `physical_sky=True` the enhanced reconstruction uses the reference-sky template with an air-mass-colored sun. The seam is wired, not on by default.
- ⚠️ **`lm83_method_conformant` is always false by design.** §§2.2.8–2.2.11 are out of scope, so glazing runs at raw `tvis`, biasing sDA up. Read `conditions.departures` before quoting.
- ⚠️ **The OBJ carries no spectral data.** Reflectances are user-assigned; `.mtl` is a hint. The measured-SPD path exists, but the shipped catalog is illustrative scalars pending data.
- 📐 **Accuracy envelope** (Lark, Pierson 2023): daylight mel-EDI within ±20%, validated for neutral-colored interiors — chromatic or strongly inter-reflecting scenes degrade. 3-channel is an approximation; **9-channel is recommended**, and the exact-from-SPD α-opic path is provided for validation.

---

## Documentation

| Document | What it covers |
| --- | --- |
| [`INSTALL.md`](INSTALL.md) | Step-by-step install for macOS / Windows / Linux across five MCP clients |
| [`docs/operating-guide.md`](docs/operating-guide.md) | Running an end-to-end study: workflows (§3), every tool (§4), resources and prompts (§5), prerequisites (§6) |
| [`docs/technical-reference.md`](docs/technical-reference.md) | Full methodology, mathematics, per-module source map, consolidated correctness findings (§12) |
| [`docs/hcl-methodology.md`](docs/hcl-methodology.md) | The HCL method itself, independent of this implementation |
| [`docs/spectral-sky-as-built.md`](docs/spectral-sky-as-built.md) | EPW→spectral-sky as-built: stage map, deviations ledger, canonical caveats (§9) |
| [`docs/spectral-sky-methodology.md`](docs/spectral-sky-methodology.md) | Spectral-sky physics, equations, per-symbol source map |
| [`docs/spectral-engine-comparison.md`](docs/spectral-engine-comparison.md) | Live three-way engine comparison: SPECTRL2 vs SMARTS vs `gensdaymtx` |
| [`docs/recalibrating-cloud-ccm.md`](docs/recalibrating-cloud-ccm.md) | Re-fitting the SEDES1 cloud CCM from your own measured diffuse spectra |
| [`docs/engines-install.md`](docs/engines-install.md) | Building and verifying Radiance, Daysim and SMARTS |
| [`docs/literature-bibliography.md`](docs/literature-bibliography.md) | Full citation map and grounding-status index |
| [`docs/adr/`](docs/adr/) | Architecture decision records — why the contentious choices are what they are |

---

## References & License

The load-bearing authorities. The complete map, with grounding status per claim, is in
[`docs/literature-bibliography.md`](docs/literature-bibliography.md).

| Quantity / method | Authority |
| --- | --- |
| α-opic EDI/ELR, action spectra, K_D65 | **CIE S 026/E:2018** |
| 3-/9-channel spectral method, EML | Inanici, Brennan & Clark 2015; Lark Spectral Lighting v3.0 |
| Neuropic / OPN5 (9-channel) | Jung, Cheng, Brennan & Inanici 2023; Kojima 2011 |
| CCT / Duv | Ohno 2013; CIE 1931 2° observer |
| ipRGC FOV weighting | Khademagha 2021 (TU/e) |
| nvRD alerting model | Amundadottir 2016 (EPFL) |
| 2-phase Daylight Coefficient with Direct Sun (DDS) | Subramaniam 2017 |
| Clear-sky spectral model (SPECTRL2) | Bird & Riordan 1986, *J. Climate Appl. Meteorol.* **25**:87 |
| Cloud spectral modifier (SEDES1) | Nann & Riordan 1991, *J. Appl. Meteorol.* **30**:447 |
| Relative optical air mass | Kasten & Young 1989, *Appl. Opt.* **28**:4735 |
| Precipitable water | Gueymard 1994; Reitan 1963 |
| Accuracy envelope (±20%) | Pierson, Aarts & Andersen 2023, *J. Build. Perf. Sim.* **16**(2):179–197 |
| Neutral-sun bias; sky/sun spectra | Inanici, Abboushi & Safranek 2023, *Light. Res. Technol.* **55**:502–529 |
| Lighting controls | EnergyPlus Engineering Reference v25.2 |
| IES photometry format | IESNA LM-63-1995 / 2002 |
| Compliance standards | WELL v2 L03; Brown et al. 2022, *PLoS Biol.* **20**:e3001571; ISO/CIE 8995-1:2025; EN 17037:2018; EN 12464-1:2021 |

### Acknowledgements & License

`hcl-mcp` is released under the **[MIT License](LICENSE)** — © 2026.

It is an independent implementation grounded in primary scientific literature that derives certain
spectral algorithms from **[Lark Spectral Lighting](https://faculty.washington.edu/inanici/Lark/Lark_home_page.html)**
(Mehlika Inanici et al., University of Washington; ZGF Architects LLP; EPFL; Oregon State
University; Eindhoven University of Technology) — a prior implementation of the same science — and
**invokes** the **[Radiance](https://www.radiance-online.org/)** (LBNL) and
**[Daysim](https://github.com/MITSustainableDesignLab/Daysim)** (NRC / Fraunhofer ISE) engines as
external subprocesses. It bundles no Lark, Radiance, or Daysim binaries.

The Lark algorithms are distributed under a **Modified 3-Clause BSD License**; its copyright notice
is retained, and this product is named `hcl-mcp` (not "Lark") in compliance with that license.
Radiance, Daysim and all Python dependencies (`fastmcp` — Apache-2.0; `mcp`, `pydantic` — MIT;
`colour-science` — BSD-3-Clause) retain their own licenses.

**→ Full attributions and license texts: [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).**
