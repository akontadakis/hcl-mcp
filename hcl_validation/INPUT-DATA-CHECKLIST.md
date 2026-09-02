# HCL-MCP — Input Data Checklist (everything you need *before* a start-to-finish run)

This is the complete list of input data to have in a folder before driving a full Human-Centric
Lighting (HCL) study (daylight + electric + spectral + annual) through the hcl-mcp.

**Key framing.** Three of hcl-mcp's five modules decide what input data you need (`hcl_mcp` is
protocol only and `hcl_platform` is a stdlib compat base; neither reads study inputs):

- `hcl_core` (pure Python spectral math) — **runs with zero files**; you feed SPDs/channels as text inline.
- `hcl_radiance` / `hcl_daysim` (simulation) — these consume **on-disk geometry/weather/photometry files**.
  They are **capability-gated**: if the external binary is missing they return the *exact command plan*
  instead of executing (still a valid, non-error result).

So "required files" only really applies to the daylight / electric / annual **simulation** paths. The
spectral-only path needs nothing but an SPD string (or a built-in `presets` illuminant).

A ready-to-use copy of every reusable file already shipped in the repo has been assembled for you under
[`inputs/`](inputs/). The table's "Provided?" column says what is already there vs. what you must obtain.

---

## The 7 input-data classes

| # | Class | Required for | File format | Provided? |
|---|-------|--------------|-------------|-----------|
| 1 | **Room geometry** | any Radiance run | Wavefront `.obj` (CAD export) **or** hand-authored Radiance `.rad` | ✅ `inputs/geometry/office_room{,_blinds,_corner_window,_corner_window_blinds}.obj` (+ `.mtl` + pinned `*_material_map.json`), plus the mm-unit twin `office_room_mm.obj` for the `units` regression (W2.10) |
| 2 | **Weather / climate** | spectral-sky + annual | EnergyPlus `.epw`; `.wea` derived from it | ✅ `inputs/weather/GRC_Athens.167160_IWEC.epw` (`.wea` is generated) |
| 3 | **SPD (spectral power distribution)** | spectral metrics; lamp/surface spectra | 2-column text `wavelength_nm value`, 380–780 nm | ✅ `inputs/spd/L09_{cool,neutral,warm}.spd` (or use `presets`) |
| 4 | **Luminaire photometry (IES)** | electric / glare / energy | IESNA **LM-63** `.ies` | ✅ `inputs/luminaires/L09_{cool,neutral,warm}.ies` |
| 5 | **Materials / reflectances / glazing** | any Radiance run | you assign them (per-surface `refl` / glazing `tvis`, or SPD) — **not read from CAD** | ✅ one pinned `inputs/geometry/<name>_material_map.json` per OBJ |
| 6 | **Sensor grid + observer (eye) points** | grid / annual / image | `[x y z dx dy dz]` rows in a `.pts`, or auto-derived from the OBJ | ✅ `inputs/sensors/office_room_grid.pts` (45 work-plane pts), `observer_1.pts`, `observer_2.pts` (eye pts), `sensor_1.pts`, `sensor_2.pts` (daylight-dimming pts) — for the single-window south model |
| 7 | **Compliance target / preset** | pass-fail judgement | a *selection*, not a file (`standard=`, `period=`, `channel_type=`) | n/a — chosen at call time |

---

### 1. Room / scene geometry — REQUIRED for any simulation
- **Two accepted forms** (there is **no inline geometry dict**):
  - **Wavefront `.obj`** exported from Rhino / Revit / SketchUp / Blender → fed to `import_geometry`,
    which authors the per-channel Radiance `.rad` for you (`obj2rad → xform`).
  - Pre-authored Radiance **`.rad`** scene files consumed directly by `run_grid` / `run_annual`.
- **Minimal OBJ** needs: `v` vertices, ideally `vn` normals, one `g`/`usemtl` **group per surface class**
  (floor, walls, glazing, …), `f` faces. The OBJ carries **no spectral data** — see class 5.
- You also supply: `units` (`mm|cm|m|ft`), `up_axis` (`Y|Z`), and — important — `north_angle_deg`
  (the clockwise azimuth the model's +Y axis points toward; the sky is built in a fixed +Y = true-north
  frame, so omitting north is silently wrong for daylight).
