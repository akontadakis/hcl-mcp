# hcl-mcp — Human-Centric Lighting MCP Server

A literature-grounded HCL engine exposed as a local **[Model Context Protocol](https://modelcontextprotocol.io)** server. The spectral and circadian methods implement published scientific models directly — Bird & Riordan 1986 (SPECTRL2 clear-sky), Nann & Riordan 1991 (SEDES1 cloud modifier), CIE S 026:2018 (α-opic action spectra), Amundadottir 2016 (nvRD alertness) — see [`docs/literature-bibliography.md`](docs/literature-bibliography.md) for the full citation map and grounding-status index. The engine computes spectral / human-centric-lighting (HCL) metrics, builds and runs the per-channel **Radiance** simulation pipeline, models electric lighting and energy savings, and estimates light-driven alertness — all callable from any MCP client in natural language.

> **Version:** 0.1.0
> ****Methodology:** Bird & Riordan 1986 (SPECTRL2) · Nann & Riordan 1991 (SEDES1) · CIE S 026:2018 (α-opic) · Amundadottir 2016 (nvRD) · Inanici, Brennan & Clark 2015 (3-/9-channel) — see [`docs/literature-bibliography.md`](docs/literature-bibliography.md)
> **Python:** ≥ 3.11
> **Optional engines:** Radiance 6.1a (daylight/electric/glare + native spectral) · Daysim (sub-hourly weather)**

The pure-Python spectral core has **zero runtime dependencies on Radiance or Daysim** — it always runs. The simulation layers follow a strict **run-or-emit** contract: if the binary is present they execute; if not, they return the exact command sequence they *would* have run, so the toolkit is useful even on a machine with no rendering engine installed.

## Install in two lines

In Claude Code:

```
/plugin marketplace add akontadakis/hcl-mcp
/plugin install hcl-mcp@hcl-mcp
```

Restart Claude Code and the 47 lighting tools are live, together with the
`running-hcl-studies` skill. You need [`uv`](https://docs.astral.sh/uv/) on your
`PATH`; Radiance stays optional. Other hosts and the manual route are in
[Installation](#installation) below.

---

<details open>
<summary><strong>Table of Contents</strong></summary>

- [Key Features](#key-features)
- [What It Computes](#what-it-computes)
- [Installation](#installation)
  - [Requirements](#requirements)
  - [Claude Code — plugin (two lines)](#claude-code--plugin-two-lines)
  - [Claude Code (CLI)](#claude-code-cli)
  - [Claude Desktop / other MCP clients](#claude-desktop--other-mcp-clients)
  - [Development setup](#development-setup)
- [The run/emit contract](#the-runemit-contract)
- [Capabilities](#capabilities)
  - [Tools (47)](#tools-47)
  - [Advisories](#advisories)
  - [Resources (14)](#resources-14)
  - [Prompts (13)](#prompts-13)
- [Usage Examples](#usage-examples)
- [Architecture](#architecture)
- [Process Overview & Dataflow](#process-overview--dataflow)
- [Project Structure](#project-structure)
- [Validation Kit](#validation-kit)
- [Configuration](#configuration)
- [Prerequisites & External Engines](#prerequisites--external-engines)
- [Troubleshooting](#troubleshooting)
- [Validation & Accuracy Caveats](#validation--accuracy-caveats)
- [References & Citations](#references--citations)
- [Related Documentation](#related-documentation)
- [Acknowledgements & License](#acknowledgements--license)

</details>

---

## Key Features

- 🌈 **Spectral foundation** — Parse a spectral power distribution (SPD) into the 3-/9-channel bins; compute the full **CIE S 026** α-opic suite (S/M/L-cone, rhodopic, melanopic E / ELR / EDI), photopic/melanopic/neuropic equivalent illuminance, CCT + Duv, mel-DER, and EML.
- ☀️ **Spectral daylight simulation** — Colored Perez sky/sun generation and the per-channel **Radiance** pipeline: point-in-time grids, fisheye eye-level images, and a 2-phase **annual Daylight-Coefficient (DDS)** simulation with circadian dosimetry.
- 🌌 **Physical spectral sky from EPW** — A radiative-transfer spectral sky reconstructed from a standard EPW, replacing the CIE-D-series / air-mass templates with physics: a pure-Python **Bird SPECTRL2** clear-sky engine + **SEDES1** cloud bridge driven by EPW-derived atmosphere (AOD / PWV / ozone) and solar geometry, resampled to 1 nm 380–780 nm. The clear-sky engine is **user-selectable** — `engine="spectrl2"` (default) | `"smarts"` on `spectral_sky_from_epw` / `spectral_epw` / `annual_nvrd` — and a parallel native **Radiance 6.x `gensdaymtx`** engine is exposed as its own tool (all capability-gated). Four atmospheric refinements (declared-wavelength AOD → τ₅₀₀ Ångström conversion; aerosol asymmetry `g`; a settable SMARTS Ångström α; a van Heuklon (1979) ozone climatology) are exposed as **opt-in parameters** (`aod_anchor_nm`, `aerosol_g`, `smarts_aerosol`, `ozone_mode` — every default reproduces the base physics byte-for-bit). *Offline Python stack is unit-tested end-to-end; the native `gensdaymtx` engine AND **SMARTS** have both had first live validations (Radiance 6.1a, NCOMP=20; and SMARTS compiled from the NREL Fortran source — agreeing with SPECTRL2 to ~2–7 %, r≈0.99) — validations, not baselines — the live `physical_sky` flip has now had its first live execution too (2026-07-18, `office_room` + GRC Athens IWEC, Radiance 6.1a + Daysim `ds_shortterm`: 50.03% physical coverage, time-resolved sun — see Validation & Accuracy Caveats), and the physics is opt-in — see [Validation & Accuracy Caveats](#validation--accuracy-caveats).*
- 💡 **Electric lighting** — IESNA **LM-63** photometry parsing, `ies2rad` Radiance conversion, **EnergyPlus**-faithful daylight-responsive controls + energy savings, glare (**evalglare** → UGR/DGP), and **EN 12464-1** interpretation.
- 🧠 **Circadian alertness** — The **nvRD** non-visual direct-response model (Amundadottir 2016) and an automatic annual → alertness bridge driven by Daysim sub-hourly weather.
- ✅ **Compliance** — mel-EDI/EML verdicts against **WELL v2 L03**, **Brown 2022**, **ISO/CIE 8995-1:2025**, and **EN 17037** (automatic EML ↔ mel-EDI conversion), plus **EN 12464-1:2021** task-lighting interpretation through the electric-lighting path.
- 🔌 **Portable & dependency-light** — Pure-Python math runs anywhere; the simulation layers degrade gracefully to emitting their exact command plans when Radiance/Daysim are absent.
- 🔬 **Verifiable** — A built-in `validate()` self-test anchors constants against CIE S 026 published values; every constant is documented against the Lark source line it came from.
- 🧭 **Guided studio journey** — `hcl_studio` conducts a full start-to-finish HCL artificial-lighting study (goal → first-principles fixture design via `recommend_fixtures` → simulate → `build_report`), with a resumable study brief (`save_brief`/`load_brief`).
- 📐 **OBJ/CAD geometry import** — Bring a real Wavefront `.obj` room into the pipeline: `import_geometry` converts it to a per-channel **Radiance** scene with `obj2rad` + `xform`, binds per-group spectral materials (scalar reflectance/transmittance or a measured SPD), normalizes units/axis, and returns `geometry_set`/`material_sets` that drop straight into `run_grid` / `run_annual`. The OBJ carries **no** spectral data — reflectances are user-assigned per group, and unmapped or unrenderable groups **hard-fail** (no silent generic material, no silent empty geometry). The importer **closes the loop to a runnable study**: a named **surface library** + `*.matmap.json` sidecar + `.mtl` *hints* + `dry_run` discovery for fast authoring; **geometry-derived sensors** (auto work-plane grid + eye-level observers at **both seated 1.2 m and standing 1.6 m**, DGP views); **true-north** georeferencing (`north_angle_deg` → `xform -rz`) so the room is correctly oriented to the spectral sky; a **ground↔sky bridge** (`type:"ground"` → a 1-nm `ground_albedo` for `spectral_sky_from_epw(spectral_albedo=…)`); `type:"context"` **exterior-shading** surfaces; `type:"luminaire"` markers as a **drop-in `electric_lights`** payload; a per-aperture true-north orientation report; and a provenance **manifest** (JSON sidecar **+** embedded `.rad` header). The core paths (geometry round-trip, north rotation, IES-luminaire octree, **and the colored-by-material annotate render**) are live-validated on Radiance 6.1a. For methodology-grade sensor placement, the standalone `workplane_grid` (EN 12464-1 illuminance grid) and `observer_points` (workstation eye sensors with seat↔screen pairing) tools provide an explicit, auditable alternative to the `derive_sensors` quick path.

---

## What It Computes


| Domain                    | Quantities                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **α-opic (CIE S 026)**   | Melanopic / S-/M-/L-cone / rhodopic irradiance (E_α), efficacy of luminous radiation (ELR), Equivalent Daylight Illuminance (EDI), D65-normalized`K_D65`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **Circadian metrics**     | Photopic lux;**mel-EDI** (melanopic Equivalent Daylight Illuminance — the CIE S 026 quantity every circadian standard is written in) and **`melanopic_lux`** (the melanopic-weighted illuminance), which are **two different quantities**, not two names for one — they differ by D65's own melanopic/photopic ratio (~1.0997× on the 9-bin route, 1.0432× on the 3-bin route). Thresholds are `≥`, so substituting the larger `melanopic_lux` silently manufactures compliance; score against `mel_edi` only (see [`docs/adr/0001-mel-edi-is-the-circadian-quantity.md`](docs/adr/0001-mel-edi-is-the-circadian-quantity.md)). Plus neuropic lux (9-channel), mel-DER, EML (Equivalent Melanopic Lux) |
| **Color**                 | CCT (Ohno 2013) + Duv                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| **Daylight**              | Point-in-time grid HCL metrics, fisheye FOV-weighted melanopic luminance, annual mel-EDI time series, hours-above-threshold dosimetry, climate-based daylight metrics (DA/cDA/UDI, spatial sDA/ASE), CIE-overcast Daylight Factor, named/persistent sensor sets                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **Physical spectral sky** | EPW-hour atmospheric state (AOD, PWV, ozone, pressure, albedo), solar geometry (zenith / azimuth / air mass), SPECTRL2 clear-sky + SEDES1 cloud-modified 1 nm direct-normal and sky-diffuse spectral irradiance (380–780 nm), spectral ground glow, and annual spectral-sky artifacts (SPD set / band matrix / spectral`.wea` / sidecar)                                                                                                                                                                                                                                                                                                                                                                   |
| **Electric**              | Rated lumens / efficacy / LOR / beam & field angles, zonal flux, daylight-control power fraction & energy savings (kWh/m²·yr)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **Alertness**             | Relative non-visual direct response`R_D(t)` and cumulative dose                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **Fixture design**        | First-principles sizing (lumen method + CIE S 026 mel-DER): required flux, fixture count + spacing-to-height layout, target CCT band, power density, binding constraint (visual vs circadian)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| **Compliance**            | Pass/fail verdicts with thresholds, citations, and measurement conventions                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |

---

## Installation

### Requirements

**Core (always required):**


| Requirement                            | Version           | Notes                                                                    |
| ---------------------------------------- | ------------------- | -------------------------------------------------------------------------- |
| **Python**                             | ≥ 3.11           | from[`pyproject.toml`](pyproject.toml) (`requires-python = ">=3.11"`)    |
| **[`uv`](https://docs.astral.sh/uv/)** | recommend current | used to sync deps & launch the server                                    |
| `fastmcp`                              | ≥ 2.0            | installed automatically by`uv sync`                                      |
| `pydantic`                             | ≥ 2              | installed automatically by`uv sync`                                      |
| `colour-science`                       | ≥ 0.4.4          | installed automatically by`uv sync`                                      |
| `matplotlib`                           | ≥ 3.7            | installed automatically by`uv sync` — required (drives `preview_scene`) |

The four Python deps install automatically via `uv sync`. **The pure-Python spectral core has zero runtime dependencies on any rendering engine — it always runs.**

**Optional external engines** (only needed for the simulation layers — they degrade to emitting their exact command plans if absent, per the [run/emit contract](#the-runemit-contract)):

- **Radiance 6.1a** — one build covers everything: the daylight / electric / glare pipeline (the old `≥ 5.4` floor) AND the native spectral-sky driver `spectral_sky_native` (`gensdaymtx`). 6.1a is a superset, so a single install satisfies both — install an official 6.x release, or build 6.1a from the LBNL source. **Nothing is bundled here** — see [`docs/engines-install.md`](docs/engines-install.md) for the get-source → build → set-env → verify checklist.
- **Daysim** — sub-hourly weather / annual circadian work (`ds_shortterm`, `epw2wea`).
- **SMARTS** (with `$SMARTSPATH` set) — only if you choose `engine="smarts"` for the spectral sky; the default `engine="spectrl2"` needs nothing extra.

See [Prerequisites & External Engines](#prerequisites--external-engines) for where to find and how to install each engine on macOS and Windows.

**→ Full step-by-step manual for macOS / Windows / Linux across five clients: [`INSTALL.md`](INSTALL.md).**
The summary below is the short version.

### Claude Code — plugin (two lines)

This repository is also a Claude Code plugin marketplace. Adding it registers the
server *and* the `running-hcl-studies` skill in one step:

```
/plugin marketplace add akontadakis/hcl-mcp
/plugin install hcl-mcp@hcl-mcp
```

Restart Claude Code, then check with `/mcp` (the server should list as `hcl-mcp`).

The plugin launches the server with `uvx --from git+https://github.com/akontadakis/hcl-mcp hcl-mcp`,
so `uv` must be on your `PATH` — see [Requirements](#requirements). It declares no
environment variables: the server inherits your shell's. If Radiance is not on your
`PATH`, set `HCL_RADIANCE_BIN` (and `RAYPATH`) in your shell profile, or install with the
[Claude Code (CLI)](#claude-code-cli) method below, which takes `--env` flags.

Update or remove later with `/plugin`.

### Claude Code (CLI)

```bash
claude mcp add hcl-mcp -- uvx --from git+https://github.com/akontadakis/hcl-mcp hcl-mcp
```

`uvx` fetches, builds, and caches the server on first run — no clone, no `PYTHONPATH`. Add environment
variables with `--env` (repeatable), e.g. `--env HCL_RADIANCE_BIN=/usr/local/radiance/bin`. Use `-s user` to
register globally instead of per-project; verify with `claude mcp list`.

### Claude Desktop / other MCP clients

Add to your client's MCP config (e.g. `claude_desktop_config.json`). Remove the `//` comments — JSON does not allow them.

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

> VS Code uses `servers` (not `mcpServers`) and needs `"type": "stdio"` — see [`INSTALL.md`](INSTALL.md).

> **⚠️ Running from a local clone?** Use `uv tool install .` (then the launch command is just `hcl-mcp`), **not**
> `uv run --directory …`. `uv run`'s implicit sync can regenerate this project's editable install in a state
> where the bare interpreter cannot import the `src/`-layout packages, and the server fails to start with
> `ModuleNotFoundError: hcl_core`. Details and the fallback in [`INSTALL.md`](INSTALL.md) (Method B).

### Development setup

**Prerequisites:** [`uv`](https://docs.astral.sh/uv/) and Python ≥ 3.11.

```bash
uv sync --extra dev      # install runtime + dev (pytest) deps
uv run pytest -q         # run the full test suite
```

Runtime dependencies (installed automatically): `fastmcp>=2.0`, `pydantic>=2`, `colour-science>=0.4.4`, `matplotlib>=3.7`. All four are hard dependencies — there is no optional-extras group beyond `dev` (pytest).

---

## The run/emit contract

Every tool that touches Radiance or Daysim takes a `run: bool = True` flag and behaves identically:

- **`run=True` and the binary is available** → it **executes** and returns results.
- **`run=False`, or the binary is missing** → it does **not** execute and returns
  `{"ran": false, "commands": [ ...exact ordered shell lines... ], "reason": ...}`.

This means you can design and inspect a full simulation pipeline — sky generation, octree compilation, ray-tracing, matrix multiplication — on any machine, then run the identical commands where an engine is installed. Call `validate()`, `radiance_status()`, and `daysim_status()` first to see which layers will execute vs. emit.

---

## Capabilities

**47 tools · 14 resources · 13 prompts.** *(the server registers 51 tool names: the 47 below plus 4 verb-object aliases — `get_reference`, `list_presets`, `import_weather`, `run_validation` — for clearer AI tool selection.)*

### Tools (47)

🌈 **Spectral core** *(pure Python — always runs)*

- `spd_to_channels` — Average an SPD into the 3- or 9-channel bins.
- `circadian_metrics` — Photopic / melanopic / neuropic equivalent illuminance from channel irradiances.
- `alpha_opic` — CIE S 026 α-opic E/ELR/EDI. Provide `spd` (exact-spectrum route; `.spd` path, text, or `[wl,val]` list) **or** `channels` (binned route).
- `spectral_metrics` — Derived HCL quantities from an SPD: CCT/Duv, mel-DER, mel/photopic ratio, EML ↔ EDI.
- `compliance` — Check a mel-EDI/EML value against a standard (`well_v2_l03` | `brown_2022` | `iso_cie_8995_1_2025` | `en_17037` | `en_12464_1` | `ul_24480`). Return shape is standard-specific: pass/fail (Brown/ISO-CIE), `result_points` 0/1/3 (WELL), `n/a` (EN 17037, non-circadian), `unsupported` (UL 24480, out of scope), and the electric **task** verdict for EN 12464-1 (needs `task`+`em/ugr/uo/ra`, not a `mel_edi`).
- `presets` — List illuminant presets (CIE standards + illustrative LED models), or fetch one by name.
- `glass_transmissivity` — Convert glazing transmittance (0–1) to Radiance transmissivity.
- `write_material` — Write Radiance material `.rad` file(s) (glass / plastic).
- `validate` — Run the built-in correctness self-test (weight sums, α-opic guards, K_D65 vs. published).
- `reference` — Look up HCL reference content (`bins` | `coefficients` | `caveats` | `overview`).
- `recommend_fixtures` — First-principles fixture-design sizing: lumen-method visual flux reconciled with a CIE S 026 mel-DER circadian solve → required flux, count, layout, CCT band, energy, and explicit caveats.

☀️ **Daylight simulation (Radiance)**

- `radiance_status` — Report Radiance availability `{available, bin_dir, version, found, missing}`.
- `quality_presets` — *(pure Python — always runs)* The ambient-accuracy/runtime trade-off, selectable by name instead of inherited by not choosing. Returns the whole table, or one level: **`low`** (`-ab 0` — geometry checks and direct-sun questions; **no interreflection, so DA/sDA/UDI are meaningless there** while ASE stays exact), **`medium`** (`-ab 2` — draft studies, preview convergence), **`high`** (`-ab 3` — reportable DA/sDA/UDI and compliance), **`extra_high`** (`-ab 5` — indirect-dominated scenes, validation against measurement). Each level states what it is *for* and what it cannot support. Nine simulation tools take `quality=`; an explicit `rad_params` always wins, so a tuned string is never silently overridden. **Why it exists:** on a validated annual run the preview-grade default returned sDA **77.78%** where a converged solve returned **100.00%** on identical geometry, with nothing in the return revealing the result was sampling-limited — `annual_daylight` now attaches a `convergence_warning`, plus the `rad_params` that caused it, whenever the ambient settings are too coarse for a threshold metric. Direct-only passes (`-ab 0`, used by ASE) are never flagged, since ambient settings cannot affect them.
- `colored_sky` — Generate a colored Perez sky + sun Radiance definition.
- `run_grid` — Point-in-time grid HCL metrics (oconv → rtrace -I per channel → recombine).
- `run_image` — Fisheye HCL image workflow (rpict → melanopic/neuropic luminance maps).
- `run_annual` — Annual 2-phase DDS HCL simulation → annual mel-EDI + circadian dosimetry.
- `annual_daylight` — Annual climate-based daylight metrics on the grid: per-point **DA** (Daylight Autonomy, fraction of occupied hours ≥ `da_threshold`, default **300 lx**), **cDA** (continuous DA, partial credit `min(1, E/threshold)` averaged over occupied hours), **UDI** (Useful Daylight Illuminance) bins `<100` / `100–300` / `300–3000` / `>3000 lx` (all defaults, overridable via `udi_lower`/`udi_sup`/`udi_aut`), plus the spatial rollups **sDA** (fraction of points with DA ≥ `sda_da_fraction`, default **50%**, i.e. sDA300/50%) and **ASE** (Annual Sunlight Exposure: fraction of points where *direct* sun ≥ `ase_threshold`, default **1000 lx**, for more than `ase_hours`, default **250 h**, of occupied time). Occupancy defaults to weekday `occupied_start`–`occupied_end` (**08:00–18:00**), Monday-anchored across the 8760-hour year (HOY 0 = Monday 00:00); pass an explicit per-timestep `occupancy` mask to override. **Honesty notes:** ASE runs its own dedicated **direct-only (`-ab 0`)** Radiance pass (the DA/UDI pass is the normal total sky+sun, ambient-bounced illuminance) — the two passes are not interchangeable. The tool always simulates the full 8760-hour year (no `period` subsetting yet, unlike `run_annual`); the underlying metrics function accepts a `partial_year` flag for a shorter series, but `annual_daylight` does not currently set it, so `partial_year=True` is not yet observable through this tool. When it *is* set (calling `daylight_metrics` directly), the result carries a `partial_year_note` spelling out the caveat — sDA/DA/UDI become fractions of the supplied occupied hours, and ASE's 250-hour criterion is a **full-year** threshold that a shorter window cannot reach, so a low partial-year ASE means "not enough hours", not "no direct-sun problem". Accepts `points=[...]`/a `.pts` path, or `sensor_set='name'` (see `sensors`). Takes `quality=` (see `quality_presets`); when the ambient settings are too coarse for a threshold metric the result carries a **`convergence_warning`** naming the offending parameters, alongside the **`rad_params`** that produced it. *First live run through the MCP tool end-to-end on the realistic `office_room` + GRC Athens IWEC (2026-07-18, 8760-h year, 45 workplane points): sDA300/50% = 75.6%, ASE1000,250h = 31.1%, DA_avg = 0.71, per-point DA ranges 2.3%–96.6% (far corner → −Y window). The async wrapper is now exercised end-to-end live, not just the core. Two further runs (2026-07-23, `quality="medium"`, 3-channel) gave sDA **66.7% and 82.2%** — the same model, weather, points and settings, run twice. Radiance's ambient calculation is stochastic, so at `-ab 2 -ad 512` seven of 45 points crossed the DA 0.50 threshold between runs; **ASE was 31.11% in every run, bit-identical**, since its direct-only `-ab 0` pass has no ambient sampling to vary. That contrast is the concrete case for `convergence_warning`: preview-grade sDA is not reproducible, so use `quality="high"` for anything you intend to quote. Not a measured/calibrated baseline.*
- `lm83_daylight` — IES **LM-83-12** sDA/ASE with operable blinds **actually operated** per §2.2.6: a **three-phase** transport (view/transmission/daylight matrices with a Klems glazing BSDF) switches each window group's blind state per timestep whenever >2 % of the analysis points see direct sun (floored at 1 point; default blind = **5 % diffuse VLT**, not 20 %). Contrast `annual_daylight`, which computes the same metric arithmetic on whatever shading the scene already has. **Not a submission:** `lm83_method_conformant` is **always false by design** — glazing runs at raw `tvis` (§§2.2.8–2.2.11 out of scope), biasing sDA up — so read `conditions.departures` before quoting anything. Takes `quality=`; elicits confirmation before a long run.
- `daylight_factor` — Daylight Factor (%) per point under the **CIE Standard Overcast Sky** (`gensky -c`, month/day/hour only fix the sun-free overcast dome's solar geometry). `DF = E_indoor / E_outdoor × 100`, where `E_outdoor` is traced from a sky-only exterior reference point (unobstructed upward-facing sensor) — not a fixed constant. Returns `df_per_point`, `df_avg`, `df_min`, `uniformity` (`df_min/df_avg`), and `e_outdoor`. Accepts `points=[...]`/a `.pts` path, or `sensor_set='name'`. *First live run on the realistic `office_room` (2026-07-18, 45 workplane points, CIE overcast sky): DF falls off smoothly from the −Y window (15.87%) to the far corner (0.29%), df_avg = 3.53% — magnitudes plausible for a side-lit office. (The earlier toy-scene run had already found and fixed a sky-file-ordering bug.) Not a measured/calibrated baseline.*
- `weather` — Ingest a `.wea` and/or decompose an analysis period into HOY + wea line numbers.
- `import_geometry` — Import a Wavefront `.obj` room (+ a per-group `material_map`) into a per-channel Radiance scene (`obj2rad` → `xform`): discovers material groups, binds per-group spectral materials, normalizes units (`mm|cm|m|ft`) and up-axis (`Y|Z`), and returns index-aligned `geometry_set`/`material_sets` for `run_grid`/`run_annual`. *Run-or-emit; needs `obj2rad`/`xform` (Radiance 6.1a). Unmapped/mixed-untagged OBJs hard-fail.* **Optional kwargs:** `dry_run` (discovery payload), `sidecar` (`*.matmap.json`), `north_angle_deg` (true-north `-rz`), `derive_sensors` (grid + dual-height `observer_sets` + DGP), `eye_heights`/`workplane_h`/`spacing` (sensor layout), `annotate` (colored-by-material export), `strict` (raise `GeometryHealthError` — `.payload` carries the report — when the embedded health report holds error-severity findings, instead of returning results built on defective geometry). Conditional outputs: `ground_albedo` (→ `spectral_sky_from_epw(spectral_albedo=…)`), `electric_lights` (drop-in luminaires), `context_groups`; always-on `apertures`, `manifest` (JSON sidecar + `.rad` header), and `health` (the same report `check_geometry` returns).
- `check_geometry` — health-check an imported OBJ (non-finite vertex coordinates, coplanar surfaces, blocked window openings, duplicate/non-planar faces, unclosed enclosure, no `type:"floor"` group) without building a scene.
- `workplane_grid` — *(pure Python — always runs)* EN 12464-1 working-plane illuminance grid from a Wavefront `.obj` (requires `material_map`/sidecar): detects the interior extent via per-axis innermost-wall-face analysis, applies the EN 12464-1 cell-size formula `p = 0.2·5^log10(d)` and insets a calc-area margin, then returns cell-centre points. Writes `grid.pts` for direct use with `run_grid` (horizontal task lux + EN 12464-1 compliance).
- `observer_points` — *(pure Python — always runs)* Workstation eye sensors from a Wavefront `.obj`: pairs `seat` ↔ `screen` objects by trailing name suffix, places the eye at the seat centroid at `floor_top + eye_height` gazing toward the screen (with window/azimuth/sweep fallbacks), and returns `observers` + DGP `glare_views`. Writes `observers.pts` for `run_grid`/`run_annual` (vertical mel-EDI) and `glare_ugr`.
- `sensors` — *(pure Python — always runs)* Manage named, persistent daylight sensor sets, reused across `annual_daylight` / `daylight_factor` / `daylight_savings` via `sensor_set='name'` instead of re-passing `points=[...]` every call. `action`: `create` (`name` + either explicit `points=[[x,y,z,dx,dy,dz],...]` or `grid={interior, floor_z, workplane_h?, max_spacing?}` for an EN 12464-1 grid; `overwrite=True` to replace), `list` (all saved sets: name/path/count/source), `get` (a set's points + `.pts` path), `delete`. Sets persist under `work_dir` as `.pts` files plus a JSON registry.
- `photosensors` — *(pure Python — always runs)* Daylight-dimming reference sensors from a Wavefront `.obj` (requires `material_map`/sidecar): locates the dominant glazed facade, builds window-head-height sidelighting zones, and drops one horizontal sensor per zone (centred on the facade, clipped to the floor). Writes a `.pts` for `run_grid`/`run_annual` to drive daylight-linked dimming control.
- `preview_scene` — *(pure Python — always runs; matplotlib is a hard runtime dependency, installed by `uv sync`, not an optional extra)* Diagnostic **matplotlib PNG** scene preview from a Wavefront `.obj` (requires `material_map`/sidecar): draws the true floor polygon plus whichever point layers you pass (grid/observer/photosensor `.pts` or inline rows) and luminaire footprints, in an orthographic plan view and a real `mplot3d` 3D view (points at their true heights, observer gaze arrows, ceiling luminaires + window; box aspect derived from the room's own footprint + height). `render="all"` writes `<prefix>_all_plan.png` + `<prefix>_all_3d.png`; returns `{image_paths, format, render, layers, warnings}`. A **placement check, not** a photometric render (contrast `run_image`).

🌌 **Physical spectral sky (EPW)**

- `atmosphere_from_epw` — *(pure Python — always runs)* Derived atmospheric state (AOD, PWV, ozone, pressure, albedo, aerosol asymmetry `g` + provenance) for an EPW hour. Opt-in refinements (defaults unchanged): `ozone_mode="climatology"` (van Heuklon 1979, from the EPW lat/lon + date) in place of the 300 DU constant; `aerosol_g` override (default 0.65); `aod_anchor_nm` to Ångström-convert a declared-wavelength AOD to τ₅₀₀.
- `spectral_sky_from_epw` — *(pure Python — always runs)* Physical 1 nm spectral sky (direct-normal + sky-diffuse, 380–780 nm) reconstructed from an EPW hour via SPECTRL2 + SEDES1; optional spectral ground glow for a receiver tilt (`surface_tilt_deg`) — gray albedo by default, or a 1-nm **`spectral_albedo`** override (e.g. `import_geometry(...)["ground_albedo"]`). Pick the clear-sky engine with `engine="spectrl2"` (default) | `"smarts"` (SMARTS needs `$SMARTSPATH`). Accepts the same opt-in `ozone_mode` / `aerosol_g` / `aod_anchor_nm` refinements as `atmosphere_from_epw`, plus `smarts_aerosol="user"` to make the SMARTS Ångström α and asymmetry `g` settable (default `"rural"`, unchanged). `cloud_variant` selects which SEDES1 cloud CCM drives the diffuse reshape — `"reanchored"` (default, byte-identical to omitting it) | `"verbatim"` | `"seed"` | `"local"` (your own recalibrated coefficients, requires `ccm_coeffs` — a fitted CSV path from `hcl_core.sedes1_fit`; see [`docs/recalibrating-cloud-ccm.md`](docs/recalibrating-cloud-ccm.md)). Every record's provenance now also carries the CCM's per-wavelength regression uncertainty as `ccm_sigma` (sampled at 400/500/600/700 nm) and `ccm_sigma_mean`; a `"local"` fit additionally records its source CSV path as `ccm_source`.
- `spectral_epw` — *(pure Python — always runs; long-running for a full year)* Emit spectral-sky artifacts (SPD set · band matrix · spectral `.wea` · sidecar) from an EPW over the year (or a subset of hours), written to `work_dir`. Honors the same `engine="spectrl2"` (default) | `"smarts"` selector, plus `ozone_mode` / `aerosol_g` / `aod_anchor_nm` / `smarts_aerosol` / `cloud_variant` / `ccm_coeffs` (same semantics as `spectral_sky_from_epw`).
- `spectral_sky_native` — *(run-or-emit)* Native **Radiance 6.x `gensdaymtx`** spectral sky from an EPW (20-band matrix); runs the binary if present, else emits the exact command plan. *Capability-gated.*

💡 **Electric lighting**

- `ies_analyze` — Parse an IESNA LM-63 luminaire → photometric report (lumens, watts, efficacy, beam/field).
- `ies_to_radiance` — Convert an IES luminaire to a Radiance `.rad` via `ies2rad`, optionally placed via `xform`.
- `colored_luminaire` — Inject a channel triplet into a luminaire `.rad` (writes a new file; never edits input).
- `lighting_controls` — Daylight-responsive lighting-control calculator (EnergyPlus §7.3.5).
- `daylight_savings` — Automated daylight-responsive savings: daylight sim at reference points → controls. `mode="point_in_time"` (default) uses `run_grid` with one or more reference points; `mode="annual"` uses the annual daylight runner (`channel_scenes` + `wea` + `points`, 8760 h) and now supports **multiple reference points** in one call — pass `points=[...]`/a `.pts` path or `sensor_set='name'`, with one `weights` entry (floor-area fraction) per point — rather than a single point at a time. The annual mode elicits confirmation before running (long); a decline returns the emitted command plan instead.
- `glare_ugr` — Render a fisheye (daylight and/or electric) and run `evalglare` → UGR/DGP/glare sources.

🧠 **Circadian alertness**

- `nvrd` — Light-driven alerting response over time (Amundadottir nvRD).
- `reconstruct_spectrum` — Reconstruct a 401-value 380–780 nm @1 nm spectrum from sky+sun channel sets.
- `annual_nvrd` — Annual light-driven alertness (nvRD `R_D`) straight from weather. **Long-running.** Opt-in `physical_sky=True` feeds per-timestep EPW-derived physical sky+sun spectra into the enhanced reconstruction instead of templates (default off); on that path, `engine="spectrl2"` (default) | `"smarts"` picks the clear-sky engine (resolved lazily — only when `physical_sky=True`).

🗓️ **Daysim (sub-hourly weather)**

- `daysim_status` — Report Daysim availability (`ds_shortterm` + `epw2wea`).
- `build_daysim` — Build Daysim from source (clone master + headless CMake).
- `generate_subhourly_wea` — EPW → sub-hourly broadband `.wea` (epw2wea → `.hea` → ds_shortterm).

🧭 **Guided studio journey** *(pure Python — always runs)*

- `save_brief` — Persist (shallow-merge) the resumable study brief to `<work_dir>/<study>/brief.json`. Validates the study slug and rejects unknown phase keys.
- `load_brief` — Load the study brief (or an empty skeleton) to resume the journey where it left off.
- `build_report` — Render the brief to `report.{md,html}`: goal recap, fixture spec, target-vs-achieved pass/fail, mel-EDI↔UGR cross-check, compliance, and caveats. Emit-safe.

### Advisories

Any tool that returns a **dict** may carry an `advisories` list alongside its normal fields — the key
is absent entirely when there is nothing worth flagging (adding an empty `[]` for every clean result
would train callers to stop reading it). Each entry has the shape:

```json
{ "code": "ALBEDO_NOT_MEASURED", "severity": "warn", "message": "…", "field": "albedo" }
```

`field` is only present when the advisory points at a specific key in the result. `severity` means:

- `error` — the result is probably not usable as-is.
- `warn` — the result is usable but easy to misreport.
- `info` — a default was applied that is worth confirming against your brief or standard.

Advisories are **reporting, not physics**: each rule re-reads a field the tool already computed and
phrases a caution about it — nothing is recomputed. They attach at the tool-registration seam (every
one of the 47 tool functions / 51 registered names, wherever the result is a dict), not by decorating
individual tools. See [`docs/adr/0005-advisories-attach-at-the-registration-seam.md`](docs/adr/0005-advisories-attach-at-the-registration-seam.md)
for why.

The nine codes:


| Code                           | Severity   | Fires when                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| -------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `MEL_DER_BINNED`               | warn       | mel-EDI was inferred from binned channels (`mel_der_source == "binned_channels"`) rather than a full SPD — exact for D65, within ~1.5% for smooth spectra, up to ~8% high for a narrow-band source. Walks `run_grid`'s nested per-point blocks, with a per-block message; **exempt on `daylight`**, which is present on every run, costs ~0.13% there, and offers no source spectrum to pass instead — warning on it would be permanent and unactionable. |
| `SPECTRAL_TRANSPORT_SHIFT`     | warn       | The room moved the spectrum ≥5% away from the luminaire's own (`abs(1 - transport_ratio) ≥ 0.05`). Not a defect: `mel_der`/`mel_edi` are the correct AT-POINT values (ADR-0006) and `source_mel_der` holds the luminaire's. It fires because a datasheet figure will not match the reported one, and should not.                                                                                                                                          |
| `ELECTRIC_EXCEEDS_LUMEN_BOUND` | error      | The`electric` block's mean illuminance exceeds sum(luminaire lumens) / grid area (`electric.lumen_bound.exceeded`) — the perfect-utilisation ceiling no real room reaches. Means the block counts light no fixture emitted: classically a sky that reached the "electric-only" octree (ADR-0007), otherwise a double-counted fixture or multiplier.                                                                                                        |
| `ALBEDO_NOT_MEASURED`          | warn       | Ground albedo resolved to the documented default (`provenance.albedo.source == "default"`) rather than an EPW-measured value — checked on both `atmosphere_from_epw`'s top-level `provenance` and `spectral_sky_from_epw`'s nested `atmosphere.provenance` (see ADR-0004).                                                                                                                                                                                 |
| `DOSE_THRESHOLD_IS_DEFAULT`    | info       | Dosimetry was summarised against the built-in 250 lx mel-EDI threshold (`dosimetry.threshold == 250.0`). Value-based, not provenance-based — FastMCP fills unset parameters with their declared default before the tool function runs, so a deliberate 250.0 and an omitted argument are indistinguishable by the time the wrapper sees them.                                                                                                              |
| `ZONE_WEIGHT_REMAINDER`        | warn       | `lighting_controls` / `daylight_savings` zone weights sum to less than 1.0. This is documented, intended behaviour (the remainder is uncontrolled floor billed at full power), so the advisory quantifies the remainder rather than asserting an error — it's a real defect only if the weights came from a different convention than floor-area fractions (e.g. `photosensors` zone weights, Σw≈0.707).                                                 |
| `GEOMETRY_HEALTH_UNCLEAN`      | error/warn | The embedded`health` report has errors, warnings, or unchecked (`skipped`) categories. `error` if `health.ok` is false, `warn` otherwise.                                                                                                                                                                                                                                                                                                                   |
| `NVRD_ZERO_DIVERGENCE`         | warn       | `annual_nvrd`'s single-shot `divergence.neutral_vs_colored_sun.mel_edi_pct` is exactly 0 — almost always a representative timestep that landed pre-sunrise (all sun channels zero) rather than genuine spectral agreement. Quote `RD_series_divergence` instead.                                                                                                                                                                                           |
| `RADIANCE_DROPS_IES_CANDELA_SCALE` | error  | The run's `engine.source_cal` stamp reports `a1_honored: false` — this Radiance build ignores the `ies2rad` A1 candela-scale multiplier, so every IES luminaire emitted at unit scale: electric illuminances are low by each luminaire's own candela scale and glare metrics collapse toward zero. The factor differs per luminaire, so the numbers cannot be rescaled — set `HCL_RADIANCE_SHIM=1` (corrected `source.cal` on RAYPATH) and re-run.        |

**Known v1 gap:** advisories attach only to dict results. `circadian_metrics` with multi-point input
returns a **list** of per-point dicts, and wrapping a list would change that tool's published contract
— so it carries no advisories; check `mel_der_source` per point by hand there. This is also stated in
the server's `instructions` (surfaced to MCP clients that read them).

### Resources (14)

Read-only reference content, addressable by URI. The 14 are **11 fixed resources + 3 URI templates**;
MCP serves those through two different calls, so a client counting `resources/list` alone sees 11 and
finds the remaining 3 under `resources/templates/list`.

- `hcl://reference/coefficients` · `hcl://reference/bins` · `hcl://reference/ies` · `hcl://reference/lighting-controls` · `hcl://reference/daysim` · `hcl://reference/nvrd-bridge` · `hcl://reference/geometry`
- `hcl://reference/caveats` — the §9.3 source-port caveats (markdown)
- `hcl://reference/glossary` — HCL metrics & units glossary (markdown)
- `hcl://index` — one-read catalog of every resource + valid template argument values
- `hcl://preset/{name}` — an illuminant SPD by name (e.g. `D65`, `A`, `LED_4000K`)
- `hcl://action-spectrum/{type}` — a CIE S 026 action spectrum by type
- `hcl://compliance/en_12464_1` · `hcl://compliance/{standard}` — stored compliance threshold tables

### Prompts (13)

Guided workflows that orchestrate the tools:

- `hcl_studio` — **The front door.** Conducts the full start-to-finish HCL artificial-lighting study (goal → first-principles fixture design → simulate → report) over 8 phases, with a resumable study brief.
- `spd_to_circadian` — Turn an SPD into circadian metrics + compliance.
- `hcl_grid_study` — Set up a point-in-time grid HCL analysis.
- `import_obj_room` — Import a Wavefront `.obj`/CAD room (`import_geometry`) into a per-channel scene, then run a grid/annual HCL study.
- `fisheye_eye_analysis` — Fisheye / FOV eye-level circadian analysis.
- `annual_circadian_dose` — Annual circadian dose workflow.
- `annual_daylight_study` — Annual climate-based (photopic) daylight metrics: create/reuse a named `sensor_set`, then `annual_daylight` (DA/cDA/UDI/sDA/ASE), `daylight_factor` (CIE overcast DF), and `daylight_savings` (annual multi-point) — interpreted vs LEED v4 / EN 17037.
- `electric_lighting_design` — Full electric + daylight HCL design pass with savings & EN 12464-1.
- `annual_alertness` — Annual light-driven alertness (nvRD `R_D`) from weather, interpreted relatively.
- `spectral_sky_from_epw` — Reconstruct the physical spectral sky from an EPW hour (`atmosphere_from_epw` → `spectral_sky_from_epw` → `alpha_opic`/`spectral_metrics`), then read its CCT / mel-DER / mel-EDI.
- `place_sensors` — Orchestrates `workplane_grid`, `observer_points`, `photosensors`, and `preview_scene` conversationally for a given OBJ room, then hands the resulting point files to `run_grid` and `glare_ugr` for a full grid + glare pass.
- `visualize_scene` — Guided **matplotlib PNG** preview flow: ensure an OBJ + `material_map`, generate/locate the grid/observer/photosensor `.pts`, then `preview_scene(render="all")` and report the `image_paths` (diagnostic plan + 3D overlays, not a photometric render).
- `explain_concept` — Explain an HCL metric/method/component, grounded in the reference resources.

---

## Usage Examples

> These show the underlying tool calls. In any MCP client you simply ask in natural language (e.g. *"What's the melanopic EDI of D65 and does it pass WELL v2?"*) and the model selects the tools. `channel_type`: **0 = 3-channel, 1 = 9-channel**. `spd` accepts a **`.spd` file path**, SPD text (`"380 v\n381 v … 780 v"`), or `(wavelength, value)` rows.

**1 · SPD → circadian metrics + compliance** *(pure Python — no engine needed)*

```json
{ "tool": "presets",          "arguments": { "name": "D65" } }
{ "tool": "spd_to_channels",  "arguments": { "spd": "<SPD data from step 1>", "channel_type": 1 } }
{ "tool": "alpha_opic",       "arguments": { "channels": [0.10,0.12,0.20,0.30,0.35,0.33,0.25,0.18,0.12], "channel_type": 1 } }
{ "tool": "compliance",       "arguments": { "mel_edi": 250, "standard": "well_v2_l03" } }
```

> `alpha_opic` also accepts `{ "spd": "<SPD data>" }` for the exact (non-binned) integration.

**2 · Colored sky + point-in-time grid** *(3-channel; emits commands if Radiance is absent)*

```json
{ "tool": "colored_sky", "arguments": {
    "diffuse_channels": [0.40, 0.42, 0.45], "direct_channels": [0.85, 0.90, 0.92],
    "channel_type": 0, "month": 5, "day": 13, "hour": 12,
    "lat": 37.9, "lon": 23.7, "utc": 2, "direct": 800, "diffuse": 110, "run": true } }
{ "tool": "run_grid", "arguments": {
    "scene_sets": [["materials.rad", "room.rad", "sky.rad"]],
    "points": "points.txt", "channel_type": 0, "run": true } }
```

**3 · Annual circadian dose**

```json
{ "tool": "generate_subhourly_wea", "arguments": { "epw": "Athens.epw", "timestep_min": 6 } }
{ "tool": "run_annual", "arguments": {
    "channel_scenes": [{ "materials": "materials.rad", "geometry": "room.rad", "sky_color": [0.9, 0.95, 1.0] }],
    "wea": "athens_6min.wea", "points": "points.txt", "channel_type": 0,
    "dosimetry_threshold": 250, "run": true } }
```

**4 · Electric lighting design + glare**

```json
{ "tool": "ies_analyze",       "arguments": { "ies": "fixture.ies" } }
{ "tool": "lighting_controls", "arguments": {
    "itot_per_point": [320], "iset": 500, "control_type": "ContinuousOff", "p_rated": 448 } }
{ "tool": "glare_ugr", "arguments": {
    "scene_sets": [["materials.rad", "room.rad", "sky.rad"]], "channel_type": 0, "run": true } }
```

**5 · Annual climate-based daylight metrics** *(reuse a named sensor set across the daylight tools)*

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
{ "tool": "daylight_savings", "arguments": {
    "mode": "annual", "channel_scenes": [{ "materials": "materials.rad", "geometry": "room.rad", "sky_color": [0.9, 0.95, 1.0] }],
    "wea": "athens.wea", "sensor_set": "wp", "weights": [0.5, 0.5], "run": true } }
```

> `annual_daylight` returns per-point **DA/cDA/UDI** + spatial **sDA/ASE** (ASE via its own direct-only `-ab 0` pass); `daylight_factor` adds the CIE-overcast **DF %**. The `annual_daylight_study` prompt orchestrates the whole chain conversationally.

**6 · Guided studio journey — design the fixtures and grade the result** *(the front door)*

In any MCP client you just say *"design human-centric lighting for a 6×4×3 m office targeting WELL mel-EDI 250 and run a study."* The `hcl_studio` prompt then conducts all 8 phases; the fixture-design and reporting steps are pure-Python and always run:

```json
{ "tool": "recommend_fixtures", "arguments": {
    "length_m": 6, "width_m": 4, "height_m": 3, "mount_height_m": 2.8,
    "target_em_lux": 500, "target_mel_edi": 250 } }
{ "tool": "save_brief",   "arguments": { "study": "office_a", "brief": { "fixture_spec": "<result above>" } } }
{ "tool": "build_report", "arguments": { "study": "office_a", "brief": "<accumulated brief>" } }
```

> `recommend_fixtures` returns the *required* flux, fixture count, layout, CCT band, energy, and the binding constraint (visual vs circadian) — a starting spec you then match with a real IES and confirm with `run_grid`.

**→ See [`docs/operating-guide.md`](docs/operating-guide.md)** for the full end-to-end operating guide: the run/emit model in depth, the exact tool chain for each workflow (including the **studio journey, §G**), work-dir resolution, and prerequisites.

---

## Architecture

Five modules in four layers, strict discipline. Imports point **downward** only, so knowing
which layer a tool lives in tells you what it needs to run:

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
│                Imported by every module above.                           │
└──────────────────────────────────────────────────────────────────────────┘
```

`hcl_radiance` and `hcl_daysim` are **peers**, not stacked layers: they sit side by side above
`hcl_core`, and the one edge between them is the annual nvRD pass borrowing Daysim's sub-hourly
`.wea` generator. Both run engine subprocesses and write simulation output; everything below
them is pure Python.

The layer separation is **enforced, not conventional**: `hcl_core` has **zero dependency on the Radiance/Daysim binaries** (the property that matters for portability — the spectral core always runs), and it is import-pure — `tests/test_module_layering.py` walks `src/` and fails the suite on any import above a module's layer. (The EPW `LOCATION` parser used to break that rule; it now lives in `hcl_core/epw_location.py` and is re-exported from `hcl_daysim.epw`, so the `.wea` writers and the analysis scripts import it exactly as before.) The one remaining caveat is the optional **SMARTS oracle** (`hcl_core/spectral_engine/smarts.py`), the single core path that shells out, capability-gated on `$SMARTSPATH`. All **Radiance/Daysim** subprocess transport lives in `hcl_radiance` / `hcl_daysim`; the MCP layer holds no business logic.

---

## Process Overview & Dataflow

Every tool is a node in one of a few dataflows. The MCP layer is a thin dispatcher with **no domain logic** — it routes each call down to `hcl_core` (pure Python, always runs), `hcl_radiance` (run-or-emit), or `hcl_daysim`. All inputs reduce to a small set of canonical artifacts — an **SPD**, a **channel vector**, a Radiance **scene**, an **EPW**, an **IES** luminaire — and the pipelines below convert between them, converging on circadian metrics, a compliance verdict, or a study report.

```
  INPUTS                              ENGINE  (hcl_mcp dispatch → core / radiance / daysim)            OUTPUTS
  ──────                              ───────────────────────────────────────────────────             ───────

                            ┌──────────────────────────────────────────────────────────┐
                            │  hcl_mcp — FastMCP server: 47 tools · 14 resources · 13 prompts │
                            │  no domain logic — maps each call to a layer below            │
                            └──────────────────────────────────────────────────────────┘

  A · SPECTRAL CORE   (hcl_core — pure Python, always runs)
  SPD data ─┬─ spd_to_channels ─► channels[3|9] ─┬─ alpha_opic ───────► α-opic E/ELR/EDI, mel-EDI ─┐
  preset ───┘   (or exact SPD ─────────────────► )├─ circadian_metrics ► photopic/melanopic/neuropic lux, EML ├─► compliance
                                                  └─ spectral_metrics ─► CCT/Duv, mel-DER, EML↔EDI ┘   └─► PASS/FAIL + citations
                                                                                                          (WELL · Brown · ISO/CIE · EN)

  B · DAYLIGHT SIMULATION   (hcl_radiance — run-or-emit)
  channels ─► colored_sky ─► sky.rad ─┐
  scene (.rad materials + geometry) ──┼─► run_grid  ─► oconv → rtrace -I ×channel → recombine ─► grid HCL metrics
                                      ├─► run_image ─► rpict ×channel ──────────────────────► melanopic/neuropic luminance maps
  weather (.wea) ─────────────────────┴─► run_annual ─► 2-phase DDS (DC matrices) ─────────► annual mel-EDI series ─► dosimetry

  C · PHYSICAL SPECTRAL SKY   (hcl_core — pure Python; native variant run-or-emit) — detailed view below
  EPW + (m,d,h) ─► atmosphere + solar geometry ─► SPECTRL2 + SEDES1 ─► SpectralSkyRecord ─► channels · reconstruction · emitters · α-opic
  optional correction layers (default-off): clear-sky bias K(λ) inserted pre-cloud-modifier · Perez anisotropic façade colour as a record consumer

  D · ELECTRIC LIGHTING   (hcl_core analysis + hcl_radiance render)
  IES (LM-63) ─┬─ ies_analyze ───────────────────────► photometric report (lumens · efficacy · LOR · beam/field)
               └─ ies_to_radiance ─► .rad ─► colored_luminaire ─► luminaire.rad ─┐
  scene + sky ─────────────────────────────────────────────────────────────────┴─► glare_ugr ─► UGR/DGP + glare sources
  illuminance @ points ─► lighting_controls ─► power fraction ─► daylight_savings ──────────► energy savings (kWh/m²·yr)

  E · CIRCADIAN ALERTNESS   (hcl_daysim sub-hourly → hcl_core nvRD)
  EPW ─► generate_subhourly_wea ─► sub-hourly .wea ─► annual_nvrd ─┬─ reconstruct_spectrum ─► per-nm SPD (sky+sun)
                                                                   └─ nvrd ─► R_D(t) alerting response + cumulative dose

  F · GUIDED STUDIO JOURNEY   (hcl_studio prompt orchestrates — pure Python steps always run)
  goal (room dims · targets) ─► recommend_fixtures ─► fixture spec ─► save_brief ─► [run B / D sims] ─► build_report ─► report.{md,html}
```

Three properties hold across all six pipelines: the **core path always runs** (no engine needed); the **simulation paths run-or-emit** (execute if the binary is present, else return the exact command plan — see [The run/emit contract](#the-runemit-contract)); and **physics is computed once, then consumed** — nothing downstream recomputes it.

### Spectral sky from EPW — detailed view

Pipeline **C** is the flagship path, shown here in full. It transforms one EPW timestamp into a single self-describing spectral record, then derives every external product from it. **Nothing recomputes physics downstream of the engine:** the `SpectralSkyRecord` is the frozen sky-truth, and channels, reconstruction, emitters, and circadian metrics are all *consumers* of it. *(Full math and per-symbol source map: [`docs/spectral-sky-methodology.md` §3](docs/spectral-sky-methodology.md).)*

```
  EPW file + (month, day, hour)
        │
        │  (a) parse hourly row                          ── epw_hourly.parse_epw_hourly / row_for
        ▼
  hourly drivers {DNI, DHI, GHI, T, RH, Td, P, sky-cover, AOD?, albedo?}
        │
        ├──(b) atmosphere.derive ───────────────► AtmosphericState {τ500, α, w, u_O3, P, ρ, provenance}
        │                                          (Gueymard94/Reitan63 PWV; documented defaults)
        ├──(c) solpos.compute (mid-interval hour)► SolarGeometry {z, γs, m, R_v, n}
        │                                          (Cooper-1969 zenith == weather.solar_zenith)
        ▼
  (d) SpectralEngine.compute(atm, geo)  ─────────► ClearSkySpectra (122 pts, 300–4000 nm, W·m⁻²·µm⁻¹)
        │     SPECTRL2 (default) | SMARTS (oracle)    {I_dλ (direct-normal), I_sλ (sky-diffuse-horiz)}
        ▼
  (e) CloudModifier.apply(clear; DNI,DHI,GHI,Kt)► all-sky ClearSkySpectra (full range) + {k_dir,k_dif,Kt}
        │     SEDES1: energy-rescale (always) + CCM(λ,Kt) diffuse reshape
        ▼
  (f) resample_to_1nm  (×0.001 µm→nm) ───────────► (I_dλ, I_sλ) on 380–780 nm @1 nm, W·m⁻²·nm⁻¹
        ▼
  ╔══════════════════════════════════════════════════════════════════╗
  ║  SpectralSkyRecord  (canonical sky-truth, frozen, self-describing) ║
  ║   direct_normal[401], sky_diffuse_horizontal[401] @1 nm           ║
  ║   + broadband {DNI,DHI,GHI,Kt} + atmosphere + geometry + provenance║
  ╚══════════════════════════════════════════════════════════════════╝
        │
        ├──(g) ground_for_receiver(rec, tilt, ρ(λ)) ─► ground_glow[401]   (tilted/vertical receivers)
        ├──(h) to_channels(rec) ─────► colored_sky (3/9-band physical channels)
        ├──(h) to_reference(rec) ────► reconstruct_spectrum (sky_spd + sun_spd)
        ├──(i) emitters ─────────────► 1nm SPD set / 20-band matrix / spectral .wea / augmented EPW
        └──(j) alpha_opic_from_spd ──► E_α, mel-EDI  (CIE S 026 circadian metrics)
```

**Boundary data structures** — the only types that cross stage edges: `dict` (EPW row) → `AtmosphericState` + `SolarGeometry` → `ClearSkySpectra` (native, full-range) → `ClearSkySpectra` (all-sky, full-range) → `SpectralSkyRecord` (1 nm, visible, canonical). Every downstream consumer reads only the last one.

**One timestep** (`record_from_epw`): parse the EPW row and location → shift to the mid-interval hour (EPW hours are hour-*ending*) → derive solar geometry (`solpos.compute`) and atmospheric state (`atmosphere.derive`) → hand both to `build_record`.

**The orchestrator** (`build_record`): a night guard short-circuits to a zeroed record when the sun is at/below the horizon (`zenith ≥ 90°`); otherwise it runs the clear-sky **engine** → computes the clearness index `Kt = clamp(GHI / (I0·cosz), 0, 1.2)` → applies the **cloud** modifier (energy-rescale always on, CCM diffuse reshape) → resamples to 1 nm → freezes the `SpectralSkyRecord` with full provenance.

**Annual loop** (`annual_records`): one record per EPW data row (~8760), with an optional hours-subset filter. ~50% of hours are night and short-circuit at the orchestrator's night guard → cheap zero records, so a full year stays tractable.

> For the exact tool chain behind each pipeline above — work-dir resolution, prerequisites, and the run/emit model in depth — see [`docs/operating-guide.md`](docs/operating-guide.md).

---

## Project Structure

```
hcl-mcp/
├── src/
│   ├── hcl_core/            # Pure-Python spectral math (the verifiable asset)
│   │   ├── alpha_opic.py    #   CIE S 026 α-opic E/ELR/EDI integrals
│   │   ├── data.py          #   bins, weight vectors, constants
│   │   ├── _spectra.py      #   401-pt action spectra, V(λ), D65
│   │   ├── spd.py           #   SPD parsing & channel binning
│   │   ├── metrics.py       #   photopic/melanopic/neuropic lux
│   │   ├── spectral_metrics.py  # CCT/Duv, mel-DER, EML
│   │   ├── compliance.py    #   WELL / Brown / ISO-CIE / EN verdicts
│   │   ├── nvrd.py          #   Amundadottir alertness model
│   │   ├── spectral_reconstruct.py  # per-nm reconstruction (annual→nvRD)
│   │   ├── ies.py           #   IESNA LM-63 photometry
│   │   ├── lighting_controls.py     # EnergyPlus daylight controls
│   │   ├── daylight_metrics.py      # climate-based photopic metrics: DA/cDA/UDI/sDA/ASE (consumes annual lux matrix)
│   │   ├── lm83.py · klems.py       # LM-83-12 §2.2.6 blind-operation policy + sDA basis · Klems glazing BSDF (three-phase T matrix)
│   │   ├── fixtures.py       #   first-principles fixture-design engine (recommend_fixtures)
│   │   ├── epw_hourly.py · epw_location.py · solpos.py · atmosphere.py  # EPW hour/LOCATION → atmosphere + solar geometry
│   │   ├── cloud_modifier.py · _sedes1_data.py · _sedes2_data.py · sedes1_fit.py  # SEDES1 cloud bridge (CCM + energy-rescale) · SEDES2 tabulated coefficients (opt-in) · local CCM re-fit
│   │   ├── spectral_sky.py · spectral_pipeline.py     # SpectralSkyRecord + EPW→record pipeline
│   │   ├── spectral_emit.py · spectral_validate.py    # artifact emitters + validation
│   │   ├── spectral_engine/  #   pluggable clear-sky engines
│   │   │   ├── base.py · _spectrl2_data.py · spectrl2.py  # pure-Python Bird SPECTRL2 port
│   │   │   └── smarts.py     #   SMARTS 2.9.5 oracle (capability-gated)
│   │   ├── glazing.py · clearsky_bias.py              # glazing deconfound, for an SPD that did cross glass (assumed τv) · clear-sky bias K(λ) (opt-in)
│   │   ├── perez_distribution.py · sky_radiance.py · receiver.py  # anisotropic diffuse wrapper (orientation-dependent façade colour)
│   │   ├── skyspectra.py                              # P4 external SKYSPECTRA-dataset loader (cross-validation)
│   │   ├── weather.py · _recon_data.py · proc.py      # .wea import · reconstruction templates · subprocess helper
│   │   ├── materials.py · presets.py · surface_library.py · luminaire.py · dosimetry.py · validation.py
│   │   │                              # surface_library.py = named surface catalog for OBJ material_map strings (illustrative scalars; source-gated `measured` flag for real SPDs)
│   ├── hcl_radiance/        # Radiance adapter (run-or-emit)
│   │   ├── sky.py · grid.py · image.py · image_commands.py · commands.py · runner.py · discover.py
│   │   ├── annual.py · annual_commands.py · annual_results.py · annual_nvrd.py · ies_radiance.py
│   │   ├── annual_daylight.py · daylight_factor.py · sky_overcast.py  # photopic DA/cDA/UDI/sDA/ASE runner · Daylight Factor (gensky -c) · CIE overcast sky builder
│   │   ├── threephase.py · threephase_commands.py · aperture.py  # three-phase transport (V/T/D matrices) · command builders · window-aperture extraction
│   │   ├── lm83_run.py · lm83_sun.py  # LM-83 runner (blind-state switching over the year) · direct-sun trigger pass
│   │   ├── source_cal.py             # HCL_RADIANCE_SHIM: corrected source.cal (ies2rad A1 multiplier) on RAYPATH
│   │   ├── spectral_native.py        # native Radiance 6.x gensdaymtx driver (capability-gated)
│   │   ├── geometry_obj.py           # pure Wavefront .obj/.mtl parser (vertices/faces/normals, mesh quality, markers, hints)
│   │   ├── geometry_import.py        # .obj → per-channel Radiance scene (library/sidecar/sensors/north/ground-albedo/context/electric_lights/manifest)
│   │   ├── sensor_layout.py          # geometry-derived work-plane grid / eye observers / DGP views (pure Python)
│   │   ├── sensor_methodology.py     # standalone EN 12464-1 workplane_grid + workstation observer_points (pure Python — no Radiance needed)
│   │   ├── sensor_daylight.py        # photosensors: daylight-dimming reference sensors (glazed-facade zones, pure Python)
│   │   ├── sensor_sets.py            # named, persistent .pts sensor sets (sensors.json registry; reuses EN 12464-1 grid)
│   │   ├── footprint.py              # room floor-slab footprint polygons + point clipping (pure stdlib)
│   │   ├── scene_preview.py          # preview_scene diagnostic renderer: pure-stdlib geometry extraction + matplotlib PNG plan/3D (Agg backend; shape-adaptive box aspect)
│   │   ├── geometry_health.py        # check_geometry backend: non-finite verts, coplanar/duplicate/non-planar faces, blocked openings, unclosed enclosure
│   │   ├── masks.py                  # ipRGC field-of-view masks — consumed by image.py for fisheye eye-level melanopic weighting.
│   │   │                             #   NOTE: the four Khademagha retinal-region .hdr masks are NOT bundled (no redistribution right).
│   │   │                             #   The faithful path activates only when you supply them yourself in `mask_dir`
│   │   │                             #   (`1_upper_inner.hdr` · `2_lower_inner.hdr` · `3_upper_outer.hdr` · `4_lower_outer.hdr`);
│   │   │                             #   otherwise an explicitly APPROXIMATE synthesis fallback is used and flagged in the result.
│   ├── hcl_daysim/          # Daysim adapter (sub-hourly weather)
│   │   ├── subhourly.py · epw.py · commands.py · build.py · discover.py · runner.py
│   ├── hcl_platform/        # Cross-platform compat layer (stdlib-only; used by all layers)
│   │   ├── paths.py · exe.py · textio.py  # forward-slash rad paths · .exe/PATHEXT exe resolution · LF-normalized text I/O
│   └── hcl_mcp/             # FastMCP server
│       ├── server.py · prompts.py · resources.py · clientfeatures.py · studio.py  # prompts.py = 13 guided prompts · resources.py = 14-resource registry · studio.py = brief store + report renderer
│       ├── advisories.py    #   the 9 advisory rules + the registration-seam wrapper that attaches
│       │                    #   them to every dict-returning tool (see docs/adr/0005)
├── tests/                   # 149 test files · 1923 tests
├── docs/
│   ├── operating-guide.md · technical-reference.md · hcl-methodology.md   # operating guide · methodology+citations map · whole-system science
│   ├── spectral-sky-methodology.md · spectral-sky-as-built.md  # spectral-sky physics · as-built + deviations ledger
│   ├── spectral-engine-comparison.md · spectral-engine-radiance-deep-dive.md · spectral-engine-validation.md  # SPECTRL2/SMARTS/gensdaymtx: head-to-head · angular+cross-city · corrections & external cross-validation (canonical)
│   ├── literature-bibliography.md     # cited-source map
│   ├── engines-install.md · radiance-6-build.md · smarts-build.md · recalibrating-cloud-ccm.md  # engine install+verify checklist · Radiance/SMARTS build guides · SEDES1 CCM re-fit
│   ├── adr/                           # architecture decision records (0001 mel-EDI · 0002 tolerance unit-scale ·
│   │                                  #   0003 sample duration · 0004 sub-physical EPW values · 0005 advisory seam ·
│   │                                  #   0006 mel-DER at the point · 0007 scene role by content)
│   ├── Coefficient provenance/        # fig11_CCM_coefficients.csv — the digitized SEDES1 CCM table (source PDFs and digitization artifacts not redistributed)
│   └── img/spectral-deep-dive/        # figures embedded by spectral-engine-radiance-deep-dive.md
├── scripts/                 # live-validation drivers + captured output (referenced from Validation & Accuracy Caveats)
│   ├── live_validation_phase2/  # electric/daylight phase-2 runs · apply_source_cal_patch.sh (the Radiance `A1` fix)
│   └── physical_sky_live/       # the 2026-07-18 physical_sky Daysim/DDS live run driver + captured out/
├── skills/running-hcl-studies/SKILL.md  # shipped Claude Code skill for DRIVING the tools (symlinked into ~/.claude/skills/)
├── hcl_validation/          # End-to-end chat/MCP validation kit (BYO-data driven)
│   ├── GUIDE.md · TEST-PLAN.md · README.md · INPUT-DATA-CHECKLIST.md  # beginner→reference walkthrough · assertion-driven test plan · overview · input-data checklist
│   ├── inputs/              # active_inputs.json selector + geometry/ · luminaires/ · sensors/ · spd/ · weather/ (office_room OBJ/RAD, L09 IES/SPD, Athens IWEC EPW)
│   ├── test_room/           # Blender source models (office_room ± corner-window ± blinds .blend)
│   └── results/             # run-output landing (README; generated results/work/ is git-ignored)
├── .claude/agents/          # hcl-mcp-tester validation subagent (Claude Code)
├── CONTEXT.md               # single-context domain notes
├── INSTALL.md · LICENSE · THIRD-PARTY-NOTICES.md · pyproject.toml · uv.lock · pyrightconfig.json
└── .gitignore
```

---

## Validation Kit

[`hcl_validation/`](hcl_validation/) is a self-contained, end-to-end kit for testing the server **through real chat tool-calls** — not unit-test scripts — from connection to final report. It's the complement to the `tests/` suite: `tests/` verifies the Python math in isolation, `hcl_validation/` exercises the whole MCP surface the way a user actually drives it (every tool called live, every resource read, every prompt rendered).

**What's in it**


| Path                                                                             | What it is                                                                                                                                                                                                                                                |
| ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`README.md`](hcl_validation/README.md) · [`GUIDE.md`](hcl_validation/GUIDE.md) | Orientation, then the full connect → verify → run → bring-your-own-data → drive-the-prompts walkthrough (incl.**Appendix A**: installing the optional engines on macOS / Linux / Windows)                                                             |
| [`TEST-PLAN.md`](hcl_validation/TEST-PLAN.md)                                    | The ordered test matrix — every tool / prompt / resource with its expected result and PASS/FAIL assertion                                                                                                                                                |
| [`INPUT-DATA-CHECKLIST.md`](hcl_validation/INPUT-DATA-CHECKLIST.md)              | The complete list of input data a full HCL run needs                                                                                                                                                                                                      |
| `inputs/`                                                                        | Ready-to-run sample data: an`office_room` OBJ (± corner-window, ± blinds) with material maps + hand-authored `.rad` scenes, an Athens IWEC EPW, L09 IES fixtures + SPDs, and sensor point sets. `active_inputs.json` is a mostly-`"auto"` selector      |
| `test_room/`                                                                     | The Blender source models the OBJs were exported from                                                                                                                                                                                                     |
| `results/`                                                                       | Where a run lands its output — one folder per workflow (`W0`…`W9`, plus negative / cross-tool / energy / argument sweeps), each with a reviewable `RESULTS.md` and a top-level `VALIDATION-REPORT.md` roll-up. Generated `results/work/` is git-ignored |

**Drop-and-run, bring your own data.** The kit is auto-discovering: drop a file with the right **extension** into the matching `inputs/` subfolder (`<name>.obj`+`.mtl`, `<name>.epw`, `<name>.ies`, `<name>.spd`, `<name>.pts`) and it's picked up automatically — no JSON editing. A bare `<name>.obj` + `<name>.mtl` even auto-generates an illustrative material map so it runs end-to-end.

**Live vs. emit.** The pure-Python spectral core always runs; the simulation tools call external engines (Radiance / Daysim / SMARTS). Whichever you have installed run live — the rest emit their exact command plan (`{"ran": false, "commands":[…]}`), a valid capability-gated result scored **PASS(emit)**, not a failure.

**How to run it.** Connect the server (see [Configuration](#configuration) / [Installation](#installation)), then from the main chat launch the bundled tester subagent:

> Use the **hcl-mcp-tester** agent ([`.claude/agents/hcl-mcp-tester.md`](.claude/agents/hcl-mcp-tester.md)) to run the full validation against `hcl_validation/TEST-PLAN.md`.

It acts as the user, drives every tool live, judges each result, and writes `hcl_validation/results/VALIDATION-REPORT.md`. (Slash-command prompts can't be triggered by a subagent, so you drive those yourself — the walkthrough is in [`GUIDE.md`](hcl_validation/GUIDE.md) Part 5.)

---

## Configuration

Environment variables (all optional):


| Variable           | Purpose                                                                | Default                                 |
| -------------------- | ------------------------------------------------------------------------ | ----------------------------------------- |
| `PYTHONPATH`       | Only for a local clone launched from source — set to the `src` dir. Not needed with `uvx` / `uv tool install .` (see [`INSTALL.md`](INSTALL.md)) | —                    |
| `HCL_WORK_ROOT`    | Directory where simulation files are written                           | first MCP client root, else`~/hcl_work` |
| `HCL_RADIANCE_BIN` | Radiance`bin` directory, if not on `PATH`                              | auto-discovered on`PATH`                |
| `HCL_DAYSIM_BIN`   | Daysim`bin` directory (`ds_shortterm`, `epw2wea`)                      | auto-discovered on`PATH`                |

**work_dir precedence:** explicit tool argument → `HCL_WORK_ROOT` → first MCP client root → `~/hcl_work`.

---

## Prerequisites & External Engines


| Layer                                             | Needs                                                                                     | Notes                                                                                                                                                                                                                                                                                                                             |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Spectral core**                                 | nothing                                                                                   | Pure Python — always runs.                                                                                                                                                                                                                                                                                                       |
| **Daylight / electric / glare + native spectral** | [Radiance](https://www.radiance-online.org/) **6.1a** (one build — superset of `≥ 5.4`) | Provides`oconv`, `rtrace`, `rpict`, `gendaylit`, `gendaymtx`, `rfluxmtx`, `rcontrib`, `dctimestep`, `ies2rad`, `evalglare`, `obj2rad`, `xform` AND the spectral `gensdaymtx` / `rcomb` from a single install. **Not bundled** — install an official 6.x release or build from the LBNL source ([`docs/engines-install.md`](docs/engines-install.md)). Without it, tools emit their command plans. |
| **Sub-hourly weather**                            | [Daysim](https://github.com/MITSustainableDesignLab/Daysim) (`ds_shortterm`, `epw2wea`)   | Source-available (NRC/Fraunhofer-ISE),**not bundled** — build from source via `build_daysim`. Only needed for the `annual_nvrd` alertness bridge.                                                                                                                                                                                |
| **Spectral RT oracle** (opt-in)                   | [SMARTS 2.9.5](https://www.nrel.gov/grid/solar-resource/smarts.html) (Gueymard)           | **Not bundled** — obtain 2.9.5 from NREL and compile the Fortran source ([`docs/engines-install.md`](docs/engines-install.md)). Only when you pass`engine="smarts"`. `$SMARTSPATH` must name the `smarts295bat` **executable file**, kept beside its data dirs — a directory is rejected. Default `engine="spectrl2"` is pure Python and needs nothing.                                                                                                                                             |

### Where to find & how to install (macOS / Windows)

None of these ship with `hcl-mcp` — it invokes them as external subprocesses and bundles **no binaries and no source**. **Agent-runnable checklist: [`docs/engines-install.md`](docs/engines-install.md)** (get source → build → set env → verify). Install the ones you need, put their executables on `PATH` (or point the `HCL_*_BIN` env vars at them), then re-run `radiance_status()` / `daysim_status()` to confirm discovery.

#### Radiance 6.1a (one version — classic pipeline + native `gensdaymtx`)

**Recommended (one version for everything):** install an official **Radiance 6.1a** release, or build 6.1a from the LBNL source (the build steps below
cover both). 6.1a is a superset of the old `≥ 5.4` requirement, so a single
install drives both the daylight / electric / glare pipeline and the native `spectral_sky_native`
(`gensdaymtx`) — build the **full toolset**, not the spectral subset only.

- **macOS / Linux** — Xcode Command Line Tools (`xcode-select --install`) + CMake (`brew install cmake`),
  then `cmake .. -DCMAKE_INSTALL_PREFIX=$HOME/radiance6 && make && make install` from a `build/` dir under the
  unpacked Radiance source tree. Put `bin` first on `PATH` and set `RAYPATH` (so `gensdaymtx` finds `mie_ca.dat`):

  ```bash
  export PATH="$HOME/radiance6/bin:$PATH"
  export RAYPATH=".:$HOME/radiance6/lib"
  ```

  Verify with `rtrace -version` (shows `RADIANCE 6.1a`). (Alternatively, point `HCL_RADIANCE_BIN` at the `bin`
  dir instead of editing `PATH`.)
- **Windows** — Visual Studio Build Tools (C++), CMake, and Git; build from the LBNL source, or download an
  official **6.x** installer/`.zip` from the releases page. Add `bin` to **PATH** and set **RAYPATH** to `lib`.
  Verify with `rtrace -version`.

**Alternative:** official builds — **[github.com/LBNL-ETA/Radiance/releases](https://github.com/LBNL-ETA/Radiance/releases)**
(also HEAD builds at [radiance-online.org](https://www.radiance-online.org/download-install/CurrentReleaseInstall)).
Use a **6.x** release if you want both the classic and spectral paths; an older `≥ 5.4` release covers only the
classic pipeline and lacks `gensdaymtx`. For the macOS official release: download the archive, extract it (e.g.
to `/usr/local/radiance`), add to `~/.zshrc`:

```bash
export PATH="/usr/local/radiance/bin:$PATH"
export RAYPATH=".:/usr/local/radiance/lib"
```

First launch may be blocked by Gatekeeper — clear the quarantine flag: `xattr -dr com.apple.quarantine /usr/local/radiance`. Verify with `rtrace -version`. For Windows: the installer sets `PATH`/`RAYPATH` for you; for the `.zip`, extract to e.g. `C:\Radiance` and add `C:\Radiance\bin` to **PATH** and set **RAYPATH** to `C:\Radiance\lib`.

> The native `gensdaymtx` (20-band spectral) path has had its **first live validation** against Radiance 6.1a
> (NCOMP=20 confirmed; loose-envelope agreement with the offline Python engine — first validation, not a
> known-good baseline). See [Validation & Accuracy Caveats](#validation--accuracy-caveats).

#### Daysim (`ds_shortterm`, `epw2wea`) — build from source

Not bundled and there are no current official prebuilt binaries — the `build_daysim` tool clones **[github.com/MITSustainableDesignLab/Daysim](https://github.com/MITSustainableDesignLab/Daysim)** and builds it headless. Only needed for the `annual_nvrd` alertness bridge. Build prerequisites:

- **macOS** — Xcode Command Line Tools + CMake + Git:

  ```bash
  xcode-select --install
  brew install cmake git
  ```

  Then call the `build_daysim` tool (a one-line `time_step` source patch may be applied automatically — see `hcl_daysim/build.py`).
- **Windows** — [Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/) (C++ workload, supplies MSVC + the CMake generator), [CMake](https://cmake.org/download/), and [Git](https://git-scm.com/download/win). With those on `PATH`, run `build_daysim`, then point `HCL_DAYSIM_BIN` at the resulting `bin` directory.

#### SMARTS 2.9.5 (optional spectral oracle)

**SMARTS is not bundled here.** Obtain the 2.9.5 distribution from NREL
(<https://www.nrel.gov/grid/solar-resource/smarts.html>, free, licence-gated). The distribution's prebuilt Mac
binary is **PowerPC** (dead on modern macOS), so **compile it from that distribution's Fortran source**
(strip CRLF, flip `batch=.TRUE.`, build with `gfortran -std=legacy` — full steps in [`docs/smarts-build.md`](docs/smarts-build.md)). Then point `$SMARTSPATH` at the resulting `smarts295bat`, kept beside its data dirs:

```bash
brew install gcc                                # provides gfortran
# ...compile smarts295bat from the NREL Fortran source (gfortran -std=legacy)...
export SMARTSPATH="$HOME/smarts/smarts295bat"   # executable FILE, not the directory
```

- **Windows** — use the distribution's `.exe`; set **SMARTSPATH** to the executable **file** itself (e.g. `C:\smarts\smarts295bat.exe`), keeping the `*.txt`/`*.inp` data files and data folders beside it. A directory value is rejected.

Selecting `engine="smarts"` without `$SMARTSPATH` raises a clear `RuntimeError`. This path was **first
live-validated 2026-06-21** (compiled from the NREL 2.9.5 Fortran source to a native arm64 binary; the gated cross-check
`tests/test_smarts.py::test_smarts_cross_check_clear_sky` passes, and SMARTS agrees with the Python SPECTRL2
engine to ~2 % direct / ~7 % diffuse, r≈0.99 — see [`docs/spectral-engine-comparison.md`](docs/spectral-engine-comparison.md)). First validation, not a calibrated baseline — see [Validation & Accuracy Caveats](#validation--accuracy-caveats). The default deck (`smarts_aerosol="rural"`, `S&F_RURAL` aerosol) is byte-identical to before; `smarts_aerosol="user"` is a **resolved, opt-in** refinement (see [`docs/technical-reference.md#7bis6-smarts--the-validation-oracle--selectable-engine-spectral_enginesmartspy`](docs/technical-reference.md#7bis6-smarts--the-validation-oracle--selectable-engine-spectral_enginesmartspy)) that makes the Ångström α and asymmetry `g` settable SMARTS inputs, live-smoke-checked to move direct-normal irradiance monotonically with α.

---

## Troubleshooting


| Symptom                                                                    | Cause & fix                                                                                                                                                                                                                                                          |
| ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Server won't start / `ModuleNotFoundError: hcl_core`**                   | The`src/`-layout packages aren't importable. Set `--env PYTHONPATH=/ABSOLUTE/PATH/TO/hcl-mcp/src` in the MCP registration (see [Installation](#installation)).                                                                                                       |
| **A simulation tool returns `{"ran": false, "commands": […]}`**           | Working as designed — Radiance/Daysim isn't found, so the tool**emits** the command plan instead of running. Run `radiance_status()` / `daysim_status()` to confirm, install the engine or set `HCL_RADIANCE_BIN` / `HCL_DAYSIM_BIN`, then re-call with `run=true`. |
| **`alpha_opic` / `spd_to_channels` raises "no integer-wavelength rows…"** | `spd` must resolve to SPD rows — pass a readable `.spd` **file path**, SPD text (`"380 v\n381 v … 780 v"`), or `(λ, value)` rows. A preset *name* isn't an SPD: use `presets(name=…)` to fetch a standard illuminant's SPD first.                                |
| **`compliance(standard="en_12464_1")` returns `"incomplete"`**             | EN 12464-1 is judged on task parameters, not a `mel_edi` — pass `task` plus the measured `em`/`ugr`/`uo`/`ra` (and surround/background/wall/ceiling values where you have them). With no task parameters the verdict is `"incomplete"` by design, never a vacuous pass. The `hcl://compliance/en_12464_1` resource lists the task table.                     |
| **`build_daysim` fails**                                                   | `cmake` must be installed; the build clones [Daysim](https://github.com/MITSustainableDesignLab/Daysim) and builds `ds_shortterm` + `epw2wea` headless. A one-line `time_step` source patch may be needed (documented in `build.py`).                                |
| **Files written somewhere unexpected**                                     | Output goes to`work_dir`: explicit arg → `HCL_WORK_ROOT` → first MCP client root → `~/hcl_work`. Set `HCL_WORK_ROOT` to pin it.                                                                                                                                   |

---

## Validation & Accuracy Caveats

This toolkit is **honest about what is proven vs. what is latent.** Read this before trusting a *live* run:

- ✅ **The spectral math is verified.** `validate()` anchors `K_D65` against the CIE S 026 published values (within 0.05%), checks weight-sum and scale-invariance properties, and confirms `mel-DER(D65) ≈ 1.0`. Every constant is documented against its Lark source line. Two deliberate fixes over the Lark source are applied (Python-2 integer-division zeroing; a 3-channel bin-ordering misalignment).
- ✅ **The grid daylight pipeline is live-verified** — a unit-radiance hemisphere reproduces `562.345 lux = 179 × π` for both 3- and 9-channel paths under live Radiance 5.4.
- ✅ **OBJ geometry import — live-checked on Radiance 6.1a.** **Four** capability-gated tests pass live: the `obj2rad → xform → oconv → rtrace` round-trip (and the `obj2rad` `-m` qualifier rule — `Group` for group-only OBJs, `Material` for `usemtl`, mixed/unmapped **hard-fail**), a **north-rotation** round-trip, an **IES-luminaire octree build**, and the **colored-by-material `annotate` render** (`oconv → rpict → falsecolor`). The **v2 program (P5–P8)** plus the **v3 program** (correctness + provenance; merged `6cca8e2`, suite 1076/8) are built & shipped (2026-06-26), added **additively** so the v1 return contract is unchanged: surface library + sidecar + `.mtl` hints + `dry_run` discovery, geometry-derived sensors (now **dual seated/standing** `observer_sets`, tunable `eye_heights`/`workplane_h`/`spacing`), true-north `-rz`, a **ground↔sky `spectral_albedo` bridge**, `type:"context"` **exterior-shading** surfaces, a **drop-in `electric_lights`** luminaire payload, a per-aperture (area-weighted) orientation report, and a provenance manifest now written as a **JSON sidecar + embedded `.rad` header**. The frame-consistency property (`-s`/`-rx 90`/`-rz(−north)` applied once across sensors/apertures/luminaires) holds. **Honest limits:** the OBJ/`.mtl` still supplies **no** spectral data (reflectances are user-assigned; `.mtl` is a *hint*). The **measured-SPD path now exists** (a library entry is `measured` only with a citation + readable SPD file), but the *shipped* catalog stays **illustrative scalars** pending data. Deferred: frame-vs-glazing split, auto ground-plane *geometry* synthesis, BSDF/shading-device conventions, glTF/IFC.
- ⚠️ **`R_D` (alertness) is relative only.** The nvRD intensity-response was fit from nighttime electric-light studies; daytime adaptation is unvalidated. A physically-unexplained channel→irradiance constant biases absolute `R_D` (it cancels in ELR/EDI ratios but not in the nonlinear alertness sigmoid). Use `R_D` for *relative* comparisons, not absolute alertness.
- ⚠️ **The enhanced colored-sun reconstruction falls back to constant-zenith (30°) only when solar zeniths are unavailable.** The first live execution of the production path (2026-07-18, `office_room` + GRC Athens IWEC, Radiance 6.1a + Daysim `ds_shortterm`) showed the Daysim sub-hourly adapter DOES surface real per-timestep solar zeniths — `has_enhanced_solar_note` was `false` across both the 15-min (35,040-step) and 6-min (87,600-step) runs, i.e. the air-mass reddening was time-resolved throughout, with no 30° fallback firing. The honest residual: the constant-30° template still fires whenever solar zeniths are genuinely unavailable (e.g. a `_channel_provider` hook that omits them, or a degraded/unavailable Daysim adapter). This is surfaced honestly in the tool output.
- ⚠️ **The electric-lighting path had its first end-to-end live run on 2026-07-18** (realistic `office_room`, 4× L09 downlights, `run_grid`/`glare_ugr` driven from an `electric_lights` payload plus `lighting_controls`) — prior to this it was emit-/mock-tested only. `ies_analyze`, `ies_to_radiance` (the `ies2rad -o` path), `spd_to_channels`, and `colored_luminaire` all ran clean as unit tools; `run_grid`/`glare_ugr` colorized the IES payload internally (no separate `colored_luminaire` chaining needed) and `run_grid` reported the expected `total_wattage` 152 W (4 × 38 W); `lighting_controls` produced a clean dimming curve. **Radiance-build caveat (root-caused + fixed):** the first run showed electric illuminance ~14× too low (~34 lux avg). This was traced **not** to hcl-mcp but to the local custom **Radiance 6.1a build's compiled `source_corr` dropping the `ies2rad` brightdata `A1` (candela-scale) multiplier** — so IES luminaires under-emit by their candela scale. Proven three ways (10× `A1`-arg change → no effect; folding `A1` into RGB → correct; an explicit `source.cal` `flatcorr` override → correct) and fixed by patching `source.cal` (`scripts/live_validation_phase2/apply_source_cal_patch.sh`, needs `sudo`): the office_room 4×L09 electric grid then reads **avg 494 lux (min 363 / max 627)** — realistic, and exactly 14.4× the unpatched value. So the hcl-mcp electric pipeline is correct given a Radiance whose `source_corr` honors `A1`; do **not** fold `A1` into `color_luminaire` (that would double-scale on a stock Radiance). Sky (`gensky`/`gendaymtx`) paths are unaffected. The patch was applied and MCP-verified (2026-07-18): `run_grid` electric then read 412–623 lux across the grid, and `glare_ugr` **UGR=19.24 / DGP=0.199** (2 ceiling-panel sources ~5609 cd/m²) — realistic (UGR≈19 = the standard office limit). The earlier `UGR=0` was **not** a separate issue: it was the same `A1` under-emission (14× too dim → below evalglare's glare threshold → `UGR=0`), resolved by the same patch. Treat this as *"the pipeline moves end-to-end and, with a correct Radiance source.cal, at the right magnitude,"* not an absolute-photometry baseline.
- ⚠️ **`annual_daylight` / `daylight_factor` / `daylight_savings` / `sensors` have had a first live validation on a realistic scene (2026-07-18), not a measured/calibrated baseline.** The DA/cDA/UDI/sDA/ASE math (`hcl_core/daylight_metrics.py`) and the CIE-overcast DF ratio are unit-tested against known inputs; `daylight_factor` and `annual_daylight` (this time including the MCP async wrapper end-to-end, not just the core) both ran live on the realistic `office_room` + GRC Athens IWEC: `daylight_factor` gave df_avg 3.53% (df_min 0.29% far corner → df_max 15.87% near the −Y window), and `annual_daylight` gave sDA300/50% = 75.6%, ASE1000,250h = 31.1% over the full 8760-h year. `daylight_savings` ran both modes live end-to-end: `point_in_time` completed but read `daylight_lux=0` because `run_grid` (unlike `daylight_factor`) adds no sky internally, so the scene needs an explicit sky source — a usage nuance, not a wrapper failure; `annual` mode ran the full 8760-h simulation with per-hour controls (mean_reduction 85.9%, 5.24 kWh/m²/yr, 2,610 occupied hours) — high daylight-harvesting savings, as expected for a well-daylit center reference point in sunny Athens. `annual_daylight`'s dedicated direct-only (`-ab 0`) ASE pass is separate from the total (sky+sun, ambient-bounced) pass used for DA/UDI — treat the two lux matrices as non-interchangeable. `annual_daylight` always simulates the full 8760-hour year; `daylight_metrics()` has a `partial_year` flag but the tool does not yet set it.
- 📐 **Accuracy envelope** (Lark, Pierson 2023): daylight mel-EDI within ±20%; validated for neutral-colored interiors — chromatic / strongly inter-reflecting scenes degrade. 3-channel is an approximation; **9-channel is recommended**, and the exact-from-SPD α-opic path is provided for validation.

**Physical spectral-sky pipeline (EPW → spectral sky)** — read this before trusting a *live* spectral-sky run (canonical wording in [`docs/spectral-sky-as-built.md`](docs/spectral-sky-as-built.md) §9):

- ✅ **The offline Python stack runs end-to-end and is unit-tested.** The EPW → atmosphere/solar-geometry → SPECTRL2 clear-sky → SEDES1 cloud bridge → `SpectralSkyRecord` → artifact path is exercised by the test suite. The SPECTRL2 constants are transcribed **verbatim** from the NREL `spectrl2_2.c` source.
- ⚠️ **Native `gensdaymtx` and SMARTS have both had first live validations.** `gensdaymtx` (Radiance 6.1a, NCOMP=20, loose-envelope agreement with the Python engine). **SMARTS** was first run live 2026-06-21 — compiled from the NREL 2.9.5 Fortran source (that distribution's Mac binary is dead PowerPC); with `$SMARTSPATH` set the gated cross-check passes and SMARTS agrees with the Python SPECTRL2 engine to ~2 % direct / ~7 % diffuse, r≈0.99 ([`docs/spectral-engine-comparison.md`](docs/spectral-engine-comparison.md)). **Both are first validations, not calibrated baselines** (neither is validated against *measured* sky spectra). Selecting `engine="smarts"` without `$SMARTSPATH` raises a clear `RuntimeError`. The live **`physical_sky` Daysim/DDS flip** had its **first live execution on 2026-07-18** (`office_room` + `GRC_Athens.167160_IWEC.epw`, Radiance 6.1a + Daysim `ds_shortterm`): a 15-min-timestep coarse run (35,040 steps, `-ab 1 -ad 256 -aa 0.2 -ar 32`) and a 6-min-timestep run at the tool's default ambient parameters (87,600 steps, `-ab 2 -ad 512 -aa 0.1 -ar 64`) both measured **50.03% physical coverage** — daylight timesteps carry EPW-derived physical sky/sun shapes; night/zero-irradiance timesteps legitimately fall back to the reference-sky/air-mass-sun template by design, so this is **not** full coverage — with **time-resolved sun** throughout (`has_enhanced_solar_note: false`, i.e. no constant-30° fallback fired). This is a **first live execution, not a calibrated baseline** validated against *measured* sky spectra.
- ⚠️ **The SEDES1 CCM's spectral shape under cloud carries real uncertainty** — the default `reanchored` variant is a faithful 10 nm digitization of Nann–Riordan Fig. 11 (the opt-in `seed` variant is the older 9-anchor digitization); only the always-on **energy-rescale is exact**. The per-wavelength regression uncertainty is now surfaced in provenance (`ccm_sigma`/`ccm_sigma_mean`), and the CCM can be locally re-fit via `cloud_variant='local'` (see [`docs/recalibrating-cloud-ccm.md`](docs/recalibrating-cloud-ccm.md)) until validated against measured sky spectra.
- ℹ️ **A tabulated alternative to the digitization exists: SEDES2** (`hcl_core.cloud_modifier.Sedes2Modifier`, opt-in). The same Nann–Riordan regression is **published as a table** in Whitaker & Newmiller 1998 (NREL/SR-520-23942 Table 2-1 — 74 rows, 320–1050 nm @10 nm, free), so it closes the *digitization* caveat, and it carries a **1/cos z zenith term** the three-term SEDES1 quadratic cannot express. It is **not** a drop-in: its independent variable is **NGH** (measured GHI over *estimated clear-sky* GHI), not `Kt` — under clear sky NGH → 1 while `Kt` → ~0.7 — so `Sedes2Modifier.apply` refuses to run without a clear-sky GHI reference rather than evaluating on the wrong variable, and it is **not reachable via `cloud_variant`** (construct the class directly in Python). It remains a **German-site fit**, so it does *not* close site transfer — only a local re-fit does. See [`docs/spectral-sky-methodology.md`](docs/spectral-sky-methodology.md) §8.6(f).
- ⚠️ **Physics (the EPW-derived spectral *shape* of the sky/sun) is opt-in, not the default.** Unless a caller passes `physical_sky=True` (or a `sun_spd`), the enhanced reconstruction uses the reference-sky template with the air-mass colored sun. Note this is about the spectral **shape**, not the sun's geometry: on the production path the air-mass sun is still **time-resolved** via the real per-timestep solar zeniths (see the constant-30° caveat above — the 30° fallback fires only when zeniths are genuinely unavailable, not merely because `physical_sky` is off). The spectral-sky seam is *wired*, not flipped on by default.

For the complete methodology, math derivations, and per-module source map, see [`docs/technical-reference.md`](docs/technical-reference.md) (including its **§12 Correctness findings — consolidated**). For the spectral-sky pipeline specifically, see [`docs/spectral-sky-as-built.md`](docs/spectral-sky-as-built.md) and [`docs/spectral-sky-methodology.md`](docs/spectral-sky-methodology.md).

---

## References & Citations


| Quantity / method                                         | Authority                                                                                                                               |
| ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| α-opic EDI/ELR, action spectra, K_D65                    | **CIE S 026/E:2018** — *System for Metrology of Optical Radiation for ipRGC-Influenced Responses to Light*                             |
| 3-/9-channel spectral method, EML, ×179 efficacy         | Inanici, Brennan & Clark 2015 (IBPSA Building Simulation); Lark Spectral Lighting v3.0                                                  |
| Neuropic / OPN5 (9-channel)                               | Jung, Cheng, Brennan & Inanici 2023 (IBPSA); Kojima 2011                                                                                |
| CCT / Duv                                                 | Ohno 2013; CIE 1931 2° observer (via`colour-science`)                                                                                  |
| EML ↔ mel-EDI (×1.103)                                  | "Five-Step" HCL method, Eq. 3                                                                                                           |
| ipRGC FOV weighting {2.06, 1.37, 0.34, 0.23}              | Khademagha 2021 (TU/e)                                                                                                                  |
| nvRD alerting model (sigmoid, filters, EI50/slope/zeff)   | Amundadottir 2016 (EPFL)                                                                                                                |
| 2-phase Daylight-Coefficient method with Direct Sun (DDS) | Subramaniam 2017                                                                                                                        |
| Sub-hourly stochastic disaggregation (Skartveit-Olseth)   | Walkenhorst 2002, in Daysim`ds_shortterm`                                                                                               |
| Annual → alertness precedent                             | Jakubiec & Alight 2021 (IBPSA)                                                                                                          |
| Accuracy envelope (±20%, ~9% of exposures)               | Pierson, Aarts & Andersen 2023 (*J. Build. Perf. Sim.* 16(2):179–197)                                                                  |
| Neutral-sun bias; sky/sun spectra                         | Inanici, Abboushi & Safranek 2023 (*Light. Res. Technol.* 55:502–529)                                                                  |
| Reference-SPD vs. flat within-bin (flat ≈ +7% bias)      | Gkaintzatzi-Masouti / Pierson 2021 (SimAUD)                                                                                             |
| Direct-normal solar reference spectrum                    | ASTM G173 / Gueymard SMARTS (intended basis; embedded data is a representative approximation)                                           |
| Clear-sky spectral model (SPECTRL2)                       | Bird & Riordan 1986 (*J. Climate Appl. Meteorol.* **25**:87; = SERI/TR-215-2436); NREL `spectrl2_2.c` (constants transcribed verbatim)  |
| Cloud spectral modifier (SEDES1)                          | Nann & Riordan 1991 (*J. Appl. Meteorol.* **30**:447)                                                                                   |
| Relative optical air mass                                 | Kasten & Young 1989 (*Appl. Opt.* **28**:4735)                                                                                          |
| Precipitable water (T/RH or dew point)                    | Gueymard 1994 (*Solar Energy* **53**:57); Reitan 1963 (*J. Appl. Meteorol.* **2**:776); pvlib formulation                               |
| Spectral radiative-transfer oracle                        | SMARTS 2.9.5 (Gueymard) — high-accuracy parallel engine (capability-gated)                                                             |
| Native spectral sky matrix                                | Radiance 6.x`gensdaymtx` (LBNL) — 20-band spectral DC matrix (capability-gated)                                                        |
| Daylight S0/S1/S2 reconstruction                          | CIE 15 / Judd-MacAdam-Wyszecki                                                                                                          |
| Lighting controls (Continuous / Off / Stepped / LPR)      | EnergyPlus Engineering Reference v25.2                                                                                                  |
| IES photometry format                                     | IESNA LM-63-1995 / 2002                                                                                                                 |
| Compliance standards                                      | WELL v2 L03; Brown et al. 2022 (*PLoS Biol.* 20:e3001571); ISO/CIE 8995-1:2025; EN 17037:2018; EN 12464-1:2021; UL 24480 (out of scope) |

---

## Related Documentation

- [`docs/operating-guide.md`](docs/operating-guide.md) — how to run an end-to-end HCL simulation & analysis.
- [`docs/technical-reference.md`](docs/technical-reference.md) — full methodology, mathematics, and per-module source map (includes **§12 Correctness findings — consolidated**).
- [`docs/spectral-sky-as-built.md`](docs/spectral-sky-as-built.md) — physical spectral-sky-from-EPW pipeline as-built: stage map, deviations ledger, and the canonical validation caveats (§9).
- [`docs/spectral-sky-methodology.md`](docs/spectral-sky-methodology.md) — spectral-sky physics, equations, and per-symbol source map (SPECTRL2 / SEDES1 / SMARTS / Radiance).
- [`docs/recalibrating-cloud-ccm.md`](docs/recalibrating-cloud-ccm.md) — how-to: locally re-fit the SEDES1 cloud CCM from your own measured diffuse spectra (`hcl_core.sedes1_fit`, `cloud_variant="local"`).
- [`docs/spectral-engine-comparison.md`](docs/spectral-engine-comparison.md) — live three-way comparison of the spectral-sky engines (SPECTRL2 vs SMARTS vs `gensdaymtx`): how close they are and where they diverge.

---

## Acknowledgements & License

`hcl-mcp` is released under the **[MIT License](LICENSE)** — © 2026

It is an independent implementation grounded in primary scientific literature (see [docs/literature-bibliography.md](docs/literature-bibliography.md)) that derives certain spectral algorithms from **[Lark Spectral Lighting](https://faculty.washington.edu/inanici/Lark/Lark_home_page.html)** (Mehlika Inanici et al., University of Washington; ZGF Architects LLP; EPFL; Oregon State University; Eindhoven University of Technology) — a prior implementation of the same science — and **invokes** the **[Radiance](https://www.radiance-online.org/)** (LBNL) and **[Daysim](https://github.com/MITSustainableDesignLab/Daysim)** (NRC / Fraunhofer ISE) engines as external subprocesses. It bundles no Lark, Radiance, or Daysim binaries.

The spectral algorithms derive from **Lark Spectral Lighting**, distributed under a **Modified 3-Clause BSD License**; its copyright notice is retained, and this product is named `hcl-mcp` (not "Lark") in compliance with that license. Radiance, Daysim, and all Python dependencies (`fastmcp` — Apache-2.0; `mcp`, `pydantic` — MIT; `colour-science` — BSD-3-Clause) retain their own licenses.

**→ Full attributions and license texts: [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).**
