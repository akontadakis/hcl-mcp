# Operating the hcl-mcp Server — running an HCL simulation & analysis

This guide explains how to **use** the `hcl-mcp` MCP server end-to-end: how it is structured, how
to drive a real human-centric-lighting (HCL) simulation and analysis through its tools, and what you
get back. It documents the server through the guided **studio journey** and the **spectral-sky-from-EPW**
radiative-transfer pipeline (47 tools, 14 resources, 13 prompts).

> For *why* the numbers are what they are — the methodology, math derivations, and per-module source
> map — see the sibling [`technical-reference.md`](technical-reference.md), and for the spectral-sky
> pipeline specifically [`spectral-sky-as-built.md`](spectral-sky-as-built.md) and
> [`spectral-sky-methodology.md`](spectral-sky-methodology.md). This document is about **operation**.

---

## 1. What the server is (and the one rule that governs everything)

`hcl-mcp` is an independent, literature-grounded HCL engine exposed over MCP. Its spectral and
circadian methods implement published models directly from primary literature (see
[`docs/literature-bibliography.md`](literature-bibliography.md)). It is organised in three
capability layers (the thin `hcl_mcp` protocol layer and the stdlib-only `hcl_platform` helpers
sit around them — README's "five modules in four layers"), and **knowing which layer a tool lives
in tells you what it needs to run**:


| Layer              | What it does                                                                                                                                                                                                 | External dependency                  |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| **`hcl_core`**     | Pure-Python spectral math (channels, alpha-opic, circadian metrics, compliance, the nvRD model, the spectral reconstruction,**and the EPW→spectral-sky radiative-transfer pipeline — SPECTRL2 + SEDES1**). | **None.** Runs anywhere, always.     |
| **`hcl_radiance`** | Wraps the**Radiance** CLI (daylight/electric ray-tracing: grids, images, annual DDS, glare, IES; **and the native `gensdaymtx` spectral-sky engine**).                                                       | Radiance binaries.                   |
| **`hcl_daysim`**   | Wraps**Daysim** `ds_shortterm`/`epw2wea` (sub-hourly weather for the alertness model).                                                                                                                       | Daysim binaries (built from source). |

### The run/emit contract — the single most important operating concept

Every tool that touches Radiance or Daysim takes a `run: bool = True` flag and behaves the same way:

- **`run=True` and the binary is available** → it **executes** and returns results.
- **`run=False`, OR the binary is missing** → it does **not** execute; it returns
  `{"ran": false, "commands": [...]}` — the *exact* shell command sequence (and any input files it
  wrote), so you can inspect the plan, run it yourself, or run it later.

This means **you can drive the entire pipeline with zero binaries installed** — every step will hand
you a runnable command plan. Install Radiance/Daysim only when you want the server to execute for you.
Pure-`hcl_core` tools (metrics, compliance, reconstruction) always run regardless.

### Advisories — the result tells you when it is easy to misread

Any tool returning a **dict** may carry an `advisories` list beside its normal fields. Each entry is
`{code, severity, message, field?}`. The key is **absent entirely** when nothing fired — an empty
list on every clean result would train you to stop looking.

| severity | what it means |
|---|---|
| `error` | the result is probably not usable as-is |
| `warn` | usable, but easy to misreport |
| `info` | a default nobody explicitly chose — confirm it is the one you want |

The nine current codes are `MEL_DER_BINNED`, `SPECTRAL_TRANSPORT_SHIFT`,
`ELECTRIC_EXCEEDS_LUMEN_BOUND`, `ALBEDO_NOT_MEASURED`, `DOSE_THRESHOLD_IS_DEFAULT`,
`ZONE_WEIGHT_REMAINDER`, `GEOMETRY_HEALTH_UNCLEAN`, `NVRD_ZERO_DIVERGENCE` and
`RADIANCE_DROPS_IES_CANDELA_SCALE`. Several of the manual
checks this guide asks you to make — reading `mel_der_source`, confirming the dosimetry threshold,
sanity-checking zone weights — are now also raised for you automatically. Read the list before
quoting any number; an **absent** `advisories` key means no rule fired, not that the model is right.

Advisories attach only to dict results, so a **list**-returning call carries none. The only such tool
is `circadian_metrics` with multi-point input — inspect `mel_der_source` per point there yourself.

> **A rule only fires where it looks.** `run_grid` puts every per-point field under
> `daylight`/`electric`/`combined`.`metrics[]`, so a rule reading the top level alone never fires
> there. `MEL_DER_BINNED` and `SPECTRAL_TRANSPORT_SHIFT` both walk the nested blocks.
>
> `MEL_DER_BINNED` is **deliberately silent on the `daylight` block**: that block is present on every
> run, its spectrum is a smooth sky where the binned route costs ~0.13%, and there is no single
> source spectrum you could pass instead — so the warning would be permanent, unactionable and ~60×
> overstated. It fires on `electric` (give every luminaire the same `spd`/`preset` and the block
> moves to the transported route) and on `combined`, where the mixture has no single source spectrum
> but **mel-EDI is additive** — read `daylight` and `electric` separately and add their `mel_edi`.
> Measured, the parts stay within ~0.4% of truth where the mixture runs up to **8.1%** high once
> luminaires dominate.
The rules live in `src/hcl_mcp/advisories.py`; see [`adr/0005-advisories-attach-at-the-registration-seam.md`](adr/0005-advisories-attach-at-the-registration-seam.md)
for why they sit in the protocol layer and attach at the tool-registration seam.

### Where files go (`work_dir`)

Tools that write files resolve their output directory with this precedence:
`explicit work_dir arg` → `HCL_WORK_ROOT` env → the MCP client's first **root** → `~/hcl_work`.
Pass `work_dir` explicitly for deterministic placement; otherwise outputs land in a sensible default.

### The channel model (3 vs 9)

HCL spectral rendering is done per **channel** (`channel_type`): `0` = 3-channel (`r,g,b`), `1` =
9-channel (`b1..b3, g1..g3, r1..r3`, finer spectral resolution, the default and recommended). The
same `channel_type` must be used consistently across a workflow. 9-channel needs **3** Radiance scene
sets (one per RGB triple); 3-channel needs **1**.

### Ambient quality (`quality=`) — the setting you inherit by not choosing

**All nine** Radiance-executing simulation tools — `run_grid`, `run_image`, `run_annual`,
`annual_daylight`, `lm83_daylight`, `daylight_factor`, `glare_ugr`, `daylight_savings` and `annual_nvrd` — accept
`quality=` (`low` `-ab 0` / `medium` `-ab 2` / `high` `-ab 3` / `extra_high` `-ab 5`; call
`quality_presets()` for the table). An explicit `rad_params` always wins over it.

Passing **neither** inherits a preview-grade default *by not choosing*. That is not a neutral act:
Radiance's ambient calculation is stochastic, so threshold metrics drawn from it are a draw from a
distribution rather than a value. Two `quality="medium"` `annual_daylight` runs on an unchanged model
returned sDA **66.7% then 82.2%** — a 15.6 pp swing. Use **`quality="high"` for any number you will
quote**. Direct-only quantities (ASE's `-ab 0` pass) are unaffected and correct at any level.

---

## 2. Launching the server

The canonical install/launch route is the README's `uvx` one (no clone, no `PYTHONPATH`):

```bash
claude mcp add hcl-mcp -- uvx --from git+https://github.com/akontadakis/hcl-mcp hcl-mcp
```

From a **local clone**, use `uv tool install .` (the launch command is then just `hcl-mcp`) —
**not** `uv run --directory …`: `uv run`'s implicit sync can regenerate the editable install in a
state where the bare interpreter cannot import the `src/`-layout packages, and the server fails
with `ModuleNotFoundError: hcl_core`. If you must use `uv run --directory` anyway, it works only
with `--env PYTHONPATH=/path/to/hcl_mcp/src` set — that `PYTHONPATH` is required, not optional.
(Tests are unaffected either way — they use `pythonpath = ["src"]` from `pyproject.toml`.) The
README's install section and [`INSTALL.md`](../INSTALL.md) are the authoritative instructions.

Optional environment:

- `HCL_RADIANCE_BIN` — directory of the Radiance binaries (else `PATH`).
- `HCL_DAYSIM_BIN` — directory of `ds_shortterm`/`epw2wea` (else `PATH`; build via `build_daysim(run=True)`).
- `HCL_DAYSIM_REF` — the Daysim commit or branch `build_daysim` builds, in place of its pinned commit.
  Only this variable can change what is built; the tool takes no such argument.
- `HCL_WORK_ROOT` — default output directory (else a client root, else `~/hcl_work`).
- `HCL_ATMOS_CACHE` — where `spectral_sky_native` (`gensdaymtx`) keeps its pre-computed
  scattering tables (else `<HCL_WORK_ROOT>/atmos_cache`). The first run in an empty cache takes
  several minutes; later runs take seconds. The result names the folder as `atmosphere_cache`.
- `HCL_RADIANCE_SHIM` — set to `1` **only if** `radiance_status()` reports `source_cal.a1_honored:
  false` (see below). Off by default.

**First thing to call:** `validate()` (confirms the spectral core is self-consistent),
`radiance_status()` and `daysim_status()` (tell you which layers will execute vs emit).

> ⚠️ **Check `radiance_status().source_cal` before trusting ANY electric-lighting number.** Some
> Radiance builds ignore the `ies2rad` `A1` candela scale, so every IES luminaire emits at unit
> scale — an office grid reads **34 lx instead of 494 lx**, and `glare_ugr` returns a clean
> **UGR 0** because the fixtures are too dim for `evalglare` to see as glare sources at all. No
> error is raised anywhere. If `a1_honored` is `false`, set `HCL_RADIANCE_SHIM=1`, which puts a
> corrected `source.cal` on `RAYPATH` for every run **without touching the Radiance install** (no
> `sudo`; revert by unsetting it). **The error factor is each luminaire's own candela scale —
> 14.4× for one fixture, 2.07× for another — so affected results must be RE-RUN, never rescaled.**
> Daylight-only results are unaffected: sky paths never use `A1`. Runs that rendered luminaires
> carry the verdict as `engine.source_cal`, and a bad build also raises the
> `RADIANCE_DROPS_IES_CANDELA_SCALE` advisory.

---

## 3. End-to-end workflows

Pick the workflow that matches your question. Each lists the tool chain, the inputs you supply, and
the analysis you get out. All Radiance/Daysim steps honour the run/emit contract above.

### A. "What are the circadian metrics of this light?" — pure spectral analysis (no binaries)

The fastest path; everything here is pure `hcl_core` and always executes.

1. **`spd_to_channels(spd, channel_type)`** — average a measured/illuminant SPD into channels.
   (Or skip and use `presets(name)` to pull a standard illuminant's channels.)
2. **`circadian_metrics(channels, channel_type, spd=None)`** — photopic / melanopic / neuropic equivalent
   illuminance, **plus `mel_edi` / `mel_der` / `mel_der_source`**. And/or **`alpha_opic(channels=…)`**
   (or `alpha_opic(spd=…)` for the gold-standard per-nm path) — CIE S 026 α-opic E / ELR / **mel-EDI**.
   > ⚠️ **Pass `mel_edi` to step 4, never `melanopic_lux`.** They are different quantities — a
   > melanopic-weighted illuminance vs `photopic_lux × mel-DER` — differing by D65's own binned
   > melanopic/photopic ratio **1.099665** (~9%). Standards are written in mel-EDI, and near a threshold
   > the difference decides the outcome: 260.65 `melanopic_lux` "passes" Brown's ≥250 lx where the true
   > mel-EDI of 237.03 fails. Supply `spd=` when a single **source** spectrum feeds these channels: it
   > keeps the source's within-bin structure and recovers the room's per-bin transport from the channels,
   > so `mel_der` describes the spectrum **at the point** (`mel_der_source:"spd_transported"`, plus
   > `source_mel_der` and `transport_ratio`). Without it, mel-DER is inferred from the bins alone —
   > ~0.13% for daylight, up to ~8% high for a narrow-band fluorescent — and carries `mel_der_note`.
   >
   > ⚠️ **`mel_der` will not match the luminaire's datasheet, and should not.** The datasheet quotes the
   > *source* figure — that is `source_mel_der`. The room stands between the lamp and the point and does
   > not treat every wavelength alike; `transport_ratio` is the size of the shift, and
   > `SPECTRAL_TRANSPORT_SHIFT` announces it past 5%. Do not "correct" `mel_der` toward the datasheet.
   >
3. **`spectral_metrics(spd, metric="all")`** — CCT/Duv, mel-DER, mel/photopic ratio, EML↔EDI.
4. **`compliance(mel_edi=…, standard="brown_2022", period="daytime", daylight_met=…)`** — grade the
   mel-EDI against any of the **six** standards: WELL v2 L03 / Brown 2022 / ISO-CIE 8995-1:2025 / EN 17037 /
   EN 12464-1 / UL 24480. The return *shape* is standard-specific (see Output below); `ul_24480` returns
   `unsupported` and `en_17037` returns `n/a` (daylight-provision, non-circadian — neither is scored).
   > **`en_12464_1` is the electric visual-task path and ignores `mel_edi` entirely.** Pass
   > `task` (one of the 8 in `hcl://compliance/en_12464_1`) plus the measured `em`/`ugr`/`uo`/`ra`,
   > and optionally the surround/background (`em_surround`, `uo_surround`, `em_background`,
   > `uo_background`) and wall/ceiling/cylindrical (`em_wall`, `uo_wall`, `em_ceiling`,
   > `uo_ceiling`, `em_cylindrical`, `uo_cylindrical`) values — each relationship is evaluated only
   > when its inputs are supplied. Supplying the `task` but no measured values returns
   > `"incomplete"`, never a vacuous `"pass"`. *(Until 2026-08-11 the MCP tool did not forward any
   > of these arguments, so this documented path raised `unknown EN 12464-1 task None` and the whole
   > standard was unreachable over MCP even though the core supported it. Fixed; if a client of
   > yours worked around it by calling `hcl_core.compliance` directly, it can now use the tool.)*

→ *Output:* a full HCL metric set + a standard-specific compliance verdict for one light/SPD — pass/fail
(Brown 2022 / ISO-CIE 8995-1:2025), `result_points` 0/1/3 (WELL v2 L03), `n/a` (EN 17037, non-circadian),
`unsupported` (UL 24480), or the EN 12464-1 task verdict.

### B. "What melanopic exposure do occupants get at these desks?" — point-in-time daylight grid

1. **`write_material(channels, material_type, channel_type, name)`** — per-channel Radiance materials
   for each glazing/surface SPD. Pass glazing channels as raw transmittance (Tvis) — `write_material`
   converts to transmissivity internally; do NOT pre-convert with `glass_transmissivity`.
2. **`spd_to_channels`** on the sky/sun SPDs → **`colored_sky(diffuse_channels, direct_channels, channel_type, month, day, hour, lat, lon, utc, …)`** — a colored Perez all-weather sky+sun per
   channel. (Sky model: Perez et al. 1990/1993, *Sol. Energy* **44**:271; model
   lives in Radiance `gendaylit`/`gendaymtx`, Reinhart/Tregenza 145-patch vault.)
   > ⚠️ **If those SPDs came from `spectral_sky_from_epw` (workflow H), also pass that record's
   > geometry verbatim** — `sun_zenith_deg=rec["geometry"]["zenith_deg"]`,
   > `sun_azimuth_deg=rec["geometry"]["azimuth_deg"]`. The two tools' `hour` arguments **mean
   > different things**: `spectral_sky_from_epw`'s is an EPW **hour-ending** label whose geometry is
   > evaluated at the mid-interval instant (`hour − 0.5`, because the row's DNI/DHI are averaged over
   > the preceding hour), while `colored_sky`'s is a **wall-clock** instant that gendaylit re-derives
   > the sun from. Passing the same integer to both leaves the spectrum and the traced sky **half an
   > hour — 7.5° of diurnal arc — apart, and nothing raises.** Supplied together, the two arguments
   > emit gendaylit's `-ang` form and make the record's position authoritative; omitted, behaviour is
   > unchanged. This is a correctness requirement, not a refinement.
   >
3. **`run_grid(scene_sets, points, channel_type, sky_files?, run=…)`** — `oconv → rtrace -I` per channel →
   recombined per-point HCL metrics. `scene_sets` = your materials+geometry+sky `.rad` paths
   (1 list for 3-channel, 3 lists for 9-channel); `points` = `[x,y,z,dx,dy,dz]` rows or a `.pts` path.
   Add `export_csv` to dump the per-point table; add `electric_lights` to combine daylight + luminaires.
   > ⚠️ **With `electric_lights`, a sky-free octree is built for the `electric` block — and which files
   > are sky is DETECTED** (gensky/gendaylit primitives, `skyfunc`, the sky/ground hemispheres, plus a
   > basename hint). That covers the generators this toolkit and Radiance use, but not a hand-rolled sky
   > using none of them. **Pass `sky_files=` to state it exactly** for an unusual scene — in either
   > direction: to name a sky nothing would detect, or to *keep* a sky-looking file (exterior context)
   > inside the electric octree. A leak here reports daylight as electric light; it once turned 1662 lx
   > into 17705 lx with nothing in the result saying so (ADR-0007). The `electric` block now carries
   > **`lumen_bound`** — Σ luminaire lumens over the grid's bounding box — and
   > `ELECTRIC_EXCEEDS_LUMEN_BOUND` fires when the mean passes that ceiling. Read it before quoting the
   > block. It bounds the **mean**, never a single point (under a downlight legitimately exceeds it).
   *(For an OBJ-based scene the EN 12464-1 `grid.pts` from `workplane_grid` drops in here directly —
   see workflow I and the `place_sensors` prompt.)*
4. Feed the per-point mel-EDI into **`compliance(...)`** per point.

→ *Output:* per-sensor melanopic/photopic/neuropic metrics at one date-time, optionally CSV, gradeable.

### C. "Does this space meet circadian targets across the year?" — annual daylight + dose

1. **`weather(wea_path, period?, timestep_min?)`** — ingest a `.wea` (and/or decompose an analysis
   window into hours-of-year). (A `.wea` comes from EnergyPlus/Radiance tooling, or from workflow F's
   sub-hourly generator.)
2. **`run_annual(channel_scenes, wea, points, channel_type, dosimetry_threshold=250, period?, run=…)`**
   — 2-phase daylight-coefficient DDS per channel → **annual mel-EDI time series + circadian
   dosimetry** (e.g. hours/day above the threshold). `channel_scenes` = 1 dict (3ch) or 3 dicts (9ch),
   each `{materials, geometry, sky_color:[r,g,b]}`.
   > **Reading `dosimetry.hours_above`.** It is scored on CIE S 026 **mel-EDI** (not `melanopic_lux`), and
   > each timestep contributes its **own** duration (`timestep_min`), so a `period` covering only occupied
   > hours — or one repeated across months — is counted correctly. Both were defects until 2026-07-25: the
   > old code fed `melanopic_lux` (relaxing the threshold by ≈1.0997×) and charged the last sample of each
   > block the whole non-occupied gap, so a 3-day 08:00–18:00 window read 59 h instead of 33 h and a
   > Jun–Aug window read 1475 h instead of 33 h. Any dosimetry figure quoted from before that date should be
   > recomputed rather than rescaled — the threshold comparison is non-linear.
   >
3. *(Optional)* **`annual_daylight(channel_scenes, wea, points?, sensor_set?, channel_type=1, …, run=True)`**
   — the same annual 2-phase DDS pass, reduced instead to **climate-based daylight metrics**: per-point
   **DA** (≥ `da_threshold`, default 300 lx), **cDA** (continuous, partial credit), **UDI** bins
   (`<100` / `100–300` / `300–3000` / `>3000 lx`), and the spatial rollups **sDA** (≥ `sda_da_fraction`,
   default 50%) and **ASE** (direct sun ≥ `ase_threshold` 1000 lx for more than `ase_hours` 250 h).
   Occupancy defaults to weekday 08:00–18:00 (Monday-anchored 8760 h); pass `occupancy=[...]` to
   override. ASE uses its own dedicated direct-only (`-ab 0`) pass — separate from the total
   (sky+sun, ambient-bounced) pass DA/UDI use. Pass `points=[...]`/a `.pts` path, or `sensor_set='name'`
   (see workflow tool `sensors`). Always simulates the full 8760-h year — `period`/`partial_year`
   is not yet wired at the tool level.
   **Pick the ambient level with `quality=`** (`low`/`medium`/`high`/`extra_high` — see
   `quality_presets`); an explicit `rad_params` always wins. When the settings are too coarse for a
   threshold metric the result carries a **`convergence_warning`** naming the offending parameters,
   next to the **`rad_params`** that produced it. **Read it before quoting sDA/UDI** — those are
   threshold crossings, so under-converged indirect sampling moves them far more than it moves means.
   ASE is never flagged: its direct-only `-ab 0` pass is unaffected by ambient settings.
   *Core `run_annual_daylight` first live-validated on real
   Radiance 6.1a (toy fully-glazed scene); then, on 2026-07-18, the MCP tool itself ran live
   end-to-end on a realistic `office_room` + GRC Athens IWEC (8760-h year, 45 workplane points):
   sDA300/50% = 75.6%, ASE1000,250h = 31.1%, DA_avg 0.71. Two further runs on 2026-07-23
   (`quality="medium"`, 3-channel, everything else identical) gave sDA **66.7% then 82.2%** — a 15.6 pp
   swing on an unchanged model, because Radiance's ambient calculation is stochastic and at
   `-ab 2 -ad 512` seven of 45 points crossed the DA 0.50 threshold between runs. **ASE was 31.11% in
   every run, bit-identical** (direct-only `-ab 0`, nothing to vary). Preview-grade sDA is therefore not
   reproducible — use `quality="high"` for a number you will quote. Not a measured/calibrated baseline.*
4. *(Optional)* **`daylight_factor(scene_sets, points?, sensor_set?, month=6, day=21, hour=12.0, gnd_refl=0.2, run=True)`** — a point-in-time **Daylight Factor** check under a CIE Standard
   Overcast Sky (`gensky -c`): `DF = E_indoor / E_outdoor × 100`, with `E_outdoor` traced from a
   sky-only exterior reference point. Returns `df_per_point`/`df_avg`/`df_min`/`uniformity`. *First
   live smoke-validated on real Radiance 6.1a (toy fully-glazed scene) — trends sane (DF falls off
   with distance) though magnitudes are extreme for the toy fixture; a sky-file-ordering bug found
   during that run was fixed. Then, on 2026-07-18, ran live end-to-end through the MCP tool on a
   realistic `office_room` (45 workplane points, CIE overcast sky): df_avg 3.53% (df_min 0.29% far
   corner → df_max 15.87% near the window) — plausible magnitudes for a side-lit office. Not a
   measured/calibrated baseline.*

→ *Output:* annual melanopic dose metrics per point — the core "is this a circadian-healthy space?" result. With `annual_daylight`/`daylight_factor`, this extends to the standard climate-based/overcast daylight-performance metrics used in green-building compliance (LEED/EN 17037/BREEAM-style DA/UDI/sDA/ASE/DF checks).

### D. "Add electric lighting" — IES luminaires, grids, glare, and energy

1. **`ies_analyze(ies)`** — sanity-check a luminaire's photometry (lumens, watts, efficacy, angles, LOR).
2. **`ies_to_radiance(ies, placement?, color?, run=…)`** — `ies2rad` (+ `xform` placement) → a luminaire
   `.rad`. **`colored_luminaire(rad_path, channels9, count)`** injects a 9-channel spectral triplet.
3. Use the luminaire `.rad`s as the **`electric_lights`** input to **`run_grid`** (daylight + electric in
   one combined grid) or **`run_image`**.
4. **`glare_ugr(scene_sets, electric_lights?, run=…)`** — fisheye render → `evalglare` → **UGR / DGP /
   glare sources**.
5. **`lighting_controls(itot_per_point, iset=500, control_type="ContinuousOff", …)`** — daylight-
   responsive dimming → fraction-of-power & **energy savings** (EnergyPlus §7.3.5). Or one-shot it with
   **`daylight_savings(...)`**, which runs the daylight sim at the reference points *and* the controls
   calculation together.

→ *Output:* combined daylight+electric metrics, glare ratings, and lighting-energy savings.

### E. "What does an occupant's eye actually see?" — fisheye image + field-of-view + glare

1. **`run_image(scene_sets, channel_type, view, fov_weighting?, mask_dir?, glare?, electric_lights?, run=…)`** — `rpict` per channel → mel/neuropic **greyscale luminance maps** (falsecolor-ready), with
   optional ipRGC field-of-view weighting and per-region masks.
2. For numeric glare from the same viewpoint, **`glare_ugr(...)`**.
   *(For an OBJ-based scene the `glare_views` strings from `observer_points` are ready-made fisheye
   `view` arguments — see workflow I and the `place_sensors` prompt.)*

→ *Output:* eye-level melanopic luminance images + FOV-weighted exposure (+ glare).

### F. "How alerting is the daylight over the year?" — the annual → nvRD alertness bridge

This is the deepest pipeline: weather → sub-hourly spectra → the Amundadottir alerting model.

1. **`daysim_status()`** — is Daysim present? If not, **`build_daysim(run=True)`** clones + builds it
   from source (needs `cmake` + a C compiler), then set `HCL_DAYSIM_BIN` to the reported `bin_dir`.
   *(Daysim is never bundled — NRC/Fraunhofer ISE EULA — it is built locally.)*
2. **`generate_subhourly_wea(epw, timestep_min=6, run=…)`** — EPW → `epw2wea` → `.hea` → `ds_shortterm`
   → a **6-minute** broadband `.wea` (location is read from the EPW automatically — you normally pass
   only the EPW path). (`ds_shortterm` implements the Skartveit & Olseth 1992 / Walkenhorst et al. 2002
   stochastic sub-hourly decomposition; model lives in Daysim.)
3. **`annual_nvrd(point_xyz, view_vec, epw, channel_scenes, points, channel_type, reconstruction="both", run=…)`** — EPW → sub-hourly `.wea` → separated colored DDS → per-timestep 401-nm spectrum
   reconstructed **two ways** (`faithful` flat vs `enhanced` reference-SPD/colored-sun) →
   `nvrd()` twice → **both R_D alerting series + their divergence** (`divergence`,
   `RD_series_divergence`). It is **LONG-RUNNING** and elicits confirmation before executing.

   *Standalone option:* **`reconstruct_spectrum(sky_channels, sun_channels, …)`** returns one 401-nm
   spectrum + the reconstruction divergence without any simulation. **`nvrd(spectral_series)`** runs the
   alerting model directly on a spectral series you already have.

   *Live physical-sky flip (opt-in):* pass **`annual_nvrd(..., physical_sky=True)`** to drive the live
   nvRD path with the **physical per-timestep sky/sun spectra** from the EPW-derived spectral record
   (workflow H) instead of the static reference-SPD / 30° templates, with a per-step template fallback +
   a coverage report. Default is `False` → bit-identical to the template path. On the physical-sky path
   you can pick the clear-sky engine with **`engine="spectrl2"`** (default) **| `"smarts"`** (resolved
   lazily — only when `physical_sky=True`, so selecting `smarts` never errors on a `physical_sky=False`
   call). This live path is **not live-validated** (see §6).

→ *Output:* a relative alertness (R_D) time series, with an honest measure of how much the spectral
reconstruction choice moves the result.

> **Read R_D relatively.** The nvRD response was fit from nighttime studies; daytime adaptation is
> unvalidated and the reconstruction constant scales R_D. Compare scenarios/orientations, never as an
> absolute number — `annual_nvrd` always returns this caveat in `relative_RD_note`, and the
> `hcl://reference/nvrd-bridge` resource has the full list.

### G. "Design the lighting for this space and tell me if it works" — guided studio journey

This is the **front door**: instead of picking a single workflow, invoke the **`hcl_studio`** prompt and
it conducts a complete start-to-finish study — *set a goal → design the fixtures → simulate → visualise
and grade the result* — over **8 phases**, keeping one **resumable study brief** so the journey survives
an interrupted conversation. It is the orchestration layer over workflows A–F plus three studio-specific
tools (`recommend_fixtures`, `save_brief`/`load_brief`, `build_report`).


| Phase                                | What happens                                                                                                                                        | Tools                                                        |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| 0.**Orient**                         | Report what will run vs emit; pick a study slug +`channel_type` (held constant after)                                                               | `validate`, `radiance_status`, `daysim_status`, `load_brief` |
| 1.**Goal**                           | Circadian standard +**mel-EDI target at the vertical eye plane** and the occupied *condition* it applies at; EN 12464-1 visual task (Ēm/UGR/Uo/Ra) | `hcl://compliance/en_12464_1`                                |
| 2.**Space**                          | Dimensions, mounting/ceiling height, work-plane + eye height, surface reflectances, maintenance factor; orientation/glazing if daylight-aware       | —                                                           |
| 3.**Daylight baseline** *(optional)* | Daylight contribution at the reference points, at the goal's stated condition.**Credits the circadian budget only**                                 | `run_grid` / `run_annual`                                    |
| 4.**Fixture sizing**                 | First-principles spec: how many fixtures, what flux, what CCT/spectrum, what layout (§G.1)                                                         | **`recommend_fixtures`**                                     |
| 5.**Instantiate**                    | Supply a real IES that matches the spec; validate it and place it on the recommended layout                                                         | `ies_analyze`, `ies_to_radiance`                             |
| 6.**Simulate**                       | Grid with**both** horizontal work-plane **and** vertical eye-height sensors; optional annual dose/alertness                                         | `run_grid`, `run_annual`, `nvrd`                             |
| 7.**Controls & energy**              | Daylight-responsive dimming → power reduction and kWh/m²·yr                                                                                      | `daylight_savings`                                           |
| 8.**Report**                         | Render the brief to`report.{md,html}` and narrate the verdict inline (§G.3)                                                                        | **`build_report`**                                           |

After **every** phase the conductor calls `save_brief`; at the start it calls `load_brief` and resumes
if a populated brief exists. Every Radiance/Daysim step still honours the run/emit contract, so **the whole
journey works with zero binaries installed** — the sim steps emit command plans and the report still renders.

#### G.1 The fixture-design engine — `recommend_fixtures`

Pure `hcl_core`; **always runs**. Given a *space* + a *circadian/visual goal* it answers *"what artificial
lighting do I add?"* from first principles — no product catalogue. It reconciles two requirements:

- **Visual (lumen method).** `Φ = Ēm · A / (UF · MF)`, where `A` = floor area, `MF` = maintenance factor,
  and `UF` is a utilisation factor estimated from the **room cavity ratio** and the reflectances for the
  chosen distribution class (`direct` | `direct_indirect` | `indirect`). **Daylight is *not* subtracted**
  here — the installation must meet `Ēm` with no daylight; daylight savings are realised operationally in
  phase 7, not by under-installing.
- **Circadian (CIE S 026 mel-DER).** Required `mel-DER = (mel-EDI_target − mel-EDI_daylight) / E_v,eye`,
  where `E_v,eye = Ēm · (vertical/horizontal ratio)` (default V/H = 0.4, the dominant uncertainty). The
  needed mel-DER is solved over the project's **illustrative LED palette** and clamped to a physical
  ceiling, giving three bands:
  1. `≤ ~0.82` (palette max) → reachable; an example preset + CCT is named.
  2. `0.82 … 1.2` → reachable but **beyond the illustrative palette** → recommend a cool / blue-enriched
     white (CCT ≳ 5500 K) and verify mel-DER on the real SPD.
  3. `> 1.2` (`MEL_DER_PHYSICAL_MAX`) → **no spectrum can do it** → `binding_constraint = "circadian"`,
     `supplementary_fixtures_advised = true`, `glare_warning = true` (raise vertical/indirect light).

The binding (larger) of the two flux requirements sets the total; a spacing-to-height grid then fixes the
**layout** (`fixture_count = nx·ny ≥ max(flux_count, uniformity_count)` with positions), and
`watts = Φ / efficacy` gives the energy. Output (written to the `fixture_spec` brief slot) includes
`required_flux_lm`, `fixture_count`, `layout{nx,ny,spacing_m,positions}`, `target_cct_band`, `min_mel_der`,
`binding_constraint`, `power_density_w_m2`, `per_fixture_options`, plus `assumptions` and `caveats`.

> **Treat the spec as a starting point, never the verdict.** The CU table, the V/H ratio, and the
> CCT→mel-DER mapping are *illustrative estimates*. Phase 5 (`ies_analyze` on the real IES → recompute UF)
> and phase 6 (`run_grid` measuring real mel-EDI at vertical eye sensors) are authoritative.

#### G.2 The study brief — `save_brief` / `load_brief`

One JSON at `work_dir/<study>/brief.json` carrying the slug plus eight phase slots: `orient`, `goal`,
`space`, `daylight_baseline`, `fixture_spec`, `sim_results`, `energy`, `compliance`. `save_brief`
shallow-merges only the keys a phase changed (others untouched); the **slug argument is canonical** and
always overrides any `study` key inside the payload. `load_brief` returns an empty skeleton when none
exists, which is what makes the journey resumable. Two guards apply: the **study slug must match
`[A-Za-z0-9._-]+`** (no path separators — it becomes a directory name from tool arguments), and **unknown
top-level keys are rejected** so a typo'd phase name fails loudly instead of corrupting the schema.

#### G.3 The report — `build_report`

Pure templating over the brief (no Radiance) → `work_dir/<study>/report.md` and `report.html`. Sections:
**Goal · Space · Daylight Baseline · Fixture Spec · Target vs Achieved** (Ēm / mel-EDI / UGR / energy, each
with a ✅/❌ pass mark — UGR scored lower-is-better) **· Compliance · Notes & Caveats** (the fixture spec's
own assumptions and caveats, i.e. *what to change*). It also surfaces two cross-checks: the **circadian
verdict provenance** (annual/occupied-hours vs a single point-in-time grid) and a **mel-EDI ↔ UGR
conflict** flag when the circadian target is met but UGR exceeds the EN 12464-1 limit. It is
**emit-safe**: phases that were never run render *"not evaluated"*, and a simulated-but-imageless run shows
*"emit-only — no renderings"* rather than crashing.

### H. "Build a physically-derived spectral sky from an EPW" — radiative-transfer spectral pipeline

This pipeline replaces the channel-template sky with a **physical 1-nm spectrum** reconstructed from a
real weather file. The whole offline stack is pure `hcl_core`, so steps 1–3 **always run** (no binaries);
step 4 is the parallel native-Radiance engine and is **run-or-emit**.

**The pipeline:** EPW + `(month, day, hour)` → parse the hourly row + `atmosphere.derive` (AOD / PWV /
ozone / albedo) + `solpos.compute` (zenith / azimuth / air-mass at the mid-interval hour) → the
**SPECTRL2** clear-sky engine (pure-Python Bird port) → the **SEDES1** cloud bridge (an *always-on*
energy-rescale to the EPW's DNI/DHI, plus a CCM diffuse reshape keyed to the clearness index *Kt*) →
resample to 1 nm over 380–780 → a `SpectralSkyRecord` → consumers.

1. **`atmosphere_from_epw(epw, month, day, hour)`** — introspect the **derived atmospheric state** for one
   EPW hour: AOD, PWV, ozone, pressure, surface albedo, plus provenance. SYNC, pure-Python, **always runs**.
   Use it to see exactly what the pipeline assumed about the sky before you trust the spectrum.
   *Opt-in atmosphere refinements (all default to byte-identical prior output):* `ozone_mode="climatology"`
   (van Heuklon 1979 ozone from the EPW LOCATION lat/lon + date), `aerosol_g=` (aerosol asymmetry, default 0.65),
   and `aod_anchor_nm=` (Ångström-convert a declared-wavelength AOD to τ₅₀₀). The two spectral tools below
   accept the same three, plus `smarts_aerosol="user"` to make the SMARTS Ångström α + `g` settable.
2. **`spectral_sky_from_epw(epw, month, day, hour, overrides?, surface_tilt_deg?, engine?, spectral_albedo?, cloud_variant?, ccm_coeffs?)`**
   — the one-hour **physical SPD**: a `SpectralSkyRecord` as a dict (direct + sky-diffuse, 1 nm, 380–780).
   Pass `surface_tilt_deg` to also get the spectral **`ground`** glow term for a tilted receiver; by default
   this uses the grey albedo from the derived atmosphere — check its provenance if the ground term matters,
   since `source: "default"` means the EPW had no usable albedo (IWEC/TMY2 write `0.000`, which is treated
   as missing; see ADR-0004) and the 0.20 default is carrying the term — but you can pass a 1-nm **`spectral_albedo`**
   (401 values, `[0,1]`) to drive it with a real ground reflectance — e.g. feed
   `import_geometry(...)["ground_albedo"]` (workflow I) so the scene's ground material colours the sky's
   ground reflection. `overrides` lets you force individual atmosphere terms; `engine="spectrl2"`
   (default) **| `"smarts"`** selects the clear-sky engine (SMARTS needs `$SMARTSPATH`). It also accepts
   `cloud_variant="reanchored"` (default, byte-identical) **| `"verbatim"` | `"seed"` | `"local"`** to pick
   the SEDES1 cloud CCM, plus `ccm_coeffs=` (path to a fitted `wavelength_nm,A,B,C,sigma` CSV, required
   for `cloud_variant="local"`, from `hcl_core.sedes1_fit`). Every record's provenance now carries the
   CCM's per-wavelength regression uncertainty (`ccm_sigma`, sampled at 400/500/600/700 nm, +
   `ccm_sigma_mean`) — additive, default output unchanged. SYNC, pure-Python, **always runs**.
3. **`spectral_epw(epw, forms?, hours?, work_dir?, engine?, cloud_variant?, ccm_coeffs?)`** — emit spectral-sky **artifacts over the year** (or
   the `hours` subset, a list of `[month, day, hour]`) into `work_dir`:
   `forms ⊆ {spd_set, band_matrix, spectral_wea, sidecar}` (default all). Returns `{files, n_records}`.
   Honors the same `engine="spectrl2"` (default) **| `"smarts"`** selector, plus the same
   `cloud_variant`/`ccm_coeffs` SEDES1 selection and `ccm_sigma`/`ccm_sigma_mean` provenance as step 2.
   ASYNC and **LONG-RUNNING for a
   full year**, but still pure-Python (with the default engine) — **no binaries**, so it always runs.
4. **`spectral_sky_native(epw, mf=1, mode="all", work_dir?, run=True, timeout?)`** — the **parallel native
   engine**: a native Radiance 6.x spectral sky via **`gensdaymtx`** (a 20-band W/sr/m² matrix → `rcomb -c M`
   melanopic collapse). `mode = all | sun (-d) | sky (-s)`. (`gensdaymtx` implements Perez et al.
   1990/1993 all-weather sky + OPAC continental aerosol spectral shape; model
   lives in Radiance 6.x. Sky-vault patches: Reinhart/Tregenza, Reinhart 2001 MF subdivisions of
   Tregenza 1987.) **RUN-OR-EMIT**: it degrades to emitting the
   `gensdaymtx` + `rcomb` command plan when Radiance 6.x `gensdaymtx` is absent (on this system
   Radiance 6.1a is installed at `/usr/local/radiance/bin`, so it runs live).
   > **Cost & `timeout`.** `gensdaymtx` processes **every hour of the EPW**. A full 8760-hour year at
   > `mf=1` (NROWS=146, NCOMP=20) is **fast — ~12 s wall / ~10 s CPU on Radiance 6.1a** (measured
   > 2026-06-29) — but cost grows **steeply with the Reinhart subdivision `mf`** (minutes at `mf≥4`).
   > `timeout` (seconds) caps the subprocess; **default `None` = no cap** so a real annual run completes.
   > On expiry the tool returns `{ran:True, ok:False, timed_out:True, …}` rather than raising. Keep `mf`
   > low (or trim the EPW) for a fast run.
   >

→ *Output:* a physically-derived spectral sky for one hour or the whole year — introspectable atmosphere,
a 1-nm SPD (+ optional receiver ground), annual artifact files, and a parallel native-Radiance matrix.
Feed it forward via `annual_nvrd(physical_sky=True)` (workflow F) to drive the live alertness path with
physical per-timestep spectra.

> **Rendering this sky (the bridge to workflow B).** To trace it, bin both components with
> `spd_to_channels` (once on `sky_diffuse_horizontal`, once on `direct_normal`) and pass them to
> `colored_sky` — **together with the record's solar geometry**:
> `sun_zenith_deg=rec["geometry"]["zenith_deg"]`, `sun_azimuth_deg=rec["geometry"]["azimuth_deg"]`.
> The record's geometry is evaluated at the **mid-interval** instant; `colored_sky`'s `hour` is a
> wall-clock instant gendaylit re-derives the sun from, so without those two arguments the spectrum
> and the sky it is painted onto sit **7.5° of diurnal arc apart**. See workflow B step 2.

> **Engine selection.** Steps 2–3 (and `annual_nvrd(physical_sky=True)` in workflow F) take an
> `engine="spectrl2"` (default) **| `"smarts"`** argument, resolved by `hcl_core.spectral_engine.resolve_engine`.
> SPECTRL2 is the pure-Python default that always runs; `"smarts"` requires `$SMARTSPATH` and raises a clear
> `RuntimeError` early when it is unset (no silent fallback). `atmosphere_from_epw` takes **no** `engine` (its
> derived-atmosphere output is engine-invariant), and `spectral_sky_native` (step 4) is the separate native
> engine with its own output contract.
>
> **Capability-gated honesty.** The offline Python stack (steps 1–3, default engine) runs end-to-end and is
> unit-tested. The native `gensdaymtx` engine (`spectral_sky_native`, step 4) has had its **first live
> validation** against Radiance 6.1a: NCOMP=20 confirmed, loose-envelope agreement with the offline Python
> engine (Pearson 0.987) — this is a validation run, not a known-good baseline. **SMARTS** (selectable via
> `engine="smarts"`, `$SMARTSPATH`-gated) was **first run live 2026-06-21** — compiled from the NREL 2.9.5 Fortran source
> (that distribution's Mac binary is dead PowerPC); with `$SMARTSPATH` set the gated
> cross-check passes and SMARTS agrees with the Python SPECTRL2 engine to ~2 % direct / ~7 % diffuse, r≈0.99
> (`docs/spectral-engine-comparison.md`) — also a validation, not a baseline. The live `physical_sky` flip
> had its **first live execution 2026-07-18** (`office_room` + GRC Athens IWEC on real Daysim + Radiance 6.1a,
> 50.03 % physical coverage, time-resolved sun — `spectral-sky-as-built.md` §3septies), superseding the
> "never run against real binaries" note this line used to carry. It remains **opt-in, default-off and
> shape-only**, and one live run is not a validation of the shape it substitutes. The SEDES1 **CCM coefficients are now the
> faithful Nann & Riordan Fig. 11 digitization** (re-anchored to unity at clear — the shipped default; the
> legacy 9-point seed is opt-in via `cloud_variant="seed"`), and only the energy-rescale to EPW DNI/DHI is exact
> (the spectral *shape* carries figure-digitization uncertainty). That uncertainty is now **surfaced, not
> just acknowledged**: every record's provenance carries the CCM's per-wavelength regression σ
> (`ccm_sigma`/`ccm_sigma_mean`), and the CCM itself is **locally re-fittable** — pass `cloud_variant="local"`
> with `ccm_coeffs=` pointing at your own fit from `hcl_core.sedes1_fit` (see
> `docs/recalibrating-cloud-ccm.md`). The physics is
> **opt-in** (the 30° template fallback is still the default everywhere). Canonical caveat wording lives
> in `docs/spectral-sky-as-built.md` §9.

### Which engine, when, why — the decision guide

**Default path (what ships).** `spectral_sky_from_epw` / `spectral_epw` run **SPECTRL2 + SEDES1** by
default — pure-Python, no binaries, every hour. Reach past the default only when it is the wrong tool for
your **receiver** and **metric**; for a horizontal / energy / photopic number it always is.


| You need…                                                                         | Use                                             | Tool / flag                                   | Why                                                                                                                                                                                                                                                                   |
| ------------------------------------------------------------------------------------ | ------------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Fast, portable spectrum for any hour —**the default**                             | **SPECTRL2 + SEDES1**                           | `spectral_sky_from_epw` (`engine="spectrl2"`) | Pure-Python, always runs; direct beam golden-tested (<0.05 % vs the Fortran reference); within ~7 % of SMARTS on diffuse. The everyday choice.                                                                                                                                            |
| Reference**direct-beam** spectrum / maximum spectral resolution                    | **SMARTS**                                      | `engine="smarts"` (needs `$SMARTSPATH`)       | Line-resolved gases, 280–4000 nm.*Caveat:* it is the **bluest** engine, and that blueness is **engine physics**, not an atmosphere assumption. Use for the beam, **not** for circadian colour.                         |
| Façade- or eye-level**colour / melanopic** — the HCL case                        | **gensdaymtx** *(or SPECTRL2 + the P3 wrapper)* | `spectral_sky_native` (Radiance 6.x)          | Only engine with**angular structure**: it produces an orientation-dependent façade colour (the wrapper's fitted η = 0.5 gives a ~1676 K spread at a clear afternoon hour). The isotropic engines predict **one colour for every façade** — constitutionally wrong off-horizontal. |
| Horizontal roof / energy / photopic number                                         | **any of the three**                            | the default is fine                           | They agree on horizontal`E_diffuse` **by construction** (the DHI anchor); the angular model buys nothing here.                                                                                                                                                                            |
| Annual spectral artifacts (`spd_set` / `band_matrix` / `spectral_wea` / `sidecar`) | **SPECTRL2 + SEDES1**                           | `spectral_epw` (`engine="spectrl2"`)          | Pure-Python → always completes; same engine selector as the one-hour tool.                                                                                                                                                                                                               |
| Drive the live alertness / nvRD path with physical spectra                         | physical pipeline                               | `annual_nvrd(physical_sky=True)`              | Per-timestep physical spectra instead of the 30° template (opt-in; the template is still the default everywhere).                                                                                                                                                                        |
| Maximum rigour, willing to build input decks                                       | **libRadtran** (external, not in repo)          | —                                            | Full RTE + per-direction radiance; highest fidelity, highest effort. Listed for completeness as the highest-fidelity external option.                                                                                                                                                     |
| Shape only, no physics (legacy / backward-compat)                                  | template / D-series path                        | `colored_sky` etc.                            | ±25 % melanopic error — superseded by the physical path; keep only for compatibility.                                                                                                                                                                                                   |

**Optional correction layers** (composable consumers of the record — the engines themselves are untouched):

- **Anisotropic wrapper** — gives the isotropic engines (SPECTRL2/SMARTS) orientation-dependent façade
  colour without paying for a full `gensdaymtx` matrix (one fitted knob, η = 0.5). Turn it on for vertical
  or eye-level receivers; `isotropic` mode stays bit-identical to today. ⚠️ η is **empirical**, fitted
  against an internal dataset that is not published with this toolkit, and the fit constrains it to an
  **interval, η ∈ [0.19, 0.69]**, not a point — so "fitted" here must not be read as a point estimate.
- **Clear-sky bias `K(λ)`** — **default-off**, opt-in spectral warming of the clear diffuse, which runs
  too blue before any cloud term. It stays **opt-in because it is a correction layer that changes
  output** — enabling it moves every clear-sky number, and any figure computed with it enabled should be
  recomputed after any change to the curve; with the default every output is bit-identical. ⚠️ `K(λ)` is
  **empirical**: the shipped curve was derived from an internal dataset that is not published with this
  toolkit. It is applied **shape-only** on unit-area-normalised spectra, so that dataset's absolute scale
  never enters the correction. See [validation §5](spectral-engine-validation.md).

> **The one rule that orders all of this: _bluer ≠ better._** For a **horizontal** sensor all three engines
> are interchangeable (DHI-anchored). The instant the receiver is a **vertical façade or an eye**, angular
> structure is first-order — only `gensdaymtx` / the P3 wrapper has it, and SMARTS's extra blueness becomes
> the *largest* melanopic error rather than an asset. Full per-engine comparison:
> [`docs/spectral-engine-comparison.md`](spectral-engine-comparison.md) and
> [`docs/spectral-engine-validation.md`](spectral-engine-validation.md); the wider landscape (libRadtran,
> legacy templates, D-series) is summarized in the engine decision table above.

### I. "Bring a real CAD room into the pipeline" — OBJ/CAD geometry import

`import_geometry` turns a Wavefront `.obj` (exported from CAD/BIM) into the per-channel Radiance scene
that workflows B/C/E consume — no hand-built geometry. It is **run-or-emit** (needs `obj2rad` + `xform`,
both in Radiance 6.1a); the material `.rad` files and the `obj2rad` mapfiles are always authored in pure
Python, so the **emit path works with no binary installed**.

1. **`import_geometry(obj_path, material_map, units, up_axis, channel_type=1, work_dir, run=…, north_angle_deg=…, dry_run=…, sidecar=…, derive_sensors=…, annotate=…, eye_heights=(1.2, 1.6), workplane_h=0.8, spacing=0.6, strict=False)`** —
   discover the OBJ's material groups (`usemtl` names, else `g` groups), bind each to a spectral material,
   convert per channel-set with `obj2rad -m <mapfile>` (→ suffixed modifiers `<group>_a/_b/_c` matching
   `write_material`), and normalize units/axis with `xform` (`-s` to metres; `-rx 90` for `up_axis="Y"`).

   - **`material_map`** = `{group: <spec>}`, keyed by the discovered group names, where `<spec>` is **either**
     a library-name **string** (e.g. `"painted_gypsum"`, resolved through the surface library — flagged
     *illustrative*) **or** an inline dict `{"type": "plastic"|"glass"|"ground"|"context"|"luminaire"|"floor", "refl"|"tvis": v, "spd"?: …, "ies"?: …, "roughness"?, "specularity"?}`. Tag the floor slab
     **`type:"floor"`** — it anchors the sensor footprint, sets the floor-top Z that work-plane height is
     measured from, and supplies the interior reference that orients observer gaze inward; omitting it is what
     `check_geometry` reports as `NO_FLOOR_GROUP`, and the untyped-floor fallback has produced observer gaze
     116° off (see `hcl-methodology.md` §12.6). A scalar `refl`/`tvis` is
     broadcast to a flat per-channel triplet; an `spd` is binned via `bin_average(parse_spd(…))`. **Every
     discovered group must be mapped** — an unmapped group **hard-fails** with an `UnmappedGroupsError`
     whose `.payload` is the full discovery report (no silent generic material; the OBJ carries no spectral
     data of its own).
     The map may also carry **its own metadata alongside the group specs** — `_`-prefixed comment keys
     (e.g. `_README`) are dropped, and `units` / `up_axis` / `north_angle_deg` / `channel_type` are read as
     import scalars wherever you left the corresponding argument unset (an explicit argument always wins).
     This is the same convention for both routes, so **you can pass a sidecar's parsed contents straight
     into `material_map=`** — previously only the `sidecar=` file loader stripped metadata, and an inline
     paste died with `KeyError: unknown surface "Pinned material map for …"`, quoting the file's own
     comment as a material name. A key that is neither a comment nor a recognised scalar is still a group
     spec, so a typo'd material name raises as before.
   - **`units`**: `mm|cm|m|ft`; **`up_axis`**: `Y|Z`. A bounding-box sanity check warns on implausible
     room sizes (the usual symptom of a wrong unit or up-axis).
   - **`dry_run=True`** — return a **discovery payload** (`groups`, `bbox_m`, `mesh_quality`, and `.mtl`
     `suggestions`) without binding materials or running Radiance: confirm the mapping *before* committing
     compute. **`sidecar=`** points at a reusable `*.matmap.json` (explicit kwargs always win over it).
   - **`north_angle_deg`** — the true clockwise azimuth (`0=N, 90=E`) that the model's post-remap +Y faces;
     applied as the final `xform -rz (−north_angle_deg)` to **every** channel run so the room is correctly
     oriented to the spectral sky's sun. **Wrong-is-silent** (like units/axis) — set it deliberately.
   - **`derive_sensors=True`** — also return `grid_points` (work-plane, floor **top face** + `workplane_h`, up-facing) and
     eye-level observers gazing toward the glazing as **`observer_sets`** — one set per entry in
     `eye_heights` (default **seated 1.2 m + standing 1.6 m**), each with its own `points` and DGP
     `glare_views`; flat `observer_points`/`glare_views` (all heights concatenated) are also returned for
     back-compat. `workplane_h`/`spacing`/`eye_heights` tune the layout. All points are in the scene's final
     world frame. **`annotate=True`** — also return a material `summary` table + the colored-by-material
     `falsecolor` command plan (the `oconv→rpict→falsecolor` render is live-validated on Radiance 6.1a).
   - **Returns** `geometry_set` + `material_sets` — index-aligned, one entry per channel-set (1 for 3ch,
     3 for 9ch) — plus the discovered `groups`, `warnings`, run-or-emit `commands`, an always-present
     per-aperture **`apertures`** report (area + true-north azimuth/tilt), a provenance **`manifest`**
     written to a `manifest.json` sidecar (`manifest_path`) **and** embedded as a `#`-comment header in each
     geometry `.rad`, and an always-present **`result["health"]`** geometry-health report ({`ok`, `counts`,
     `findings`, `checked`, `skipped`, `confidence`}) — plus an `advisories` entry
     (`GEOMETRY_HEALTH_UNCLEAN`) whenever that report is not clean, so an unread `health` block still
     surfaces. (`check_geometry` returns the same report at the **top level**, with no `health`
     wrapper.) The report covers non-finite (NaN/infinite) vertex coordinates,
     coincident surfaces, an unopened window, duplicate/non-planar/degenerate/non-manifold faces, an
     unclosed room, and no group typed `type:"floor"` (**`NO_FLOOR_GROUP`**, warning — heights and the
     interior reference are then estimated rather than measured from a real floor) — none of which stop
     the import from completing with a plausible-looking scene otherwise. Non-finite coordinates are
     *reported*, not fatal: the health check never raises on a parseable OBJ, it used to crash on a NaN or
     infinite vertex before this was caught and fixed. **`strict=True`** raises `GeometryHealthError`
     (`.payload` is the same report) instead of returning when the report holds any `error`-severity
     finding; the standalone **`check_geometry`** tool runs the same audit with no Radiance call and no
     scene build, for auditing a model before committing compute. Conditionally (only when their feature
     is mapped/requested): **`ground_albedo`** +
     `ground_albedo_kind` (a 1-nm albedo from any `type:"ground"` group → feed to
     `spectral_sky_from_epw(spectral_albedo=…)`), **`electric_lights`** (drop-in luminaire payload),
     **`context_groups`** (the `type:"context"` exterior-shading groups), and the
     sensor/`observer_sets`/`summary` sections above.
     Beyond the quick bundled `derive_sensors`, several dedicated **methodology-grade** tools generate
     analysis points and diagnostics from the same OBJ and material_map — without requiring Radiance:
     **`workplane_grid`** applies the EN 12464-1 work-plane spacing formula (plane at floor-top +
     `workplane_h`; max spacing `p = 0.2·5^log10(d)`, d = the larger dimension of the **calculation area**
     — the interior inset by `border_offset`, not the raw interior extent; interior extent by
     innermost-wall-face detection, not the outer vertex bbox) and writes `grid.pts` → feed directly to
     `run_grid` for horizontal task lux. It now **clips to the real floor polygon by default**
     (`clip_to_footprint=True`, `footprint_border=0.0`) and covers **non-rectangular rooms end-to-end,
     including concave L/T/U shapes** — when inner-wall detection degenerates on a concave room, the
     interior falls back to the floor bounding box (then polygon-clipped), reported via
     `interior_extent_source="footprint_bbox"` with a warning; the rectangular office grid stays
     byte-identical (45 points; a live L-room test yields 48 cells with 16 dropped, both arms covered).
     **`observer_points`** anchors eye sensors at seat-object centroids and aims them at paired screen objects
     (by trailing name suffix); when no screen is found it falls back to window gaze, a fixed azimuth, or a
     sweep of N views; when no seats are found it falls back to `position_fallback="room_center"`. It also
     returns ready-made `glare_views` fisheye strings → feed to `glare_ugr`. It now also **checks (but does
     not move) observers against the floor footprint** (`clip_to_footprint=True`), reporting
     `methodology.footprint_checked` and warning on any furniture-anchored observer that falls outside it.
     **`photosensors`** places daylight-dimming reference sensors: it locates the dominant glazed facade,
     builds window-head-height sidelighting zones, and drops one horizontal sensor per zone (centred on the
     facade, clipped to the floor) — feed the resulting `.pts` into `run_grid`/`run_annual` to drive
     daylight-linked dimming logic (workflow D). **`preview_scene`** renders a matplotlib PNG plan + 3D
     view of the true floor polygon plus whichever point layers you pass (grid/observer/photosensor `.pts`)
     — a diagnostic placement check, not a photometric render. Use these tools (via the `place_sensors` and
     `visualize_scene` prompts) when you need the full EN-compliant methodology and a visual sanity check
     rather than the heuristic bundled grid; `import_geometry(derive_sensors=True)` remains the quick
     integrated path.
2. **Compose into a grid/annual run** — and let the geometry supply the sensors too:

   ```python
   result = import_geometry(obj_path, material_map=…, units=…, up_axis=…,
                            north_angle_deg=θ, derive_sensors=True, work_dir=…)
   sky = spectral_sky_from_epw(epw, m, d, h, surface_tilt_deg=90,
                               spectral_albedo=result.get("ground_albedo"))   # ground couples to the sky
   scene_sets = [[*mats, sky_rad, geom]
                 for mats, geom in zip(result["material_sets"], result["geometry_set"])]
   run_grid(scene_sets=scene_sets,
            points=result["observer_points"],          # vertical-at-eye (mel-EDI); or ["grid_points"]
            electric_lights=result.get("electric_lights"),   # drop-in luminaires (run_grid colorizes)
            channel_type=…)
   ```

   `grid_points`/`observer_points` are already `[x,y,z,dx,dy,dz]` rows — `run_grid`/`run_annual`'s `points`
   take them directly (use a single `observer_sets` entry's `points` to pick seated-only or standing-only);
   `glare_views` are ready-made fisheye `view` strings for `run_image`/`glare_ugr`; `electric_lights` is a
   drop-in luminaire payload `run_grid`/`run_image` consume directly (they run `ies2rad`/colorize); and
   `ground_albedo` colours the sky's ground-glow term. Then proceed with workflow **B** (grid), **C**
   (annual), **D** (electric), or **E** (image/glare) — no hand-built geometry, points, or camera.

   > **North is the one silent-correctness lever.** The sky/sun (`colored_sky`, `run_annual`'s DDS) is built
   > in a **fixed +Y = true-north** world frame; the imported room is rotated to match **only** by
   > `north_angle_deg` (geometry-side `xform -rz` — there is no north knob on `run_grid`/`run_annual`/the sky).
   > Omitting it assumes the model was authored +Y = true-north; if it wasn't, every daylight/annual result is
   > azimuth-wrong with no error. Set it whenever you combine imported geometry with a sky.
   >

→ *Output:* a per-channel Radiance scene from a real CAD export — ready to drop into the daylight
pipeline — with discovered groups + warnings, derived sensors/views, and (when Radiance is absent) the
exact `obj2rad`/`xform` command plan.

> **`Material` vs `Group` qualifier (live-checked).** `obj2rad`'s `-m` mapfile matches the `Material`
> qualifier **only** to `usemtl` names. So `import_geometry` emits `(Group "x")` for OBJs whose groups
> come from `g` (no `usemtl`) — otherwise obj2rad would silently drop every face and render nothing — and
> keeps `(Material "x")` when `usemtl` is present. A **mixed** OBJ (`usemtl` plus bare-`g` faces obj2rad
> would drop) **hard-fails** rather than silently losing geometry. A capability-gated test runs real
> `obj2rad` and confirms a group-only OBJ emits polygons.
>
> **Convenience features.** The auto work-plane/eye sensors (`derive_sensors`,
> with **dual seated 1.2 m + standing 1.6 m** `observer_sets` and tunable `eye_heights`/`workplane_h`/`spacing`),
> true-north orientation (`north_angle_deg`), the named **surface library** + `*.matmap.json` sidecar, `.mtl`
> reflectance **hints** (in `dry_run` discovery), and the per-aperture orientation report (area-weighted normal)
> are all live-validated against Radiance 6.1a — added **additively**, so the base return contract
> is unchanged (new keys only). `type:"ground"` yields a 1-nm **`ground_albedo`**
> that feeds `spectral_sky_from_epw(spectral_albedo=…)`; `type:"context"` is **exterior shading** (in the octree,
> out of the sensor footprint); `type:"luminaire"` markers emit a **drop-in `electric_lights`** payload; the
> provenance **manifest** is a `manifest.json` sidecar **and** an embedded `.rad` header; and the annotated
> colored-by-material render is **live-validated**. Still: **no spectral data is read from the OBJ or its
> `.mtl`** — reflectances are user-assigned (the `.mtl` is a hint only). The **measured-SPD path exists**
> (a library entry is `measured` only with a citation + a readable SPD file), but the *shipped* catalog stays
> illustrative scalars pending data. Deferred: frame-vs-glazing split, auto ground-plane *geometry* synthesis,
> BSDF/shading-device conventions, and glTF/IFC import. See the `import_obj_room` prompt and the
> `hcl://reference/geometry` resource for the full contract.

---

## 4. Tool reference (all 47, grouped)

> **47 tools, 51 registered names.** The server also registers **4 verb-object aliases** against the
> same callables — `get_reference`→`reference`, `list_presets`→`presets`, `import_weather`→`weather`,
> `run_validation`→`validate` (`server.py`, `_TOOL_ALIASES`) — for clearer AI tool selection. They are
> not additional tools, so a client's `list_tools` shows **51** while this guide, the README and
> `technical-reference.md` all count **47**. Both numbers are right; neither is a drift.

**Spectral core — always runs (no binaries):**
`spd_to_channels`, `glass_transmissivity`, `write_material`, `circadian_metrics`, `alpha_opic`,
`spectral_metrics`, `compliance`, `presets`, `reconstruct_spectrum`, `nvrd`, `lighting_controls`,
`validate`, `reference`, `recommend_fixtures`, `quality_presets`.

**Radiance layer — run or emit:**
`radiance_status`, `colored_sky`, `colored_luminaire`, `run_grid`, `run_image`, `run_annual`,
`annual_daylight`, `lm83_daylight`, `daylight_factor`, `weather`, `import_geometry`, `check_geometry`,
`ies_analyze`, `ies_to_radiance`, `glare_ugr`, `daylight_savings`.
(`lm83_daylight` computes IES LM-83-12 sDA/ASE through a **three-phase** transport with a Klems
glazing BSDF and **operates blinds** per §2.2.6 — deploy when >2 % of the grid sees direct sun,
floored at 1 point, default blind 5 % diffuse VLT. `annual_daylight` computes the same metric
arithmetic on whatever shading the scene already has. Neither is a submission:
`lm83_method_conformant` is always false by design — glazing runs at raw `tvis`, §§2.2.8–2.2.11 out
of scope — read `conditions.departures`.)
(`import_geometry` needs `obj2rad`/`xform`; it writes material `.rad` + mapfiles in pure Python and
emits the `obj2rad`/`xform` plan when Radiance is absent — see workflow I.)
(`quality_presets` is pure-Python but belongs with these in practice: it names the ambient
accuracy/runtime trade-off — `low` `-ab 0` / `medium` `-ab 2` / `high` `-ab 3` / `extra_high` `-ab 5` —
that the **nine** simulation tools accept as `quality=`. An explicit `rad_params` always wins. Passing
neither inherits a preview-grade default *by not choosing*, which on a validated annual run returned
sDA 77.78% against a converged 100.00% on identical geometry; `annual_daylight` now says so in its
result via `convergence_warning`.)
(`annual_daylight` runs the annual 2-phase DDS pass (total sky+sun, ambient-bounced) plus a dedicated
direct-only `-ab 0` pass for ASE, then reduces both to per-point DA/cDA/UDI and spatial sDA/ASE
(`hcl_core.daylight_metrics`). `daylight_factor` runs an indoor grid under a CIE Standard Overcast Sky
(`gensky -c`) plus a sky-only exterior reference point, then returns `DF = E_indoor/E_outdoor × 100`
per point. Both accept `points=[...]`/a `.pts` path or `sensor_set='name'`; both always simulate the
full 8760-h year (`annual_daylight`) or year-scale energy pass (`daylight_savings` annual) — neither
wires a `period`/`partial_year` flag yet. **Live status:** `daylight_factor` had a first live smoke
validation on real Radiance 6.1a (toy fully-glazed scene — sane DF distance falloff, a sky-file-ordering
bug found there is fixed); `annual_daylight`'s core `run_annual_daylight` likewise ran live on
the same toy scene first. On **2026-07-18**, both MCP tool wrappers ran live end-to-end on a realistic
`office_room` + GRC Athens IWEC: `daylight_factor` gave df_avg 3.53% (df_min 0.29% → df_max 15.87%);
`annual_daylight` gave sDA300/50% = 75.6%, ASE1000,250h = 31.1% over the full 8760-h year.
`daylight_savings` ran both modes (point-in-time + annual) live end-to-end too. Not a
measured/calibrated baseline.)

**Daysim + alertness bridge — run or emit:**
`daysim_status`, `build_daysim`, `generate_subhourly_wea`, `annual_nvrd`.

**Spectral-sky from EPW — pure-Python (always runs), except the native engine:**
`atmosphere_from_epw`, `spectral_sky_from_epw`, `spectral_epw` (all pure `hcl_core`, no binaries);
`spectral_sky_native` is **run-or-emit** (native Radiance 6.x `gensdaymtx`, degrades to emitting the
command plan). `spectral_sky_from_epw` and `spectral_epw` accept `engine="spectrl2"` (default) | `"smarts"`
to choose the clear-sky engine, plus `cloud_variant="reanchored"` (default) | `"verbatim"` | `"seed"` | `"local"`
(with `ccm_coeffs=` for `"local"`) to choose the SEDES1 cloud CCM; `atmosphere_from_epw` does not (engine-invariant output).

**Geometry sensor tools — pure-Python (always run, no binaries):**
`workplane_grid`, `observer_points`, `sensors`, `photosensors`, `preview_scene`.
(The first four parse the OBJ and write `.pts` sensor files with no Radiance call — they always execute
like `import_geometry`'s pure-Python authoring stage. Each requires the same `material_map` or `sidecar`
used for `import_geometry` to identify floor/wall/glazing groups. `workplane_grid` produces an EN 12464-1
work-plane grid (`grid.pts`) → feed to `run_grid` for horizontal task lux; it clips to the real floor
polygon by default (`clip_to_footprint=True`) and covers non-rectangular rooms end-to-end, including
concave L/T/U shapes (falling back to the floor bounding box, polygon-clipped, when inner-wall detection
degenerates). `observer_points` produces workstation eye sensors anchored to seat/screen object pairs,
with window/azimuth/sweep fallbacks, plus ready-made `glare_views` strings for `glare_ugr`; it now also
checks (without moving) observers against the floor footprint (`clip_to_footprint=True`), reporting
`methodology.footprint_checked`. `sensors` is a separate, general-purpose named-set manager —
`action=create|list|get|delete` persists an explicit points list or an EN 12464-1 `grid={...}`
under `work_dir` as a `.pts` file + JSON registry entry, so `annual_daylight`/`daylight_factor`/
`daylight_savings` can reference it later via `sensor_set='name'` instead of re-passing `points=[...]`.
`photosensors` places daylight-dimming zone sensors: it finds the dominant glazed facade, builds
window-head-height sidelighting zones, and drops one horizontal sensor per zone (centred on the facade,
clipped to the floor) for daylight-linked dimming control (workflow D). `preview_scene` renders a
matplotlib PNG plan + 3D scene preview — the true floor polygon plus whichever point layers
you pass (grid/observers/photosensors) — a diagnostic placement check, explicitly NOT a photometric
render (contrast with `run_image`, which is Radiance `rpict`).)

**Studio journey — brief persistence and reporting:**
`save_brief`, `load_brief`, `build_report`.

(Run `validate()` + `radiance_status()` + `daysim_status()` at the start of a session to see what will
execute vs emit. Full signatures are in each tool's docstring / MCP schema.)

## 5. Resources & prompts

**Resources** (14 — read for reference data and conventions). They are served from a single registry
module (`hcl_mcp/resources.py`); each carries a title/description/mime-type/tags, and the three `{…}`
templates offer argument completion:

- `hcl://reference/coefficients` · `hcl://reference/bins` · `hcl://reference/ies` ·
  `hcl://reference/lighting-controls` · `hcl://reference/daysim` · `hcl://reference/nvrd-bridge` ·
  `hcl://reference/geometry` — the OBJ/CAD import contract (`import_geometry`: material_map + surface
  library, the obj2rad Material/Group qualifier rule, units/axis/north, run-or-emit, core import plus
  dual-height sensors/north/ground-albedo bridge/context-shading/drop-in electric_lights/manifest sidecar+header,
  plus `photosensors`, `preview_scene`, and footprint clipping on `workplane_grid`/`observer_points`)
- `hcl://reference/caveats` — the §9.3 source-port caveats (markdown)
- `hcl://reference/glossary` — HCL metrics & units glossary: mel-EDI, EML, mel-DER, CCT/Duv, α-opic (markdown)
- `hcl://index` — a one-read catalog of every resource + valid template argument values
- `hcl://preset/{name}` — an illuminant SPD by name (e.g. `D65`, `A`, `LED_4000K`)
- `hcl://action-spectrum/{type}` — a 1-nm CIE S 026 action spectrum (`S | M | L | rhod | mel | V | D65`)
- `hcl://compliance/en_12464_1` · `hcl://compliance/{standard}` — the **stored** threshold tables
  (`well_v2_l03 | brown_2022 | iso_cie_8995_1_2025 | en_17037 | en_12464_1 | ul_24480`), returned
  read-only with **no scoring** (backed by `compliance.describe_thresholds`, not a `mel_edi=250` probe).
  The static `en_12464_1` is registered before the `{standard}` template so it wins on exact match.

(For a free-text overview, call the `reference` tool with `topic="overview"`.)

**Prompts** (13 — guided multi-step workflows — good entry points):
`hcl_studio` · `spd_to_circadian` · `hcl_grid_study` · `import_obj_room` · `fisheye_eye_analysis` ·
`annual_circadian_dose` · `annual_daylight_study` · `electric_lighting_design` · `annual_alertness` ·
`spectral_sky_from_epw` · `explain_concept` · `place_sensors` · `visualize_scene`.

> **`import_obj_room`** is the guided entry point for **workflow I** — it walks `radiance_status` →
> `import_geometry` → `scene_sets` composition → `run_grid`/`run_annual`, with the OBJ honesty rules
> (unmapped/mixed-untagged groups hard-fail). Full contract: the `hcl://reference/geometry` resource.

> **`spectral_sky_from_epw`** is the guided entry point for **workflow H** — it walks
> `atmosphere_from_epw` → `spectral_sky_from_epw` → `alpha_opic`/`spectral_metrics` to reconstruct the physical
> spectral sky for one EPW hour and read its CCT / mel-DER / mel-EDI.

> **`place_sensors`** orchestrates the methodology-grade sensor tools: confirm geometry → `workplane_grid`
> (shows the EN 12464-1 spacing math, produces `grid.pts`, footprint-clipped) → `observer_points` (shows
> detected workstations and any fallbacks applied, produces the observer `.pts` + `glare_views`, footprint-
> checked) → `photosensors` (daylight-dimming zone sensors) → `preview_scene` (a final matplotlib PNG placement check)
> → hands `grid.pts` to `run_grid` for horizontal task lux and the observer `.pts` + `glare_views` to
> `glare_ugr`.

> **`visualize_scene`** is the guided entry point for the **PNG preview** flow: confirm OBJ + material_map →
> generate or locate grid/observer/photosensor `.pts` → `preview_scene(render="all", ...)` → report the
> `image_paths` (diagnostic plan + 3D PNG overlays, not a photometric render).

> **`annual_daylight_study`** is the guided entry point for the **climate-based (photopic) daylight**
> track: create/reuse a named `sensor_set` → `annual_daylight` (per-point DA/cDA/UDI + spatial sDA/ASE,
> with ASE on its own direct-only `-ab 0` pass) → `daylight_factor` (CIE-overcast DF %) →
> `daylight_savings(mode="annual")` for the multi-point energy reduction, interpreted against
> LEED v4 / EN 17037. It is the visual-daylighting counterpart to `annual_circadian_dose`.

---

## 6. Prerequisites & gotchas

- **Radiance** (workflows B–E and spectral-sky step 4): install Radiance and either put it on `PATH` or
  set `HCL_RADIANCE_BIN`. Without it, every grid/image/annual/glare tool *emits* its command plan instead
  of running. Installing Radiance 6.1a (or later) also enables the native spectral `gensdaymtx` path
  (`spectral_sky_native`) and the OBJ importer (`import_geometry`, workflow I — needs `obj2rad`/`xform`).
- **The Radiance build's `A1` handling** (any workflow using `electric_lights` / IES luminaires):
  check `radiance_status().source_cal.a1_honored` **before** quoting an electric or glare number. A
  build that resolves `source.cal`'s `corr`/`flatcorr` to the compiled `source_corr` drops the
  `ies2rad` candela scale, and every IES luminaire silently under-emits — 34 lx instead of 494 lx on
  a 4-downlight office, with `glare_ugr` reporting a clean **UGR 0** rather than an obviously wrong
  number. Fix with `HCL_RADIANCE_SHIM=1` (no `sudo`, install untouched). ⚠️ The factor is
  per-luminaire, so **re-run** affected studies rather than scaling them, and **re-check after any
  Radiance reinstall or upgrade**. Stock builds are typically fine; source builds are the risk.
- **Daysim** (workflow F): not bundled. `build_daysim(run=True)` builds it from source (`cmake` + a C
  compiler required); then set `HCL_DAYSIM_BIN`. Without it, `generate_subhourly_wea`/`annual_nvrd`
  emit their plans.
- **Coordinate convention** for Daysim location overrides: WEST-positive longitude, `time_zone` in
  **degrees** (= −15 × UTC offset). You normally don't touch this — location is read from the EPW.
- **`annual_nvrd` is long-running** and elicits a confirmation; pass `run=False` to just get the plan.
- **`run=False` everywhere** is your friend: it shows the exact commands so you can audit or run a
  pipeline by hand on a Radiance/Daysim machine, then feed results back into the pure-`hcl_core` tools.
- **Honesty caveats are returned in-band:** `annual_nvrd` carries `relative_RD_note` and (when per-
  timestep sun positions aren't available) `enhanced_solar_note`; reconstruction tools always return a
  `divergence`. Read them — they tell you where a result is relative or approximate.
- **Spectral-sky pipeline (workflow H) is capability-gated:** the offline Python stack
  (`atmosphere_from_epw`, `spectral_sky_from_epw`, `spectral_epw`, default `engine="spectrl2"`) runs
  end-to-end and is unit-tested. The native `gensdaymtx` engine (`spectral_sky_native`) has had its
  **first live validation** against Radiance 6.1a (NCOMP=20, loose-envelope agreement with the offline
  Python engine, Pearson 0.987 — validation, not a known-good baseline). **SMARTS** (user-selectable via
  `engine="smarts"`, gated on `$SMARTSPATH`) was **first run live 2026-06-21** — compiled from the NREL 2.9.5
  Fortran source (that distribution's Mac binary is dead PowerPC); with `$SMARTSPATH` set the gated
  cross-check passes and SMARTS agrees with SPECTRL2 to ~2 % direct / ~7 % diffuse, r≈0.99
  (`docs/spectral-engine-comparison.md`) — validation, not a baseline. The
  `annual_nvrd(physical_sky=True)` flip had its **first live execution 2026-07-18** (50.03 % physical
  coverage on `office_room` + GRC Athens IWEC); it stays **opt-in, default-off and shape-only**, and a
  single live run validates that it executes, not the shape it substitutes. Selecting `engine="smarts"` without `$SMARTSPATH` raises a clear
  `RuntimeError` rather than silently falling back. The SEDES1 **CCM default is the faithful 10 nm Nann &
  Riordan Fig. 11 digitization**, re-anchored to unity at clear (`cloud_variant="reanchored"`, byte-identical
  default) — the legacy 9-anchor digitization is opt-in via `cloud_variant="seed"`; only the energy-rescale
  to the EPW's DNI/DHI is exact, and the CCM shape's figure-digitization uncertainty is now surfaced
  (`ccm_sigma`/`ccm_sigma_mean` in provenance) and locally re-fittable (`cloud_variant="local"` + `ccm_coeffs=`,
  see `docs/recalibrating-cloud-ccm.md`). ⚠️ A **tabulated** alternative also ships opt-in — `Sedes2Modifier`
  (Whitaker & Newmiller 1998, NREL/SR-520-23942 Table 2-1), a **model swap** (6 coefficients with a 1/cos z
  zenith term, driven by NGH not Kt) reachable only from Python, **not** via `cloud_variant`; the default is
  unchanged and byte-identical. See [validation §2](spectral-engine-validation.md).
  Physics is opt-in: the 30° template fallback is still the default.
  See `docs/spectral-sky-as-built.md` §9.

---

*Server version: annual→nvRD bridge + guided studio journey + spectral-sky-from-EPW pipeline + OBJ/CAD geometry import + annual climate-based daylight metrics + geometry-driven sensor placement (photosensors, preview_scene, footprint-aware grids/observers) + LM-83 three-phase blind operation. 47 tools · 14 resources · 13 prompts.*