- **Provided (four models, Z-up, ≈ 4.3 × 7.3 × 3.4 m furnished office, authored in the true-north frame →
  `north_angle_deg 0`):**
  - `office_room.obj` / `office_room_blinds.obj` — single window in the **South** (−Y) wall, so
    **south-facing** at `north_angle_deg 0`; bare vs. with venetian blinds (`8` groups each; note the blinds
    OBJ carries no luminaire group).
  - `office_room_corner_window.obj` / `office_room_corner_window_blinds.obj` — L-shaped corner window with
    **compass-named per-facade groups**: glazing on the **South** (−Y, `Rad_Glazing_South_T073`) and **West**
    (−X, `Rad_Glazing_West_T073`) walls → a **south-west corner** at `north_angle_deg 0`; bare vs. blinds
    (`11` / `13` groups). Distinct per-facade modifiers let each facade be evaluated independently (south vs. west).
  - Each ships a pinned `<name>_material_map.json` (all `north_angle_deg 0`; see `inputs/geometry/README.md`).
    **Second path:** every model also ships as a hand-authored Radiance scene in `inputs/geometry/radiance/`
    (`<model>.rad` + `materials.rad` + `luminaires_L09.rad`) for direct `run_grid`/`run_annual`. Get your own
    by exporting OBJ from CAD.

### 2. Weather / climate — REQUIRED for spectral-sky & annual
- **EPW** (`.epw`, EnergyPlus Weather): header `LOCATION,…,lat,lon,tz,elev` + 8760 hourly rows. Drives
  `spectral_sky_from_epw`, `atmosphere_from_epw`, `spectral_epw`, `spectral_sky_native`, and is the
  source for sub-hourly weather. Lat/lon/UTC/elevation are read from the header.
  - Sources: **climate.onebuilding.org**, **energyplus.net/weather** (TMY / IWEC / TMYx).
- **`.wea`** (Radiance/Daysim broadband): needed by `run_annual`. **Generated**
  from the EPW by `generate_subhourly_wea` (needs Daysim) or `epw2wea` — you don't author it by hand.
- **Spectral-sky atmosphere is *derived from the EPW*** (SPECTRL2, pure Python). **AERONET is NOT a
  required input.** The `atmos_data/` Mie tables matter only for the native `gensdaymtx` engine (must be
  on `RAYPATH`).
- **Optional atmosphere refinements — no extra files, all opt-in (defaults unchanged).** If you *have*
  better atmosphere data you can push it in via keyword args on `atmosphere_from_epw` /
  `spectral_sky_from_epw` / `spectral_epw`: `ozone_mode="climatology"` (computes a **van Heuklon 1979**
  ozone column from the EPW LOCATION lat/lon + date — no file needed), `aerosol_g` (aerosol asymmetry),
  `aod_anchor_nm` (Ångström-convert a **satellite/measured AOD** given at e.g. 550 nm to τ₅₀₀), and
  `smarts_aerosol="user"` (settable SMARTS Ångström α + `g`). Every default reproduces prior output
  byte-for-bit; these are exercised in TEST-PLAN **G3.8**.
- **Provided:** `GRC_Athens.167160_IWEC.epw` (Athens IWEC, 37.90 N / 23.73 E — matches the README example).

### 3. SPD — REQUIRED input to the spectral core
- **Format** (`hcl_core/spd.py`): two columns `wavelength_nm value`, one sample per line; delimiter
  whitespace / tab / comma; comments tolerated. Clamped to **380–780 nm**, resampled to a **1 nm grid**.
- **Relative SPD is fine** for ratio metrics (mel-DER, CCT). **Absolute** (W·m⁻²·nm⁻¹) is needed only for
  absolute mel-EDI/lux *directly from an SPD* (peak ≤ 1.5 triggers a `scale_warning`).
- The MCP `spd` argument accepts **a `.spd` file path** (read from disk, like `ies`/`epw`/`wea`/`obj`/`pts`),
  the SPD text/rows, or a list of `[wavelength, value]` pairs. For standard illuminants use the `presets`
  tool (CIE D65/D50/A/FL1–12, plus illustrative LED models) — no file needed.
