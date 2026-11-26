# Spectral Sky from EPW — As-Built vs. Spec & Mathematics

> **Doc map.** One of four spectral-engine docs:
> [comparison](spectral-engine-comparison.md) (engine-vs-engine) ·
> [radiance-deep-dive](spectral-engine-radiance-deep-dive.md) (angular & cross-city) ·
> [validation](spectral-engine-validation.md) (corrections & external cross-validation — canonical) ·
> [as-built](spectral-sky-as-built.md) (implementation ledger).
> **Owns:** the per-module implementation as-built and the deviation ledger; the correction layers live in [validation](spectral-engine-validation.md).

> **What this is.** A living record of what has **actually been implemented** in `hcl-mcp` for the
> physical spectral-sky pipeline, mapped against the umbrella design spec and the methodology &
> mathematics reference. It documents the *final, as-coded* behaviour after the corrections and
> modifications made during execution — so you can see, per module, exactly how the shipped code
> lines up with the math (M-equations) and the spec (§ references), and where it deliberately
> diverges.
>
> **Status of this doc:** covers **Phase 1 (Foundation), Phase 2 (Engine), Phase 3 (Cloud +
> Ground + Orchestrator), Phase 4 (Track A — physics replaces templates), Phase 5 (Track B — artifacts +
> annual loop + new MCP tools), Phase 6 (SMARTS oracle + validation harness), the Live-DDS physical-sky
> flip (opt-in `physical_sky` on `annual_nvrd`, addressing D-16/D-17), and **Phase 7 (native Radiance
> `gensdaymtx` driver)** — all implemented and verified.** All seven phases of the program are executed; the
> optional correction layers (§1a) sit on top. Native `run_gensdaymtx` /
> `spectral_sky_native` takes a caller-supplied `timeout` (default `None`) so a live full-year run is not bound by the
> old hard-coded 600 s cap — see **D-29** (§3.27/§3.28/§4). An outer-repo pointer-bump also carried a
> spec §8 correction (see §3octies/D-25).
>
> **Scope note on the executed Phase 6.** The Phase-6 *plan* (and this section) is **SMARTS oracle + validation
> harness** — NOT the live-DDS-transport physics-by-default flip. Earlier (Phase-5) text in this doc said the live
> flip would be "Phase 6"; that did **not** land here. The 30°-zenith fallback is still the live default.
> ⚠️ **Updated:** "D-16/D-17 remain open" was true when written and is now **superseded** — the Live-DDS
> physical-sky flip shipped as its own workstream (§3septies) and had its first live execution 2026-07-18,
> so §4 and §7 correctly record both as **DOWNGRADED, not closed**: physics is wired and live-exercised but
> remains **opt-in** (`physical_sky=False` by default in both the core and the MCP wrapper). Only the
> default flip is outstanding. Three later "Phase 6" mentions in this document still carry the retracted
> "the live flip is Phase 6" meaning — read them as "a later workstream", which is what happened.
>
> **Companion documents** (all in this `docs/` folder — this as-built record is the authoritative
> in-repo source). The original umbrella **design spec** and the seven **per-phase plans** were
> internal planning drafts that this published set supersedes; bare section markers like "§8" /
> "§11 #9" below refer to that design spec, and "M-eq…" refers to the methodology doc:
>
> - Methodology & mathematics: [`spectral-sky-methodology.md`](spectral-sky-methodology.md) (the "M-eq" refs)
> - Whole-server technical reference: [`technical-reference.md`](technical-reference.md)

---

## 1. Implementation status dashboard

| Phase                                      | Scope                                                                                                                                                                                                                                                                                                       | Modules                                                                                          | Status                                                                                                                                                                                              | Tests                                                   |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| **1 — Foundation**                  | EPW hourly parse · solar geometry · atmospheric state                                                                                                                                                                                                                                                     | `epw_hourly`, `solpos`, `atmosphere`                                                       | ✅**Implemented & verified**                                                                                                                                                                  | 23 unit                                                 |
| **2 — Engine**                      | SPECTRL2 port ·`ClearSkySpectra` · resampler · `SpectralSkyRecord` · SMARTS scaffold                                                                                                                                                                                                                | `spectral_engine/*`, `spectral_sky`¹                                                        | ✅**Implemented & verified**                                                                                                                                                                  | 18 unit + 1 cap-gated skip                              |
| **3 — Cloud + ground**              | SEDES1 cloud modifier · bridge invariant ·`ground_for_receiver` · `build_record` · SKYSPECTRA gate                                                                                                                                                                                                  | `cloud_modifier`, `_sedes1_data`, `spectral_sky`                                           | ✅**Implemented & verified**                                                                                                                                                                  | 21 unit + 1 cap-gated skip                              |
| **4 — Track A**                     | `sun_spd` injection · `to_channels`/`to_reference` · `reconstruct_from_record` · MCP `sun_spd` passthrough                                                                                                                                                                                     | `spectral_emit`(new), `spectral_reconstruct`(mod), `server`(mod)                           | ✅**Implemented & verified**                                                                                                                                                                  | 11 unit                                                 |
| **5 — Track B (Artifacts + tools)** | `record_from_epw`/`annual_records` · 4 emitters (`emit_spd_set`/`emit_band_matrix`/`emit_spectral_wea`/`emit_augmented_epw_sidecar`) + `record_to_dict` · 3 MCP tools (`atmosphere_from_epw`/`spectral_sky_from_epw`/`spectral_epw`) · **D-14 closed** (CCM caveats on record) | `spectral_pipeline`(new), `spectral_emit`(mod), `spectral_sky`(mod, D-14), `server`(mod) | ✅**Implemented & verified**                                                                                                                                                                  | 16 unit                                                 |
| **6 — SMARTS + validation**         | SMARTS deck/parser/subprocess engine · drift-vs-templates + cross-engine compare + SKYSPECTRA harness                                                                                                                                                                                                      | `spectral_engine/smarts`(rewritten), `spectral_validate`(new)                                | ✅**Implemented & verified** (**run path first live-validated 2026-06-21** — compiled from the SMARTS 2.9.5 source, kept outside this published repo; gated cross-check passes, ~2–7 % agreement with SPECTRL2, r≈0.99 — D-19) | 7 unit + 3 cap-gated (now run live with`$SMARTSPATH`) |
| **Live-DDS physical-sky flip**       | opt-in`physical_sky` on `annual_nvrd` — per-timestep physical sky+sun shapes replace the static-reference/30° templates in the *enhanced* path; per-step fallback + coverage report (D-16/D-17, opt-in)                                                                                             | `spectral_reconstruct`(mod), `annual_nvrd`(mod), `server`(mod)                             | ✅**Implemented & verified; first live execution 2026-07-18** (`office_room`/GRC Athens IWEC, Radiance 6.1a + Daysim `ds_shortterm`; 50.03% physical coverage, time-resolved sun); opt-in; default-template                                                                                                         | 13 unit                                                 |
| **7 — Native Radiance**             | `gensdaymtx`/`rcomb` command builders (implemented flags only) · `parse_smx_header` (NCOMP + RGB partition) · `reconcile_to_native_bands` (NCOMP-derived uniform grid) · `run_gensdaymtx` (run-or-emit) · `spectral_sky_native` MCP tool                                                    | `hcl_radiance/spectral_native`(new), `server`(mod)                                           | ✅**Implemented & verified** (capability-gated; **run path first live-validated 2026-06-20 under Radiance 6.1a** — NCOMP=20; cross-check now runs live, no longer a skip)         | 16 unit + 1 live cross-check (was cap-gated skip)  |

> ¹ `spectral_sky` was **partial** at Phase 2 (record + resampler only). **Phase 3 completed its sky-truth
> surface** (`ground_for_receiver()` + `build_record()`); **Phase 5 closes the last gap** — `record_from_epw`
> and the annual loop now ship in the new `spectral_pipeline` module (the EPW-driven wrapper around the
> per-timestep `build_record`), so deviation **D-6 is closed**. Phase 5 also extends `spectral_sky.build_record`
> in-place to carry the CCM caveat provenance (**D-14 closed**).

**The full suite is green** — re-measured 2026-08-12: **1917 passed, 6 skipped, 0 failed**. The skip set is
environment-dependent, and on a machine with the binaries installed it is *not* the SMARTS/native pair this
line originally named. Measured on the dev machine (Radiance 6.1a, Daysim, `$SMARTSPATH` set), the six are:
2 live-harness (`test_live_phase5`), 1 Daysim-live, 1 geometry-live (missing `sample.ies` fixture), 1
SKYSPECTRA (raw dataset not downloaded — Zenodo 8147546, CC BY-NC-ND, not redistributable), and 1
**inverted** SMARTS gate
(`test_compute_raises_without_binary`, which skips *because* SMARTS is present — the absence-path assertion
is only meaningful when the binary is missing). So the SMARTS↔SPECTRL2 cross-check and the live `compute`
units/band test **both run** here rather than skipping, and the Radiance-6 native
cross-check [`test_native_vs_python_engine_envelope`] is likewise a **passing live test** under Radiance 6.1a.
On a bare checkout with no binaries the count differs — the capability gates are the point.

> ✅ **RESOLVED (2026-08-11/12) — the native cross-check went dark after the 2026-08-10 reorg, and is live
> again.** The 2026-08-11 correction that stood here recorded a real defect: the test gated on a
> **hardcoded absolute path** to an EPW the reorg had moved, so it skipped with `"EPW fixture unavailable"`
> while Radiance was installed — a green suite hiding a dark capability test, exactly the failure mode this
> document exists to prevent. The path is now **repo-relative**
> (`hcl_validation/inputs/weather/GRC_Athens.167160_IWEC.epw`, `tests/test_spectral_native.py:196`, fixed in
> `63d2ac5`), the fixture ships in-tree, and the test **runs and passes** under Radiance 6.1a (re-confirmed
> 2026-08-12). The original live validation of 2026-06-20 stands as the baseline event; the "now a passing
> live test" statements below (§1, §3octies, §3.27, §3.29, §5, §7, §9) are accurate again. The **Live-DDS physical-sky flip added 13 unit** (spectral_reconstruct +2 series-seam; annual_nvrd
+10: 3 `_physical_spd_series`, 3 `physical_sky` e2e, `_build_record_index`, divergence, no-source, partial-note;
server +1 MCP passthrough) — no new skips, all binary/EPW-free via the `_channel_provider`/`_record_provider` hooks. Phase-1 unit tests were 23; Phase 2 added 18 unit + 1 gated skip; **Phase 3 added
21 unit + 1 gated skip** (cloud_modifier 10, _sedes1_data 4, spectral_sky +6, skyspectra 1 pass + 1 skip); **Phase 4
added 11 unit** (spectral_reconstruct +4 sun_spd, spectral_emit 6, server 1) — no new skips; **Phase 5 added 16
unit** (spectral_pipeline 5, spectral_emit +6, server +3, spectral_sky +2 for D-14) — no new skips; **Phase 6 added
7 unit + 1 new gated skip** (test_smarts +3 unit: `build_deck`/`parse_ext_output`/`compute`-raises-without-binary,
plus the now-**real** gated cross-check and a new gated live-`compute` test; test_spectral_validate 4 unit; the
Phase-3 SKYSPECTRA pass test was strengthened in place, the gated comparison filled). **Phase 7 added 16 unit +
1 gated cross-check** (initially a skip, now a passing live test): test_spectral_native 15 (the `gensdaymtx`/`rcomb` command builders, `parse_smx_header` +
the `rgb_partition`/NCOMP reframe, `radiance_spectral_status`, `reconcile_to_native_bands` proven ==
`band_average`, the three `run_gensdaymtx` run-or-emit shape tests, and the `ground_refl`-tuple type-guard) +
test_server 1 (`spectral_sky_native` emit), plus `test_native_vs_python_engine_envelope` — the native cross-check, now **passing live** under Radiance 6.1a (was a `pytest.skip` stub).

> ⚠️ **Read the per-phase test counts above as "tests added by that phase, at that time", not as current
> file totals.** They were accurate when each phase landed and every file has grown since, so §5's
> phase-time figures and §3's later per-module figures disagree in four places (`cloud_modifier` 10 vs 23,
> `spectral_pipeline` 5 vs 11, `sedes1_data` 4 vs 6, `skyspectra` "1 pass" vs 6 pass). Both numbers are
> historically true of different moments; neither is the count today. Measured 2026-08-12, the whole suite
> collects **1923 tests (1917 passed, 6 skipped)**, and the current per-file totals are:
> `test_atmosphere` 24, `test_cloud_modifier` 23, `test_spectral_native` 21, `test_annual_nvrd` 21,
> `test_spectral_sky` 18, `test_spectral_reconstruct` 18, `test_spectral_emit` 12, `test_spectral_pipeline`
> 11, `test_smarts` 8, `test_solpos` 8, `test_skyspectra` 7, `test_epw_hourly` 7, `test_sedes1_data` 6,
> `test_spectral_validate` 4. **The load-bearing claim is the green suite, not the arithmetic.**

**Files present in `src/hcl_core/` from this work today:** `epw_hourly.py`, `solpos.py`, `atmosphere.py`
(Phase 1); `spectral_engine/{__init__,base,_spectrl2_data,spectrl2,smarts}.py` and `spectral_sky.py` (Phase 2);
`cloud_modifier.py` and `_sedes1_data.py` (Phase 3; `spectral_sky.py` extended in-place); `spectral_emit.py`
(Phase 4 — new record→pipeline bridge); `spectral_pipeline.py` (Phase 5 — new EPW→record orchestrator;
`spectral_emit.py` extended with the four artifact emitters + `record_to_dict`; `spectral_sky.py` extended again
for D-14; `src/hcl_mcp/server.py` gains the three additive MCP tools). **Phase 6** rewrites the
`spectral_engine/smarts.py` scaffold into the working oracle (`build_deck` + `parse_ext_output` +
subprocess `SmartsEngine.compute`) and adds the new `spectral_validate.py` (`drift_vs_templates` +
`compare_engines`); both are imported only by tests + opt-in callers, so no existing computed path changes.
(`_spectra.py`, `spectral_metrics.py` still pre-date this effort and are untouched. **`spectral_reconstruct.py`
is now modified by Phase 4** — additively: a `sun_spd` injection seam so the existing D-series/air-mass
*template* pipeline can be fed physical sun references; default behaviour is bit-identical to before.
`src/hcl_mcp/server.py` gains a matching `sun_spd` passthrough.)

The spec's headline goal — *"kill the 30° solar-zenith fallback"* — is now **seam-complete on the reconstruct
side**: Phase 1 shipped the zenith *source* (`solpos.compute`); **Phase 4 added the sun-side injection seam**
(`sun_spd` on `reconstruct_spectrum` + `reconstruct_from_record`) so a physical sun reference can replace the
air-mass `solar_spd_for_zenith(30°)` template per timestep. **Phase 5 builds the offline EPW→artifact path on top
of that seam** — `record_from_epw`/`annual_records` produce canonical physical records straight from an EPW, and
the four emitters + three MCP tools expose them — but it deliberately does **not** flip the *live `colored_sky`/
annual-DDS transport* to physics-by-default: `hcl_radiance/annual_nvrd.py` still calls `assemble_nvrd_rows`
without `sun_spd`, and the `solar_zenith=30.0` template still fires when no `sun_spd` is supplied
(backward-compatible). So the replacement is now *possible per call* and a full physical-record/artifact pipeline
exists offline; making physics the *default in the live 8760-hour DDS path* is **Phase 6** — see D-16/D-17
(re-targeted from Phase 5).

---

## 1a. Correction layers — status

This as-built captures the engine implementation. A subsequent program shipped three optional
correction layers on top of it. Canonical synthesis:
[`spectral-engine-validation.md`](spectral-engine-validation.md).

| Layer                   | Outcome (one line)                                                                           |
| ----------------------- | -------------------------------------------------------------------------------------------- |
| Faithful SEDES1         | Fig. 11 re-anchored CCM is the **default** (seed B(400)=−3.55 → faithful −2.037)              |
| Anisotropic wrapper     | Optional façade projector; η = **0.5**, empirical, constrained to an **interval [0.19, 0.69]** rather than a point — the fitting dataset is not published with this toolkit |
| SKYSPECTRA              | External no-glazing check (FR-VLX cloud slope +639 K; Berlin anti-solar +4697 K)              |
| Clear-sky bias K(λ)     | Optional / default-off spectral warming; empirical, same unpublished fitting dataset          |
| Consolidation           | `spectral-engine-validation.md`                                                              |

---


## 2. How Phases 1–4 fit the dataflow

Phase 1 is the three pure-Python, offline, stdlib-only inputs every spectral engine needs; Phase 2 adds the
engine and the 1nm resampler that consume them; **Phase 3 adds the cloud bridge, ground-glow, and the
per-timestep orchestrator that binds engine → cloud → record** (spec §2 pipeline diagram):

```
EPW(path, month, day, hour)
   ├─▶ epw_hourly.parse_epw_hourly  → per-row dicts (DNI/DHI/GHI, T, RH, Td, P, sky cover, AOD?, albedo?)
   ├─▶ atmosphere.derive            → AtmosphericState (AOD, PWV, ozone, pressure, albedo + provenance)
   └─▶ solpos.compute               → SolarGeometry (zenith, azimuth, air mass, ERV, day-of-year)
                                       └─ zenith ≡ existing weather.solar_zenith (single source of truth)
   ▼  Spectrl2Engine.compute(atm, geo)          → ClearSkySpectra (122 pts, 300–4000nm, W/m²/µm)   ◀ Phase 2
   ▼  Sedes1Modifier.apply(clear, dni, dhi, ghi, kt)                                                ◀ Phase 3
   │     ├─ energy_normalize → grey-scale direct→DNI, diffuse→DHI on FULL native range (bridge invariant)
   │     └─ CCM(λ,Kt)=A+B·Kt+C·Kt² reshape of DIFFUSE only → renormalize diffuse back to DHI (shape-only)
   ▼  resample_to_1nm(scaled)                   → (direct, diffuse) on 380–780 @1nm, W/m²/nm        ◀ Phase 2
   ▼  build_record(...)                         → SpectralSkyRecord (+ provenance, night handling)  ◀ Phase 3
   ▽  ground_for_receiver(rec, tilt, albedo)    → spectral ground-glow input for Radiance           ◀ Phase 3
```

Phases 1–3 are pure-Python, offline, stdlib-only. No Radiance, no network. The engine takes geometry as input
(never calls solpos). The cloud modifier runs energy + shape on the **full native range BEFORE** the resample
narrows to 380–780 (so the energy match is exact across the whole spectrum). `build_record` zeroes night hours
and flags any twilight-edge EPW energy. **Phase 5 wraps this chain in `record_from_epw(epw, m, d, h)`** (parse the
EPW row + LOCATION header → `atmosphere.derive` → `solpos.compute` at the **mid-interval** hour `h−0.5`, with
`i0_normal = 1361·ERV` → `build_record`) and `annual_records(epw, hours=…)` (one record per EPW data row, night
rows short-circuiting to zero-spectra via `build_record`'s own fast path). These are the offline EPW→record
orchestrators; the four artifact emitters and three MCP tools (§3quinquies) consume their output.

**Phase 4 attaches on the *reconstruct* (consumer) side** of this producer chain — it does not extend the
diagram above; it gives the existing reconstruction pipeline a way to *consume* a `SpectralSkyRecord`:

```
SpectralSkyRecord ──▶ spectral_emit.to_reference(rec) → (sky_spd, sun_spd) 401-pt refs ─┐
                  └─▶ spectral_emit.to_channels(rec)   → (diffuse, direct) 3/9 channels ─┘ (for colored_sky)
                                                                                          ▼
   reconstruct_spectrum(sky_channels, sun_channels, …, sky_spd=, sun_spd=)  ← Radiance supplies the bin TOTALS;
                                                                                the record supplies the SHAPES
   reconstruct_from_record(rec, sky_channels, sun_channels)  = the one-call "engine= source" wiring
```

The record supplies **reference shapes only** — the Radiance per-channel transport totals are untouched; only
the within-bin reshaping template (formerly the D-series sky / air-mass sun) is replaced with physics. With no
`sun_spd`/`sky_spd` supplied, the templates still fire (default-off). **No live transport path passes these
yet** — that wiring is Phase 5 (see D-16).

---

## 3. As-built modules (Phase 1)

For each module: the **actual public API as coded**, the **math as coded** (cross-referenced to the
methodology M-equations and verified numerically), and the **spec mapping**.

### 3.1 `epw_hourly` — hourly EPW column parser

**File:** `src/hcl_core/epw_hourly.py` · **Spec:** §3 (`epw_hourly` row), §11 #7 (N22/N23 fix) ·
**Methodology:** §4 (Stage A) · **Tests:** `tests/test_epw_hourly.py`

**Public API (as coded):**

```python
parse_epw_hourly(path) -> list[dict]   # one dict per data row
row_for(rows, month, day, hour) -> dict | None   # first match else None
```

**Row dict keys (as coded):** `month, day, hour` (ints) + floats-or-`None`:
`dry_bulb_c, dew_point_c, rh_pct, pressure_pa, ghi, dni, dhi, total_sky_cover, opaque_sky_cover, precip_water_mm, aod, albedo`.

**Field map (0-based comma indices) — as coded, matches the EPW data dictionary and methodology §4:**

| field           | idx          | sentinel→None | field            | idx | sentinel→None |
| --------------- | ------------ | -------------- | ---------------- | --- | -------------- |
| dry_bulb_c      | 6            | 99.9           | total_sky_cover  | 22  | 99.0           |
| dew_point_c     | 7            | 99.9           | opaque_sky_cover | 23  | 99.0           |
| rh_pct          | 8            | 999.0          | precip_water_mm  | 28  | 999.0          |
| pressure_pa     | 9            | 999999.0       | aod              | 29  | 0.999          |
| ghi / dni / dhi | 13 / 14 / 15 | 9999.0         | albedo           | 32  | 999.0          |

**Behaviour notes (as coded):**

- The data-source-flags **string** sits at index 5 — the classic off-by-one trap; the index map accounts
  for it. (§11 #7: total/opaque sky cover are **N22/N23**, the corrected indices.)
- **8 header lines** skipped before data.
- **Degradation:** rows with `< 16` comma fields, or a non-integer date triple, are skipped — now logged and
  counted via `parse_epw_hourly_diagnostics` (which returns a `{"kept","dropped","reasons"}` report and logs a
  drop summary); `parse_epw_hourly` is a thin wrapper over it that returns just the row list and never raises.
  Missing-value sentinels map to `None` (`_num` returns `None` on
  out-of-range index, unparseable value, or exact sentinel match).
- **`hour` is stored verbatim** as the EPW hour-ending value (1–24). Conversion to a mid-interval clock
  hour (`hour − 0.5`) for `solpos` is **deferred to the Phase 5 orchestrator** — *not* done here. This is
  the documented boundary that prevents a 30–60 min solar-time error.

### 3.2 `solpos` — solar geometry

**File:** `src/hcl_core/solpos.py` · **Spec:** §3 (`solpos`), §4 (`SolarGeometry`), §11 #6 (extend
existing zenith) · **Methodology:** §5 (Stage B), eqs **M-1…M-6, M-8** · **Tests:** `tests/test_solpos.py`

**Public API (as coded):**

```python
@dataclass(frozen=True)
class SolarGeometry:
    zenith_deg: float
    azimuth_deg: float          # 0=N, 90=E, 180=S, 270=W (SPECTRL2 aspect convention)
    air_mass: float             # Kasten-Young 1989; inf below horizon
    earth_radius_vector: float  # NREL/Spencer correction; multiply ETR by this
    day_of_year: int

compute(*, month, day, hour, latitude, longitude, time_zone) -> SolarGeometry
air_mass(zenith_deg) -> float
earth_radius_vector(day_of_year) -> float
```

**Site convention (DAYSIM):** latitude north-positive; longitude **WEST-positive**;
`time_zone` = standard meridian deg = `−15 × UTC_offset`. Matches `weather.solar_zenith` and
`hcl_core.epw_location.parse_epw_location`.

**Math as coded (each verified numerically against its source):**

| quantity                  | equation (as coded)                                                                                         | M-eq | check                                                        |
| ------------------------- | ----------------------------------------------------------------------------------------------------------- | ---- | ------------------------------------------------------------ |
| Declination (Cooper 1969) | `δ = 23.45·sin(360(284+n)/365)`                                                                         | M-1  | —                                                           |
| Equation of time          | `EoT = 9.87 sin2B − 7.53 cosB − 1.5 sinB`, `B = 360(n−81)/364`                                       | M-2  | —                                                           |
| Solar time / hour angle   | `t = h + (4(L_std − L) + EoT)/60`; `ω = 15(t − 12)`                                                  | M-3  | —                                                           |
| Zenith (clamped)          | `cos z = sinφ sinδ + cosφ cosδ cosω`                                                                 | M-4  | **0.0 error vs `weather.solar_zenith` over 5 sites** |
| Azimuth (N=0 CW)          | `γs = (atan2(sinω, cosω sinφ − tanδ cosφ)·180/π + 180) mod 360`                                  | M-5  | 9h/12h/15h = 115°/180°/245° (lat 40°N), monotonic E→S→W            |
| Earth-radius-vector       | `R_v = 1.000110 + 0.034221 cosD + 0.001280 sinD + 0.000719 cos2D + 0.000077 sin2D`, `D = 2π(n−1)/365` | M-6  | range 0.9666–1.0351; perihelion>aphelion                    |
| Air mass (Kasten-Young)   | `m = 1/(cos z + 0.50572(96.07995 − z)^−1.6364)`, `∞` for `z ≥ 90°`                               | M-8  | m(0°)=1.000, m(60°)=1.994, m(85°)=10.306                  |

**Single-source-of-truth guarantee:** the declination/EoT/hour-angle/cos-zenith block is a
character-for-character copy of `weather.solar_zenith` (`weather.py`), so `geo.zenith_deg` can never drift
from the existing pipeline — confirmed to `0.0` absolute error (test
`test_zenith_matches_weather_solar_zenith`, asserted `< 1e-9`).

**Azimuth correctness note:** at solar noon on the prime meridian the azimuth reads ≈177°, *not* exactly
180°. This is physically correct — the equation of time places true solar noon ~7 min early on 21 Mar, so
the sun is just east of due south at clock-noon. It is the expected behaviour, not an error.

### 3.3 `atmosphere` — atmospheric state with provenance

**File:** `src/hcl_core/atmosphere.py` · **Spec:** §3 (`atmosphere`), §4 (`AtmosphericState`), §13
(degradation), §11 #10 (PWV) · **Methodology:** §6 (Stage C), eqs **M-12, M-13** (M-7 documented, not
coded — see §4 below) · **Tests:** `tests/test_atmosphere.py`