- **Provided:** `L09_cool.spd`, `L09_neutral.spd`, `L09_warm.spd` (measured spectra for the three L09 CCTs).
  Get more from a spectroradiometer or manufacturer datasheets.

### 4. Luminaire photometry (IES) — REQUIRED only for electric / glare / energy
- **IESNA LM-63** `.ies`. Consumed by `ies_analyze` (photometric report) and `ies_to_radiance`
  (`ies2rad → .rad`). The IES carries geometry/intensity only — **no color**.
- **SPD ↔ IES pairing:** bind a 9-channel SPD triplet to the luminaire `.rad` via `colored_luminaire`,
  or in OBJ import give a `type:"luminaire"` group both `ies` and `spd`.
- **Provided:** `L09_cool.ies`, `L09_neutral.ies`, `L09_warm.ies` (the three L09 CCTs; the pinned material
  maps bind `L09_neutral` to the `Rad_Luminaire_L09` group). Get more from manufacturer downloads.

### 5. Materials / reflectances / glazing — you assign them (REQUIRED for renders)
- **Not read from CAD.** The `.mtl` `Kd` values are a hint only. You provide:
  - opaque: per-channel reflectance or scalar `refl` (`write_material`, plastic).
  - glazing: visible `tvis` → `write_material` (glass) directly. `write_material` converts
    transmittance→transmissivity itself; pre-converting with `glass_transmissivity` double-converts
    (0.70 → 0.763 → 0.831, ~9% high). `glass_transmissivity` is for hand-written .rad primitives only.
  - in OBJ import: a `material_map` mapping **every** group → library-name string **or** inline dict
    `{"type":"plastic|glass|ground|context|luminaire", "refl"|"tvis"|"spd": …}`. **Unmapped group = hard fail.**
- **Provided:** one pinned `<name>_material_map.json` per OBJ (correct keys for each `office_room*` model,
  incl. `up_axis`/`north_angle_deg`).

### 6. Sensor grid + observer points — REQUIRED for grid/annual/image (or auto-derive)
- `points`: `[x y z dx dy dz]` rows (position + gaze) inline or in a `.pts`. For mel-EDI the meaningful
  sensor is **vertical at the eye**, oriented toward the glazing.
- **⚠️ A `.pts` is not one interchangeable class — there are three, and they are not substitutable.**
  One extension carries the **horizontal work-plane grid** (up-facing `0 0 1` at `workplane_h`), the
  **vertical eye observers** (gaze toward glazing), and the **daylight-dimming photosensors**. Feeding one
  where another belongs fails *quietly*, because every one of them is a syntactically valid `.pts`:
  a 1-point eye file in place of the 45-point grid makes **sDA/ASE degenerate** (a single point can only be
  0% or 100%), averages **DF over the wrong plane**, and leaves **EN 12464-1 uniformity** (`df_min/df_avg`)
  undefined. `active_inputs.json` therefore names a default **per role** — `points` /
  `points_observer` / `points_photosensor` — and `_resolution.by_class.points.roles` matches on filename
  (`grid|workplane|wp|task` · `observer|eye|view|occupant` · `sensor|photo|dimming|zone`). **Roles always
  win over alphabetical order.** Name your own files accordingly, or regenerate per role with
  `workplane_grid` / `observer_points` / `photosensors`.
- **Four ways to generate these from the OBJ:**
  1. `import_geometry(derive_sensors=True)` returns scene-aligned `grid_points` (work-plane) and
     `observer_sets` (seated 1.2 m + standing 1.6 m, each with DGP `glare_views`).
  2. **`workplane_grid`** — dedicated EN 12464-1 working-plane grid tool. Given an OBJ + material map or
     sidecar, it detects the interior extent, applies a border offset, and lays a uniform grid at the
     specified `workplane_h` (default 0.8 m). Returns `{points, methodology, pts_path}`. Feed `grid.pts` →
     `run_grid` for horizontal/task illuminance and EN 12464-1 compliance. `clip_to_footprint` (default
     true) clips the grid to the real floor polygon (off-floor cells dropped) and now covers
     **non-rectangular rooms end-to-end**, including concave L/T/U shapes: when inner-wall detection
     degenerates on a concave room, the interior falls back to the floor bounding box (then
     polygon-clipped) so the grid still spans the whole shape. `methodology` gains
     `clipped{kept,dropped,footprint_source,footprint_border}`. Rectangular office grids stay
     byte-identical (45 points).
  3. **`observer_points`** — workstation eye-sensor tool. Pairs chair seats to display screens (by object-name
     suffix matching), places eye sensors at `eye_height` (default 1.2 m; accepts a list for dual-height),
     and computes gaze direction toward the paired screen. Fallbacks: `direction_fallback="window"` (gaze
     toward glazing centroid), `"azimuth"` (fixed bearing), or `"sweep"` (`sweep_n` rotated views per seat).
     When no seats are found, `position_fallback="room_center"`. Returns `{observers, points, glare_views,
     methodology, pts_path}`. The `glare_views` strings are ready-made fisheye `-vp … -vd … -vta -vh 180 -vv
     180` strings — feed directly to `glare_ugr`. Feed observer `.pts` → `run_grid`/`run_annual` for vertical
     mel-EDI. `clip_to_footprint` (default true) **reports** (warns) observers that fall outside the floor
     footprint but does not move them (observers stay furniture-anchored); `methodology` gains
     `footprint_checked`.
  4. **`photosensors`** — daylight-dimming reference-sensor tool (pure-Python, no Radiance; methodology.md §3).
     Locates the dominant glazed facade, builds window-head-height sidelighting zones, and places one
     horizontal sensor per zone at `sensor_fraction` (default 2/3) of the zone depth, centred on the facade
     and clipped to the floor. `zone_rule` ∈ `"head_height"` (default) / `"ies_2.5"`; `mount` ∈
     `"workplane"` (up-facing, at `workplane_h`) / `"ceiling"` (down-facing). Requires a floor + a glass
     group. Returns `{points, methodology{facade, zones[], zone_rule, sensor_fraction, mount, count},
     pts_path, assumptions, warnings}`. Feed the resulting `.pts` → `run_grid`/`run_annual` for
     daylight-linked dimming control logic.
- **Reuse a grid by name (`sensors` tool):** once you have a set of points (from any of the four ways
  above, or an explicit list), persist it with `sensors(action="create", name="wp", points=…)` **or**
  `sensors(action="create", name="wp", grid={interior:[xmin,xmax,ymin,ymax], floor_z, workplane_h?,
  max_spacing?})` (builds an EN 12464-1 grid). It writes a `.pts` + a `sensors.json` registry under
  `work_dir`. Then pass `sensor_set="wp"` to **`annual_daylight` / `daylight_factor` /
  `daylight_savings`** instead of re-listing `points=[...]` every call (`list`/`get`/`delete` manage the
  saved sets). This is what the `annual_daylight_study` prompt uses to run all three daylight-metric tools
  over one grid.
- **Provided (for the single-window south model `office_room.obj`; regenerate for the other three):**
  `office_room_grid.pts` (45 EN 12464-1 work-plane points, up-facing `0 0 1`, output of `workplane_grid`);
  `observer_1.pts` (`-1.75 1.2 1.2 1 0 0`, Chair_Seat_1↔Disp_Panel_1) and `observer_2.pts`
  (`1.75 -1.2 1.2 -1 0 0`, Chair_Seat_2↔Disp_Panel_2) — output of `observer_points`; `sensor_1.pts`/`sensor_2.pts`
  (primary/secondary daylight-dimming zone sensors near/deep of the south facade, z=0.8 m, up-facing) — output
  of `photosensors`. *(The `preview_scene` PNG overlays no longer ship — regenerate with
  `preview_scene(render="all")`, a placement diagnostic, not a photometric render.)*

### 7. Compliance target / preset — a selection, no file
- `standard` ∈ `brown_2022 | well_v2_l03 | iso_cie_8995_1_2025 | en_17037 | en_12464_1 | ul_24480`
  (all six are accepted; note `ul_24480` returns `result:"unsupported"` / out-of-scope — it needs Circadian
  Stimulus, which this toolkit doesn't compute — and `en_12464_1` is the **electric-photopic task** path:
  pass `task` + `em/ugr/uo/ra`, not a `mel_edi`);
  plus `period` (`daytime|evening|night`), `daylight_met`, and `channel_type` (0 = 3-channel, 1 = 9-channel; 9 recommended).