**Public API (as coded):**

```python
gueymard94_pw(temp_air_c, relative_humidity_pct) -> float   # precipitable water, cm
reitan63_pw(dew_point_c) -> float                           # precipitable water, cm (fallback)

@dataclass(frozen=True)
class AtmosphericState:
    aod500: float            # AOD @ 500nm
    angstrom_alpha: float    # Ångström exponent
    pw_cm: float             # precipitable water, cm
    ozone_atm_cm: float      # ozone column, atm-cm (300 DU = 0.30)
    pressure_mbar: float
    albedo: float            # broadband ground albedo
    provenance: dict         # {field: {source, method, uncertainty}}   ← uncertainty reserved (None) in v1; see deviation D-1
    aerosol_g: float = 0.65  # aerosol asymmetry factor — resolved, opt-in (D-7); default byte-identical

derive(row, *, overrides=None, ozone_mode="constant", aod_anchor_nm=None,
       lat_deg=None, lon_deg=None, day_of_year=None) -> AtmosphericState
```

**Precipitable water (as coded):**

- **Primary — Gueymard 1994** (the pvlib `gueymard94_pw` formulation) from T[K] + RH[%], M-12. Verified to
  match the explicit pvlib formula exactly; `gueymard94_pw(28, 60) = 3.5744…` cm.
- **Fallback — Reitan 1963** `w = exp(−0.0392 + 0.0681·Td)` from dew point, M-13. `reitan63_pw(20) = 3.7539…` cm.
- **The EPW precip-water column (28) is intentionally ignored** for PWV (officially unreliable) — PWV is
  always derived from T/RH (Gueymard) or Td (Reitan), per spec §3 / §11 #10.

**Resolution order & defaults (as coded — methodology Algorithm A):** `override` > `epw` > `default`,
each tagged in `provenance[field] = {source, method}`.

| field              | EPW source     | default | transform            | provenance`method` when from EPW  |
| ------------------ | -------------- | ------- | -------------------- | ----------------------------------- |
| `pressure_mbar`  | col 9 (Pa)     | 1013.25 | `/100`             | `pa_to_mbar`                      |
| `albedo`         | col 32         | 0.20    | col value accepted only if `>= _ALBEDO_MIN_PHYSICAL` (0.01) — IWEC/TMY2 write `0.000` as de-facto "no data" (4 of the 11 EPWs the pre-release tree bundled did, Athens included; the published tree ships only the Athens IWEC fixture), which previously zeroed the whole ground-reflected term while claiming `source: "epw"`; gated in `epw_hourly` **and** `atmosphere.resolve`. See ADR-0004. | `epw` (real value) / `default` (0.000 or absent) |
| `aod500`         | col 29         | 0.10    | — (broadband proxy); optionally Ångström-converted from `aod_anchor_nm` (D-3, opt-in, default `None`=no-op) | `epw_broadband_proxy` (or `angstrom_from_<nm>nm` when `aod_anchor_nm` is set) |
| `ozone_atm_cm`   | — (never EPW) | 0.30    | optional `ozone_mode="climatology"` (van Heuklon 1979, opt-in, default `"constant"`) | `default`/`override`, or `climatology`/`van_heuklon79` |
| `angstrom_alpha` | — (never EPW) | 1.14    | —                   | (always`default` or `override`) |
| `aerosol_g`      | — (never EPW) | 0.65    | — (resolved, opt-in override, D-7) | (always`default` or `override`) |