---

## What ships in the repo you can reuse (already copied into `inputs/`)

| Type | Source in repo | Count | Copied to |
|------|----------------|-------|-----------|
| EPW | downloaded from climate.onebuilding.org (Athens IWEC) | 1 shipped | `inputs/weather/GRC_Athens.167160_IWEC.epw` |
| OBJ + MTL + map | Blender exports of the furnished office | 4 models (single/corner × ±blinds) | `inputs/geometry/office_room*.obj` (+ `.mtl` + `*_material_map.json`) |
| Radiance scenes | hand-authored `.rad` equivalents of the 4 models | 4 + shared materials/luminaires | `inputs/geometry/radiance/*.rad` (`materials.rad`, `luminaires_L09.rad`, `L09_neutral.rad`/`.dat`) |
| IES | L09 fixture photometry | 3 CCTs | `inputs/luminaires/L09_{cool,neutral,warm}.ies` |
| SPD | L09 fixture spectra | 3 CCTs | `inputs/spd/L09_{cool,neutral,warm}.spd` |
| Sensor `.pts` | generated by `workplane_grid` / `observer_points` / `photosensors` on `office_room.obj` (south model) | 5 | `inputs/sensors/office_room_grid.pts`, `observer_1.pts`, `observer_2.pts`, `sensor_1.pts`, `sensor_2.pts` |

**Not shipped (generated at runtime):** `.wea` (from EPW), study brief JSON (created by `save_brief`), and the
`preview_scene` PNG overlays (regenerate on demand). Measured reference SPDs and atmosphere CSVs live in an
internal validation tree outside this repository and are **validation references, not runtime
inputs** — nothing here depends on them. The sensor `.pts` files ship pre-generated
(for the single-window south model) but can always be regenerated from any OBJ via `workplane_grid` /
`observer_points` / `photosensors` (and a preview via `preview_scene`) — see class 6 above.

---

## Engine status — optional, check yours with the status tools

The simulation engines are **optional and cross-platform** (macOS / Linux / Windows). **Whichever are
installed run live; the rest emit the exact command plan** (`{"ran": false, "commands":[…]}`) — the
**expected, correct** capability-gated behaviour, scored **PASS(emit)**, not FAIL. Check your own state
with `radiance_status` and `daysim_status` (and try `engine="smarts"`) before a run.

| Engine | Powers | Found via | Where to get it |
|--------|--------|-----------|-----------------|
| **Radiance** (6.x for native spectral) | grid / image / annual / glare / native-spectral / `ies2rad` / `epw2wea` | `HCL_RADIANCE_BIN` + `RAYPATH` | [github.com/LBNL-ETA/Radiance/releases/latest](https://github.com/LBNL-ETA/Radiance/releases/latest) |
| **Daysim** (`ds_shortterm`) | `generate_subhourly_wea`, `annual_nvrd` transport (`timestep_min` ∈ {1,2,3,4,5,6,10,12,15,20,30}) | `HCL_DAYSIM_BIN` | [github.com/MITSustainableDesignLab/Daysim](https://github.com/MITSustainableDesignLab/Daysim) (build, or the `build_daysim` tool) |
| **`reinsrc.cal`** | live 2-phase DDS for `run_annual` / `annual_nvrd` (absent → emit) | Radiance `lib` (on `RAYPATH`) | ships in the Radiance/Daysim source; copy into the Radiance `lib` |
| **SMARTS 2.9.5** | `engine="smarts"` (optional; `spectrl2` pure-Python is the default) | `SMARTSPATH` | [nrel.gov/grid/solar-resource/smarts.html](https://www.nrel.gov/grid/solar-resource/smarts.html) |

→ Each engine is located through an `env` path in your client config (restart the client to load env
changes). **Install steps with the exact build/copy commands per OS are in
[GUIDE.md Appendix A](GUIDE.md#a--installing-the-engines-optional--for-live-simulation).**