**PWV provenance `method` vocabulary** (documented in `derive`'s docstring for Phase-2 consumers):
`gueymard94` (T+RH) · `reitan63` (Td only) · `fixed` (no humidity fields → 1.5 cm mid-latitude default) ·
`explicit` (`pw_cm` supplied via overrides).

**Degradation (spec §13):** every field has a documented default; `derive` never raises on a missing
field. With an entirely empty row, `derive({})` returns the all-defaults state (PWV = 1.5 cm, `method="fixed"`).

---

## 3bis. As-built modules (Phase 2 — Engine)

> **Equation-numbering convention (Bird & Riordan).** Equation labels of the form "N-M" used throughout this section (e.g. Eq. 3-1, 3-12, 3-17) follow the SERI/NREL `spectrl2_2.c` C-source section numbering that the implementation ports; the original Bird & Riordan 1986 paper uses a single continuous scheme (Eqs. 1–30). See `literature-bibliography.md` §2C for full details.

The swappable engine, its 122-wavelength coefficient table, the pure-Python SPECTRL2 port, the canonical
record + resampler, and the capability-gated SMARTS oracle slot. Math cross-referenced to methodology **§7
(Stage D, M-9…M-24)** and **§9 (Stage F, M-30)**, and to the Bird & Riordan 1986 equation numbers carried
in the code comments; constants verified 1:1 against the SPECTRL2 C source (`spectrl2_2.c`).

### 3.4 `spectral_engine/base` — the backend swap point

**File:** `src/hcl_core/spectral_engine/base.py` · **Spec:** §3, §4 (`ClearSkySpectra`, `SpectralEngine`) ·
**Methodology:** §3 (boundary types) · **Tests:** `tests/test_spectral_engine_base.py` (3)

```python
@dataclass(frozen=True)
class ClearSkySpectra:
    wavelength_nm: list            # engine-native grid in nm (SPECTRL2: 122 pts, 300–4000nm)
    direct_normal: list            # W/m²/µm
    sky_diffuse_horizontal: list   # W/m²/µm — diffuse on a horizontal plane (incl. sky-ground multi-reflection)
    units: str = "W/m^2/um"

@runtime_checkable
class SpectralEngine(Protocol):
    name: str
    def compute(self, atm, geo, *, tilt_deg: float = 0.0, cos_incidence=None) -> ClearSkySpectra: ...
```

`SpectralEngine` is a `@runtime_checkable` Protocol — backends satisfy it structurally (no inheritance).
`ClearSkySpectra` is frozen (sky-truth; callers must not mutate). The µm→nm conversion is **not** the
engine's job — it lives only in the resampler (§3.7).

### 3.5 `spectral_engine/_spectrl2_data` — the 122-wavelength coefficient table

**File:** `src/hcl_core/spectral_engine/_spectrl2_data.py` (generated, then committed) · **Spec:** §3 ·
**Methodology:** §7 (the $A[5][122]$ table) · **Tests:** `tests/test_spectrl2_data.py` (3)

Five 122-element float lists — `WL_UM, ET_H0, ABS_H2O, ABS_O3, ABS_UMG` (column order = C `A[0..4]`:
wavelength µm, extraterrestrial $H_{0\lambda}$ W/m²/µm, water-vapor/ozone/uniform-gas absorption coeffs).
**Generated** from the authoritative SPCTRAL2 PC reference table (`SPCTRAL2_TAPE2.txt`, = the C `A[5][122]`,
= methodology TAPE2), not hand-typed; anchor tests gate it. Anchors (verified): row 0 = `0.300, 535.9, 0.0, 10.0, 0.0`; row 121 = `4.000, 8.6, 0.0045, 0.0, 0.025`; strictly ascending; 34 wavelengths in 0.380–0.780 µm.

### 3.6 `spectral_engine/spectrl2` — the SPECTRL2 port (`Spectrl2Engine`)

**File:** `src/hcl_core/spectral_engine/spectrl2.py` · **Spec:** §3, §9.2 (port + golden gate) ·
**Methodology:** §7 (Stage D), eqs **M-9, M-11, M-14…M-24** · **Tests:** `tests/test_spectrl2.py` (5)

**Public API (as coded):**

```python
class Spectrl2Engine:
    name = "spectrl2"
    def compute(self, atm, geo, *, tilt_deg=0.0, cos_incidence=None) -> ClearSkySpectra
```

Pure-Python, stdlib `math` only. Faithful transcription of `spectrl2_2.c` **units==1** (W/m²/µm per λ in
µm). Geometry is **passed in** (`SolarGeometry`) — no native solpos. Output arrays are 122-long, native grid
300–4000nm exposed in nm. **Production calls use `tilt_deg=0`** → direct-normal + diffuse-horizontal (the
tilt branch exists only to reproduce the tilted Fortran golden). **Night guard:** `zenith ≥ 90°` or
`cos z ≤ 0` or non-finite air mass → all-zeros.

**Math as coded (verified line-by-line against `spectrl2_2.c` and the methodology pseudocode §7):**

| quantity                                   | equation (as coded)                                                                         | M-eq / Bird Eq                            | check                                                         |
| ------------------------------------------ | ------------------------------------------------------------------------------------------- | ----------------------------------------- | ------------------------------------------------------------- |
| pressure / ozone air mass                  | `Amp = m·P/1013`, `Amo = 1.003454/√(cos²z+0.006908)`                                 | M-9, M-11                                 | golden z=79.94°,P=816 → m=5.55,**Amp=4.47**, Amo=5.19 |
| aerosol optical depth                      | `c_a = τ₅₀₀·(2λ)^−α`                                                              | M-14                                      | —                                                            |
| single-scattering albedo                   | `ω(λ)=0.945·exp(−0.095·ln(λ/0.4)²)`                                                | M-15 / Bird 3-16                          | ω(0.4µm)=0.945                                              |
| forward-scatter`F_s`,`F_sp`            | afs/bfs polynomials, asymmetry**g=0.65** (rural)                                      | M-16 / Bird 3-12…3-14                    | —                                                            |
| ET day correction                          | `H₀λ·R_v`                                                                              | M-17                                      | —                                                            |
| transmittances`Tr,To,Tw,Tu,Tas,Taa,Ta`   | Beer–Lambert,**C constants verbatim** (115.6406, 1.3366, 118.3, 0.2385, 20.07, 1.41) | M-18 / Bird 2-4,2-8,2-9,2-11,3-9,3-10,2-6 | **Rayleigh lock** `Tr(0.5µm,Amp=4.471)=0.52281`      |
| **direct normal** `I_dλ`          | `H₀λ·R_v·Tr·To·Tw·Tu·Ta`                                                          | **M-19** / Bird 2-1                 | golden <0.5% (actual**<0.05%**)                         |
| primed diffuse-path                        | `Tr',Tw',Tu',Tas',Taa'` at fixed M'=1.8                                                   | M-20                                      | —                                                            |
| `C_s` small-λ factor                    | `(λ+0.55)^1.8 if λ≤0.45µm else 1`                                                     | M-21 / Bird 3-17                          | —                                                            |
| diffuse components`ρ_a,I_r,I_a,I_g`     | per M-22 (Rayleigh + aerosol + ground back-scatter)                                         | M-22 / Bird 3-5…3-8                      | —                                                            |
| **sky diffuse horizontal** `I_sλ` | `(I_r+I_a+I_g)·C_s`                                                                      | **M-23** / Bird 3-1                 | golden <1% (actual**<0.01%**)                           |
| tilt diffuse (golden path only)            | ground + beam-correlated + isotropic                                                        | M-24 / Bird 3-18                          | TAPE @40° reproduced                                         |

`omeg=0.945`, `omegp=0.095` (`spectrl2_2.c:172/174`) are hardcoded engine constants; `assym` (`:484`, default
0.65) is **now parameterized** — `AtmosphericState.aerosol_g` (default 0.65, resolved opt-in — see **D-7**)
replaces the old `0.65` literal in the engine.

### 3.7 `spectral_sky` — canonical record + 1nm resampler (Phase-2 surface; extended in Phase 3)

**File:** `src/hcl_core/spectral_sky.py` · **Spec:** §3, §4 (`SpectralSkyRecord`), §11 #2 (pinned µm→nm) ·
**Methodology:** §9 (Stage F), eq **M-30** · **Tests:** `tests/test_spectral_sky.py` (18)

**Public API (as coded):**

```python
GRID_NM = [380.0 … 780.0]   # 401 pts @1nm

@dataclass(frozen=True)
class SpectralSkyRecord:
    timestamp: tuple; grid_nm: list
    direct_normal: list            # W/m²/nm
    sky_diffuse_horizontal: list   # W/m²/nm
    broadband: dict                # {dni, dhi, ghi, clearness_kt}
    atmosphere: object; geometry: object; provenance: dict

resample_to_1nm(spectra) -> (direct_1nm, diffuse_1nm)   # on GRID_NM, W/m²/nm
```

`resample_to_1nm` linearly interpolates the engine's native W/m²/µm spectra onto the 380–780 @1nm grid
(endpoint-clamped binary search), **then ×0.001** (µm→nm) — **the one and only place** that conversion lives
(spec §11 #2 / methodology M-30; the engine's `×1000` is the *wavelength axis*, a different quantity). A
degenerate single-point native grid clamps to a flat spectrum (regression-tested). Phase 2 shipped the record
dataclass + resampler; **Phase 3 added `ground_for_receiver` (§3.11) and `build_record` (§3.12)** in the same
file; only `record_from_epw` + the annual loop remain **Phase 5** (**D-6**, narrowed).

### 3.8 `spectral_engine/smarts` — SMARTS oracle scaffold (capability-gated) → **implemented in Phase 6**

**File:** `src/hcl_core/spectral_engine/smarts.py` · **Spec:** §3, §9.2 (oracle from day one) ·
**Methodology:** §12 (parallel engines) · **Tests:** `tests/test_smarts.py`

> **This subsection describes the Phase-2 *scaffold*.** Phase 6 promotes it into the working subprocess oracle —
> see **§3.21** for the as-built `build_deck`/`parse_ext_output`/`SmartsEngine.compute`. **D-9 is now CLOSED.**

As shipped at Phase 2:

```python
smarts_available() -> bool          # True iff $SMARTSPATH names an existing executable
class SmartsEngine:
    name = "smarts"
    def compute(...) : raise NotImplementedError   # full subprocess impl = Phase 6 (now landed, §3.21)
```

This established the validation-oracle slot "from day one": `SmartsEngine` satisfied `SpectralEngine` so it could
slot in later, while `compute()` raised until Phase 6 wired the input-deck + subprocess (now done, §3.21). The
cross-check test was `@skipif(not smarts_available())` — green pytest ≠ live-validated here (**D-9**).

---

## 3ter. As-built modules (Phase 3 — Cloud + Ground + Orchestrator)

The all-sky cloud bridge (energy-rescale + SEDES1 spectral modifier), the derived CCM coefficient table, the
spectral ground-glow term, and the per-timestep orchestrator. Math cross-referenced to methodology **§8 (Stage
E, the cloud bridge)** and the **Nann & Riordan 1991 (SEDES1)** equation numbers; the design caveats are spec
**§5/§6**. Reference paper: Nann & Riordan 1991, *Solar spectral irradiance under clear and cloudy skies: Measurements and a semiempirical model*, J. Appl. Meteorol. **30**(4):447 (the SEDES1 model).

**Two-part bridge.** The cloud step has an **energy half** (always on) and a **shape half** (SEDES1 CCM):

- *Energy* — grey-scale the clear-sky direct/diffuse so their **full-range** broadband integrals equal EPW
  **DNI/DHI** exactly. This is the **bridge invariant** and it alone guarantees broadband correctness.
- *Shape* — reshape the **diffuse** spectrum by `CCM(λ,Kt)=A+B·Kt+C·Kt²`, then renormalize diffuse back to DHI
  (shape-only). Direct keeps its grey-scaled clear-sky shape. At clear Kt the CCM is ~unity, so clear hours
  pass through essentially unchanged; under cloud the diffuse goes bluer (the physical cloud-blueing signal).

### 3.9 `cloud_modifier` — clearness index, bridge invariant, SEDES1 modifier

**File:** `src/hcl_core/cloud_modifier.py` · **Spec:** §5 (energy + CCM), §13 (degrade) · **Methodology:**
§8, SEDES1 Eqs. 6, 9–11 · **Tests:** `tests/test_cloud_modifier.py` (23)

**Public API (as coded):**

```python
clearness_index(ghi, i0_normal, cos_zenith) -> float          # Kt = GHI/(I0·cos z), clamp [0,1.2], 0 at night
broadband_integral(spectrum_per_um, wavelength_um) -> float   # trapezoidal ∫, W/m²/µm × µm → W/m²
energy_normalize(spectra, dni, dhi) -> (ClearSkySpectra, info)  # grey per-component → DNI/DHI on native range

class CloudModifier(Protocol):
    name: str
    def apply(self, clear, *, dni, dhi, ghi, kt, geo) -> tuple[ClearSkySpectra, dict]: ...

class Sedes1Modifier:    # name = "sedes1"
    def __init__(self, variant="reanchored", *, coeffs=None, sigma=None, source=None): ...
    def apply(self, clear, *, dni, dhi, ghi, kt, geo) -> (ClearSkySpectra, info)
```

**Swappable + locally re-fittable CCM (four variants).** `Sedes1Modifier` now takes a `variant`: `reanchored`
(default, byte-identical to before — the faithful 10 nm Fig. 11 digitization, reanchored to unity at clear
`Kt=KT_CLEAR=0.70`), `verbatim` (the faithful Fig. 11 CCM as published, not reanchored), `seed` (the legacy
eyeballed 9-anchor digitization, over-blues ~2×, opt-in for comparison), and **new** `local` — a
caller-injected CCM (`coeffs=<callable wl_nm -> (a,b,c)>`, optional `sigma=`, `source=<provenance string>`),
reanchored the same way as `reanchored`, for a locally re-fitted coefficient set (see `hcl_core/sedes1_fit.py`
below). MCP exposure: `spectral_sky_from_epw`/`spectral_epw` accept `cloud_variant` (reanchored default |
verbatim | seed | local) and `ccm_coeffs` (path to a fitted CSV, required for `local`) — see §3.20. Every
variant now also surfaces its shape uncertainty: `ccm_sigma`/`ccm_sigma_mean` (the Fig.11 regression standard
error, sampled at 400/500/600/700 nm) ride in `apply()`'s info dict and the persisted record's provenance
alongside `ccm_basis`/`coeff_method`/`ccm_variant`/`ccm_source` (see below and §3.19).

**Math as coded (each verified by independent re-computation):**

| quantity              | equation (as coded)                                                                        | source             | check                                             |
| --------------------- | ------------------------------------------------------------------------------------------ | ------------------ | ------------------------------------------------- |
| Clearness index       | `Kt = GHI/(I0_normal·cos z)`, clamp `[0,1.2]`, `0` if `cos z ≤ 0` or `I0 ≤ 0` | SEDES1 Eq. 6       | `600/(1361·0.5)=0.8817`; night→0; >1.2 clamps |
| Broadband integral    | `Σ ½(yᵢ+yᵢ₊₁)·Δλ` on the µm grid                                               | trapezoid          | flat 1000·3.7=3700; triangle=500 (exact)         |
| Energy normalize      | per-component`k = target/clear_bb`; integral on `wl_nm×0.001` µm grid                | SEDES1 Eq. 9       | ∫direct=DNI, ∫diffuse=DHI to FP precision       |
| CCM reshape (diffuse) | `ccm = max(0, A+B·Kt+C·Kt²)`; then `diffuse ×= DHI/∫diffuse`                      | SEDES1 Eqs. 10–11 | invariant preserved (renorm restores DHI)         |

**`Sedes1Modifier.apply` info dict (as coded):** `k_dir, k_dif, clear_dni_bb, clear_dhi_bb` (from
`energy_normalize`) **+** `kt, ccm_applied=True, cloud_model="sedes1"`, plus the **variant-aware** provenance
strings `ccm_variant=<variant>` (default `"reanchored"`), `ccm_basis`/`coeff_method` looked up per variant from
`Sedes1Modifier._BASIS` — `reanchored`/`verbatim` → `ccm_basis="fig11-faithful"`,
`coeff_method="webplotdigitizer_fig11"`; `seed` → `ccm_basis="seed-9anchor"`, `coeff_method="eyeballed_seed"`;
`local` → `ccm_basis="local-fit"`, `coeff_method="local_recalibration"` — plus `ccm_source` (the caller-supplied
CSV path/fit metadata for `local`, `None` otherwise) and the surfaced uncertainty `ccm_sigma` (Fig.11 regression
σ sampled at 400/500/600/700 nm) / `ccm_sigma_mean`. *(Historical note: through Phase 3 the `seed` variant
emitted `ccm_basis="global-fit->diffuse(approx)"` / `coeff_method="fig10_3class_solve"`. Those strings no longer
appear anywhere in `src/` — the `_BASIS` table above is authoritative. See §8.)* These ride onto the
persisted record's day-branch provenance — **Phase 5 closed D-14 via Decision A** — see **D-14** and §8.

**Bridge invariant — independently verified end-to-end** (not via the tests): clear hour direct ∫ = 800.000 /
diffuse ∫ = 120.000; overcast (Kt=0.25, heavy CCM reshape) direct ∫ = 200.000 / diffuse ∫ = 180.000. Exact and
always-on, on the full 300–4000 nm native range **before** the resampler narrows to 380–780.

### 3.10 `_sedes1_data` — derived CCM coefficient table

**File:** `src/hcl_core/_sedes1_data.py` (derived, then committed) · **Spec:** §5 · **Methodology:** §8
(SEDES1 CCM) · **Tests:** `tests/test_sedes1_data.py` (6)

```python
# legacy eyeballed 9-anchor seed (retained for the 'seed' variant):
SEED_WL_NM                     # 9-pt seed grid 350–1050 nm
SEED_A, SEED_B, SEED_C         # legacy seed CCM quadratic coeffs, aligned to SEED_WL_NM
# faithful Fig.11 digitization (primary source of truth, loaded from _sedes1_fig11.csv):
FIG11_WL, FIG11_A, FIG11_B, FIG11_C, FIG11_SIGMA   # 10 nm grid 330–1100 nm

ccm_coeffs(wl_nm) -> (A, B, C) # faithful default; pass-through (1,0,0) outside 330–1100 nm
ccm_sigma(wl_nm)  -> σ         # Fig.11 regression standard error; 0.0 outside range
seed_coeffs(wl_nm) -> (A, B, C) # legacy seed variant; linear interpolation, endpoint-clamped
```

**Derivation (as coded).** The *paper* gives the CCM only as **figures**, not a coefficient table — ⚠️ but
"no coefficient table exists anywhere" is **false** — see the note below. The three
sky-class mean R̄(λ) curves of Fig. 10 (overcast Kt=0.25, all Kt=0.50, clear Kt=0.70) were digitized at 9 seed
anchor wavelengths and a **3×3 per-wavelength quadratic** `A+B·Kt+C·Kt²=R̄` solved by Cramer's rule. The
committed coefficients reproduce the seed R̄ to machine precision (independently re-solved). **Cross-check vs
Fig. 11:** `B(400 nm) = −3.55` (paper ≈ −3.5). **Physics checks:** CCM ≈ 1.0 across the visible at clear Kt
(neutral limit); CCM(400) > CCM(700) and > 1.3 at overcast Kt (cloud blueing). *This is a figure digitization
with residual uncertainty — only the energy-rescale is exact (see D-10).*

The shipped default is the faithful WebPlotDigitized Fig. 11 set (re-anchored, unity at clear), not the 9-anchor seed; the seed is retained as a selectable option. See [validation §2](spectral-engine-validation.md) and `docs/Coefficient provenance/`.

> **⚠️ A tabulation of these coefficients DOES exist.** The claim that the
> coefficients are recoverable only by digitising a figure is **false**: **Whitaker & Newmiller
> (1998), NREL/SR-520-23942, Table 2-1, pp. 19–20** tabulates them (74 rows at 10 nm, 320–1050 nm;
> US Government contractor report, no copyright restriction), and its own p. 20 states they "were
> derived from measured data using statistical analyses as described by Nann and Riordan, 1991". The
> *paper* still tabulates nothing — that part of the sentence above stands; what was wrong was the
> generalisation to "no table exists anywhere". See
> D-10a below.
> ⚠️ **Not a coefficient swap** — the tabulated form is a **six-coefficient model with a 1/cos z
> zenith term** driven by **NGH**, not $K_t$, so it ships as the separate opt-in `Sedes2Modifier`
> rather than a `Sedes1Modifier` variant. **Every figure in this document is a SEDES1-default figure
> and is byte-identical**; adopting SEDES2 changes overcast colour and requires a re-run before any
> overcast number is re-quoted.

**Local re-fitting.** `hcl_core/sedes1_fit.py` (new, pure Python) computes drop-in replacement coefficients from
local measured data: `fit_ccm(spectra, kt_values, reference_shapes, wavelength_nm)` does a per-wavelength
quadratic least-squares of the normalized diffuse shape-ratio against Kt (same functional form as `ccm_coeffs`),
and `write_ccm_csv`/`load_ccm_csv` round-trip the result through the same `wavelength_nm,A,B,C,sigma` schema as
`_sedes1_fig11.csv`. The resulting CSV is exactly what `cloud_variant='local'` (`ccm_coeffs=<path>`) loads — see
`docs/recalibrating-cloud-ccm.md` for the how-to.

### 3.11 `spectral_sky.ground_for_receiver` — spectral ground-glow term

**File:** `src/hcl_core/spectral_sky.py` · **Spec:** §6 · **Methodology:** §10 (Stage G), eq **M-31** ·
**Tests:** `tests/test_spectral_sky.py` (2)

```python
ground_for_receiver(rec, *, surface_tilt_deg, spectral_albedo) -> list   # 401-pt, W/m²/nm
```

`ground(λ) = [direct_normal(λ)·cos z + sky_diffuse_horizontal(λ)] · albedo(λ) · (1−cos tilt)/2`. The
view-factor `(1−cos tilt)/2` is 0 at tilt 0 (returns zeros) and 0.5 at tilt 90. Direct is projected to
horizontal by `cos z`; diffuse is **not** projected. Ground is **isotropic** (no orientation argument). **NB
(spec §6):** this is the spectral ground-glow **input** for the Radiance path — Radiance owns the
sky/receiver transposition; this is not a finished receiver irradiance.

### 3.12 `spectral_sky.build_record` — per-timestep orchestrator

**File:** `src/hcl_core/spectral_sky.py` · **Spec:** §5, §13 (night/twilight) · **Methodology:** §8–§9 ·
**Tests:** `tests/test_spectral_sky.py` (4: clear end-to-end, night, twilight-edge flag, day provenance)

```python
build_record(engine, modifier, atm, geo, *, timestamp, dni, dhi, ghi, i0_normal, clearsky_correction=None) -> SpectralSkyRecord
```

Order: `engine.compute(atm, geo)` (tilt 0) → optional `clearsky_correction.apply(...)` (clear-sky bias K(λ), default `None`/off) → `modifier.apply(...)` on the native range → `resample_to_1nm` →
`SpectralSkyRecord`. **Day provenance (as coded):** `engine, cloud_model, night=False, native_resolution, clearness_kt, k_dir, k_dif, clear_dni_bb, clear_dhi_bb`. **Night** (`zenith ≥ 90°` or `cos z ≤ 0`): returns
401-zero spectra and provenance `night=True, k_dir=0, k_dif=0, clearness_kt=0` **plus the twilight-edge audit
flag** `night_but_epw_nonzero = (dni>0 or dhi>0 or ghi>0)` — so any EPW radiation dropped at a below-horizon
sampled instant is auditable rather than silent (spec §13). `broadband` carries `{dni, dhi, ghi, clearness_kt}`.

### 3.13 `tests/test_skyspectra` — measured-data streaming harness (capability-gated)

**File:** `tests/test_skyspectra.py` · **Spec:** §7.4, §10 · **Tests:** 6 pass + 1 gated skip

Streams/parses the measured SKYSPECTRA horizontal-irradiance and patch-set data onto the 401-pt grid
(`to_grid` / `iter_horizontal` / `iter_patch_sets`), verified against **committed synthetic, license-clean
fixtures** (SKYSPECTRA is CC BY-NC-ND, so no raw data is redistributed). One live-streaming test
(`test_full_horizontal_streams_frvlx`) is gated `@skipif(not os.path.exists(tests/fixtures/skyspectra/raw/spectral_horizontal_irradiance.csv))`
and only runs when the real (multi-GB, not-in-repo) dataset is downloaded. Establishes "green
pytest ≠ measured-validated" now (spec §10) — see **D-15**.

---

## 3quater. As-built modules (Phase 4 — Track A: physics replaces templates)

The reconstruct-side seam that lets the physically-derived `SpectralSkyRecord` feed the existing reconstruction
pipeline — a `sun_spd` injection point mirroring the long-standing `sky_spd` one (closing the spec §11 #4
sky/sun asymmetry), plus a thin `spectral_emit` bridge that turns a record into the two shapes the legacy
pipeline consumes. **Strictly additive: every new path defaults to the existing template behaviour**, so
`reconstruct_spectrum` with no `sun_spd` is bit-identical to before Phase 4. The record supplies *reference
shapes*, never *transport totals* — the Radiance per-channel bin totals are untouched; only the within-bin
reshaping template changes (spec §2, §A.4). The bin-energy invariant of `_shape_within_bins` (each bin's total
is preserved under any reference shape) is the same one Phase 2/3 rely on — Phase 4 only swaps *which* reference
shape the sun is reshaped onto.

### 3.14 `spectral_reconstruct` (modified) — `sun_spd` injection + `_sun_reference_spd`

**File:** `src/hcl_core/spectral_reconstruct.py` · **Spec:** §11 #4 (the sun-side seam), §12 (additive/default-off)
· **Methodology:** §2 (reference-shaped reconstruction) · **Tests:** `tests/test_spectral_reconstruct.py` (+4)

**Public API (as coded — additions only):**

```python
_sun_reference_spd(sun_spd, solar_zenith) -> list   # 401-pt; explicit sun_spd (len==401) else air-mass template
reconstruct_spectrum(sky_channels, sun_channels, channel_type, *, method="reference",
                     sky_spd=None, sun_spd=None, sun_spectral="colored", solar_zenith=None,
                     dseries_sky=False, sky_cct=None)
assemble_nvrd_rows(..., *, ..., sky_spd=None, sun_spd=None, ...)   # sun_spd threaded through to reconstruct
```

`_sun_reference_spd` mirrors the existing `_sky_reference_spd`: a non-`None` `sun_spd` must be a 401-value
380–780 @1 nm list (else `ValueError`) and is returned as a fresh copy; `sun_spd=None` falls back to
`solar_spd_for_zenith(30.0 if solar_zenith is None else solar_zenith)` — **byte-identical to the pre-Phase-4
inline code**. The colored-sun branch now reshapes `flat_sun` onto this reference; `sun_spectral="neutral"` is
unchanged. `sun_spd` is threaded through `assemble_nvrd_rows` into its inner `reconstruct_spectrum` call, so the
nvRD row builder can carry a physical sun per timestep (row layout/length 413 unchanged). **Backward-compat is
test-locked** (`test_sun_spd_none_is_unchanged_template_behavior` asserts `base == same`).

### 3.15 `spectral_emit` (new) — record → legacy-pipeline bridge

**File:** `src/hcl_core/spectral_emit.py` · **Spec:** §2, §8 ("engine= source"), §9.4 (Track A emitters) ·
**Methodology:** §2 · **Tests:** `tests/test_spectral_emit.py` (6)

**Public API (as coded):**

```python
record_to_spd_dict(grid_nm, values) -> dict            # {int_nm: value}; caller supplies the 380..780 grid
to_channels(record, channel_type) -> (diffuse, direct) # bin_average each record component → 3 or 9 channels
to_reference(record) -> (sky_spd, sun_spd)             # (sky_diffuse_horizontal, direct_normal) as 401-lists
reconstruct_from_record(record, sky_channels, sun_channels, channel_type=1, method="reference") -> list
```

`to_channels` bins the record's diffuse → `diffuse_channels` and direct → `direct_channels` via the existing
`bin_average` (3 channels in `BINS_3` r,g,b order for `channel_type=0`; 9 ascending bins for `=1`) — exactly the
input shape `colored_sky(diffuse_channels, direct_channels, channel_type)` expects. `to_reference` yields the
sky (=diffuse) and sun (=direct) 401-value reference SPDs for `reconstruct_spectrum`. `reconstruct_from_record`
is the **"engine= source" wiring in one call** (spec §8): it pulls `(sky_spd, sun_spd)` from the record and
reconstructs with both physical references + a colored sun — replacing the D-series/air-mass templates with
physics for that timestep. The Radiance transport still supplies `sky_channels`/`sun_channels` (the per-bin
totals); the record only supplies the reshaping shapes.

### 3.16 `server.reconstruct_spectrum` (modified) — `sun_spd` passthrough

**File:** `src/hcl_mcp/server.py` · **Spec:** §11 #4, §12 · **Tests:** `tests/test_server.py` (+1)

The MCP `reconstruct_spectrum` tool wrapper gains `sun_spd: list | None = None`, passed straight through to the
core `reconstruct_spectrum`. Default `None` → unchanged behaviour (all 74 pre-existing server tests stay green).
The `divergence` call is **deliberately left without `sun_spd`** — it measures *template* divergence by design,
and `reconstruction_divergence` has no such parameter (passing it would `TypeError`); the omission is correct,
not a dropped argument (**D-16** covers the broader live-wiring boundary).

---

## 3quinquies. As-built modules (Phase 5 — Track B: artifacts + annual loop + MCP tools)

The EPW→record orchestration (point-in-time + annual), the four artifact emitters off the canonical record, and
the three additive MCP tools that expose them — plus the in-place closure of **D-14** (CCM caveats on the
record). Everything here is **offline, pure-Python, stdlib-only**, and consumes the now-complete Phase 1–3
producer chain through `build_record`. Spec **§8 (artifacts), §9.5 (Track B)**; methodology **§4/§5/§9**.

### 3.17 `spectral_pipeline` (new) — EPW → canonical record orchestration

**File:** `src/hcl_core/spectral_pipeline.py` · **Spec:** §8, §9.5, §13 (annual scale) · **Methodology:** §4
(Stage A boundary), §5 (Stage B) · **Tests:** `tests/test_spectral_pipeline.py` (11)

**Public API (as coded):**

```python
record_from_epw(epw_path, month, day, hour, *, engine=None, modifier=None, overrides=None,
                ozone_mode=None, aerosol_g=None, aod_anchor_nm=None, return_diagnostics=False) -> SpectralSkyRecord
annual_records(epw_path, *, engine=None, modifier=None, hours=None, overrides=None,
               ozone_mode=None, aerosol_g=None, aod_anchor_nm=None, return_diagnostics=False) -> list[SpectralSkyRecord]
_SOLAR_CONSTANT = 1361.0   # normalization-only; decoupled from engine ETR (spec §12)
```

`record_from_epw` parses the EPW hourly rows (`epw_hourly.parse_epw_hourly_diagnostics` + `row_for`) and the LOCATION header
(`hcl_core.epw_location.parse_epw_location`), derives the atmosphere (`atmosphere.derive(row, overrides=)`), computes
geometry at the **mid-interval hour** (`solpos.compute(hour=hour − 0.5, …)` — EPW is hour-ending, the documented
30–60 min boundary), forms `i0_normal = 1361.0 · earth_radius_vector`, and calls `build_record(..., timestamp=(month, day, hour), …)` — **the record `timestamp` keeps the original EPW hour** while geometry uses the
mid-interval. Raises `ValueError` if the row or the LOCATION header is missing. Defaults: `Spectrl2Engine` +
`Sedes1Modifier`, both swappable. `annual_records` is the batch driver: one record per EPW data row (or per
`(month, day, hour)` in the optional `hours` subset), each built the same way; it returns a concrete **list** (not
a generator). Night rows are not special-cased here — `build_record`'s own night guard zeroes them.

> **Note (carried scope):** both functions parse the EPW twice (`parse_epw_hourly_diagnostics` + `parse_epw_location`) — one
> extra *header* read per call, not per row, so the annual path scales fine. This is the plan's clean
> interface-consumption design (two documented Phase-1 parsers); folding them into a single read is an optional
> later refactor, not a correctness issue. The `1361` constant is a Kt-normalization value only and is
> deliberately **not** unified with the engine's internal ETR table (spec §12 — SMARTS keeps 1367, SPECTRL2 its
> own ET_H0).

### 3.18 `spectral_emit` (extended) — four artifact emitters + JSON view

**File:** `src/hcl_core/spectral_emit.py` · **Spec:** §8 (the four artifact forms), §9.5 · **Methodology:** §8/§11
#9 (band grid) · **Tests:** `tests/test_spectral_emit.py` (+6)

**Public API (as coded — Phase-5 additions):**

```python
record_to_dict(record) -> dict                        # JSON-able: timestamp(list), broadband, provenance,
                                                       #   both 401-pt spectra, + atmosphere/geometry (asdict if dataclass)
emit_spd_set(record, ground=None) -> str              # CSV: wavelength_nm,direct_normal,sky_diffuse_horizontal[,ground] + 401 rows
BAND_EDGES_20 = [380, 400, …, 780]                    # 21 edges → 20 bands (380–780 @20nm)
band_average(values_401) -> list[float]               # mean of 1nm values in each of the 20 bands
emit_band_matrix(records) -> str                      # per-record: m d h + 20 diffuse + 20 direct band means (#-header lists centers)
emit_spectral_wea(records) -> str                     # .wea-style: per-record m d h + 20 DIFFUSE band means (diffuse-only by design)
emit_augmented_epw_sidecar(records) -> str            # lossless CSV: m,d,h + 401 dir_<nm> + 401 dif_<nm> per record
```

The emitters are **thin** — every external form derives from the canonical 1nm record; no physics is recomputed
(the µm→nm conversion already happened in the resampler). `band_average` partitions the 401 indices (0–400) into
20 bins with **no gaps or overlaps**: band *k* spans `[20k, 20(k+1))` for *k* < 19 (20 samples each), and band 19
spans `[760, 780]` **inclusive** (21 samples — the 401st endpoint folds into the last band by design; commented
in-code). The **20-band grid is the documented hcl band grid**; reconciliation with `gensdaymtx` (Phase 7)
re-bins onto its NCOMP-derived UNIFORM 380–780nm grid — which equals this nominal grid for ncomp=20, so it is a
confirmation, not a correction. (`gensdaymtx`'s `WAVELENGTH_SPLITS` header is the 4-value RGB partition, not band edges.) Format note: the four band/sidecar emitters
format values with `:.6g`; **`emit_spd_set` deliberately keeps raw float precision** (it is the lossless 1nm
archival form — commented so it isn't "cleaned up" into `:.6g`). The `.wea` form is **diffuse-only** (the standard
daylight-coefficient sky-diffuse matrix); the **sidecar is complete** — it carries both components (`dir_`/`dif_`
columns) for archival — but at `:.6g` precision like the other three (6 significant digits, not raw-float
lossless; only `emit_spd_set` is numerically lossless).

### 3.19 `spectral_sky.build_record` (extended, D-14) — CCM caveats on the record

**File:** `src/hcl_core/spectral_sky.py` · **Spec:** §5/§12 (auditability) · **Tests:** `tests/test_spectral_sky.py` (+2)

Phase 5 closes **D-14**: the day-branch `prov` dict now copies `ccm_basis`, `coeff_method`, and `ccm_applied`
from the modifier `info` — **defensively, via `info.get(...)`** so a custom `CloudModifier` that omits them yields
`None` rather than a `KeyError`. The night branch carries `ccm_applied = False` for schema symmetry (and, by
design, **not** the two strings — no CCM runs at night). This is pure additive audit metadata: no spectrum, scalar,
or pre-existing provenance key changes. Two new tests assert the exact caveat strings ride on a day record (using
the real `Sedes1Modifier`) and that a night record carries `ccm_applied=False` without the strings. So every
persisted/emitted record (and thus `record_to_dict`'s JSON view and the MCP `spectral_sky_from_epw` output) is now
self-describing about the global→diffuse CCM approximation (D-11) and the figure-digitized coefficients (D-10).

**Extended (swappable/re-fittable CCM):** the day-branch `prov` dict now also copies `ccm_source`,
`ccm_sigma`, and `ccm_sigma_mean` from the modifier `info` (same defensive `info.get(...)` pattern), in addition
to `ccm_basis`, `coeff_method`, and `ccm_applied`. `ccm_variant` rides alongside via the existing `cloud_model`/
provenance path. So a record now discloses not just *that* a CCM ran and *which* labels apply, but *which
variant* was used, *where* a `local` variant's coefficients came from (`ccm_source`), and *how uncertain* the
applied shape is (`ccm_sigma`/`ccm_sigma_mean`) — all still pure additive audit metadata, no spectrum/scalar
change.

### 3.20 `server` (extended) — three additive MCP tools

**File:** `src/hcl_mcp/server.py` · **Spec:** §8, §9.5 · **Tests:** `tests/test_server.py` (+3)

**Public API (as coded — registered additively in the `for _tool in (...)` loop; no existing tool touched):**

```python
atmosphere_from_epw(epw, month, day, hour) -> dict                    # derived AtmosphericState (introspection). sync
spectral_sky_from_epw(epw, month, day, hour, overrides=None,          # record_to_dict(record); + a 401-pt `ground`
                      surface_tilt_deg=None,                          #   array when surface_tilt_deg given (gray albedo).
                      cloud_variant=None, ccm_coeffs=None) -> dict    #   SEDES1 CCM variant selector. sync
async spectral_epw(epw, forms=None, hours=None, work_dir=None,
                   cloud_variant=None, ccm_coeffs=None, ctx=None) -> dict   # writes chosen artifacts → {files, n_records}
```

`atmosphere_from_epw` returns `asdict(record.atmosphere)` for introspection. `spectral_sky_from_epw` returns the
canonical record as a dict and, **only when `surface_tilt_deg` is given**, adds a spectral ground-glow array via
`ground_for_receiver(rec, surface_tilt_deg=…, spectral_albedo=[rec.atmosphere.albedo]*401)` (gray albedo from the
derived atmosphere — the Phase-3 signature, no `orientation_deg`). `spectral_epw` is the long-running batch tool:
it derives `annual_records` (or the `hours` subset), then writes the requested `forms ⊆ {spd_set, band_matrix, spectral_wea, sidecar}` (default all) into the resolved `work_dir` (context-managed `open`), returning
`{files: {form: path}, n_records}`. The `spd_set` form is a combined CSV with per-record blocks separated by a
`# m d h` comment.

**`cloud_variant`/`ccm_coeffs` (both tools).** A shared `_build_modifier(cloud_variant, ccm_coeffs)`
helper builds the `Sedes1Modifier` the pipeline uses: `cloud_variant=None`/`"reanchored"` keeps the pipeline's
byte-identical default; `"verbatim"` and `"seed"` select the other built-in variants; `"local"` requires
`ccm_coeffs=<path to a fitted CSV>` (loaded via `sedes1_fit.load_ccm_csv`) and raises `ValueError` if the path is
missing or fails to load. `atmosphere_from_epw` is intentionally not *cloud*-parameterized here (its output is
engine/cloud-invariant).

> **Later-phase kwargs (not shown in the signature block above).** All three tools also expose the
> atmosphere-physics refinements `ozone_mode` / `aerosol_g` / `aod_anchor_nm` (see §3.3 and D-2/D-3/D-7);
> additionally `spectral_sky_from_epw` and `spectral_epw` carry `engine="spectrl2"` (+ `smarts_aerosol`) to select
> the SMARTS physical engine, and `spectral_sky_from_epw` carries `spectral_albedo`. All were added after Phase 5
> and are default-off / byte-identical when unset.

---

## 3sexies. As-built modules (Phase 6 — SMARTS oracle + validation harness)

The Phase-2 SMARTS scaffold (`compute()` raised — **D-9**) is promoted into a working subprocess **oracle**, and a
new validation module lands the drift-vs-templates report and the cross-engine comparator. Everything in this phase
is **capability-gated**: the SMARTS *run* needs the `smarts295bat` binary (`$SMARTSPATH`) and the SKYSPECTRA
*streaming* test needs the measured dataset (a `skipif` on the raw fixture CSV's presence); both skip cleanly when absent. **"Green pytest ≠
live-validated"** for the binary/dataset paths — stated in the code and below. The pure pieces (deck generation,
output parsing, the comparator math, the drift passthrough) are fully unit-tested with no binary. Spec **§3, §9.2
(oracle), §9.6 (oracle + validation), §10 (measured validation)**; methodology **§12 (parallel engines)**.

### 3.21 `spectral_engine/smarts` (rewritten) — deck generator + parser + subprocess engine

**File:** `src/hcl_core/spectral_engine/smarts.py` · **Spec:** §3, §9.2, §9.6 · **Methodology:** §12 ·
**Tests:** `tests/test_smarts.py` (3 unit + 1 gated cross-check + 1 gated live-`compute`; + `smarts_available`/Protocol)

**Public API (as coded):**

```python
smarts_available() -> bool                              # True iff $SMARTSPATH names an executable file (unchanged)
build_deck(atm, geo, *, aerosol="rural") -> str          # 29-line SMARTS 2.9.5 deck (LF-terminated), 280–4000nm
parse_ext_output(text) -> (wavelength_nm, direct_normal, diffuse_horizontal)   # cols 0/2/3, W/m²/nm
class SmartsEngine:                                     # name = "smarts"; satisfies SpectralEngine Protocol
    def compute(self, atm, geo, *, tilt_deg=0.0, cos_incidence=None) -> ClearSkySpectra
```

**`build_deck` (as coded).** `build_deck(atm, geo, *, aerosol="rural")`. A flat, ordered list of
apostrophe-quoted, free-format cards joined with `\n` + a trailing `\n` (LF only, **no `\r`** — SMARTS is
line-ending- and position-sensitive). The fixed card map encodes: ISPR=1 site pressure (`atm.pressure_mbar`,
ALTIT 0.012, HEIGHT 0), `USSA` reference atmosphere, **IH2O=0** explicit PWV (`atm.pw_cm`), **IO3=0** explicit
ozone (`atm.ozone_atm_cm`), IGAS=1/qCO2=370, **ITURB=0** TAU5 = `atm.aod500` (AOD@500), **IALBDX=−1** fixed
albedo (`atm.albedo`), ITILT=0, WLMN/WLMX 280–4000, IPRT=2 with **IOUT `1 2 3`** (ET / direct-normal /
diffuse-horizontal), and **IMASS=0** → Card 17a `ZENIT AZIM` (`geo.zenith_deg`, azimuth 180). Card 8 (aerosol)
is where **default** `aerosol="rural"` emits **`S&F_RURAL`** — unchanged, byte-identical, 17 logical cards. **Ångström
α is NOT a settable input under the default `"rural"` mode** — it comes from the `S&F_RURAL` aerosol model; only
the AOD500 *magnitude* is set via TAU5. **Resolved, opt-in (D-20):** `aerosol="user"` instead emits
`AEROS='USER'` + a Card 8a (`ALPHA1 ALPHA2 OMEGL GG` = `atm.angstrom_alpha atm.angstrom_alpha 0.95
atm.aerosol_g`), a 30-line deck, making both α and the asymmetry factor settable SMARTS inputs.

**`parse_ext_output` (as coded).** Splits `smarts295.ext.txt` on whitespace; for each line with ≥4 fields it reads
col 0 = Wvlgth, **col 2 = direct-normal (IOUT 2)**, **col 3 = diffuse-horizontal (IOUT 3)**, skipping the header /
any non-numeric line via a `ValueError` guard. Values are SMARTS-native **W/m²/nm** at this layer (the ×1000 → µm
conversion is `compute`'s job, not the parser's). The IOUT `1 2 3` → col 0/2/3 mapping is the **pure** direct/diffuse
variants (distinct from the `+circumsolar` IOUT 9/10) and was checked against the bundled SMARTS Examples (D-19).

**`SmartsEngine.compute` (as coded).** Raises `RuntimeError` when `smarts_available()` is False (callers gate on
it — replaces the Phase-2 `NotImplementedError`, **D-9 closed**). When the binary is present: `mkdtemp` a **fresh
run dir** (SMARTS refuses to overwrite `smarts295.out.txt`/`.ext.txt`), symlink each sibling of the binary into it
(the ancillary data tree, reachable from CWD), write `build_deck(...)` to `smarts295.inp.txt` with `newline="\n"`,
`subprocess.run([binary], cwd=run_dir, check=True, timeout=120)` (stdout/stderr → DEVNULL), parse `…ext.txt`, and
**`shutil.rmtree` in a `finally`** so the temp dir is cleaned on every path. Returns a `ClearSkySpectra` with
`direct_normal`/`sky_diffuse_horizontal` each **×1000** (W/m²/nm → **W/m²/µm**, the engine-uniform convention the
resampler's ÷1000 expects) and `units="W/m^2/um"` (the dataclass default). `tilt_deg`/`cos_incidence` are accepted
for Protocol conformance but unused (the deck hardcodes ITILT=0) — **D-21**. *Capability-gated on `$SMARTSPATH`;
**first run live 2026-06-21** (compiled from the NREL 2.9.5 Fortran source to a native arm64 binary — that
distribution's Mac binary is dead PowerPC), agreeing with the Python SPECTRL2 engine to ~2% direct / ~7% diffuse, r≈0.99. See
§5 and [`spectral-engine-comparison.md`](spectral-engine-comparison.md).*

### 3.22 `spectral_validate` (new) — drift-vs-templates + cross-engine compare

**File:** `src/hcl_core/spectral_validate.py` · **Spec:** §9.6 (drift harness + cross-engine compare) ·
**Methodology:** §2, §12 · **Tests:** `tests/test_spectral_validate.py` (4)

**Public API (as coded):**

```python
drift_vs_templates(sky_channels, sun_channels, channel_type, *, sky_spd=None, solar_zenith=None) -> dict
compare_engines(a, b, *, lo_nm=380, hi_nm=780) -> dict   # {direct_mean_pct, direct_max_pct, diffuse_mean_pct, diffuse_max_pct}
```

`drift_vs_templates` is a thin passthrough to `reconstruction_divergence` (`spectral_reconstruct.py`), forwarding
`sky_spd`/`solar_zenith` and returning its exact shape `{flat_vs_reference:{mel_edi_pct,i_eff_pct}, neutral_vs_colored_sun:{mel_edi_pct,i_eff_pct}}` — the "how far do the physical shapes move the circadian metrics
vs the flat/neutral templates" report. (It deliberately does **not** expose `reconstruction_divergence`'s
`dseries_sky`/`sky_cct` — the plan's narrower surface; noted as a Minor.)

`compare_engines` reports the **mean and signed-max relative % difference** (`100·(b−a)/a`, max by absolute value)
of two `ClearSkySpectra`'s direct + diffuse over the visible band, sampling each engine onto a shared 1-nm integer
sweep via an internal linear interpolator. Identical inputs → 0; `b = 1.1·a` direct → `direct_mean_pct ≈ 10`. A
**grid-coverage guard** (added in the Phase-6 final-review fix) raises `ValueError` if either spectrum's grid does
not span `[lo_nm, hi_nm]` — the comparator **refuses to silently clamp/extrapolate** outside an engine's measured
range (verified: SPECTRL2's 300–4000nm and SMARTS's 280–4000nm both span the band; a truncated grid raises).

### 3.23 `tests/test_smarts` cross-check + `tests/test_skyspectra` — the (gated) validation harnesses

**Files:** `tests/test_smarts.py`, `tests/test_skyspectra.py` · **Spec:** §9.6, §10 · **Tests:** gated

- **`test_smarts_cross_check_clear_sky`** — the executable form of Phase 6's "cross-engine compare (SMARTS vs
  SPECTRL2)" deliverable. Gated `@skipif(not smarts_available())`. When a binary is present it runs **both** engines
  for one clear-sky atmosphere/geometry, calls `compare_engines`, asserts both spectra span 380–780 with positive
  direct+diffuse, and bounds **direct-normal** agreement within a documented **35%** envelope; spectral **diffuse**
  is sanity-checked (finite/positive) but not tightly bounded — the two independent models genuinely diverge there,
  and a tight bound would flake on real hardware. *(This replaced a stale Phase-2 placeholder that `raise`d
  "not implemented until Phase 6" — which, being `skipif`-gated, would have **failed red** on any machine with a
  SMARTS binary. Found and fixed in the post-execution correctness pass — see §5/D-19. The SPECTRL2 half is exercised
  live; the SMARTS subprocess is binary-gated but was **first run live 2026-06-21** with a compiled `smarts295bat`
  — this cross-check now passes live, see D-19.)*
- **`test_skyspectra.py`** — the measured-data streaming/parsing harness (spec §10). Its in-repo unit tests exercise
  the 401-pt regrid (`to_grid`, incl. blank-radiance dropping), the horizontal-spectrum reader (`iter_horizontal`),
  and the patch-set grouping + geometry parse (`iter_patch_sets`) against **committed synthetic, license-clean
  fixtures** (SKYSPECTRA is CC BY-NC-ND — no raw redistributed). A single live-streaming test
  (`test_full_horizontal_streams_frvlx`) is gated
  `@skipif(not os.path.exists(tests/fixtures/skyspectra/raw/spectral_horizontal_irradiance.csv))` and streams the
  real FR-VLX dataset (asserting 401-pt spectra) only when it is downloaded — the documented **on-download wiring
  point** for measured validation. (The earlier `test_reconstructed_mel_edi_within_envelope` mel-EDI placeholder was
  dropped in favor of these fixtures.) — **D-22**.

---

## 3septies. As-built modules (Live-DDS physical-sky flip — opt-in, addresses D-16/D-17)

The first wiring of the physical, EPW-derived per-timestep `SpectralSkyRecord` into the **live** annual→nvRD
transport. It is **opt-in** (`physical_sky=False` default, bit-identical to before), shapes the *enhanced*
reconstruction's **sky and sun** with the record's diffuse/direct spectra instead of the static-reference / 30°
air-mass templates, falls back per-timestep, and reports coverage. It does **not** flip the default and is **not
live-validated** (no Daysim/Radiance here) — so D-16/D-17 are **downgraded, not closed** (§4). (The standalone
Live-DDS design spec + plan that drove this work were removed from the tree once the feature landed; this
§3septies section + D-16/D-17 are now the authoritative as-built record.) Methodology **§11.1** (reference-shaped
reconstruction, bin totals preserved); umbrella spec **§8** (the one explicitly-deferred live-wiring item),
**§5.1–§5.3** (the nvRD bridge).

**Mechanism (verified by execution, 2026-06-19).** The record's SPDs enter `reconstruct_spectrum` only as the
*reshaping shapes* (`sky_spd`/`sun_spd`); the existing `_shape_within_bins` preserves each bin's transport total, so
a physical SPD **moves the spectral shape but conserves total energy to ~5.5e-17** (methodology §11.1's invariant,
confirmed numerically). The record's absolute units/normalization are irrelevant.

### 3.24 `spectral_reconstruct.assemble_nvrd_rows` (extended) — per-timestep reference series

**File:** `src/hcl_core/spectral_reconstruct.py` · **Spec:** §3.2 · **Tests:** `tests/test_spectral_reconstruct.py` (+2)

```python
assemble_nvrd_rows(..., *, sky_spd=None, sun_spd=None, sky_spd_series=None, sun_spd_series=None, ...)
```

Two **explicit** per-timestep params (no overload heuristic — the design rejected one because a `None` *entry*,
the fallback case, would misfire). Per row `t`: `eff_sky = sky_spd_series[t] if sky_spd_series is not None else sky_spd` (same for sun), then the unchanged `reconstruct_spectrum(...)`. A `None` *entry* yields the template for
that one step (the `_sky_reference_spd`/`_sun_reference_spd` `None`-fallbacks). Both series `None` → bit-identical to
the prior single-SPD path (test-locked). The scalar-or-list `solar_zenith` indexing is untouched.

### 3.25 `annual_nvrd` (extended) — `_physical_spd_series`, `_build_record_index`, the `physical_sky` flag

**File:** `src/hcl_radiance/annual_nvrd.py` · **Spec:** §3.3–§3.4 · **Tests:** `tests/test_annual_nvrd.py` (+10)

**Public/internal surface (as coded):**

```python
_is_zero_record(rec) -> bool                                   # all-~0 direct+diffuse → night/zero
_physical_spd_series(record_index, timestamps, *, real_timestamps) -> (sky_series, sun_series, coverage)
_build_record_index(epw, timestamps, real_timestamps, engine=None) -> {(m,d,hour_ending): record}
annual_nvrd(..., physical_sky=False, engine=None, _record_provider=None, _channel_provider=None)
```

- **`_physical_spd_series`** (pure, EPW/binary-free) maps each transport timestep `(m,d,h_frac)` to its EPW
  **hour-ending** `H = min(24, max(1, ceil(h_frac)))`, looks it up in the index, and emits a 401-SPD-or-`None`
  per step via `to_reference(rec)`. A miss, a synthetic-timestamp run (`real_timestamps=False`), or a **night/zero
  record** → `None`, counted as **template** (a zero reference would only trip the flat fallback, so counting it
  physical would overstate coverage). `coverage = {n_physical, n_template, coverage_pct}`. Verified ceil edges:
  `8.0→8, 8.1→9, 9.0→9, 9.1→10, 24.0/25.0→24`.
- **`_build_record_index`** (the production glue) memoizes **one `record_from_epw` call per unique hour-ending**
  (≤8760 even for ~87k sub-hourly steps); a per-hour `ValueError` (missing row/LOCATION) leaves that hour absent →
  template. The `except` is **narrowed to `ValueError`** (review follow-up) so a real `record_from_epw` integration
  break surfaces instead of hiding as 0% coverage. No-epw / synthetic → `{}`.
- **`annual_nvrd`** gains `physical_sky` + a `_record_provider` test hook. When on: build the index (production from
  `epw`; tests inject the map), call `_physical_spd_series`, and pass `sky_spd_series`/`sun_spd_series` into the
  **enhanced** `_run_nvrd_for_method` call **only** (faithful is never given the series — baseline provably
  untouched). The representative-timestep `reconstruction_divergence` gets the physical `sky_spd` (it has no
  `sun_spd`) + a `divergence_note` that it's a template-leaning proxy while `RD_series_divergence` is the
  physics-aware delta. A `physical_sky` block reports `{requested, n_physical, n_template, coverage_pct, note}` (note
  carries the "shape-only … per-bin transport totals are unchanged" caveat — describes THIS run's transport, not a
  global never-live-validated claim; see the 2026-07-18 first live execution, §3septies). The constant-30° `enhanced_solar_note` is suppressed under
  **full** physics coverage and, under **partial** coverage, reworded to "the template-fallback timesteps" (not
  "ALL timesteps" — review follow-up).

### 3.26 `server.annual_nvrd` (extended) — MCP `physical_sky` passthrough

**File:** `src/hcl_mcp/server.py` · **Spec:** §3.5 · **Tests:** `tests/test_server.py` (+1)

The MCP `annual_nvrd` wrapper gains `physical_sky: bool = False`, forwarded straight to the core. Default off → all
existing server tests stay green. (An `engine: str = "spectrl2"` selector was later added to this same wrapper for the
SMARTS physical-sky path — §3.21; only used when `physical_sky=True`. No other tool was touched.)

---

## 3octies. As-built modules (Phase 7 — Native Radiance `gensdaymtx`)

A **parallel engine** to the Python stack: drive Radiance 6.1a's native spectral sky tool `gensdaymtx`
straight from an EPW, behind capability detection so it **degrades to emitting the command plan** when the
Radiance 6.x binary is absent. Pure command builders, a
matrix-header parser, native-band reconciliation, capability detection, a run-or-emit driver, and one MCP
tool. Spec **§9.7 (Track C)**; methodology **§12 (parallel engines)**. **Everything Track-C-facing is verified
against the upstream Radiance 6.x source** — the man page and
the binary's own usage string both advertise behaviour the parser does *not* implement, so the source is the
only ground truth (this is the lesson the phase encodes; see D-25).

> **Live-validated (2026-06-20).** Radiance 6.1a is installed at `/usr/local/radiance/bin` (full toolset).
> Both `radiance_status()` and `radiance_spectral_status()` (gensdaymtx,
> rcomb) report `available` from the same install. The subprocess **run path had its first live validation**:
> `run_gensdaymtx(..., run=True)` → `ran=True, ok=True`; header confirmed **NCOMP=20** (NROWS=146 sky patches).
> The gated cross-check test `test_native_vs_python_engine_envelope` is now **wired and runs live**
> (was a `pytest.skip` stub — D-26 closed). The **degrade path still applies** where no binary is present:
> when `gensdaymtx` is absent the tool returns the command plan as before.
>
> **Band-order note (load-bearing).** The native `.smx` matrix body stores its 20 components **DESCENDING**
> in wavelength (red→blue, matching header `WAVELENGTH_SPLITS = 780 588 480 380`). The array MUST be reversed
> (`[::-1]`) to ascending 380→780 before comparison with the Python engine or any wavelength-ordered consumer.
> Today only the test helper `_native_band_vector_for_hour` performs this reversal; no production `.smx`-body
> reducer exists yet. Un-reversed correlation vs Python engine: −0.70; reversed: +0.987 — this is the
> load-bearing finding from the live validation (documented in `spectral_native.parse_smx_header`).

### 3.27 `spectral_native` — `gensdaymtx` driver (command builders, header parse, run-or-emit)

**File:** `src/hcl_radiance/spectral_native.py` (new) · **Spec:** §9.7 · **Methodology:** §12 ·
**Tests:** `tests/test_spectral_native.py` (21, including the live cross-check, which runs under Radiance 6.1a
against the Athens IWEC EPW in `hcl_validation/inputs/weather/`)

**Public API (as coded):**

```python
build_gensdaymtx_cmd(epw_path, *, mf=1, mode="all", ground_refl=None, outfmt="a") -> list[str]
build_rcomb_melanopic_cmd(smx_path, *, ncomp=20) -> list[str]         # rcomb -c <explicit S 026 coeffs>
parse_smx_header(text) -> dict          # {ncomp, nrows, ncols, rgb_partition}
radiance_spectral_status() -> dict       # {available, gensdaymtx, rcomb}  via discover.resolve_bin
reconcile_to_native_bands(values_401, ncomp, *, lo_nm=380.0, hi_nm=780.0) -> list[float]
run_gensdaymtx(epw_path, work_dir, *, mf=1, mode="all", ground_refl=None, run=True, timeout=None) -> dict
```

**Command builders (implemented flags ONLY).** `build_gensdaymtx_cmd` emits `-m <mf>`, mode (`all`→none /
`sun`→`-d` / `sky`→`-s`), optional `-g <scalar>`, and `-o{a|f|d}`, with the `.epw` last — location/time are read
from the EPW header (`EPWopen`), so there are **no `-x/-y/-t` flags**. It **never** emits `-c/-O/-A/-D/-M`: those
appear in the binary's *stale usage string* but are not parsed and abort the run (test-locked).
`build_rcomb_melanopic_cmd` collapses a spectral matrix to a single **CIE S 026 mel-EDI** channel and
**deliberately does NOT use Radiance's own `-c M`**: that flag returns equal-energy-normalised *melanopic lux*
(the EML-style quantity), **not** mel-EDI — `util/rcomb.c:269-271` applies `scolor2melanopic * WHTMELANOPIC`
with `WHTMELANOPIC 179.` (`common/color.h:276`), matching Radiance's photopic convention. Verified live
(2026-07-17) on a D65 spectrum in descending band order: `-c M` reads **1.081× true mel-EDI (8.1% high)**,
and `-c M`/`-c Y` = 1.098 ≈ the Lucas EML/mel-EDI ratio. This is Radiance behaving as documented
(`rcomb.1:150`), not a Radiance defect — the defect was **ours**, consuming EML as if it were mel-EDI, since
S 026 requires mel-DER(D65) = 1 exactly. The builder therefore emits **explicit numeric coefficients**
(`s026_melanopic_coefficients(ncomp)`), which `rcomb` applies as a plain dot product over the components in
file order. See [`spectral-sky-methodology.md` §12.2](spectral-sky-methodology.md) and
[ADR-0001](adr/0001-mel-edi-is-the-circadian-quantity.md). **`-g` is a single scalar** gray ground reflectance (`grefl = atof(argv[++i])`,
`gen/gensdaymtx.c:647`) — a tuple raises `TypeError` (corrected from the plan's `-g r g b`; **D-25**).

**Header parse + native bands.** `parse_smx_header` reads `NCOMP`/`NROWS`/`NCOLS` and the header's
`WAVELENGTH_SPLITS` — but stores the latter as **`rgb_partition`**, because that record is the **4-value legacy
RGB partition `{780, 588, 480, 380}`** (`fputwlsplit` prints four `%g`, `common/color.h:321`; `common/color.c:94`),
**not** the spectral band edges (corrected from the plan's "WLPART band edges"; **D-25**). The native 20 bins are
**uniform 380–780 nm @20 nm** (`NSSAMP=20`, `WVLSPAN=400` over 380→780, `gen/atmos.c:164/169`), so
`reconcile_to_native_bands` re-bins a Phase-5 401-pt 1 nm spectrum onto the **NCOMP-derived uniform grid** (module
constants `NATIVE_LO_NM=380`/`NATIVE_HI_NM=780`), **not** the header splits. That native grid **equals the Phase-5
nominal `BAND_EDGES_20`** — proven in a test that compares to `spectral_emit.band_average` — so the spec §8
"byte-compat gap" the plan feared **does not exist**: reconciliation is a **confirmation, not a correction**.

**Run-or-emit (`run_gensdaymtx`).** Mirrors the established `colored_sky` degrade pattern. When `gensdaymtx` is on
`PATH` and `run=True`, it runs the subprocess into `sky_spectral.smx` and parses the header; otherwise it returns
the **command plan** (`gensdaymtx` + `rcomb -c <explicit S 026 coefficients>`) plus the `mie_ca.dat`/`RAYPATH`
startup note. The result dict is
**discriminable by an explicit `ok` field** (corrected for shape coherence; **D-25**): emit → `{ran:False, commands, reason}`; success → `{ran:True, ok:True, smx, header}`; failure → `{ran:True, ok:False, error, returncode, smx}`; **timeout → `{ran:True, ok:False, timed_out:True, error, smx}`** (added 2026-06-21 — **D-29**).
The header is read **whole-file** (not a fixed byte count) since `parse_smx_header` skips body rows. Output is
radiometric **W/sr/m²**, 20 bands.

**Timeout (`timeout`, default `None` = no cap; added 2026-06-21 — D-29).** `gensdaymtx` **always processes every
EPW hour**. A full 8760-row × NCOMP=20 year at `mf=1` is actually **fast — ~12 s wall / ~10 s CPU on the Athens
IWEC EPW under Radiance 6.1a** (re-measured 2026-06-29; `NROWS=146, NCOLS=8760`). Cost grows **steeply with the
Reinhart subdivision `mf`** (minutes at `mf≥4`), and it was a high-`mf`/loaded-machine run that once exceeded the
old hard-coded `timeout=600` and **raised `TimeoutExpired`, crashing the MCP call**. The cap is now caller-supplied:
default `None` lets a real annual run complete, and an explicit `timeout` is caught and returned as the
discriminable `timed_out=True` dict above (never raises). *(Correction: the earlier "`>12 min` for an `mf=1`
year" figure was wrong — that magnitude only appears at higher `mf` or under heavy CPU contention.)*

### 3.28 `server.spectral_sky_native` (new) — MCP tool

**File:** `src/hcl_mcp/server.py` · **Spec:** §9.7 · **Tests:** `tests/test_server.py` (+1)

`spectral_sky_native(epw, mf=1, mode="all", work_dir=None, run=True, timeout=None, ctx=None)` follows the standard
tool shape (`await resolve_work_dir(ctx, work_dir)`) and returns `run_gensdaymtx`'s dict
verbatim (the `ok`/`timed_out` fields flow through). The `timeout` param (added 2026-06-21, **D-29**) is passed
straight to `run_gensdaymtx` — default `None` = no cap, because a full-year EPW matrix is many minutes of CPU.
Registered additively in the `for _tool in (...)` loop alongside the Phase-5 spectral tools. The `+1` server test
covers the emit path (no binary). Under the installed Radiance 6.1a the tool now takes the **run path**
(`ran=True, ok=True`) — see the §3octies live-validation note above.

### 3.29 Radiance 6.x build + cross-check gate

The **full Radiance 6.1a toolset** is required (not the spectral subset only) and was built/installed at
`/usr/local/radiance/bin` (2026-05-05 build). Key runtime notes: the `mie_ca.dat`/`RAYPATH` requirement (else
`gensdaymtx` aborts at startup), the implemented-flags-only / `WAVELENGTH_SPLITS`-is-the-RGB-partition
behaviour, and the band-order reversal finding from live validation. The
`@skipif(not radiance_spectral_status()["available"])` cross-check test
(`test_native_vs_python_engine_envelope`, `gensdaymtx` vs the Python engine, reusing Phase-6 `compare_engines`)
**now runs live** under the installed binary — **D-26 closed 2026-06-20**.

---

## 4. Alignment & deviations ledger (as-built vs. spec / methodology)

The corrections and modifications that define the *final* as-built behaviour. Everything not listed here
matches the spec/methodology exactly.

**D-1 — `AtmosphericState.provenance` carried `{source, method}`, not `{source, method, uncertainty}` — resolved (see below).**

> See methodology §6 Algorithm A (atmospheric state resolution order: override > EPW > default, each tagged by source/method).
> Spec §4 declares per-field provenance as `{source, method, uncertainty}`. The as-built records originally carried only
> `source` and `method`; there was **no `uncertainty` field**. The methodology §6 Algorithm A also shows only
> source/method, so the *math reference and the code agreed* — it was the **spec §4 type annotation that ran
> ahead of the implementation**. Impact: low (provenance is auditing metadata); the uncertainty key was an additive
> fill. *Originally an intentional simplification, flagged for spec reconciliation; now reconciled.*

**Resolved:** every `AtmosphericState.provenance[field]` now carries `{source, method, uncertainty}`; `uncertainty` is `None` (reserved/unquantified in v1 — a value is a later additive fill, not a key addition). Test `tests/test_atmosphere.py::test_provenance_entries_carry_uncertainty_key`.

**D-2 — Methodology M-7 (van Heuklon 1979 ozone climatology) is documented but NOT coded — RESOLVED (opt-in).**

> **Source:** van Heuklon 1979, *Estimating atmospheric ozone for solar radiation models*, Sol. Energy **22**:63–68 (M-7). **Verified vs primary source** (`1-s2.0-0038092X79900604-main.pdf`; the methodology M-7 constants match the paper's Eq. 4 / Table 1 verbatim, with the D=0.9856-body / 0.9865-Table 1 caveat noted in methodology §6). *(Historical: the latitude/month climatology M-7 describes was **not computed** in v1; the 300 DU constant default was used instead — now resolved opt-in, see below.)*
> `derive` always sets `ozone_atm_cm` to the **0.30 atm-cm (300 DU) default** (or an override). The lat/month
> climatology (M-7) is described in methodology §6 "Optional ozone climatology" and the spec allows it, but
> no code path computes it. This is consistent with the spec's stance (ozone is a sub-percent error source
> for mel-EDI, so 300 DU is the v1 choice) and the methodology's own "documented for completeness and the
> override path" wording. *Status (historical): intentional v1 scope; the override path covers any
> site-specific ozone.*

**Resolved (opt-in); default unchanged (byte-identical).** `atmosphere.van_heuklon_ozone(lat_deg, lon_deg,
day_of_year)` now implements M-7 verbatim (Eq. 4/Table 1) with the **hemisphere-specific** coefficient sets
(NH: A=150, C=40, F=−30, β=1.28, I=20|0; SH: A=100, C=30, F=152.625, β=1.5, I=−75) — independently confirmed
against **Karavana-Papadimou et al. 2013** (*Global NEST* **15**(2):152, eq. 2, bibliography §6) and the
NH spring-max phase corroborated by **Herman et al. 1993** (Nimbus-7 TOMS). *(The first plan transcription
used a wrong hemisphere-symmetric phase that peaked in summer; corrected + pinned by published-value and
spring>summer phase tests — see methodology §6.)* `derive(row, *, ozone_mode="constant", lat_deg=None,
lon_deg=None, day_of_year=None, ...)` still defaults `ozone_mode` to `"constant"` (the 300 DU literal, tagged
`provenance["ozone_atm_cm"]={"source":"default","method":"fixed"}` exactly as before) — `derive({})` is
byte-identical to pre-refinement output. Passing `ozone_mode="climatology"` (with all three of `lat_deg`/
`lon_deg`/`day_of_year` supplied) computes the lat/month climatology instead, tagging
`{"source":"climatology","method":"van_heuklon79"}`; an explicit `ozone_atm_cm` override still always wins. The
three EPW MCP tools (`atmosphere_from_epw`, `spectral_sky_from_epw`, `spectral_epw`) expose `ozone_mode`, and
`annual_records` forwards it per-row (using each row's own `day_of_year`) so ozone can vary by season across an
annual run. Test coverage: `tests/test_atmosphere.py` + `tests/test_spectral_pipeline.py` (annual seasonal
variation). *Status: **RESOLVED**, opt-in refinement — default path untouched.*

**D-3 — EPW AOD treated as a 500 nm proxy (no Ångström conversion yet) — RESOLVED (opt-in).**

> **Source:** Bird & Riordan 1986, *Simple solar spectral model for direct and diffuse irradiance on horizontal and tilted planes at the earth's surface for cloudless atmospheres*, J. Climate Appl. Meteorol. **25**(1):87, Eq. 2-7 (Ångström turbidity law `τ_a(λ) = τ₅₀₀·(λ/0.5)^−α`). Deviation: the Ångström spectral conversion to a rigorously defined τ₅₀₀ is deferred; the EPW broadband AOD column is used as a direct proxy, and provenance is tagged accordingly.
> When EPW column 29 is present it is broadband, not strictly @500 nm. As-built, `derive` uses it directly as
> `aod500` and tags provenance `method="epw_broadband_proxy"`. The Ångström conversion to a true 500 nm value
> is a documented later refinement (spec §13). In practice column 29 is usually empty → the 0.10 default
> fires. *Status (historical): intentional, provenance-flagged.*

**Resolved (opt-in); default unchanged (byte-identical).** `derive(row, *, aod_anchor_nm=None, ...)` now
Ångström-converts a declared-wavelength AOD to a true $\tau_{500}$ (Eq. 2-7): `aod500 = aod500 *
(aod_anchor_nm/500.0) ** angstrom_alpha`, retagging provenance `method="angstrom_from_<aod_anchor_nm>nm"`.
`aod_anchor_nm=None` (the default on `derive()` and on the `aod_anchor_nm` MCP tool arg) — or the literal value
`500.0` — is a strict no-op: identity value, unchanged `epw_broadband_proxy`/`fixed` provenance. Test coverage:
`tests/test_atmosphere.py::test_aod_anchor_identity_at_500` (no-op) and
`test_aod_anchor_550_converts_up` (non-500 nm anchor converts). *Status: **RESOLVED**, opt-in refinement —
default path untouched.*

**D-4 — Dataclass ownership: types live with their producers, not in a shared `base.py`.**
Spec §4 groups `SolarGeometry`/`AtmosphericState` near the engine. As-built, `SolarGeometry` lives in
`solpos.py` and `AtmosphericState` in `atmosphere.py` (their producers), to keep "files that change
together live together" and avoid a premature shared-types module. (In the event, Phase 2's
`spectral_engine/base.py` is duck-typed via a Protocol and does **not** import these dataclasses —
see D-5.) *Status: intentional deviation, recorded in the Phase 1 plan.*

**D-5 — Public functions/dataclasses are loosely annotated.**
The plan/spec *Interfaces* prose specifies full signatures (`-> SolarGeometry`, `ClearSkySpectra.wavelength_nm: list[float]`, `resample_to_1nm(spectra: ClearSkySpectra) -> tuple[list, list]`) but the as-built code uses bare
`list` on the Phase-2 dataclass fields and omits the `resample_to_1nm`/`SmartsEngine.compute` annotations
(docstrings carry the contract). The plan's own code blocks also omitted them, so code matches plan; only the
prose promised them. `spectral_sky.py` is deliberately **duck-typed** (no import coupling to the engine
package). Impact: cosmetic. *Status: minor; annotations are an additive cleanup.*

**D-6 — `spectral_sky.py` was partial in Phase 2; narrowed by Phase 3; CLOSED by Phase 5.**
Spec §3 and methodology §3.2/§9/§10 describe the sky-truth surface as owning `build_record`, `ground_for_receiver`,
`record_from_epw`, and the annual loop. Phase 2 shipped only `SpectralSkyRecord` + `resample_to_1nm()`; **Phase 3
added `build_record` and `ground_for_receiver`** (§3.11–§3.12); **Phase 5 ships the EPW-driven wrapper
`record_from_epw` + the annual loop** in the new `spectral_pipeline` module (§3.17). The spec located these in
`spectral_sky`; as-built they live in the sibling `spectral_pipeline.py` (orchestration is kept separate from the
record/resampler/ground primitives — files-that-change-together, à la D-4). *Status: **CLOSED** — full surface
delivered; the only deviation is the module split, which is intentional.*

**D-7 — Aerosol asymmetry `g = 0.65` is a hardcoded engine constant — RESOLVED (opt-in).**

> **Source:** Bird & Riordan 1986, *Simple solar spectral model for direct and diffuse irradiance on horizontal and tilted planes at the earth's surface for cloudless atmospheres*, J. Climate Appl. Meteorol. **25**(1):87, Eqs. 3-12…3-14 (forward-scatter asymmetry factor `assym=0.65`, rural aerosol). Deviation: the paper's rural default is hardcoded (M-16); the `AtmosphericState` carries no aerosol-type field that would parameterize it.
> **Note:** `spectrl2_2.c:484` sets `assym=0.65` as the same rural default.
> The C source exposes `assym` as a settable parameter (default 0.65, rural); methodology §7 also fixes it at
> 0.65. Phase-1 `AtmosphericState` carries **no asymmetry field**, so the engine hardcodes the documented rural
> default (`spectrl2.py:36`). Code therefore matches the methodology value exactly. *Status (historical):
> intentional v1 choice; a future `AtmosphericState` aerosol-type input is the parameterization seam.*

**Resolved (opt-in); default unchanged (byte-identical).** `AtmosphericState` now carries an `aerosol_g: float =
0.65` field (the parameterization seam this deviation called for), settable via `derive(overrides=
{"aerosol_g": …})` or the `aerosol_g` MCP tool arg on the three EPW tools. `Spectrl2Engine` consumes
`atm.aerosol_g` in place of the old `0.65` literal for the forward-scatter terms (M-16), and the single-scatter
façade colour in `receiver.py` consumes the same field. Default `0.65` reproduces the prior hardcoded value
exactly (same forward-scatter output, byte-identical). *Status: **RESOLVED**, opt-in refinement — default path
untouched.*

**D-8 — In tilt mode, `sky_diffuse_horizontal` holds diffuse-on-tilt.**

> **Source:** Bird & Riordan 1986, *Simple solar spectral model for direct and diffuse irradiance on horizontal and tilted planes at the earth's surface for cloudless atmospheres*, J. Climate Appl. Meteorol. **25**(1):87, Eq. 3-18 (tilted-receiver transposition — ground + beam-correlated + isotropic sky components, M-24). Deviation: the dataclass field `sky_diffuse_horizontal` is named for the horizontal-plane case; at `tilt_deg > 0` it holds the M-24 tilted-plane result instead, a field-name inaccuracy in the test-only path.
> When `tilt_deg > 0` the engine stores diffuse-on-the-tilted-plane (M-24) in the `sky_diffuse_horizontal`
> field — a field-name inaccuracy. This path exists **only** to reproduce the tilted Fortran golden; all
> production calls use `tilt_deg=0`, where the field is genuinely diffuse-on-horizontal. *Status: documented,
> test-only path; no production impact.*

**D-9 — `SmartsEngine.compute()` scaffold — CLOSED in Phase 6.**
Through Phase 5 the SMARTS backend satisfied the `SpectralEngine` Protocol but `compute()` raised
`NotImplementedError`. **Phase 6 implements it** (§3.21): `compute` now generates a deck (`build_deck`), runs
`smarts295bat` in a fresh temp dir, parses `…ext.txt` (`parse_ext_output`), and returns a `ClearSkySpectra` in
W/m²/µm — raising `RuntimeError` (not `NotImplementedError`) only when `smarts_available()` is False. *Status:
**CLOSED** — the full subprocess engine is in the code. The live run remains capability-gated on `$SMARTSPATH`
(see D-19).*

**D-10 — SEDES1 CCM coefficients are a 9-point seed digitization of Fig. 10, not the full 10-nm curve. [STALE for the default — see "Resolved" below.]**

> **Source:** Nann & Riordan 1991, *Solar spectral irradiance under clear and cloudy skies: Measurements and a semiempirical model*, J. Appl. Meteorol. **30**(4):447, Eq. 11; A/B/C from Fig. 10/11 only — no table **in that paper** (⚠️ but one exists elsewhere: Whitaker & Newmiller 1998, NREL/SR-520-23942 Table 2-1 — see **D-10a**; the "no published table anywhere" reading of this line is retired). Figure-digitized; A/B/C reconstructed via 3-class Vandermonde solve from Fig. 10 R̄(λ) curves.
> The plan's aspiration is a full 300–1100 @10-nm digitization (≈81 points); as-built ships the **9 seed anchor
> wavelengths** (350–1050 nm, `SED_WL_NM[0]==350`) the plan provided, solved per-wavelength. The coefficients
> pass the Fig-11 cross-check (`B(400)=−3.55`) and the neutral/blueing physics tests, but **carry figure-digitization
> uncertainty** — only the always-on energy-rescale is exact. *Status: intentional v1 scope (plan-allowed); the
> energy invariant bounds broadband error regardless; a fuller digitization + SKYSPECTRA validation tightens the
> shape later (Phase 6).*
> **Context (grounds no equation — `literature-bibliography.md` §6):** independent evidence that
> this cloudy-spectrum step is genuinely uncertain comes from Wang et al. 2025 (*Renew. Energy* **256**:124417,
> measurement-trained spectral-skewness) and Paudyal et al. 2024 (*Renew. Energy* **224**:120057, measured
> bimodal clear/cloudy spectral variability) — alternative cloudy-sky routes, **not** a validation of these
> CCM coefficients. A measured cross-check (e.g. against SKYSPECTRA) remains the
> test that would actually bound D-10.

**Resolved:** the shipped **default** is the faithful **10 nm Fig. 11** digitization (330–1100 nm,
`_sedes1_fig11.csv`), reanchored to unity at clear Kt — not the 9-point seed described above. The 9-anchor
seed digitization is **retained only** as the opt-in `variant="seed"` (for comparison; over-blues ~2×).
Coefficient provenance is in `docs/Coefficient provenance/`. **Further resolved:** the CCM is now
locally **re-fittable** — `cloud_variant='local'` (with `ccm_coeffs=<fitted CSV>`) swaps in caller-supplied
coefficients from a local fit (`hcl_core/sedes1_fit.py`) — and its residual shape uncertainty is **surfaced**
on every record as `ccm_sigma`/`ccm_sigma_mean` (the Fig. 11 regression standard error), rather than being an
undisclosed, unbounded caveat. The always-on energy-rescale remains the only *exact* part of the bridge.

**D-10a — SEDES2 ships as an opt-in modifier on TABULATED coefficients. [NEW 2026-08-06 — nothing in `src/` constructs it.]**

> **Source:** Whitaker, C.M. & Newmiller, J.D. (1998), *Photovoltaic Module Energy Rating Procedure — Final
> Subcontract Report*, **NREL/SR-520-23942, Table 2-1, pp. 19–20**
> (<https://docs.nrel.gov/docs/legosti/old/23942.pdf>) — 74 rows at 10 nm, 320–1050 nm, US Government
> contractor report distributed without copyright restriction. Its own p. 20 states the coefficients "were
> derived from measured data using statistical analyses as described by Nann and Riordan, 1991", so this **is**
> a tabulation of the regression D-10's coefficients approximate from a figure. This retires the
> "no machine-readable tabulation exists" claim — see D-10a below.
>
> **As-built:** `src/hcl_core/_sedes2_data.py` (the transcribed table) and `Sedes2Modifier`
> (`src/hcl_core/cloud_modifier.py`); the retrieval-and-transcription provenance record is held in an
> internal validation tree that is not part of this repository, but the values themselves are shipped in
> `_sedes2_data.py` and `tests/test_sedes2.py` pins them against the primary source (NREL/SR-520-23942,
> Table 2-1), asserting the shipped module cannot drift from it.
>
> **⚠️ Why this is a SEPARATE class and not a `Sedes1Modifier` variant** — two structural differences, both
> verified against the primary PDF:
> 1. **Six coefficients, not three — a 1/cos z zenith term** (Eq. 2-39):
>    `CCM(λ,NGH,z) = (A1 + A2/cos z) + (B1 + B2/cos z)·NGH + (C1 + C2/cos z)·NGH²`. The three-term
>    `A+B·Kt+C·Kt²` cannot express it, so in SEDES1 the zenith dependence is absorbed into A/B/C.
> 2. **The independent variable is NGH, not $K_t$** (Eq. 2-43): measured broadband global horizontal over the
>    **estimated clear-sky** global horizontal. `cloud_modifier.clearness_index` divides by the
>    **extraterrestrial** horizontal instead. Under clear sky NGH → 1 while $K_t$ → ~0.7 — not interchangeable
>    even approximately. `Sedes2Modifier.apply` therefore **refuses to run** without a `clear_ghi` reference
>    (and where `cos z ≤ 0.05`, since 1/cos z diverges), falling back to a grey unity CCM rather than silently
>    evaluating the polynomial on the wrong variable.
>
> ⚠️ The 1040 nm and 1050 nm rows are **byte-identical in Table 2-1** — verified present in the source PDF,
> not a transcription artefact; the terminal 10 nm carries no independent information.
>
> *Status: **opt-in by construction**. Nothing in `src/` constructs it (verified by grep: the only occurrences
> are the class definition, its `sedes2_coeffs` import, and a cross-reference in `_sedes1_data.py`), and every
> published figure computed with the SEDES1 default remains **byte-identical**. ⚠️ **It is not reachable over MCP** — `server.py`'s
> `_build_modifier` accepts only `reanchored`/`verbatim`/`seed`/`local`, all of which construct a
> `Sedes1Modifier`; SEDES2 is a library-level opt-in that a caller must construct directly.
> That is deliberate — adopting SEDES2 changes overcast colour and **requires a re-run before any overcast
> number is re-quoted**. It is **not validated**: no overcast figure in
> these docs has been recomputed under it.*
>
> **What it does and does not retire of D-11…D-13.** It retires the *digitisation* uncertainty (D-10) and
> gives the zenith dependence D-13 notes the quadratic cannot carry. It does **not** retire D-11
> (global-fit-applied-to-diffuse) — ⚠️ indeed it **strengthens** it: the SEDES station measured on a **48°
> south-tilted plane**, so the fit is to *tilted*-global. Nor does it retire the Germany-only caveat: Nann &
> Riordan measured at four sites, but p. 448 states data from the **German site** were used to develop the
> model, so the *fit* is German-site-only and **that caveat must not be "corrected" to say four sites**. The
> instrument was a **LI-COR LI-1800**, 10 nm step / 6 nm bandpass, ~4 % stated absolute uncertainty
> over 400–1000 nm.

**D-11 — CCM is fit by the paper to GLOBAL spectra but applied here to the DIFFUSE component.**

> **Source:** Nann & Riordan 1991, *Solar spectral irradiance under clear and cloudy skies: Measurements and a semiempirical model*, J. Appl. Meteorol. **30**(4):447, Eq. 10 (`CCM(λ,Kt)` fit to global-horizontal spectral ratios, §4). Deviation: the paper fits CCM to global-horizontal spectra; as-built applies it to the *diffuse* component only, then renormalizes diffuse to DHI — a modeling scope choice not validated in the paper.
> Nann & Riordan fit `CCM(λ,Kt)` to *global*-horizontal spectral ratios (Eq. 10); as-built applies it to the
> *diffuse* spectrum, then renormalizes diffuse to DHI. This slightly **over-weights cloud blueing** (the global
> ratio is diluted by the less-blue direct beam) and is **not validated by the paper** — a v1 modeling choice.
> It is disclosed in `Sedes1Modifier`'s docstring and in provenance as `ccm_basis="fig11-faithful"` (the retired
> seed emitted `ccm_basis="global-fit->diffuse(approx)"`). *Status: intentional, provenance-flagged; the always-on
> energy-rescale bounds the error to DHI.*

**Resolved:** faithful Fig. 11 coefficients digitized and shipped as default; provenance in `docs/Coefficient provenance/`.

**D-12 — PWV is omitted from the CCM shape term (Kt is the sole shape driver).**

> **Source:** Nann & Riordan 1991, *Solar spectral irradiance under clear and cloudy skies: Measurements and a semiempirical model*, J. Appl. Meteorol. **30**(4):447, §4 (precipitable water as a secondary SEDES1 input, dominant absorption band ~940 nm). Deviation: the PWV term is omitted from the diffuse reshape because its ~940 nm signature falls outside the 380–780 nm record window; PWV still enters the clear-sky engine via `atm.pw_cm` (M-18, Bird & Riordan 1986 `T_w` transmittance).
> SEDES1 takes precipitable water as a genuine input, but its dominant spectral signature (~940 nm) lies **outside
> the 380–780 nm record**, so v1 drives the diffuse reshape from Kt only. PWV still enters the **clear-sky baseline**
> via the engine (`atm.pw_cm`). *Status: intentional v1 scope, documented in the `Sedes1Modifier` docstring.*

**D-13 — `NIR_FACTOR = 1.0` was exported but unused (dead constant) — RESOLVED (constant deleted).**
`_sedes1_data` formerly exported `NIR_FACTOR` as the grey 1100–4000 nm estimate, but `ccm_coeffs` instead **clamps
to the last grid endpoint** past 1100 nm and never multiplied by it. Because the value was 1.0, the clamp was
numerically identical, and the 380–780 record never reaches that range anyway. **Resolved:** the dead constant was
removed from the module; `ccm_coeffs` now passes through `(1.0, 0.0, 0.0)` outside 330–1100 nm. Re-derive and wire
in a real NIR factor only if one is ever derived.

**D-14 — CCM caveat strings on the persisted record — RESOLVED in Phase 5 (Decision A).**
Through Phase 4 `build_record`'s day-branch provenance copied only `k_dir, k_dif, clear_dni_bb, clear_dhi_bb` from
the modifier `info`, dropping `ccm_basis`/`coeff_method`/`ccm_applied` (verbatim from the plan's Task-6 code). The
§8 decision (deferred from Phase 3, user decision 2026-06-18) was taken in Phase 5: **Decision A — propagate onto
the record.** `build_record` now copies `ccm_basis`, `coeff_method`, `ccm_applied` into the day-branch `prov` via
`info.get(...)` (defensive — a modifier omitting them yields `None`, not a `KeyError`), and the night branch
carries `ccm_applied=False` for schema symmetry (no strings — no CCM at night). Two tests assert the exact caveat
strings ride on a day record (real `Sedes1Modifier`) and that night carries `ccm_applied=False` without the
strings. Pure additive metadata — no number changes. *Status: **CLOSED** (§3.19). Every persisted/emitted record —
including `record_to_dict` and the MCP `spectral_sky_from_epw` output — is now self-describing about the
global→diffuse approximation (D-11) and figure-digitized coefficients (D-10).*

**D-15 — "Degrade to grey (CCM=1.0)" is honored by composition, not a dedicated guard.**

> **Source:** Nann & Riordan 1991, *Solar spectral irradiance under clear and cloudy skies: Measurements and a semiempirical model*, J. Appl. Meteorol. **30**(4):447, Eq. 11 (`CCM(λ,Kt) = A + B·Kt + C·Kt²`; at clear Kt≈1 the CCM is ~unity, i.e. grey). The grey fallback (CCM→1.0) is physically justified as the clear-sky limiting case of the SEDES1 quadratic; the implementation achieves this through coefficient clamping at grid endpoints rather than an explicit guard.
> Spec §13 requires that if Kt or coefficients are unavailable the CCM falls back to 1.0 (grey cloud), with the
> energy-rescale still guaranteeing broadband correctness. As originally built there was **no explicit `kt is None → 1.0`
> branch** in `Sedes1Modifier.apply`; instead the fallback was satisfied by composition — the night branch zeroes
> the record before any CCM call, `ccm_coeffs` clamps to endpoints (≈unity at clear Kt) outside the grid, and the
> energy-rescale always runs. A caller passing a garbage daytime `kt` got the quadratic's value, not a forced 1.0.
> *Originally the constraint was met only in practice; the dedicated grey-fallback guard + test has since been added
> (see below). The SKYSPECTRA validation slot (`tests/test_skyspectra.py`) is the capability-gated Phase-6 hook.*

**Resolved:** `Sedes1Modifier.apply` now has an explicit `kt is None → CCM ≡ 1.0` grey-fallback branch (energy-rescale only, diffuse keeps clear-sky shape, `ccm_applied=False`, `ccm_basis="grey-fallback"`) instead of crashing on `kt=None`. Test `tests/test_cloud_modifier.py::test_sedes1_grey_fallback_when_kt_is_none`.

**D-16 — Track A/B ready the `sun_spd` seam + offline artifact path, but do NOT wire the live annual/`colored_sky`
DDS transport (now re-targeted to Phase 6).**

> **Source:** Bird & Riordan 1986, Eq. 2-1 (M-19 direct-normal per-timestep spectra) + Subramaniam 2017 2-phase DDS (`E_annual = D_sky·S_sky + D_sun·S_sun`, H-30). The seam (`sun_spd` injection into `reconstruct_spectrum`) replaces the constant-zenith template with a per-timestep M-19 spectrum; the DDS transport invariant (bin totals from Radiance, shapes from the record) is preserved by `_shape_within_bins`.
> Phase 4 threads `sun_spd` through the pure-Python
> `reconstruct_spectrum` → `assemble_nvrd_rows`; **Phase 5 adds the full offline EPW→record→artifact/MCP path**
> (`record_from_epw`/`annual_records`, the four emitters, the three tools). But **no live DDS transport path passes
> physics yet**: `hcl_radiance/annual_nvrd.py` still calls `assemble_nvrd_rows` *without* `sun_spd`, the MCP
> `colored_sky` tool gains no `engine=`/`to_channels` wiring, and the live annual loop does not call
> `record_from_epw`. The new Phase-5 tools (`spectral_sky_from_epw`, `spectral_epw`, `atmosphere_from_epw`) are a
> **standalone offline pipeline**, not a hook into the capability-gated Daysim/DDS transport. This is the spec §12
> scope boundary and matches the plan's Self-Review (which explicitly defers the live `colored_sky`/annual DDS wiring
> to a later phase). *Status: **DOWNGRADED by the Live-DDS physical-sky flip (§3septies), NOT closed.**
> `annual_nvrd` now wires the physical per-timestep record into the live enhanced reconstruction via
> `sky_spd_series`/`sun_spd_series` — but **opt-in** (`physical_sky=False` default). *(At time of writing: no
> Daysim/Radiance here; the production `_build_record_index` path is unit-tested only via a monkeypatched
> `record_from_epw`. **Update 2026-07-18:** the flip has since had its first live execution — `office_room` +
> GRC Athens IWEC, real Daysim `ds_shortterm` + Radiance 6.1a, 50.03% physical coverage, time-resolved sun; a
> first live execution, not a calibrated baseline against measured sky spectra.)* The MCP `colored_sky` single-timestep tool is still un-wired for `engine=`/`to_channels` (deliberately out of scope) — **but its solar-position half was closed 2026-07-21 (D-27, §3novies)** after that seam was found to be silently mis-aligning the spectrum and the traced sky by 7.5°. So the
> nvRD live path CAN now run physics on request; full closure waits on flipping the
> default. Real and disclosed.*

**D-17 — The `solar_zenith=30.0` template is still the live default; Phases 4–5 make physics *available*, not the
live default.**

> **Source:** Bird & Riordan 1986, *Simple solar spectral model for direct and diffuse irradiance on horizontal and tilted planes at the earth's surface for cloudless atmospheres*, J. Climate Appl. Meteorol. **25**(1):87, Eq. 2-1 (`I_dλ = H₀λ·R_v·T_r·T_o·T_w·T_u·T_a` — direct-normal irradiance, M-19). The air-mass template (`solar_spd_for_zenith(30°)`) is a constant-zenith approximation to the Beer–Lambert beam-transmittance spectrum; the `physical_sky=True` opt-in replaces it with the per-timestep SPECTRL2 result at the true solar zenith from `solpos.compute` (M-4, Cooper 1969).
> **Grounding gap:** The constant `solar_zenith=30.0` fallback has no published derivation; treat as implementation lineage. Absolute spectral shape is biased toward a fixed 30° air-mass solar reference regardless of the actual hour; circadian ratios (mel-DER) are less sensitive than absolute mel-EDI.
> The spec's "kill the 30° fallback" goal is delivered **on the reconstruct side as an opt-in** and
> **offline as a full record/artifact pipeline**: with `sun_spd=None` (the live default) the air-mass
> `solar_spd_for_zenith(30° if solar_zenith is None)` template still fires, bit-identically to before. A physical sun
> reference replaces it when a caller passes `sun_spd` (directly, via `reconstruct_from_record`, or via the MCP
> passthrough), and Phase 5 can now produce physical records/artifacts straight from an EPW. Making the physical sun
> the *default in the live 8760-hour DDS path* depends on D-16's transport wiring. **The Live-DDS physical-sky flip
> (§3septies) adds that wiring for the nvRD enhanced path** — `physical_sky=True` feeds the record's direct spectrum
> as the per-timestep sun (replacing the 30° template for covered steps; under partial coverage the
> `enhanced_solar_note` now names only the template-fallback steps). *Status: **DOWNGRADED by §3septies, NOT closed**
> — physics is reachable in the live nvRD path on request, but the default stays template and the live path is not yet
> validated. The live-default flip + a real Daysim/Radiance run remain the closure conditions.*

**D-18 — `_shape_within_bins`' zero-guard inspects the bin *sum*, so a mixed-sign reference could emit negatives
(pre-existing, not reachable here).**

> **Source:** Bird & Riordan 1986, *Simple solar spectral model for direct and diffuse irradiance on horizontal and tilted planes at the earth's surface for cloudless atmospheres*, J. Climate Appl. Meteorol. **25**(1):87, §3 (bin-energy invariant: the spectral shape of a channel is redistributed while its broadband integral is conserved). The per-bin energy-conservation invariant the reshaping helper implements is physically motivated by the need to preserve channel totals from Radiance transport; the zero-sum guard is a numerical implementation choice, not a literature requirement.
> As originally built, the reshaping helper fell back to flat only when a bin's reference *sums*
> to ≤ 0; a mixed-sign reference with a small positive bin-sum could in principle produce negative per-nm values.
> This code **pre-dated Phase 4 and was unchanged by it**, and no physical SPD path (engine output, EPW-derived
> record, or air-mass template) produces mixed-sign references, so it was unreachable in practice. *Originally
> pre-existing and out-of-Phase-4-scope; flagged by the independent correctness review as a latent hardening target
> (not a Phase-4 regression), and since hardened — see below.*

**Resolved:** `_shape_within_bins` now clamps the reference shape to non-negative before normalizing, so a mixed-sign reference can never leak negative per-nm irradiance (bin totals still preserved). Test `tests/test_spectral_reconstruct.py::test_shape_within_bins_never_emits_negatives_for_mixed_sign_reference`.

**D-19 — ~~The SMARTS deck/parse/`compute` paths are correct-by-construction but NOT live-validated.~~ FIRST
LIVE VALIDATION 2026-06-21.**

> **Update 2026-06-21.** SMARTS was compiled from the NREL SMARTS 2.9.5 Fortran source
> (that distribution's Mac binary is dead PowerPC) to a native arm64 `smarts295bat` — `batch=.TRUE.`, CRLF stripped,
> `gfortran -std=legacy`. With `$SMARTSPATH` set, the full `build_deck` →
> symlinked-data-tree `compute` → `parse_ext_output` flow **runs live** and the gated cross-check
> `test_smarts_cross_check_clear_sky` **passes** (was a skip). A live three-way comparison
> (`docs/spectral-engine-comparison.md`) shows SMARTS agreeing with the Python SPECTRL2 engine to ~2 % direct
> / ~7 % diffuse at r≈0.99 on a clear Athens hour. **This is a first validation, not a calibrated baseline:**
> the deck/parse plumbing and loose agreement with SPECTRL2 are confirmed, but SMARTS is *not* yet checked
> against measured sky spectra, and the bundled `Examples 1/6/11` deck cross-check the plan claimed was still
> not reproduced (only the SPECTRL2 cross-check was). The original (pre-validation) text follows.

The SMARTS deck/parse/`compute` paths are correct-by-construction; the bundled verification reference (Examples)
was claimed-but-not-reproduced.

> **Source:** Gueymard 2019, *The SMARTS spectral irradiance model after 25 years*, Sol. Energy **187**:233 (+ SMARTS 2.9.5 manual). The `build_deck` card map encodes the SMARTS 2.9.5 card format (29 non-blank lines under the default `rural` aerosol); IOUT `1 2 3` selects direct-normal (col 2) and diffuse-horizontal (col 3) per the SMARTS documentation.
> `build_deck`/`parse_ext_output` are fully unit-tested and the deck
> is internally consistent with the documented SMARTS 2.9.5 card map, but **no live `smarts295bat` run has happened**
> (capability-gated on `$SMARTSPATH`). The plan's "verified the card sequence + IOUT `1 2 3` against the bundled
> bundled SMARTS worked Examples 1/6/11" are **not reproducible in this tree** — that distribution is not part of this repo.
> So the deck format, the symlinked-data-tree `compute` flow, and the µm output are trusted on construction +
> unit-tests, not on a SMARTS execution. *Status: intentional capability-gating ("green pytest ≠ live SMARTS run",
> stated in the module docstring); deck-vs-binary validation is the on-install step. The post-execution correctness
> pass additionally caught that the cross-check test was a **fail-red placeholder** and replaced it with a real gated
> cross-check (§3.23, §5).*

**D-20 — Ångström α is not a free SMARTS input; only AOD500 magnitude is set — RESOLVED (opt-in).**

> **Source:** Gueymard 2019 / SMARTS 2.9.5 manual (ITURB=0 selects TAU5 — aerosol optical depth at 500 nm; aerosol spectral shape is determined by the named aerosol model, here `S&F_RURAL`). Deviation: the SPECTRL2 engine accepts `atm.angstrom_alpha` directly (Bird & Riordan 1986, Eq. 2-7); SMARTS derives α from its `S&F_RURAL` aerosol model instead — a model-fidelity difference between the two independent implementations.
> SMARTS derives the aerosol spectral
> slope from its aerosol *model* (`S&F_RURAL`), so `build_deck` sets only TAU5 = `atm.aod500` (ITURB=0) and cannot pass
> `atm.angstrom_alpha`. The SMARTS oracle therefore uses the S&F_RURAL α, while the SPECTRL2 engine uses
> `atm.angstrom_alpha` directly — a documented model-fidelity difference between the two engines, not an error.
> *Status (historical): intentional — inherent to the SMARTS aerosol-model API; disclosed in the `build_deck`
> docstring.*

**Resolved (opt-in); default unchanged (byte-identical).** `build_deck(atm, geo, *, aerosol="rural")` still
defaults to `aerosol="rural"` — same `'S&F_RURAL' !Card 8 AEROS` line, same 29-line deck, byte-identical to
before. `aerosol="user"` (the `smarts_aerosol` MCP tool arg on `spectral_sky_from_epw`/`spectral_epw`, threaded
via `SmartsEngine(aerosol=...)` → `resolve_engine(name, *, smarts_aerosol=None)`) instead emits
`AEROS='USER'` (Card 8) plus a new Card 8a (`ALPHA1 ALPHA2 OMEGL GG` = `atm.angstrom_alpha atm.angstrom_alpha
0.95 atm.aerosol_g`, a 30-line deck), making both the Ångström exponent and the asymmetry factor free SMARTS
inputs. `atmosphere_from_epw` is untouched (no engine involved). A live smoke check (SMARTSPATH set, not a
persisted test) at α=0.5 vs α=2.0 (same atmosphere) showed the expected monotonic direct-normal sensitivity
(≈5% ratio spread), with the fixed `S&F_RURAL` model landing between the two `user` bounds — confirming Card
8a is actually consumed by the binary, not just generated. Test coverage:
`tests/test_smarts_deck.py::test_deck_default_is_rural` (byte-identical default) and
`test_deck_user_sets_alpha_and_g`. *Status: **RESOLVED**, opt-in refinement — default path untouched.*

**D-21 — `SmartsEngine.compute` accepts `tilt_deg`/`cos_incidence` but ignores them (deck hardcodes ITILT=0).**

> **Source:** Gueymard 2019 / SMARTS 2.9.5 manual (ITILT=0 selects horizontal receiver: direct-normal + diffuse-horizontal outputs). The `SpectralEngine` Protocol (§3.4) defines `tilt_deg`/`cos_incidence` for conformance; receiver-plane transposition is owned by Radiance (spec §6), not the spectral engine.
> The parameters exist for `SpectralEngine`-Protocol conformance; the deck is always built for a horizontal receiver
> (direct-normal + diffuse-horizontal). A caller passing `tilt_deg=30` gets a horizontal result with no warning —
> matching the Phase-2 `Spectrl2Engine` production convention (tilt is a golden-only path there too, **D-8**). *Status:
> intentional v1 scope (Radiance owns receiver-plane transposition, spec §6); a SMARTS tilt deck is a later seam.*

**D-22 — `compare_engines` is direct-normal-bounded; spectral diffuse is sanity-only; SKYSPECTRA comparison is a
gated on-download stub.**

> **Source (direct-normal bound):** Bird & Riordan 1986, *Simple solar spectral model for direct and diffuse irradiance on horizontal and tilted planes at the earth's surface for cloudless atmospheres*, J. Climate Appl. Meteorol. **25**(1):87, Eq. 2-1 (Beer–Lambert direct-normal, M-19). Both SPECTRL2 and SMARTS implement Beer–Lambert beam transmittance independently; the 35% cross-engine envelope reflects documented inter-model scatter on direct-normal (both are physics-based, grounded in the same Beer–Lambert framework but with different coefficient sets).
> **Source (diffuse, sanity-only):** Bird & Riordan 1986, Eq. 3-1 (sky-diffuse, M-23) vs SMARTS diffuse (Gueymard 2019). Spectral diffuse between two independent models genuinely diverges far more (different single-scatter/multi-reflection treatments; SMARTS reports *pure* diffuse), so it is only checked finite/positive, not bounded — a tight bound would flake on real hardware.
> Separately, the SKYSPECTRA harness (`tests/test_skyspectra.py`) is the documented **on-download wiring point**:
> its live-streaming test (`test_full_horizontal_streams_frvlx`) sits behind
> `skipif(not os.path.exists(tests/fixtures/skyspectra/raw/spectral_horizontal_irradiance.csv))` and never executes
> without the (multi-GB, not-in-repo) dataset; the in-repo unit tests instead validate the reader against committed
> synthetic fixtures. (The earlier `test_reconstructed_mel_edi_within_envelope` mel-EDI placeholder was dropped in
> favor of these license-clean fixtures.) *Status: intentional — the honest gated treatment of binary/dataset-dependent
> validation; both are real harnesses awaiting their inputs, not silent placeholders.*

**D-23 — The physical-sky hour-mapping is enclosing-hour (no sub-hourly interpolation), and the `.wea` timestamp
convention is an unverified assumption.**

> **Source:** Cooper 1969 / Kasten & Young 1989 (solar geometry, M-1…M-8: the per-timestep spectral record is computed at mid-interval `hour − 0.5`). The enclosing-hour ceiling mapping `H = min(24, max(1, ceil(h_frac)))` is an implementation choice to pair Daysim sub-hourly transport steps with EPW-hourly records; it has no separate literature basis. The `.wea` hour convention is an assumed match to the EPW hour-ending — unverified against the Daysim `ds_shortterm` decomposition (Skartveit & Olseth 1992 / Walkenhorst 2002; model realized in Daysim).
> Each sub-hourly transport timestep `(m,d,h_frac)` maps to its EPW
> hour-ending `H = min(24, max(1, ceil(h_frac)))` — the hourly record's shape is reused across the ~6-min sub-steps in
> that hour; no interpolation between hours. The rule assumes the `.wea` `hour` is a **clock hour** (so `ceil` lands on
> the EPW hour-ending), which has **never been verified live** (no Daysim build in this tree). A wrong convention
> shifts each step's *shape* by at most one hour (energy unaffected — shape-only) and shows up as **lower coverage** if
> lookups miss, so it is detectable. The production `_build_record_index` glue is unit-tested only via a monkeypatched
> `record_from_epw` (no EPW in-repo). *Status: intentional v1 scope (enclosing-hour) + a documented assumption to
> verify against the real weather-decompose output before a live run is trusted (spec §4 Finding 4).*

**D-24 — The single-timestep `divergence` under `physical_sky` uses the physical sky but the TEMPLATE sun.**

> **Source:** Amundadottir 2016 EPFL thesis (nvRD model, H-13…H-19: R_D is a nonlinear sigmoid of effective ipRGC irradiance). nvRD model from Amundadottir et al. 2016/2017 journal versions; the EPFL thesis (full constant derivations) was not obtained as a primary source. The `divergence` proxy is a reporting metric, not a radiometric model; the physics-aware delta is `RD_series_divergence` (the actual enhanced-vs-faithful R_D series from the full nvRD sigmoid). The template-sun bias in the single-timestep proxy is tolerable because `RD_series_divergence` captures the full effect.
> `reconstruction_divergence` has a `sky_spd` parameter but **no `sun_spd`**, so when `physical_sky=True` the
> representative-timestep `divergence` proxy reshapes the sky with the physical record but leaves the sun on the
> air-mass template. The physics-aware number is `RD_series_divergence` (computed from the actual enhanced-vs-faithful
> R_D series); a `divergence_note` discloses the proxy's limitation. *Status: intentional — chosen over widening the
> `reconstruction_divergence` API (spec review Finding 2, user decision); disclosed in `divergence_note`.*

**D-25 — Two Phase-7 plan claims about `gensdaymtx` were WRONG and corrected against the bundled source.**

> **Source:** Perez et al. 1993 all-weather sky (embedded in Radiance `gensdaymtx`); OPAC continental aerosol spectral shape. Perez 1993 sky model; OPAC continental aerosol (standard reference climatology) — both realized inside Radiance 6.1a. The corrections below were verified directly against the upstream Radiance 6.x source — the authoritative ground truth when man pages and usage strings disagree.
> **Note:** both erroneous plan claims (`-g r g b` and `WAVELENGTH_SPLITS` as band edges) came from reading stale documentation rather than the source; the upstream Radiance 6.x source is the authoritative reference (it was in-tree when this check ran; since the 2026-08-10 reorg the checkout lives outside this published repo).
> The Phase-7 *plan* specified gensdaymtx's `-g` as `-g r g b` (three args) and the matrix header's `WAVELENGTH_SPLITS`
> as the 20-band edge list. The final whole-branch review checked both against the upstream Radiance 6.x source
> and found: (1) `-g` is a **single scalar** (`grefl = atof(argv[++i])`, `gen/gensdaymtx.c:647`); (2)
> `WAVELENGTH_SPLITS` is the **4-value RGB partition `{780,588,480,380}`** (`fputwlsplit` prints four `%g`,
> `color.h:321`; `color.c:94`), unrelated to the 20 spectral bins (`NSSAMP=20`, uniform 380–780 @20 nm,
> `atmos.c:164/169`). Both were *faithfully implemented from the plan*, then fixed (user decision 2026-06-19):
> the builder takes a scalar (tuple → `TypeError`); `parse_smx_header`'s key is
> `rgb_partition`; `reconcile_to_native_bands` re-bins onto the NCOMP-derived uniform grid (== `band_average`,
> proven). Two same-region fixes rode along: the discriminable `run_gensdaymtx` `ok` shape and the whole-file
> header read. **Consequence for the spec:** the native grid *equals* the Phase-5 nominal grid, so the §8
> byte-compat reconciliation gap **does not exist** — design.md §8 was corrected. *Status:
> RESOLVED; both paths are gated, so neither was ever a live regression. Lesson: grep the actual Radiance source
> (in-tree at the time; outside this published repo since the 2026-08-10 reorg)
> for every flag/header claim — the man page and usage string both lie.*

**D-26 — ~~The `gensdaymtx` subprocess RUN path is correct-by-construction but NOT live-exercised (no Radiance 6.x).~~ CLOSED 2026-06-20.**

> **Source:** Perez et al. 1993 all-weather sky (embedded in `gensdaymtx`); Ward 2024 *Hyperspectral Radiance* tutorial (NCOMP=20, 20-band spectral sky matrix, 146 sky patches MF:1) (Perez 1993 sky model + Ward 2024 tutorial, realized in Radiance 6.1a). Cross-check against Python SPECTRL2 (Bird & Riordan 1986): the loose shape agreement (Pearson 0.987) is expected — different sky models, different output units (native W/sr/m² patch radiance vs Python W/m²/nm irradiance are incommensurable for absolute broadband).
> **Note (band-order):** The `.smx` body DESCENDING order (red→blue, matching the `WAVELENGTH_SPLITS = 780 588 480 380` RGB partition) is a Radiance internal convention (`fputwlsplit`, `color.h:321`); reversal to ascending 380→780 is required before any wavelength-ordered consumer — un-reversed correlation −0.70 vs reversed +0.987.
> Radiance 6.1a (2026-05-05) is installed at `/usr/local/radiance/bin`; `radiance_spectral_status()["available"]` is
> now `True`. **First live validation executed**: `run_gensdaymtx(..., run=True)` → `ran=True, ok=True`; header
> confirmed **NCOMP=20** (NROWS=146 sky patches). The gated cross-check test
> `test_native_vs_python_engine_envelope` is now **wired and passing** (was a `pytest.skip` stub) — 20-band native
> spectrum vs Python SPECTRL2 engine: per-band normalized mean ~2.5%, Pearson correlation **0.987**, mel/phot
> native 0.987 vs python 1.015, no inversion. **This is validation, not a known-good baseline**: the loose
> shape agreement is confirmed; absolute broadband is NOT asserted (native W/sr/m² patch radiance vs Python
> W/m²/nm irradiance are incommensurable). Load-bearing finding: the `.smx` body is **DESCENDING** in wavelength
> (red→blue); must be reversed (`[::-1]`) to ascending 380→780 before use — un-reversed corr −0.70 vs reversed
> +0.987. *Mirrors D-9/D-19 for SMARTS (still open), D-16 for the live DDS path (still open).*

**D-27 — Malformed/short EPW rows are skipped SILENTLY — no "logged reason", no dropped-count report (contra
spec §13 & methodology §14).**

> **Source:** EPW data format (DOE/EnergyPlus hourly climate data dictionary). The column-index map in `epw_hourly.parse_epw_hourly` implements the EPW field layout (DNI col 14, DHI col 15, etc.); the degradation behavior for malformed rows is an implementation contract, not a method in the published EPW standard. The diagnostic half (log + count) is what spec §13 adds on top.
> Both reference docs promise that malformed/short rows are *"skipped with a logged
> reason"* and that *"a run reports how many timesteps were dropped rather than failing silently"*. As originally
> built, `epw_hourly.parse_epw_hourly` simply `continue`d past any row with `< 16` comma fields or a non-integer date
> triple — **no logger call, no counter, nothing returned** about drops. The behaviour was safe (never raises, §3.1)
> and correct for well-formed EPWs, but the *diagnostic* half of the degradation contract was not implemented; this is
> **now resolved — see below**. *Originally a spec/methodology over-promise; the silent-skip was already sufficient
> for v1 (annual runs simply produce fewer records). The returned drop-count + logged reason was an additive
> hardening, since added, so the "reports how many dropped" claim in spec §13 / methodology §14 now holds.*

**Resolved:** `epw_hourly.parse_epw_hourly_diagnostics(path)` now returns `(rows, {"kept", "dropped", "reasons": {"short_row", "bad_date"}})`; each dropped row is logged with its line number + reason and a one-line summary is logged when any are dropped. `parse_epw_hourly` is a backward-compatible thin wrapper (returns the list, drops still logged). Tests in `tests/test_epw_hourly.py` (`test_diagnostics_reports_dropped_counts_by_reason`, `test_dropped_rows_are_logged_with_a_reason`, `test_parse_epw_hourly_returns_only_rows_for_backward_compat`).

**D-28 — `ghi_epw_residual` / `bridge_residuals` provenance keys and GHI-mismatch logging (spec §4/§6/§13,
methodology §10) are NOT implemented.**

> **Source:** Nann & Riordan 1991, *Solar spectral irradiance under clear and cloudy skies: Measurements and a semiempirical model*, J. Appl. Meteorol. **30**(4):447, Eq. 9 (bridge invariant: `∫direct = DNI`, `∫diffuse = DHI`; `GHI = DNI·cos z + DHI` is the EPW-closure cross-check implied by the bridge). The bridge invariant (exact, always-on, energy match to DNI/DHI) means the GHI residual is a provenance/diagnostic quantity, not a physics invariant — the absence of `ghi_epw_residual` does not affect the spectral results.
> Spec §4 lists `bridge_residuals` and `ghi_epw_residual` among the
> `SpectralSkyRecord.provenance` keys; spec §6/§13 and methodology §10 state that any mismatch between the
> DNI/DHI-derived GHI (`GHI = DNI·cos z + DHI`) and the EPW's own GHI column "is logged in provenance". As-built,
> `build_record`'s provenance carries `k_dir, k_dif, clear_dni_bb, clear_dhi_bb` (the bridge scale factors —
> arguably the *spirit* of `bridge_residuals`) but **no key named `bridge_residuals`, no `ghi_epw_residual`, and
> no GHI cross-check is ever computed or logged** (verified: not implemented anywhere). `ground_for_receiver`
> computes `GHI(λ) = direct·cos z + diffuse` for the ground term but never compares it to the EPW GHI column.
> D-1 already flagged the missing `uncertainty` field; this entry covers the remaining spec §4 provenance keys.
> *Status: intentional leanness (provenance is auditing metadata; the bridge invariant is exact regardless), but
> the GHI-residual logging is a genuine spec'd feature that is absent. Computing `ghi_epw_residual = (DNI·cos z + DHI) − GHI_epw` and storing it is a ~3-line additive change for a later phase.*

**Resolved:** `build_record` now stores `ghi_epw_residual = (DNI·cos z + DHI) − GHI_epw` and `bridge_residuals = {"direct_bb", "diffuse_bb"}` (the true post-rescale broadband closure, ~0 by construction) in provenance on both the day and night branches. Tests in `tests/test_spectral_sky.py` (`test_day_provenance_carries_ghi_epw_residual`, `test_day_provenance_carries_bridge_residuals_near_zero`, `test_night_provenance_carries_residual_keys_for_symmetry`).

**D-29 — `run_gensdaymtx` hard-coded `timeout=600` crashed on a full-year EPW; replaced with a caller-supplied
`timeout` (default `None`) + graceful `timed_out` result. FIXED 2026-06-21.**

> **Source:** Radiance `gensdaymtx` (LBNL, in Radiance 6.1a) — the native spectral sky driver; it iterates every
> hour of the weather tape, so cost scales with the EPW row count (model + tool live in
> Radiance). The fix is an MCP-layer robustness contract, not a physics change — it touches no radiometry.
> As-built (Phase 7) `run_gensdaymtx` ran the subprocess under a hard-coded `timeout=600`. `gensdaymtx`
> **always processes the whole EPW** (8760 rows × NCOMP=20); a `mf=1` year is actually fast (**~12 s** on the
> Athens IWEC EPW, re-measured 2026-06-29), but at higher `mf` or under CPU contention it exceeded 600 s, so
> `subprocess.run` **raised `TimeoutExpired`, which propagated out and crashed the `spectral_sky_native` MCP
> call** (found during a live end-to-end run, 2026-06-21). *(The earlier "`>12 min` at `mf=1`" figure was wrong —
> mf=1 is ~12 s; the many-minutes cost is a high-`mf` regime.)* Fix: `timeout` is
> now a caller-supplied parameter on both `run_gensdaymtx` and the `spectral_sky_native` tool, **default `None` (no
> cap)** so a real annual run completes; an explicit `timeout` is caught and returned as the discriminable
> `{ran:True, ok:False, timed_out:True, error, smx}` dict (never raises). 3 unit tests lock it (default forwards
> `None`; explicit value forwarded; `TimeoutExpired` → graceful dict). Verified live: trimmed 1-day EPW →
> `ran=True, ok=True, NCOMP=20`; full-year + `timeout=1` → graceful `timed_out=True`. *Status: RESOLVED. The live
> cross-check test (§3.29) sidesteps the cost by trimming the EPW to one day; only the un-trimmed annual run
> hit the cap. Lesson: a tool whose cost scales with input size must not carry a fixed internal timeout.*

**Alignments worth stating (NOT deviations).** Two choices that look like divergences are explicitly sanctioned
by the methodology: (a) the **C-vs-Fortran constant drift** (Rayleigh `1.3366` not `1.335`; uniform-gas `118.3`
not `118.93`) is kept verbatim — methodology §7 documents these as <0.1% and "not to be fixed"; (b) **gray ground
albedo** (single `atm.albedo` for all six SPECTRL2 reflectivity bands) is the methodology §7 v1 choice, and since
the golden TAPE1 sets all six bands to 0.2, the gray path reproduces the reference exactly.

**No behavioural deviations in the computed numbers.** Every implemented equation (Phase 1: M-1…M-6, M-8,
M-12, M-13; Phase 2: M-9, M-11, M-14…M-24, M-30; Phase 3: SEDES1 Eqs. 6, 9–11) matches its cited source; the
SPECTRL2 constants are byte-for-byte the C `spectrl2_2.c` values; the golden TAPE reference is reproduced in the
visible to <0.05% (direct) / <0.01% (diffuse); the Phase-3 bridge invariant is exact to FP precision. The
Phase-3 deviations above (D-10…D-15) are **modeling-scope and provenance-plumbing** choices (figure-digitized
coefficients, CCM-on-diffuse, PWV-omission, the **now-resolved** D-14 caveat-propagation decision) — not
arithmetic errors. **Phase 4 changes no computed number on any existing path**: it is a pure additive seam
(D-16…D-18 are scope-boundary and default-sequencing choices, plus one pre-existing latent edge), and
`reconstruct_spectrum` with no `sun_spd` reproduces the prior template output bit-for-bit (test-locked).
**Phase 5 changes no computed spectrum either**: `record_from_epw`/`annual_records` only *orchestrate* the
already-verified Phase 1–3 chain (mid-interval hour + `i0_normal=1361·ERV` feeding the unchanged `build_record`);
the four emitters are thin re-serializations of the canonical record; and the D-14 closure adds only audit-metadata
keys. The one Phase-5-touched number path is provenance metadata, not radiometry. **Phase 6 changes no existing
computed path at all**: it rewrites the SMARTS *scaffold* (previously a `raise`) and adds a new validation module +
gated tests, both consumed only by tests and opt-in callers. The Phase-6 deviations (D-19…D-22) are
capability-gating and model-fidelity disclosures (no live SMARTS run; α from the aerosol model; direct-bounded
cross-check; gated SKYSPECTRA) — not arithmetic in any shipped default path. The `compare_engines` percentage
formula, the deck card map, and the µm×1000 conversion were each verified by execution in the post-Phase-6
correctness pass (§5). **The Live-DDS physical-sky flip changes no DEFAULT computed path**: `physical_sky=False` is
bit-identical (test-locked), the faithful baseline never receives the series, and when `physical_sky=True` the record
enters only as a *reshaping shape* — `_shape_within_bins` preserves each bin's transport total, so a physical SPD
moves the spectral shape but conserves total energy to ~5.5e-17 (verified by execution). Its deviations (D-16/D-17
downgraded; D-23/D-24) are scope/assumption disclosures, not arithmetic errors. **Phase 7 changes no Python
computed path at all**: `spectral_native` is a *parallel* engine that shells out to (or emits the plan for)
Radiance's `gensdaymtx` — it touches none of the SPECTRL2/SEDES1 radiometry. Its deviations are a source-verified
plan correction (D-25 — the native band grid turns out to equal the Phase-5 nominal grid, closing rather than
opening a gap) and a capability-gating disclosure (D-26 — the run path was unexercised without Radiance 6.x; **now first live-validated 2026-06-20 under Radiance 6.1a, NCOMP=20, Pearson 0.987 — D-26 closed**).

---

## 5. Verification evidence

**Automated tests — Phase 1:** `tests/test_solpos.py` (8), `tests/test_epw_hourly.py` (5, incl. the
coverage-gap additions for `opaque_sky_cover`/radiation/`dry_bulb` sentinels), `tests/test_atmosphere.py`
(10, incl. pinned-value PW anchor + `pw_cm` override path).

**Automated tests — Phase 2:** `tests/test_spectral_engine_base.py` (3, incl. frozen-contract),
`tests/test_spectrl2_data.py` (3, table anchors), `tests/test_spectrl2.py` (5, golden + Rayleigh-lock +
night-zeros), `tests/test_spectral_sky.py` (5, resampler + frozen + single-point clamp),
`tests/test_smarts.py` (2 + 1 capability-gated skip).

**Automated tests — Phase 3:** `tests/test_cloud_modifier.py` (10: Kt basics/clamp/night, trapezoid integral,
energy-normalize match + zero-safe, Protocol/isinstance, bridge-invariant preservation, diffuse-bluer-under-cloud),
`tests/test_sedes1_data.py` (4: array alignment, Fig-11 `B<−2.5` cross-check, neutral-at-clear-Kt, blue-enhanced-
at-overcast-Kt), `tests/test_spectral_sky.py` (+6: ground zeros@tilt0 + half-hemisphere@tilt90, build_record clear
end-to-end + night-zeroed, twilight-edge `night_but_epw_nonzero=True`, full day-provenance keys),
`tests/test_skyspectra.py` (1 pass + 1 capability-gated skip). **The full suite is green**
(the Phase-3 module tests run with zero warnings). *(The skip inventory once given here — "3 pre-existing
third-party opentelemetry/colour-science + SMARTS cross-check + SKYSPECTRA" — is stale: no third-party
skips remain, and the SMARTS cross-check now runs live. The current measured set is enumerated in §1.)*

**Automated tests — Phase 4:** `tests/test_spectral_reconstruct.py` (+4: `sun_spd=None` backward-compat lock,
sun_spd injection + per-bin energy invariant, `_sun_reference_spd` length-validation, `assemble_nvrd_rows`
sun_spd cascade), `tests/test_spectral_emit.py` (6: `record_to_spd_dict`, `to_channels` 9-bin + 3-bin r,g,b
order, `to_reference` 401-length, `reconstruct_from_record` equivalence + differs-from-template),
`tests/test_server.py` (+1: MCP `sun_spd` passthrough changes the spectrum). **Full suite green after Phase 4**
(the 11 Phase-4 unit tests added; no new skips).

**Automated tests — Phase 5:** `tests/test_spectral_pipeline.py` (5: `record_from_epw` clear-noon shape +
provenance + mid-interval, missing-row `ValueError`, overrides applied; `annual_records` one-per-row + `hours`
subset), `tests/test_spectral_emit.py` (+6: `record_to_dict` shape, `emit_spd_set` CSV structure + ground column,
`BAND_EDGES_20`/`band_average`, `emit_band_matrix` row shape, `emit_spectral_wea` + sidecar widths),
`tests/test_server.py` (+3: `atmosphere_from_epw`, `spectral_sky_from_epw` with/without `ground`, `spectral_epw`
writes artifacts to disk), `tests/test_spectral_sky.py` (+2: D-14 — day record carries the exact CCM caveat
strings + `ccm_applied=True`; night record carries `ccm_applied=False` and not the strings). **Full suite green**
(the 16 Phase-5 unit tests added; no new skips).

**Independent numerical spot-checks — Phase 1 (re-derived from the cited sources, not from the code):**

- Zenith parity vs `weather.solar_zenith`: **max abs error 0.0** over 5 sites/dates.
- Air mass (Kasten-Young): 0°→1.000, 60°→1.994, 85°→10.306; `inf` for `z ≥ 90°`.
- Earth-radius-vector (Spencer): full-year range 0.9666–1.0351; perihelion (day 3) > aphelion (day 185).
- Azimuth (N=0 clockwise): morning/noon/afternoon = 121°/177°/235°, strictly increasing E→S→W.
- Gueymard94 = explicit pvlib formula to machine precision; Reitan63 = `exp(a+b·Td)` exactly.
- `derive` provenance: full row→`gueymard94`, dew-only→`reitan63`, empty→`fixed` (1.5 cm); defaults fire
  when EPW fields missing; overrides tagged `source="override"`.

**Independent verification — Phase 2 (engine port):**

- **Line-by-line C transcription audit:** every transmittance, the forward-scatter block, the diffuse
  decomposition (M-22), the `C_s` branch, and the tilt block checked against `spectrl2_2.c`; all C constants
  (1.3366, 118.3, 0.2385/20.07, 0.4293/36.126, 2.538/212.94, 1.41, ω₀=0.945, ω'=0.095, g=0.65) confirmed
  verbatim. The `units==1` branch (`spectrl2_2.c:109–113`) emits `dir`/`dif` with **no** photon-flux scaling.
- **Golden gate (`SPCTRAL2_OUTPUT.txt`, tilt=40° TAPE case):** the port reproduces the Fortran direct column
  to **<0.05%** and diffuse to **<0.01%** in the visible (test asserts the looser <0.5%/<1%). Exact
  Rayleigh-constant lock `Tr(0.5µm, Amp=4.471)=0.52281` passes independently. Night (z=95°) → all-zeros.
- **End-to-end smoke through the real Phase-1 modules** (`solpos.compute` + `atmosphere.derive`, not test
  stand-ins): all 8 consumed attributes resolve; engine emits 122 pts; resampler narrows to 401 @1nm with
  finite, non-negative output. High sun (z=16.5°, AM≈1): **DNI peak 1.546 W/m²/nm @ 480nm** — matches the
  canonical clear-sky AM1 solar spectrum. Low sun (z=80.6°): DNI correctly reddened (0.089→0.745, 400→780nm);
  DHI correctly blue-dominated (peaks ~500nm) — both as Rayleigh λ⁻⁴ extinction/scattering predict.

**Independent verification — Phase 3 (cloud bridge + orchestrator), re-computed from the cited sources:**

- **Bridge invariant, end-to-end through `build_record`** (independent of the unit tests): clear hour
  direct ∫ = 800.000 / diffuse ∫ = 120.000; overcast Kt=0.25 (heavy CCM reshape) direct ∫ = 200.000 /
  diffuse ∫ = 180.000. Exact and always-on, on the full 300–4000 nm native range **before** resampling. Direct
  is the pure grey-scaled clear-sky shape (`direct == clear·k_dir` to 1e-9); CCM touches diffuse only; the
  `max(0,ccm)` floor + diffuse renorm restore DHI even when NIR nodes clamp to zero.
- **CCM coefficient round-trip:** the 3×3 Vandermonde was re-solved independently at 400/700 nm — the committed
  A/B/C reproduce the seed R̄ at Kt={0.25,0.50,0.70} exactly; `B(400)=−3.55` matches Fig. 11; `ccm_coeffs`
  interpolation + endpoint clamps verified with no off-by-one in the bracket search.
- **Ground-glow worked example:** zenith 60°, tilt 90° → view-factor 0.5, `GHI(λ)=1·0.5+0.5=1.0`,
  `ground=1.0·0.2·0.5=0.1`; tilt 0 → all zeros. Direct projected by `cos z`, diffuse not.
- **Two independent opus review passes** (correctness + completeness) confirmed: all 7 physics areas correct by
  re-derivation (no unit/sign/off-by-one/×0.001 errors), and every planned function/signature/provenance-key/test
  delivered with no Phase 4–7 leakage and only the gated SKYSPECTRA `raise`.

**Independent verification — Phase 4 (Track A), two opus passes (correctness + completeness):**

- **Correctness — CORRECT by re-derivation:** `sun_spd=None` reproduces the air-mass template byte-for-byte; the
  bin-energy invariant holds **per-bin** (not just globally), and the `s ≤ 0` guard prevents division-by-zero on
  zero/negative-sum bins; the emitter channels are not swapped (diffuse↔sky, direct↔sun) and the `BINS_3` r,g,b
  order makes the "blue-heavy → b>r" test correct; `sun_spd` reaches the core reconstruct but is correctly kept
  out of `_recon_divergence`; every new test asserts a real, non-vacuous property (the injection test's `red_ref`
  first-bin sum is 741.0 → it exercises the shaping path, not the flat fallback).
- **Completeness — COMPLETE as-specified:** all six Track-A deliverables present (the `sun_spd` seam, the two
  emitters, `reconstruct_from_record`, the `assemble_nvrd_rows` cascade, the MCP passthrough); the spec §11 #4
  sky/sun asymmetry is **resolved symmetrically** (`sky_spd` + `sun_spd` now flow through the whole chain);
  **no Phase-5 leakage** (live annual transport, an `engine=` kwarg, and new MCP tools all correctly absent —
  D-16); the deferral is honestly disclosed. The two coverage gaps the first pass flagged were closed by the
  test-polish commit (`assemble_nvrd_rows` cascade + `reconstruct_from_record`-differs-from-template now tested
  directly).

**Independent verification — Phase 5 (Track B), executed subagent-driven with a per-task spec+quality review and a
final whole-branch review (opus):**

- **Per-task gates:** each of the five plan tasks (TDD RED→GREEN) passed an independent spec-compliance + code-quality
  review before the next was dispatched; one reviewer "Important" (a feared generator-exhaustion if `spectral_epw`
  iterates `recs` twice) was adjudicated a **false positive** — `annual_records` returns a concrete `list`, and the
  two-form (`spd_set`+`band_matrix`) test exercises the double iteration safely.
- **Final whole-branch review — READY TO MERGE:** 0 Critical, 0 Important; all open findings cosmetic or
  plan-mandated. Confirmed the binding correctness invariants in live source: mid-interval hour with EPW-hour
  timestamp; `i0_normal = 1361·ERV` decoupled from engine ETR; site from `parse_epw_location`→`solpos.compute`; thin
  emitters (no physics recompute); `band_average` partitions indices 0–400 with no gaps/overlaps; `ground` emitted
  only when `surface_tilt_deg` given; additive tool registration (35 tools, nothing dropped); night handling
  inherited from `build_record`. (35 tools was the Phase-5 count; the server now exposes 51 registered names — 47 tools + 4 aliases.) Two intent-locking comments were added (raw-float lossless SPD set; band-19
  endpoint inclusion) to prevent future "cleanups."
- **D-14 closure verified:** day record provenance carries `ccm_basis`, `coeff_method`, `ccm_applied=True`
  (`ccm_basis="fig11-faithful"`, `coeff_method="webplotdigitizer_fig11"`, plus `ccm_variant`;
  the seed-era values were `global-fit->diffuse(approx)` / `fig10_3class_solve`); night carries
  `ccm_applied=False`; defensive `info.get`.

**Independent verification — Phase 6 (SMARTS oracle + validation), executed subagent-driven with per-task
spec+quality reviews, a final whole-branch review (opus), and a post-execution live-source correctness+completeness
pass:**

- **Per-task gates:** each of the four plan tasks (TDD RED→GREEN — deck/parser, `compute`, `spectral_validate`,
  SKYSPECTRA harness) passed an independent spec-compliance + code-quality review before the next was dispatched.
  One Task-4 finding (the marker test asserted a vacuous `isinstance(_HAVE, bool)`) was **strengthened** (per user
  decision) to assert the gate predicate is False for an empty/missing dir.
- **Final whole-branch review (opus) — WITH FIXES → fixed:** 0 Critical, 2 Important, both resolved:
  (#1) `compare_engines` silently clamped on under-covered grids → added a `ValueError` **grid-coverage guard** +
  covering test; (#2) the `smarts.py` module docstring still said "`compute()` raises until Phase 6" → refreshed.
- **Pure functions verified by execution** (scratch interpreter, no binary): `build_deck` emits 29 LF-only lines in
  the correct card order with every input on the right card; `compare_engines` gives the correct +10% mean/max on a
  SPECTRL2-like (sparse 300–4000nm) vs SMARTS-like (280–4000nm@1nm) pair, the guard raises on a truncated grid, the
  internal `_interp` is correct at interior/both-clamps/exact-node, and `drift_vs_templates` returns the
  `reconstruction_divergence` shape. The SPECTRL2 half of the gated cross-check runs clean (band-spanning, positive
  direct+diffuse, accepted by the guard) — so the only unexercised piece is genuinely the SMARTS subprocess.
- **Completeness gap found + fixed (the value of the live-source pass):** `test_smarts_cross_check_clear_sky` was
  still the Phase-2 placeholder (`raise "not implemented until Phase 6"`). Being `skipif(not smarts_available())`,
  it would have **failed red on any machine with a SMARTS binary** — and the plan's Self-Review had wrongly marked
  the cross-check deliverable done. Replaced with a **real gated SMARTS↔SPECTRL2 cross-check** (§3.23):
  direct-normal within a documented 35% envelope, diffuse sanity-only. The diff-only per-task/final reviews could
  not catch this — the stub was pre-existing and unchanged by the Phase-6 diff range.
- **Now verified (was capability-gated):** a **live SMARTS run** + the `compute` data-tree symlink flow — both
  exercised 2026-06-21 after compiling SMARTS from the NREL SMARTS 2.9.5 source (D-19). **Still
  unverifiable here (dataset-gated, D-22):** the deck-vs-bundled-`Examples` provenance cross-check and the
  SKYSPECTRA *measured* comparison (no measured-spectrum dataset in the tree).

**Scope discipline:** Phases 1–6 are **purely additive**. Phases 1–3 leave the template pipeline untouched;
**Phase 4 modifies `spectral_reconstruct.py`/`server.py` additively only** — a `sun_spd` seam that defaults to
the prior template (bit-identical with `sun_spd=None`) and is not yet wired into the live transport (D-16);
**Phase 5 adds one new module (`spectral_pipeline`), extends `spectral_emit`/`spectral_sky` additively, and
registers three new MCP tools alongside the existing 32 (the Phase-5 count; the server now exposes 51 registered names — 47 tools + 4 aliases) — no existing tool, signature, or computed number
changed.** The EPW hour is stored verbatim and converted to the mid-interval (`h−0.5`) only inside the Phase-5
orchestrator for geometry (the record timestamp keeps the EPW hour); the µm→nm conversion is still pinned to the
single resampler call; the CCM reshape touches diffuse only and never breaks the DNI/DHI energy match. **Phase 6
rewrites the SMARTS scaffold and adds `spectral_validate.py` + gated harnesses — no existing module's behaviour or
output changes** (the new code is reached only by tests and opt-in callers; `SmartsEngine` is injectable into
`record_from_epw(engine=…)` but `Spectrl2Engine` stays the default); it registers **no new MCP tool**.

---

## 6. Not yet implemented (the deferred live-transport flip + live validation) — and the seams already ready

**All seven phases have landed.** Phase 6 (§3sexies — the SMARTS subprocess oracle + the `spectral_validate`
drift/cross-engine harness + the gated SKYSPECTRA comparison), the **Live-DDS physical-sky flip** (§3septies — the
physical record now feeds the live nvRD enhanced reconstruction via `physical_sky=True`), and **Phase 7**
(§3octies — the native `gensdaymtx` driver + `spectral_sky_native` MCP tool, capability-gated) are all in. What
remains is **not a phase but a default flip**: of the two closure conditions originally set for D-16/D-17 —
(1) flipping `physical_sky` **on by default** in the live path, and (2) a **live Daysim/Radiance run** that
validates it — **condition (2) is now met**: the flip had its first live execution on **2026-07-18**
(`office_room` + GRC Athens IWEC, Radiance 6.1a + Daysim `ds_shortterm`, 50.03 % physical coverage,
time-resolved sun throughout, no constant-30° fallback fired). ⚠️ That was a *first live execution, not a
calibrated baseline against measured sky spectra*, and the default remains opt-in, so **only condition (1)
is outstanding**. (Earlier revisions of this line said the production `_build_record_index` path was
"unit-tested only via a monkeypatched `record_from_epw`" — that was true when written and is now
superseded by the live run recorded in §3septies, §5 and §9.) Plus
**Phase 7's live half — COMPLETED 2026-06-20** — Radiance 6.1a is installed; the `gensdaymtx` run path and the cross-check
have now executed (D-26 closed; see §3octies). The MCP `colored_sky` single-timestep tool is also still un-wired for `engine=`/`to_channels` (out of scope), though its **solar-position seam is now closed (D-27, §3novies)**. Everything was
built so the remaining work drops in cleanly:

- **Engine + cloud + record contract is live and proven.** `Spectrl2Engine.compute(atm, geo)` consumes exactly
  the `AtmosphericState`/`SolarGeometry` fields Phase 1 produces; `Sedes1Modifier.apply` energy-matches to EPW
  DNI/DHI and reshapes the diffuse; `build_record` binds them into a `SpectralSkyRecord`; `ground_for_receiver`
  emits the spectral ground-glow input — all verified end-to-end (§5).
- **Phase 3 hand-off notes from Phase 2 — now satisfied:** the tilt=0 `sky_diffuse_horizontal` (incl. the `I_g`
  sky-ground bump) maps 1:1 to EPW DHI and is absorbed by the energy-rescale; the modifier runs on the full
  native range *before* the resample; `_interp` is only ever fed the engine's 122-pt grid (no empty-grid path).
- **Phase-5 orchestrator hand-off notes — now SATISFIED** (the `record_from_epw`/annual loop, §3.17): mid-interval
  `hour − 0.5` is applied before `solpos.compute`; `i0_normal = 1361.0 · earth_radius_vector` feeds Kt;
  `provenance["pw_cm"]["method"]` ∈ `{gueymard94, reitan63, fixed, explicit}` carries through; and the **D-14
  CCM-caveat decision was resolved (Decision A)** when the emitters were built — see §8. (One note partly carried:
  `annual_records` iterates rows in memory and filters by an O(1) `set`, but still calls `parse_epw_hourly`
  per-call rather than caching a `(m,d,h)→row` index across calls; immaterial — one parse per call, not per row.)
- **Track-A/B emitters are live, and the live nvRD path now consumes them opt-in.**
  `to_channels(record)`/`to_reference(record)`/`reconstruct_from_record(record, …)` (Phase 4) and `record_to_dict` +
  the four artifact emitters (Phase 5) all ship; the three MCP tools call the Phase-5 orchestrators. **The Live-DDS
  physical-sky flip (§3septies) now calls `to_reference(record)` per timestep inside `annual_nvrd` when
  `physical_sky=True`**, feeding the per-timestep series into the enhanced reconstruction. The remaining job is to
  flip it **on by default** + validate against a live Daysim/Radiance run (D-16/D-17 closure conditions).
- **SMARTS oracle is live** (Phase 6, §3.21): `SmartsEngine.compute` runs the subprocess and returns W/m²/µm —
  capability-gated on `$SMARTSPATH` (no binary in this tree). The **SKYSPECTRA measured-data** harness
  (`tests/test_skyspectra.py`) is in place but its live-streaming test is gated until the raw dataset is downloaded, and the
  **SMARTS↔SPECTRL2 cross-check** runs when a binary is present (§3.23). `compare_engines` is **reused by Phase 7's
  cross-check** (§3.29) — now running live under Radiance 6.1a (D-26 closed): native `gensdaymtx` vs
  Python engine, Pearson 0.987 (reversed band order).
- **The 30° zenith fallback** in `spectral_reconstruct.py` is **overridable** (Phase 4's `sun_spd` seam), and the
  Live-DDS physical-sky flip (§3septies) now wires the physical sun into the **live nvRD enhanced** path on request
  (`physical_sky=True`). It remains the *live default* (physics is opt-in) until the default is flipped + a live run
  validates it (D-16/D-17 — downgraded, not closed).

When each phase lands, add its module section to §3, its deviations to §4, and flip its row in §1.

---

## 7. Master cross-reference (implemented surface)

| Implemented symbol                                                                                    | File                                       | Spec §           | Methodology              | Test(s)                                                                     |
| ----------------------------------------------------------------------------------------------------- | ------------------------------------------ | ----------------- | ------------------------ | --------------------------------------------------------------------------- |
| `parse_epw_hourly`, `row_for`                                                                     | `epw_hourly.py`                          | §3, §11#7       | §4                      | `test_epw_hourly.py`                                                      |
| `SolarGeometry`, `compute`                                                                        | `solpos.py`                              | §3, §4, §11#6  | §5, M-1…M-6            | `test_solpos.py`                                                          |
| `air_mass`                                                                                          | `solpos.py`                              | §3               | §5, M-8                 | `test_solpos.py`                                                          |
| `earth_radius_vector`                                                                               | `solpos.py`                              | §3               | §5, M-6                 | `test_solpos.py`                                                          |
| `gueymard94_pw`                                                                                     | `atmosphere.py`                          | §3, §11#10      | §6, M-12                | `test_atmosphere.py`                                                      |
| `reitan63_pw`                                                                                       | `atmosphere.py`                          | §3, §11#10      | §6, M-13                | `test_atmosphere.py`                                                      |
| `AtmosphericState`, `derive`                                                                      | `atmosphere.py`                          | §3, §4, §13    | §6, Algorithm A         | `test_atmosphere.py`                                                      |
| `ClearSkySpectra`, `SpectralEngine`                                                               | `spectral_engine/base.py`                | §3, §4          | §3                      | `test_spectral_engine_base.py`                                            |
| `WL_UM/ET_H0/ABS_H2O/ABS_O3/ABS_UMG`                                                                | `spectral_engine/_spectrl2_data.py`      | §3               | §7 (A[5][122])          | `test_spectrl2_data.py`                                                   |
| `Spectrl2Engine`, `compute`                                                                       | `spectral_engine/spectrl2.py`            | §3, §9.2        | §7, M-9/M-11/M-14…M-24 | `test_spectrl2.py`                                                        |
| `SpectralSkyRecord`, `GRID_NM`                                                                    | `spectral_sky.py`                        | §3, §4          | §9                      | `test_spectral_sky.py`                                                    |
| `resample_to_1nm`                                                                                   | `spectral_sky.py`                        | §3, §11#2       | §9, M-30                | `test_spectral_sky.py`                                                    |
| `smarts_available`                                                                                  | `spectral_engine/smarts.py`              | §3, §9.2        | §12                     | `test_smarts.py`                                                          |
| `clearness_index`, `broadband_integral`                                                           | `cloud_modifier.py`                      | §5               | §8, SEDES1 Eq. 6        | `test_cloud_modifier.py`                                                  |
| `energy_normalize`                                                                                  | `cloud_modifier.py`                      | §5, §11#1       | §8, SEDES1 Eq. 9        | `test_cloud_modifier.py`                                                  |
| `CloudModifier`, `Sedes1Modifier`                                                                 | `cloud_modifier.py`                      | §5, §6, §13    | §8, SEDES1 Eqs. 10–11  | `test_cloud_modifier.py`                                                  |
| `SEED_WL_NM/SEED_A/SEED_B/SEED_C/FIG11_*`, `ccm_coeffs`                                           | `_sedes1_data.py`                        | §5               | §8 (Fig. 10 solve)      | `test_sedes1_data.py`                                                     |
| `ground_for_receiver`                                                                               | `spectral_sky.py`                        | §6               | §9                      | `test_spectral_sky.py`                                                    |
| `build_record`                                                                                      | `spectral_sky.py`                        | §5, §13         | §8–§9                 | `test_spectral_sky.py`                                                    |
| `_sun_reference_spd`, `reconstruct_spectrum(sun_spd=)`                                            | `spectral_reconstruct.py`                | §11#4, §12      | §2                      | `test_spectral_reconstruct.py`                                            |
| `assemble_nvrd_rows(sun_spd=)`                                                                      | `spectral_reconstruct.py`                | §11#4            | §2                      | `test_spectral_reconstruct.py`                                            |
| `record_to_spd_dict`, `to_channels`, `to_reference`                                             | `spectral_emit.py`                       | §2, §9.4        | §2                      | `test_spectral_emit.py`                                                   |
| `reconstruct_from_record`                                                                           | `spectral_emit.py`                       | §8               | §2                      | `test_spectral_emit.py`                                                   |
| `reconstruct_spectrum(sun_spd=)` (MCP tool)                                                         | `hcl_mcp/server.py`                      | §11#4, §12      | —                       | `test_server.py`                                                          |
| `record_from_epw`, `annual_records`                                                               | `spectral_pipeline.py`                   | §8, §9.5, §13  | §4, §5                 | `test_spectral_pipeline.py`                                               |
| `record_to_dict`, `emit_spd_set`                                                                  | `spectral_emit.py`                       | §8               | §9                      | `test_spectral_emit.py`                                                   |
| `BAND_EDGES_20`, `band_average`, `emit_band_matrix`                                             | `spectral_emit.py`                       | §8, §11#9       | §8                      | `test_spectral_emit.py`                                                   |
| `emit_spectral_wea`, `emit_augmented_epw_sidecar`                                                 | `spectral_emit.py`                       | §8               | §9                      | `test_spectral_emit.py`                                                   |
| `build_record` CCM-caveat provenance (D-14)                                                         | `spectral_sky.py`                        | §5, §12         | §8                      | `test_spectral_sky.py`                                                    |
| `atmosphere_from_epw`, `spectral_sky_from_epw`, `spectral_epw` (MCP tools)                      | `hcl_mcp/server.py`                      | §8, §9.5        | —                       | `test_server.py`                                                          |
| `build_deck`, `parse_ext_output`, `SmartsEngine.compute`                                        | `spectral_engine/smarts.py`              | §3, §9.2, §9.6 | §12                     | `test_smarts.py`                                                          |
| `drift_vs_templates`, `compare_engines`                                                           | `spectral_validate.py`                   | §9.6             | §2, §12                | `test_spectral_validate.py`                                               |
| SMARTS↔SPECTRL2 cross-check; SKYSPECTRA measured comparison (gated)                                  | `test_smarts.py`, `test_skyspectra.py` | §9.6, §10       | §12                     | (capability-gated)                                                          |
| `assemble_nvrd_rows(sky_spd_series=, sun_spd_series=)`                                              | `spectral_reconstruct.py`                | §11#4            | §2, §11.1              | `test_spectral_reconstruct.py`                                            |
| `_physical_spd_series`, `_build_record_index`, `annual_nvrd(physical_sky=)`                     | `hcl_radiance/annual_nvrd.py`            | §5.1–§5.3      | §11.1                   | `test_annual_nvrd.py`                                                     |
| `annual_nvrd(physical_sky=)` (MCP tool)                                                             | `hcl_mcp/server.py`                      | §8               | —                       | `test_server.py`                                                          |
| `build_gensdaymtx_cmd`, `build_rcomb_melanopic_cmd`                                               | `hcl_radiance/spectral_native.py`        | §9.7             | §12                     | `test_spectral_native.py`                                                 |
| `parse_smx_header`, `radiance_spectral_status`, `reconcile_to_native_bands`, `run_gensdaymtx` | `hcl_radiance/spectral_native.py`        | §9.7             | §12                     | `test_spectral_native.py`                                                 |
| `spectral_sky_native` (MCP tool)                                                                    | `hcl_mcp/server.py`                      | §9.7             | —                       | `test_server.py`                                                          |
| native`gensdaymtx`↔Python cross-check                                                         | `test_spectral_native.py`                | §9.7             | §12                     | passing live under Radiance 6.1a (was capability-gated skip — D-26 closed) |
| `van_heuklon_ozone`, `derive(ozone_mode=, aod_anchor_nm=, aerosol_g via overrides)`             | `atmosphere.py`                          | §6               | —                       | `test_atmosphere.py` (D-2/D-3/D-7 resolved, opt-in)                        |
| `build_deck(aerosol="user")` Card 8a; `SmartsEngine(aerosol=)`; `spectral_sky_from_epw`/`spectral_epw(smarts_aerosol=)` | `spectral_engine/smarts.py`, `hcl_mcp/server.py` | §12.1  | §12                     | `test_smarts_deck.py` (D-20 resolved, opt-in)                              |

*Documented in methodology but **not** in the as-built code: M-7 (van Heuklon ozone climatology) — see
deviation D-2, **now resolved as an opt-in `ozone_mode="climatology"` refinement** (default `"constant"`
remains byte-identical). D-3 (Ångström AOD anchor) and D-7 (aerosol asymmetry `g`) and D-20 (SMARTS settable α)
are likewise **resolved as opt-in refinements** — see their entries above; every default path is unchanged.
Formerly exported but unused (now removed): `NIR_FACTOR` — see deviation D-13. **Resolved in Phase 5:** D-14 (CCM
caveat-string propagation, Decision A) — see §8. **Implemented in Phase 6 (D-9 closed):** the full SMARTS subprocess
engine + the drift/cross-engine/SKYSPECTRA validation harness — capability-gated on `$SMARTSPATH` / the raw SKYSPECTRA fixture
(**SMARTS first run live 2026-06-21** once compiled from the NREL SMARTS 2.9.5 source — D-19 closed; the SKYSPECTRA measured
comparison is still dataset-gated — D-22). **Live nvRD physics now wired opt-in (D-16/D-17 downgraded, not closed):**
the `physical_sky` flag feeds the per-timestep record into the enhanced reconstruction — default-template;
**first live execution 2026-07-18** (`office_room` + GRC Athens IWEC, Radiance 6.1a + Daysim `ds_shortterm`,
50.03% physical coverage, time-resolved sun — a first live execution, not a calibrated baseline); see
§3septies and deviations D-16/D-17/D-23/D-24. **Implemented in Phase 7 (native Radiance Track
C):** the `gensdaymtx` command builders + `parse_smx_header`/`reconcile_to_native_bands` + `run_gensdaymtx` run-or-
emit driver + the `spectral_sky_native` MCP tool — capability-gated on Radiance 6.1a (`/usr/local/radiance/bin`,
installed 2026-05-05); two plan claims were corrected against the bundled source (see §3octies, D-25); **run path
first live-validated 2026-06-20 (NCOMP=20, Pearson 0.987 vs Python engine) — D-26 closed** (see §3octies).*

---

## 8. Phase-5 decision — RESOLVED: CCM caveat strings on the persisted record (D-14, Decision A)

> **TL;DR — RESOLVED in Phase 5 (Decision A, user decision 2026-06-18).** Phase 3 computed two honest "fine-print"
> labels about *how* the diffuse was modeled (`ccm_basis="global-fit->diffuse(approx)"`,
> `coeff_method="fig10_3class_solve"`) but through Phase 4 did **not** write them onto the saved
> `SpectralSkyRecord` — they lived only in the transient modifier `info` dict. **Phase 5 took Decision A:**
> `build_record` now propagates `ccm_basis`, `coeff_method`, `ccm_applied` onto the day-branch record provenance
> (defensively, via `info.get`), with the night branch carrying `ccm_applied=False` for schema symmetry, locked by
> two tests (§3.19, D-14). Every persisted/emitted record — including `record_to_dict` and the MCP
> `spectral_sky_from_epw` output — is now self-describing. The analysis below is retained for the rationale; the
> chosen path is **Decision A**.
>
> **⚠️ Note.** The two string *values* this section quotes (`ccm_basis="global-fit->diffuse(approx)"`,
> `coeff_method="fig10_3class_solve"`) are what the **seed** CCM emits. The default `reanchored` Fig. 11 modifier emits `ccm_basis="fig11-faithful"`,
> `coeff_method="webplotdigitizer_fig11"` (+ `ccm_variant`). The *mechanism* described here (propagating these
> keys onto the day-branch provenance) is unchanged; only the values differ.

### What the two strings are (and are not)

They are **pure audit metadata** — they change **no number** in the spectrum. They flag two v1 modeling caveats:

- `ccm_basis="global-fit->diffuse(approx)"` — the SEDES1 CCM was fit by the paper to *global* spectra but is
  applied here to the *diffuse* (deviation **D-11**); a small, paper-unvalidated approximation.
- `coeff_method="fig10_3class_solve"` — the CCM coefficients came from a **figure digitization** with residual
  uncertainty (deviation **D-10**), not a closed-form table. ⚠️ That is a property of **this** default, not of
  the literature: a tabulation exists (Whitaker & Newmiller 1998) and ships opt-in as `Sedes2Modifier`, which
  emits `coeff_method="tabulated"` and `ccm_basis="whitaker1998-table2-1"` instead — see **D-10a**.

A consumer reading a record's `provenance` today sees the energy-bridge scalars (`k_dir, k_dif, clear_dni_bb, clear_dhi_bb, clearness_kt`) and the engine/cloud/resolution tags — but **cannot tell** that the diffuse shape
rests on a global→diffuse approximation and a digitized figure. That visibility is exactly what spec §5/§12 asks
for on the canonical artifact.

### Where the difference matters (which phase consumes record provenance)

| Phase                                        | Reads record`provenance`? | Relevance to the caveat strings                                                                  |
| -------------------------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------ |
| 4 — Track A (engine as`sun_spd` source)   | No                          | Uses spectra as a source, not metadata.**Indifferent.**                                    |
| **5 — Artifact emitters + MCP tools** | **Yes**               | Emits metadata sidecars / exposes provenance to users.**Primary consumer — decide here.** |
| 6 — SMARTS + SKYSPECTRA validation          | Yes (secondary)             | A validation report should cite the modeling caveat.**Benefits if present.**               |
| 7 — Native Radiance                         | No                          | Transport only.**Indifferent.**                                                            |

### The decision, and the action each way

When Phase 5 builds the emitters, pick one (both keep behaviour identical today; the choice is purely *where* the
caveat is surfaced):

- **Decision A — propagate onto the record (recommended).** *Action:* in `build_record`'s day-branch `prov`
  dict (`spectral_sky.py:98–101`), copy `ccm_basis`, `coeff_method` (and optionally `ccm_applied`) from the
  modifier `info` — a ~3-line additive change — and add a test asserting the keys are present on the record.
  *Effect:* every persisted/emitted record is self-describing; the night branch can carry the same keys (or a
  `cloud_model`-only subset) for schema symmetry. *Cost:* one deliberate deviation from the plan's literal
  Task-6 dict (recorded here as D-14), which is fine since it serves the spec's auditability intent.
- **Decision B — leave the record lean; surface at emit time.** *Action:* do **not** change `build_record`;
  instead have the Phase-5 emitter pull `ccm_basis`/`coeff_method` from the modifier `info` (or re-derive from
  the active modifier's constants) and write them into the **sidecar/emitted artifact** metadata, not the
  in-memory record. *Effect:* the canonical record stays minimal; provenance richness lives in the emitted
  files. *Cost:* the emitter must thread the modifier `info` through `record_from_epw` (so don't discard it in
  the annual loop).

**Outcome: Decision A was implemented in Phase 5** — the record is the canonical artifact, so
the caveats now ride on it (a ~3-line additive `info.get` copy in `build_record`'s day branch + `ccm_applied=False`
on the night branch, with two tests). Decision B (surface only in emitted sidecars, keep the record lean) was the
alternative; it was not chosen because the in-memory record is the single source every emitter and MCP tool reads
from, so propagating once at `build_record` makes all downstream forms self-describing for free. D-14 is **closed**
(§4, §3.19).

---

## 9. Independent review — caveats & observations (2026-06-19)

> Added after an independent code review that re-verified the load-bearing claims by **execution** (not by
> trusting this doc): the bridge invariant exact for both clear (Kt=0.70) and overcast (Kt=0.25, heavy CCM
> reshape); `reconcile_to_native_bands(ncomp=20) == spectral_emit.band_average` (the §8 "byte-compat gap does
> not exist" claim — confirmed identical); the `-g` tuple guard raising `TypeError`; and a post-as-built
> type-fix commit being behaviour-neutral (annotations + guards only — `controls_point`'s explicit
> kwargs match the prior `**params` dict exactly). Full suite re-run green.
> Everything below is **already disclosed in the §4 deviations ledger**; this section restates it in one place
> for emphasis. *Net assessment: a high-quality, well-tested, honestly-documented implementation.*

### 9.1 What you must keep in mind (the real caveats)

These are **not bugs** — they are the boundary between "green pytest" and "physically validated":

1. **Native `gensdaymtx` (2026-06-20, D-26) AND SMARTS (2026-06-21, D-19) both first-live-validated.**
   `gensdaymtx`: Radiance 6.1a installed, `run_gensdaymtx(..., run=True)` returned NCOMP=20, cross-check
   passes (Pearson 0.987 vs Python engine). **SMARTS:** compiled from the NREL SMARTS 2.9.5 source (that distribution's Mac binary
   is dead PowerPC) to a native arm64 binary; with `$SMARTSPATH` set the deck → `compute` → parse flow runs live,
   the gated cross-check passes, and SMARTS agrees with SPECTRL2 to ~2 % direct / ~7 % diffuse at r≈0.99
   (`docs/spectral-engine-comparison.md`). **Both are *validations*, not calibrated
   baselines** (neither checked against *measured* sky spectra; the SMARTS `Examples` deck cross-check is still
   not reproduced). **The live Daysim/DDS `physical_sky` flip (D-16/D-17/D-23) also had its first live execution**
   — **2026-07-18**, `office_room` + GRC Athens IWEC, Radiance 6.1a + Daysim `ds_shortterm`: 50.03% physical
   coverage (daylight timesteps only — night/zero-irradiance steps legitimately fall back to the template by
   design) with time-resolved sun throughout (no constant-30° fallback fired). A first live execution, not a
   calibrated baseline; the `.wea` hour convention in `_physical_spd_series` (**D-23**) still rests on an
   unverified assumption — the live runs did not test it.
2. **CCM coefficients are a faithful 10 nm Fig. 11 figure digitization by default** (**D-10** — the 9-point
   seed digitization is retained only as the opt-in `seed` variant), applied to the diffuse though fit to the
   global (**D-11**). Only the **always-on energy-rescale is exact**; the *spectral shape* under cloud still
   carries real uncertainty until the SKYSPECTRA validation runs — that uncertainty is now **quantified**
   (`ccm_sigma`/`ccm_sigma_mean`, the Fig. 11 regression standard error, on every record) and the CCM is now
   **locally re-fittable** (`cloud_variant='local'`, `hcl_core/sedes1_fit.py`) rather than fixed. ⚠️ A
   **tabulated** alternative also now ships opt-in — `Sedes2Modifier` on Whitaker & Newmiller 1998
   Table 2-1 (**D-10a**) — so the digitization is the default's provenance, not the only one available.
3. **Physics is opt-in, not the default.** The 30° fallback still fires unless a caller passes
   `sun_spd`/`physical_sky=True`. The spec's headline *"kill the 30° fallback"* is **seam-complete, not
   flipped** (**D-16/D-17** explicitly *downgraded, not closed*).

### 9.2 Minor observations (low priority)

- **`emit_band_matrix` produces per-band *irradiance* means (W/m²/nm)**, while spec §8 labels the 20-band form
  "W/sr/m²" (*radiance*). This is the documented hcl-nominal artifact vs. the `gensdaymtx`-native radiance —
  fine, but the unit-label divergence is worth a one-line note in the emitter docstring.
- **`NIR_FACTOR` was dead** (**D-13**, formerly exported-but-unused; the constant has since been removed) and
  provenance lacks the spec §4 `uncertainty` field (**D-1**). Both cosmetic.

### 9.3 Net

A high-quality, well-tested, honestly-documented implementation. Trust the **offline Python stack (Phases 1–5)
end-to-end**. **Both native engines are now first-live-validated:** Phase 7 `gensdaymtx` (D-26, 2026-06-20 —
NCOMP=20, Pearson 0.987 vs Python engine, band-order reversal documented) and Phase 6 **SMARTS** (D-19,
2026-06-21 — compiled from the NREL SMARTS 2.9.5 source, gated cross-check passes, ~2 % direct / ~7 % diffuse agreement with
SPECTRL2 at r≈0.99; `docs/spectral-engine-comparison.md`). Both are *validations*, not calibrated baselines (no
*measured*-spectrum check yet). The live Daysim/DDS `physical_sky` flip (D-16/D-17/D-23 — shape-only,
default-off) also had its **first live execution on 2026-07-18** (`office_room` + GRC Athens IWEC, Radiance
6.1a + Daysim `ds_shortterm`, 15-min and 6-min timesteps): 50.03% physical coverage (the rest legitimately
template-fallback, by design, for night/zero-irradiance timesteps) and time-resolved sun throughout — a first
live execution, not a calibrated baseline against measured sky spectra. The `.wea` hour convention is still
unverified (**D-23**) — the live runs exercised coverage/timing, not that assumption.

---

### Addendum 2026-06-19 — user-selectable engine

`spectral_sky_from_epw`, `spectral_epw`, and `annual_nvrd` accept `engine="spectrl2"` (default) |
`"smarts"`, resolved by `hcl_core.spectral_engine.resolve_engine`. SPECTRL2 stays the default;
`smarts` requires `SMARTSPATH` and raises `RuntimeError` early (via `smarts_available()`) when absent.
`atmosphere_from_epw` is intentionally NOT parameterized (its output is engine-invariant), and
`spectral_sky_native` remains the dedicated native `gensdaymtx` tool (different output contract).
`annual_nvrd` resolves the engine lazily — only when `physical_sky=True`. No live SMARTS run added.
---

## §3novies — D-27: the `colored_sky` solar-position seam (closed 2026-07-21)

**The defect.** `spectral_sky_from_epw` and `colored_sky` both take a parameter named `hour`, and it
meant two different things with nothing reconciling them:

| | meaning of `hour` | solar position derived by |
|---|---|---|
| `spectral_sky_from_epw` | EPW **hour-ENDING** label (1–24) | `solpos.compute(hour − 0.5)` — mid-interval (§5), correct because the row's DNI/DHI are averaged over the preceding hour |
| `colored_sky` | **wall-clock** instant | `gendaylit`'s own ephemeris, from `month day hour` + `-a/-o/-m` |

A caller passing `hour=12` to both — the only reasonable reading of two identically-named parameters —
got a spectrum computed for 11:30 painted onto a sky traced from 12:00. **No error was raised.**

**Not an ephemeris disagreement.** `hcl_core.solpos` and gendaylit's internal ephemeris agree to
**0.05° in altitude and 0.135° in azimuth** for the same instant (verified live). This was purely a
timestamp-convention mismatch: `solpos.compute` at `hour=11.5` reproduces the captured
`zenith_deg = 40.958645` to six decimals.

**Magnitude.** Altitude differs by 1.91° but azimuth by **11.3°**; total angular separation between the
two sun directions is **7.50°** — exactly half an hour of diurnal arc at 15°/hr. On the Athens equinox
case the direct-beam cosine differs by **+2.79%** on a south-facing vertical aperture and **+2.84%** on
the horizontal.

**Which side was wrong.** The spectral side is correct and stays untouched: the mid-interval convention
is deliberate and documented in eight places (the supporting write-up is kept outside this repository). Every
script in the internal engine-comparison harness (not included in this repository) already applied
`h − 0.5` before calling `gendaylit` — so **no published figure or number moves**. Only the shipped
`build_gendaylit` was the outlier.

**The fix.** `colored_sky`/`colored_sky_luminance`/`build_gendaylit`/`build_gendaylit_luminance` gained
optional `sun_zenith_deg` + `sun_azimuth_deg` (both or neither; either alone raises `ValueError`).
Supplied, they emit `gendaylit -ang <altitude> <azimuth>`, bypassing gendaylit's ephemeris; `-a/-o/-m`
are dropped because gendaylit ignores them under `-ang` (verified byte-identical output). Conventions
are taken **verbatim from the record's `geometry` block** so the caller does no arithmetic —
`90 − zenith_deg` and `azimuth_deg − 180` happen internally. Deliberately, `build_gendaylit` does **not**
apply `−0.5` itself: its `hour` may legitimately be wall-clock, and the hour-ending → mid-interval
conversion remains the orchestrator's job (§5).

**Why the prompts changed too.** Code alone would not have prevented recurrence. `hcl_grid_study` step 2
said only *"colored_sky for the date/time/location"*, and the `spectral_sky_from_epw` prompt never
mentioned `colored_sky` at all — there was **no documented bridge** from record to rendered sky, which is
why the seam was crossed by hand in the first place. Both prompts now carry the geometry handoff and
state it is a correctness requirement.

**Status.** Additive; default byte-identical (regression-locked by
`test_build_gendaylit_default_is_byte_identical_without_solar_position`). Suite green (1744 passed /
7 skipped at the time; 1917 / 6 as of 2026-08-12). Verified live on Radiance 6.1a: with the record's geometry threaded, the rendered sun
altitude is **49.041°**, exactly `90 − 40.9586`. Measured separation closed was **7.61°** — slightly more
than the 7.50° timestamp error, because the default path also carried gendaylit's own 0.05°/0.135°
ephemeris residual, which `-ang` bypasses as well.

**Still open (unchanged by D-27).** `colored_sky` remains un-wired for `engine=`/`to_channels`
auto-composition — a caller still bins the spectra itself. D-27 closes only the solar-position half of
that seam.
