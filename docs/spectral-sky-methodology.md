# Spectral Sky from EPW — Methodology & Mathematics

> **Status:** the scientific reference for the EPW → spectral-sky pipeline. Written as the companion to
> the program design spec, which lives outside this repository; this document is self-contained and does
> not depend on it.
> **Purpose:** the *scientific* counterpart to the spec. Where the spec fixes architecture, interfaces,
> and build phasing, this document states the **physics, the equations, the reference provenance, and the
> end-to-end numerical flow** of the EPW → physically-derived spectral-sky pipeline. Every equation here is
> transcribed from a named primary source and cross-checked against the in-repo implementation; papers are
> cited inline (see [literature-bibliography.md](literature-bibliography.md)), and cross-checked against the
> reference engine sources (SPECTRL2, SMARTS, Radiance).
> **Scope:** the Python stack (SPECTRL2 + SEDES1 + receiver/ground + α-opic) is the primary subject; the
> SMARTS oracle and native-Radiance `gensdaymtx` paths are covered as parallel engines (§12).
> **API note.** SPECTRL2 (default) and SMARTS are interchangeable behind the `SpectralEngine`
> protocol and are now **user-selectable** at the tool boundary (`engine="spectrl2" | "smarts"`, via
> `hcl_core.spectral_engine.resolve_engine`). This is plumbing only — it changes nothing in the math below;
> it selects which engine produces `ClearSkySpectra` at step (d).
> **Correction layers:** the faithful SEDES1 CCM, the anisotropic diffuse wrapper, the SKYSPECTRA
> external cross-validation and the optional clear-sky bias are consolidated in
> **[spectral-engine-validation.md](spectral-engine-validation.md)**.

---

## 0. How to read this document

The pipeline is a strict **producer → canonical record → consumers** chain (spec §2). This document walks
that chain stage by stage. Each stage section gives: **(i)** what it consumes and produces, **(ii)** the
governing equations with their source citation, **(iii)** the constants, and **(iv)** the numerical caveats
that bound accuracy. Equations are numbered **(M‑n)** for cross-reference within this document; where an
equation is a verbatim transcription of a source equation its original label is given inline (e.g. *Bird
Eq. 2‑4*, *Nann Eq. 11*, *C `spectrl2_2.c:361`*).

**M-10 is intentionally unassigned.** The sequence runs M-1…M-9, M-11…M-34; §7.1 carries $m_p$ and $m_o$ on
one shared `(M-9, M-11)` tag. The numbering is deliberately *not* compacted, because `hcl-methodology.md`,
`technical-reference.md` and the bibliography all cite M-numbers by value.

Symbol conventions: wavelength $\lambda$ is in **µm** inside the SPECTRL2 engine (its native unit) and in
**nm** in the canonical record; the conversion is pinned at exactly one boundary (§9). Irradiances are
spectral (per-wavelength) unless written as a broadband integral. Angles are in degrees in the EPW/clock
domain and converted to radians for trigonometry.

---

## 1. Nomenclature

| Symbol                        | Meaning                                                              | Units                      |
| ----------------------------- | -------------------------------------------------------------------- | -------------------------- |
| $\lambda$                   | wavelength                                                           | µm (engine) / nm (record) |
| $z,\ \gamma_s$              | solar zenith, solar azimuth                                          | deg                        |
| $\phi,\ L,\ L_{\text{std}}$ | site latitude, longitude (W‑positive), standard meridian            | deg                        |
| $\delta$                    | solar declination                                                    | deg                        |
| $\omega$                    | hour angle                                                           | deg                        |
| $n$                         | day-of-year (1–365, non-leap)                                       | —                         |
| $m$                         | Kasten–Young relative air mass                                      | —                         |
| $m_p$                       | pressure-corrected air mass$=m\,P/1013$                            | —                         |
| $m_o$                       | ozone air mass                                                       | —                         |
| $R_v$                       | Earth-radius-vector correction$(r_0/r)^2$                          | —                         |
| $H_{0\lambda}$              | extraterrestrial spectral irradiance at mean sun–earth distance     | W m⁻² µm⁻¹            |
| $P$                         | station pressure                                                     | mbar (hPa)                 |
| $w$                         | precipitable water                                                   | cm                         |
| $u_{O_3}$                   | ozone column                                                         | atm-cm                     |
| $\tau_{500}$                | aerosol optical depth at 500 nm                                      | —                         |
| $\alpha$                    | Ångström exponent                                                  | —                         |
| $\rho,\ \rho(\lambda)$      | ground albedo (gray / spectral)                                      | —                         |
| $I_{d\lambda}$              | direct-normal spectral irradiance                                    | W m⁻² µm⁻¹            |
| $I_{s\lambda}$              | diffuse (sky) spectral irradiance on a horizontal plane              | W m⁻² µm⁻¹            |
| $\mathrm{DNI,\ DHI,\ GHI}$  | EPW broadband direct-normal / diffuse-horizontal / global-horizontal | W m⁻²                    |
| $K_t$                       | clearness index$=\mathrm{GHI}/(I_0\cos z)$                         | —                         |
| $I_0$                       | broadband solar constant$\times R_v$                               | W m⁻²                    |
| $\mathrm{CCM}(\lambda,K_t)$ | cloud-cover modifier (spectral shape factor)                         | —                         |
| $s_\alpha(\lambda)$         | CIE S 026 α-opic action spectrum                                    | —                         |
| $E_\alpha$                  | α-opic irradiance                                                   | W m⁻²                    |
| mel-EDI                       | melanopic equivalent daylight illuminance                            | lx                         |

---

## 2. Reference provenance

Papers are cited inline (see [literature-bibliography.md](literature-bibliography.md)). "Verified" =
read and cross-checked against the implementation.

| Ref                           | Source                                                                                                                                                                                                                | What it supplies                                                                                                                      |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **Bird & Riordan 1986** | *Simple Solar Spectral Model for Direct and Diffuse Irradiance on Horizontal and Tilted Planes at the Earth's Surface for Cloudless Atmospheres*, J. Climate Appl. Meteorol. **25**:87 (= SERI/TR‑215‑2436) | The SPECTRL2 model: transmittance Eqs 2‑1…2‑11, diffuse Eqs 3‑1…3‑18, the 122‑wavelength$A[5][122]$ table.                   |
| **SPECTRL2 C source**   | NREL SPECTRL2 C source (`spectrl2_2.c`, `spectrl2_2.h`; maintained 2004 build)                                                                                                               | The authoritative constants + equation order this port transcribes**verbatim**. *Verified 1:1.*                               |
| **SPCTRAL2 PC kit**     | Fortran reference + I/O fixtures; the SPCTRAL2 PC reference kit (`SPCTRAL2_PC.f`, `SPCTRAL2_TAPE1/TAPE2/OUTPUT.txt`)                                                             | TAPE2 = the 122×5 coefficient table; TAPE1 = golden inputs; OUTPUT = golden reference (the Phase‑2 gate).*Verified.*              |
| **Nann & Riordan 1991** | *Solar Spectral Irradiance under Clear and Cloudy Skies: Measurements and a Semiempirical Model (SEDES1)*, J. Appl. Meteorol. **30**:447                                                                      | The cloud modifier: CCM Eq. 11, Fig. 10 (R̄ curves), Fig. 11 (A/B/C), Table 3 ($K_t$ range), error budget (Fig. 12). *Verified.* |
| **SMARTS 2.9.5**        | Gueymard, *SMARTS* 2.9.5 radiative-transfer code + manual + worked Examples (distribution kept outside this published repo)                                                        | The oracle/high-accuracy engine: 17‑card deck format, IOUT codes, output columns.*Deck + IOUT verified against the distribution's Examples.*  |
| Kasten & Young 1989           | relative optical air mass                                                                                                                                                                                             | —                                                                                                                                    |
| Spencer 1971 / NREL SOLPOS    | Earth-radius-vector & ozone airmass                                                                                                                                                                                   | —                                                                                                                                    |
| Cooper 1969                   | declination (extends existing`weather.solar_zenith`)                                                                                                                                                                | `src/hcl_core/weather.py:84‑103`                                                                                                    |
| Gueymard 1994 / Reitan 1963   | precipitable water from T/RH or dew point                                                                                                                                                                             | (pvlib formulation)                                                                                                                   |
| CIE S 026:2018                | α-opic action spectra & EDI                                                                                                                                                                                          | `src/hcl_core/alpha_opic.py`, `…/data.py`                                                                                        |
| Radiance 6.1a                 | `gensdaymtx`, `rcomb` spectral path                                                                                                                                                                               | the upstream Radiance 6.x source                                                                                           |
| pvlib                         | reference impls (`gueymard94_pw`, `poa_ground_diffuse`)                                                                                                                                                           | —                                                                                                                                    |

Related but **not used** in v1: a later (1997) optical-depth study in J. Appl. Meteorol. **36**:1336 — noted for
completeness only.

---

## 3. Process overview & dataflow

The pipeline transforms one EPW timestamp into one self-describing spectral record, then derives every
external product from it. **Nothing recomputes physics downstream of the engine.**

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
        │      + rec.geometry {z, γs} ─► colored_sky sun_zenith_deg/sun_azimuth_deg  (SAME instant)
        ├──(h) to_reference(rec) ────► reconstruct_spectrum (sky_spd + sun_spd)
        ├──(i) emitters ─────────────► 1nm SPD set / 20-band matrix / spectral .wea / augmented EPW
        └──(j) alpha_opic_from_spd ──► E_α, mel-EDI  (CIE S 026 circadian metrics)
```

### 3.1 Master algorithm — one timestep (`record_from_epw`)

```
ALGORITHM 0  record_from_epw
INPUT   epw_path; (month, day, hour_ending); engine=SPECTRL2; modifier=SEDES1; overrides
OUTPUT  SpectralSkyRecord
─────────────────────────────────────────────────────────────────────────────
1  rows ← parse_epw_hourly(epw_path)                              # §4  (skip 8 headers, sentinels→None)
2  row  ← row_for(rows, month, day, hour_ending)
   loc  ← parse_epw_location(epw_path)                           # {lat, lon(W+), tz=−15·UTC}
   if row is None or loc is None: raise ValueError
3  h_mid ← hour_ending − 0.5                                     # EPW hour is hour-ENDING → mid-interval
   geo   ← solpos.compute(month, day, h_mid, loc.lat, loc.lon, loc.tz)     # §5 → SolarGeometry
4  atm   ← atmosphere.derive(row, overrides)                     # §6 → AtmosphericState (+provenance)
5  I0    ← 1361 · geo.R_v                                        # broadband solar constant × ERV  (§8.1)
6  return build_record(engine, modifier, atm, geo,
                       timestamp=(month, day, hour_ending),
                       DNI=row.dni or 0, DHI=row.dhi or 0, GHI=row.ghi or 0, I0=I0)
```

### 3.2 The orchestrator (`build_record`) — engine → cloud → record

```
ALGORITHM 0a  build_record
INPUT   engine, modifier, atm, geo, timestamp, DNI, DHI, GHI, I0
OUTPUT  SpectralSkyRecord
─────────────────────────────────────────────────────────────────────────────
1  cz ← cos(geo.zenith);   night ← (geo.zenith ≥ 90° or cz ≤ 0)
2  if night:                                                     # §9 night/twilight contract
       return ZEROED record with provenance.night = True
              and provenance.night_but_epw_nonzero = (DNI>0 or DHI>0 or GHI>0)
3  clear        ← engine.compute(atm, geo)                       # §7  122 pts, W·m⁻²·µm⁻¹, tilt=0 (sky-truth)
3a if clearsky_correction:                                       # OPTIONAL, default-off (param=None); §8.6/P5
       clear, cs_info ← clearsky_correction.apply(clear)         #   per-engine warming K(λ), shape-only → provenance.clearsky_corrected
   # ⚠️ REACHABILITY: `clearsky_correction` is a parameter of build_record ONLY. Neither
   # `record_from_epw` nor `annual_records` accepts or forwards it (verified: the identifier does not
   # occur in `spectral_pipeline.py`), and no MCP tool exposes it. Enabling the K(λ) layer therefore
   # means calling `build_record` directly — the same reachability caveat SEDES2 carries in §8.6(f).
4  Kt           ← clamp(GHI / (I0·cz), 0, 1.2)                   # §8.1
5  scaled, info ← modifier.apply(clear, DNI, DHI, GHI, Kt, geo)  # §8  energy-rescale + CCM (full range)
6  (dir₁, dif₁) ← resample_to_1nm(scaled)                        # §9  interp + ×0.001 → 380–780@1nm, W·m⁻²·nm⁻¹
7  return SpectralSkyRecord(timestamp, GRID_NM, dir₁, dif₁,
                            broadband={DNI,DHI,GHI,Kt}, atm, geo,
                            provenance = info ∪ {engine.name, modifier.name, native_resolution, night:False})
```

### 3.3 Annual loop (`annual_records`)

```
ALGORITHM 0b  annual_records
INPUT   epw_path; optional hours-subset H
OUTPUT  list[SpectralSkyRecord]   (one per data row; ~8760)
─────────────────────────────────────────────────────────────────────────────
loc ← parse_epw_location(epw_path)
for row in parse_epw_hourly(epw_path):
    if H is not None and (row.month,row.day,row.hour) ∉ H: continue
    geo ← solpos.compute(row.month, row.day, row.hour − 0.5, loc.lat, loc.lon, loc.tz)
    atm ← atmosphere.derive(row)
    emit build_record(engine, modifier, atm, geo, timestamp=(row.month,row.day,row.hour),
                      DNI=row.dni or 0, DHI=row.dhi or 0, GHI=row.ghi or 0, I0=1361·geo.R_v)
# ~50% of hours are night and return the zeroed record at build_record step 2 (Algorithm 0a).
# NOTE: this is not a cost saving. `engine.compute` is called BEFORE the night branch and its
# (all-zero) result is discarded, so a night hour still pays a full 122-wavelength engine call.
```

**Boundary data structures** (the only types that cross stage edges): `dict` (EPW row) → `AtmosphericState`

+ `SolarGeometry` → `ClearSkySpectra` (native, full-range) → `ClearSkySpectra` (all-sky, full-range) →
  `SpectralSkyRecord` (1 nm, visible, canonical). Every consumer in §10–11 reads only the last one.

---

## 4. Stage A — EPW hourly extraction

**Module:** `epw_hourly`. **Consumes:** EPW path. **Produces:** per-row dicts.
**Sources.** *Papers/standards:* US‑DOE EnergyPlus *Weather File (EPW) Data Dictionary* (field layout &
missing-value sentinels). *Software:* `src/hcl_core/epw_hourly.py` (this repo), field-map cross-checked
against `hcl_core.epw_location`.

EPW hourly data begins after **8 header lines**; each data row is comma-delimited with the data-source-flags
**string** at 0-based index 5 (the classic off-by-one trap). Field map (0-based):

$$
\text{dry-bulb}=6,\ \text{dew-point}=7,\ \text{RH}=8,\ P=9,\ \mathrm{GHI}=13,\ \mathrm{DNI}=14,\ \mathrm{DHI}=15,
$$

$$
\text{total-sky}=22,\ \text{opaque-sky}=23,\ \text{precip-water}=28,\ \text{AOD}=29,\ \text{albedo}=32.
$$

Missing-value sentinels map to `None` (dew-point/dry-bulb `99.9`, RH `999`, $P$ `999999`, irradiance `9999`,
sky-cover `99`, precip `999`, AOD `0.999`, albedo `999`). **`hour` is stored verbatim as the EPW
hour-ending value 1–24**; conversion to a mid-interval clock hour (§5) is the orchestrator's job, never done
here (avoids a 30–60 min solar-time error).

---

## 5. Stage B — Solar geometry

**Module:** `solpos`. **Consumes:** date, clock hour, site (DAYSIM convention: $\phi$ N‑positive, $L$
**W‑positive**, standard meridian $L_{\text{std}} = -15\times\mathrm{UTC\ offset}$). **Produces:**
`SolarGeometry`. The zenith is **bit-identical** to the existing `weather.solar_zenith` (Cooper 1969); the
azimuth, air mass, and Earth-radius-vector are the new additions.

> **Source (M-1…M-5):** Cooper 1969 (M-1 declination, M-4 zenith); equation-of-time per Duffie & Beckman (M-2, M-3) and solar azimuth per Iqbal 1983 (M-5).
> **Source (M-6):** Spencer 1971 / NREL SOLPOS (`Fourier paper.md`, verbatim transcription; original CSIRO *Search* note never issued as PDF).
> **Source (M-8):** Kasten & Young 1989, *Revised optical air mass tables*, Appl. Opt. **28**:4735 (verified vs primary source).

**Sources.** *Papers:* Cooper (1969), *The absorption of radiation in solar stills*, Sol. Energy **12**(3):333–346 — declination
(M‑1); standard equation-of-time approximation, as used in Duffie & Beckman, *Solar Engineering of Thermal
Processes* (M‑2, M‑3); solar azimuth from standard solar-position geometry, e.g. Iqbal (1983), *An
Introduction to Solar Radiation* (M‑5); Spencer (1971), *Fourier series representation of the position of
the Sun* (M‑6, via NREL SOLPOS); Kasten & Young (1989), *Revised optical air mass tables…*, Appl. Opt.
**28**:4735 (M‑8). *Software:* `src/hcl_core/solpos.py` (extends `src/hcl_core/weather.py:solar_zenith`).

Day-of-year $n$ from a non-leap reference year. **Declination** — *Cooper 1969*:

$$
\delta = 23.45^\circ \cdot \sin\!\Big(\tfrac{360^\circ\,(284+n)}{365}\Big)\tag{M-1}
$$

**Equation of time** via the auxiliary angle $B=\tfrac{360^\circ(n-81)}{364}$ — *standard EoT (Duffie &
Beckman), Cooper-1969 lineage as coded in `weather.solar_zenith`*:

$$
\mathrm{EoT} = 9.87\sin 2B - 7.53\cos B - 1.5\sin B \quad[\text{minutes}]\tag{M-2}
$$

**Apparent solar time** and **hour angle** (clock hour $h$ is the mid-interval value, typically
$h_\text{EPW}-0.5$) — *Cooper-1969 lineage, `weather.solar_zenith`*:

$$
t_{\text{solar}} = h + \frac{4\,(L_{\text{std}} - L) + \mathrm{EoT}}{60},\qquad
  \omega = 15^\circ\,(t_{\text{solar}} - 12)\tag{M-3}
$$

**Zenith** (clamped $\cos z\in[-1,1]$ for numerical safety) — *Cooper 1969; $\equiv$ `weather.solar_zenith`*:

$$
\cos z = \sin\phi\,\sin\delta + \cos\phi\,\cos\delta\,\cos\omega\tag{M-4}
$$

**Azimuth** measured clockwise from North ($N{=}0,E{=}90,S{=}180,W{=}270$ — the SPECTRL2 aspect
convention), via the from-South arctangent rotated by $180^\circ$ — *standard solar geometry (Iqbal 1983)*:

$$
\gamma_s = \Big(\operatorname{atan2}\!\big(\sin\omega,\ \cos\omega\sin\phi - \tan\delta\cos\phi\big)\cdot\tfrac{180^\circ}{\pi} + 180^\circ\Big)\bmod 360^\circ\tag{M-5}
$$

**Earth-radius-vector** correction $R_v=(r_0/r)^2$ — *Spencer 1971 / NREL SOLPOS*, with $D=\tfrac{2\pi(n-1)}{365}$:

$$
R_v = 1.000110 + 0.034221\cos D + 0.001280\sin D + 0.000719\cos 2D + 0.000077\sin 2D\tag{M-6}
$$

$R_v\in[0.966,1.034]$: maximum near perihelion (early January), minimum near aphelion (early July). It
multiplies the extraterrestrial spectrum (§7.3) and the solar constant (§8.1).

**Relative optical air mass** (Kasten & Young 1989), with the $z\ge 90^\circ$ horizon guard:

$$
m = \begin{cases}\dfrac{1}{\cos z + 0.50572\,(96.07995 - z)^{-1.6364}} & z < 90^\circ\\[2mm]\infty & z \ge 90^\circ\end{cases}\tag{M-8}
$$

(Spot check: $m(0^\circ)=1.00$, $m(60^\circ)\approx1.99$.)

```
ALGORITHM S  solpos.compute(month, day, h, φ, L, L_std)            # all M-eqs evaluated in order
─────────────────────────────────────────────────────────────────────────────
n   ← day_of_year(month, day)                                      # non-leap reference year
δ   ← 23.45·sin(360·(284+n)/365)                          deg      # (M-1)
B   ← 360·(n−81)/364                                      deg
EoT ← 9.87·sin2B − 7.53·cosB − 1.5·sinB                   min      # (M-2)
ts  ← h + (4·(L_std − L) + EoT)/60                        hours    # (M-3)
ω   ← 15·(ts − 12)                                        deg
cz  ← clamp(sinφ·sinδ + cosφ·cosδ·cosω, −1, 1);   z ← acos(cz)     # (M-4)
γs  ← (atan2(sinω, cosω·sinφ − tanδ·cosφ)·180/π + 180) mod 360     # (M-5)
D   ← 2π·(n−1)/365
R_v ← 1.000110 + 0.034221cosD + 0.001280sinD + 0.000719cos2D + 0.000077sin2D   # (M-6)
m   ← (z<90) ? 1/(cz + 0.50572·(96.07995−z)^−1.6364) : ∞           # (M-8)
return SolarGeometry{ zenith=z, azimuth=γs, air_mass=m, earth_radius_vector=R_v, day_of_year=n }
```

---

## 6. Stage C — Atmospheric state

**Module:** `atmosphere`. **Consumes:** one EPW row + optional overrides. **Produces:** `AtmosphericState`
with **per-field provenance**; nothing fails hard on a missing field.

> **Source (M-7):** van Heuklon 1979, *Estimating atmospheric ozone for solar radiation models*, Sol. Energy **22**:63–68 (verified vs primary source — Eq. 4 / Table 1, see §6 verification note below) — referenced-not-computed; engine uses the 300 DU constant default (see as-built D-2).
> **Source (M-12):** Gueymard 1994, *Analysis of monthly average atmospheric precipitable water*, Sol. Energy **53**:57 (verified vs primary source).
> **Source (M-13):** Reitan 1963, *Surface dew point and water vapor aloft*, J. Appl. Meteorol. **2**:776 (primary source obtained; scanned image-only AMS PDF).

**Sources.** *Papers:* Gueymard (1994), *Analysis of monthly average atmospheric precipitable water…*, Solar
Energy **53**:57 — PWV (M‑12); Reitan (1963), *Surface dew point and water vapor aloft*, J. Appl. Meteorol.
**2**:776 — PWV fallback (M‑13); van Heuklon (1979), *Estimating atmospheric ozone for solar radiation
models*, Solar Energy **22**:63 — ozone climatology (M‑7). *Software:* `src/hcl_core/atmosphere.py`; M‑12
follows the `pvlib.atmosphere.gueymard94_pw` formulation; M‑7 is coded in `spectrl2_2.c:278‑299`; field
defaults per design-spec §3.

> **Corroborating context (grounds no equation — see `literature-bibliography.md` §6):**
> Gueymard & Thevenard 2009 (*Sol. Energy* **83**:1998) and Gueymard 1993 (*Sol. Energy* **51**:121)
> independently establish that **AOD and PWV dominate** clear-sky accuracy while ozone, NO₂ and pressure
> are near-negligible — corroborating the engine's priority on getting AOD/PWV from the EPW and its
> low-stakes 300 DU ozone default (M‑7). These are motivating references, **not** sources of M‑12/M‑13/M‑7.

**Precipitable water.** Primary — Gueymard 1994 (pvlib formulation) from air temperature $T$ [K] and
relative humidity $\mathrm{RH}$ [%], with $\theta = T/273.15$:

$$
w = 0.1\,\big(0.4976 + 1.5265\,\theta + e^{\,13.6897\,\theta - 14.9188\,\theta^3}\big)\cdot
    \frac{216.7\,\mathrm{RH}}{100\,T}\,e^{\,22.330 - 49.140\frac{100}{T} - 10.922\left(\frac{100}{T}\right)^2 - 0.39015\frac{T}{100}}\tag{M-12}
$$

Fallback — Reitan 1963 from dew point $T_d$ [°C] (approximate; fit to monthly means, larger scatter on
hourly data):

$$
w = \exp\!\big(-0.0392 + 0.0681\,T_d\big)\tag{M-13}
$$

The **EPW precip-water column (28) is intentionally ignored** for $w$ (officially unreliable); $w$ is always
derived from T/RH or $T_d$.

**Other fields** (documented defaults applied when EPW is missing, each recorded in provenance):

| Field                     | EPW source   | Default       | Transform                         |
| ------------------------- | ------------ | ------------- | --------------------------------- |
| pressure$P$ [mbar]      | col 9 (Pa)   | 1013.25       | $P_\text{mbar}=P_\text{Pa}/100$ |
| albedo$\rho$            | col 32       | 0.20          | col value used only if $\rho \ge 0.01$; `0.000` is IWEC/TMY2 "no data" → default² |
| $\tau_{500}$            | col 29 (AOD) | 0.10          | broadband-AOD proxy¹             |
| ozone$u_{O_3}$ [atm-cm] | —           | 0.30 (300 DU) | optional lat/month climatology (**resolved, opt-in** — `ozone_mode="climatology"`) |
| Ångström$\alpha$      | —           | 1.14          | —                                |
| aerosol asymmetry$g$    | —           | 0.65          | **resolved, opt-in** — `aerosol_g` override (D-7) |

¹ EPW AOD (col 29) when present is broadband, not strictly @500 nm; v1 treats it as a 500‑nm proxy and notes
this in provenance. **Resolved, opt-in (D-3):** an Ångström conversion to a true 500-nm value is now available
via `derive(..., aod_anchor_nm=<nm>)` — it Ångström-converts a declared-wavelength AOD to $\tau_{500}$ using the
same $\alpha$ the engine spreads with; `aod_anchor_nm=None` (the default) is a strict no-op, so existing callers
see byte-identical output. In practice column 29 is usually empty → the 0.10 default still fires. Overrides win
over EPW which wins over default; the optional cached-file hook (AERONET/CAMS) is the only non-default external
path and is never a live fetch.

² **Sub-physical albedo is missing data.** IWEC/TMY2 files write a literal `0.000` in col 32 for every hour as a
de-facto "no data" marker rather than the data dictionary's `999.0` sentinel — 4 of the 11 EPWs the
pre-release tree bundled did so, Athens included (the published tree ships only the Athens IWEC fixture). Nothing outdoors is a perfect absorber (fresh asphalt ≈0.04, calm deep water ≈0.03), so a
value at or below `_ALBEDO_MIN_PHYSICAL = 0.01` is rejected as missing and the 0.20 default applies with
`source: "default"`. Accepting `0.000` zeroed the entire ground-reflected term while reporting `source: "epw"`.
Enforced in both `epw_hourly` (parse layer) and `atmosphere.resolve` (for hand-built rows); an explicit override
always wins, and a genuinely dark surface survives (Chania's 0.07 still reads `source: "epw"`). See ADR-0004.

**Optional ozone climatology** (van Heuklon 1979; coded pure-Python in `atmosphere.van_heuklon_ozone`,
matching the canonical SPECTRL2 van Heuklon at `spectrl2_2.c:278‑299` **upstream** — no C source is bundled
in this tree; the alternative to the 300 DU default when a lat/month estimate is wanted). With $s_1=\sin\!\big(0.9865(n+c_4)\big)$,
$s_2=\sin\!\big(c_5(L'+c_6)\big)$, $s_3=\sin\!\big(c_2\phi\big)$ (arguments in degrees → radians):

$$
u_{O_3} = 0.235 + \big(c_1 + c_3 s_1 + 20\,s_2\big)\,\frac{s_3^2}{1000}\quad[\text{atm-cm}]\tag{M-7}
$$

Northern hemisphere ($\phi\ge0$): $c_1{=}150, c_2{=}1.28, c_3{=}40, c_4{=}-30, c_5{=}3, c_6{=}0$ (or $20$ if
$L'>0$, with $L'$ here in **east-positive** longitude). Southern: $c_1{=}100, c_2{=}1.5, c_3{=}30, c_4{=}152.625,
c_5{=}2, c_6{=}-75$. (Ozone is a sub-percent error source for mel-EDI, so the 300 DU default remains the v1
default; M‑7 is now **coded and opt-in**, not merely documented.)

> **Resolved, opt-in.** `atmosphere.van_heuklon_ozone(lat_deg, lon_deg, day_of_year)` implements Eq. (4)/Table 1
> above verbatim, and `derive(row, *, ozone_mode="climatology", lat_deg=…, lon_deg=…, day_of_year=…)` calls it in
> place of the 300 DU constant (tagging `provenance["ozone_atm_cm"] = {"source": "climatology", "method":
> "van_heuklon79"}`). `ozone_mode` defaults to `"constant"` — the byte-identical 300 DU behavior — and an explicit
> `ozone_atm_cm` override always wins regardless of `ozone_mode`. The three EPW-facing MCP tools
> (`atmosphere_from_epw`, `spectral_sky_from_epw`, `spectral_epw`) expose `ozone_mode`, and the annual path
> (`annual_records`) forwards it per-row so ozone varies by season across a year.

> **Verification vs primary source (van Heuklon 1979).** The constants above map **verbatim**
> to the paper's Eq. (4), $O_3 = J + \{A + C\sin[D(E+F)] + G\sin[H(\lambda+I)]\}\sin^2(\beta\phi)$ (matm cm), and its
> Table 1: $c_1\!=\!A$, $c_2\!=\!\beta$, $c_3\!=\!C$, $c_4\!=\!F$, $c_5\!=\!H$, $c_6\!=\!I$, the literal
> $20\!=\!G$ (longitude half-amplitude), and the $0.235 = J/1000$ equatorial base ($J=235$ matm cm → atm-cm). The
> N/S split ($A{=}150/100$, $\beta{=}1.28/1.5$, $C{=}40/30$, $F{=}-30/152.625$, $H{=}3/2$, $I{=}20|0\,/-75$)
> reproduces Table 1 exactly. **One paper-internal discrepancy:** the body text (p. 65) prints $D=0.9856$ (≈360/365.25)
> while **Table 1 prints $D=0.9865$ — and the upstream SPECTRL2 `spectrl2_2.c` uses 0.9865**, so the
> implementation follows Table 1, not the body value.
>
> **Independent primary-literature confirmation.** Karavana-Papadimou, Kambezidis et al. 2013
> (*Model for estimating atmospheric ozone content over Europe*, *Global NEST J.* **15**(2):152, §6 of the
> bibliography) reproduces this exact Northern-hemisphere form as its **eq. (2)** — same $A{=}150$, $C{=}40$,
> $F{=}-30$, $\beta{=}1.28$, $D{=}0.9865$, $J{=}235$ — confirming the ozone **maximum falls in NH spring**,
> minimum in autumn. This matters because the first plan transcription of `van_heuklon_ozone` used a garbled
> **hemisphere-symmetric** phase (offset $J{=}100/300$) that peaked in **summer**; it was corrected to the
> authoritative hemisphere-specific Table 1 coefficients above (pinned by published-value + spring$>$summer
> phase tests). Herman et al. 1993 (Nimbus-7 TOMS, §6) corroborates the spring-max/autumn-min latitude-season
> structure. **Lesson:** range-only tests hide phase errors — validate literature formulas against published
> point values.

```
ALGORITHM A  atmosphere.derive(row, overrides)
─────────────────────────────────────────────────────────────────────────────
resolve(field, epw_value, default):                               # provenance-tracked resolver
    if field in overrides: return overrides[field]  (source="override")
    if epw_value ≠ None:   return epw_value          (source="epw")
    else:                  return default            (source="default")

# precipitable water — never from the EPW precip column (unreliable):
if row.T ≠ None and row.RH ≠ None:  w ← gueymard94_pw(row.T, row.RH)      (method="gueymard94")   # (M-12)
elif row.Td ≠ None:                 w ← reitan63_pw(row.Td)               (method="reitan63")     # (M-13)
else:                               w ← 1.5  (default)
P  ← resolve(pressure, row.P_pa/100, 1013.25);   ρ ← resolve(albedo, row.albedo, 0.20)
τ₅₀₀ ← resolve(aod500, row.aod, 0.10);  u_O3 ← resolve(ozone, None, 0.30);  α ← resolve(alpha, None, 1.14)
return AtmosphericState{τ₅₀₀, α, w, u_O3, P, ρ, provenance}
```

---

## 7. Stage D — SPECTRL2 clear-sky engine

**Module:** `spectral_engine/spectrl2`. **Consumes:** `AtmosphericState`, `SolarGeometry`. **Produces:**
`ClearSkySpectra` — 122 wavelengths (300–4000 nm), direct-normal and sky-diffuse-horizontal, both in
**W m⁻² µm⁻¹** (`units=1`). Solar geometry is **passed in** (the engine never calls solpos, exactly like the
Fortran). All constants are the **C constants verbatim** (`spectrl2_2.c`); the known C‑vs‑Fortran drifts
(Rayleigh $1.3366$ vs $1.335$; uniform-gas $118.3$ vs $118.93$) are *not* "fixed". Rayleigh drifts $\le 0.047\%$ across the visible; uniform-gas drifts up to $0.19\%$ in the visible (762 nm O2-A band) and $1.40\%$ in the NIR at 2800 nm, so the older blanket "$<0.1\%$" understated it.

> **Source (M-9, M-11, M-14…M-24):** Bird & Riordan 1986, *Simple Solar Spectral Model for Direct and Diffuse Irradiance on Horizontal and Tilted Planes at the Earth's Surface for Cloudless Atmospheres*, J. Climate Appl. Meteorol. **25**:87 (≡ SERI/TR-215-2436).
> **Note:** the SPECTRL2 constants are taken verbatim from the reference `spectrl2_2.c`.

**Sources.** *Paper:* Bird & Riordan (1986), *Simple Solar Spectral Model for Direct and Diffuse Irradiance
on Horizontal and Tilted Planes at the Earth's Surface for Cloudless Atmospheres*, J. Climate Appl.
Meteorol. **25**:87 (≡ SERI/TR‑215‑2436) — all equations 2‑1…2‑11 and 3‑1…3‑18 (M‑14…M‑24), and the
$A[5][122]$ coefficient table. *Software (constants verbatim):* NREL `spectrl2_2/spectrl2_2.c` (2004 C
build); Fortran reference `spctral2_pc/SPCTRAL2_PC.f`; golden fixtures `SPCTRAL2_TAPE1/2.txt`,
`SPCTRAL2_OUTPUT.txt`. *Port:* `src/hcl_core/spectral_engine/spectrl2.py`, table `…/_spectrl2_data.py`.

The model is evaluated independently at each tabulated wavelength $\lambda_i$ ($i=0..121$), reading
$H_{0\lambda},\ a_w(\lambda),\ a_o(\lambda),\ a_u(\lambda)$ from the $A[5][122]$ table (TAPE2). Night
($z\ge 90^\circ$, $\cos z\le 0$, or $m=\infty$) returns all zeros.

### 7.1 Geometry & air masses

*Bird & Riordan 1986 (pressure-corrected & ozone air mass); `spectrl2_2.c`:*

$$
m_p = m\,\frac{P}{1013},\qquad
  m_o = \frac{1.003454}{\sqrt{\cos^2 z + 0.006908}}\tag{M-9, M-11}
$$

$m$ is Kasten–Young (M‑8); $m_p$ is the pressure-scaled air mass used for Rayleigh and uniform-gas; $m_o$ is
the ozone air mass. (Golden check: $z=79.94^\circ,P=816\Rightarrow m=5.55,m_p=4.47,m_o=5.19$ — matches
`SPCTRAL2_OUTPUT.txt`.)

### 7.2 Aerosol & single-scatter terms

Aerosol optical depth at $\lambda$ (Ångström law referenced to 500 nm, *Bird Eq. 2‑7*; $\lambda$ in µm so
$\lambda/0.5 = 2\lambda$):

$$
c_a(\lambda) = \tau_{500}\,(2\lambda)^{-\alpha}\tag{M-14}
$$

Wavelength-dependent single-scattering albedo (*Bird Eq. 3‑16*; $\omega_0=0.945,\ \omega'=0.095$ at 0.4 µm):

$$
\omega(\lambda) = \omega_0\,\exp\!\big(-\omega'\,[\ln(\lambda/0.4)]^2\big)\tag{M-15}
$$

Aerosol asymmetry $g=0.65$ (rural) is the default; **resolved, opt-in (D-7):** `AtmosphericState.aerosol_g`
(default `0.65`) is now a settable field — override it via `derive(overrides={"aerosol_g": …})` or the
`aerosol_g` MCP tool arg — and both the SPECTRL2 forward-scatter terms below and the single-scatter façade
colour in `receiver.py` consume it instead of the old `0.65` literal. Default `0.65` reproduces prior output
byte-for-bit. This gives the forward-scatter terms (*Bird Eq. 3‑12…3‑14*):

$$
\begin{aligned}
A_{\!f}&= \ln(1-g)\\
\mathrm{AFS}&= A_{\!f}\big(1.459 + A_{\!f}(0.1595 + 0.4129\,A_{\!f})\big)\\
\mathrm{BFS}&= A_{\!f}\big(0.0783 + A_{\!f}(-0.3824 - 0.5874\,A_{\!f})\big)\\
F_s&= 1 - \tfrac12\exp\!\big((\mathrm{AFS}+\mathrm{BFS}\cos z)\cos z\big)\\
F_{sp}&= 1 - \tfrac12\exp\!\big((\mathrm{AFS}+\mathrm{BFS}/1.8)/1.8\big)
\end{aligned}\tag{M-16}
$$

$F_s$ uses the actual sun position; $F_{sp}$ uses the fixed diffuse-path air mass $M'=1.8$ (§7.6).

### 7.3 Extraterrestrial scaling

*Bird & Riordan 1986 ($H_{0\lambda}$ from the $A[5][122]$ table) × Spencer-1971 ERV (M‑6):*

$$
H_{0\lambda}^{\text{(day)}} = H_{0\lambda}\cdot R_v\tag{M-17}
$$

### 7.4 Beam (direct-path) transmittances

Per wavelength, with the table coefficients $a_w,a_o,a_u$:

$$
\begin{aligned}
T_r(\lambda) &= \exp\!\Big[-\,m_p\big/\big(\lambda^4(115.6406 - 1.3366\,\lambda^{-2})\big)\Big] &&\text{Rayleigh, \textit{Eq. 2‑4}}\\
T_o(\lambda) &= \exp\!\big[-a_o\,u_{O_3}\,m_o\big] &&\text{ozone, \textit{Eq. 2‑9}}\\
T_w(\lambda) &= \exp\!\Big[-0.2385\,a_w\,w\,m\big/(1 + 20.07\,a_w\,w\,m)^{0.45}\Big] &&\text{water, \textit{Eq. 2‑8}}\\
T_u(\lambda) &= \exp\!\Big[-1.41\,a_u\,m_p\big/(1 + 118.3\,a_u\,m_p)^{0.45}\Big] &&\text{uniform gas, \textit{Eq. 2‑11}}\\
T_{as}(\lambda) &= \exp\!\big[-\omega\,c_a\,m\big],\quad
T_{aa}(\lambda) = \exp\!\big[(\omega-1)\,c_a\,m\big],\quad
T_{a}(\lambda) = \exp\!\big[-c_a\,m\big] &&\text{aerosol scat/abs/total, \textit{Eq. 3‑9,3‑10,2‑6}}
\end{aligned}\tag{M-18}
$$

### 7.5 Direct-normal spectral irradiance

*Bird Eq. 2‑1* (note: aerosol **scattering+absorption combined** via $T_a$, no $\cos z$ — this is the beam on
a surface normal to the sun):

$$
\boxed{\,I_{d\lambda} = H_{0\lambda}\,R_v\;T_r\,T_o\,T_w\,T_u\;T_a\,}\tag{M-19}
$$

### 7.6 Diffuse (sky) spectral irradiance on a horizontal plane

The diffuse path uses a fixed air mass $M'=1.8$ for its "primed" transmittances (*Bird §3.1*):

$$
\begin{aligned}
T_r' &= \exp\!\big[-1.8/(\lambda^4(115.6406-1.3366\,\lambda^{-2}))\big],\quad
T_w' = \exp\!\big[-0.4293\,a_w w/(1+36.126\,a_w w)^{0.45}\big]\\
T_u' &= \exp\!\big[-2.538\,a_u/(1+212.94\,a_u)^{0.45}\big],\quad
T_{as}' = \exp[-\omega c_a\,1.8],\quad T_{aa}' = \exp[(\omega-1)c_a\,1.8]
\end{aligned}\tag{M-20}
$$

Define the common factor $C_2 = H_{0\lambda}R_v\,T_o T_w T_u\,\cos z\,T_{aa}$ and the small-$\lambda$
forward-scatter correction $C_s$ (*Bird Eq. 3‑17*):

$$
C_s(\lambda) = \begin{cases}(\lambda+0.55)^{1.8} & \lambda \le 0.45\ \mu\text{m}\\ 1 & \lambda > 0.45\ \mu\text{m}\end{cases}\tag{M-21}
$$

The three diffuse components — **Rayleigh** (*Eq. 3‑5*), **aerosol** (*Eq. 3‑6*), and **ground back-scatter
multiple reflection** (*Eq. 3‑7*) — with the atmospheric back-reflectance $\rho_a$ (*Eq. 3‑8*):

$$
\begin{aligned}
\rho_a &= T_u' T_w' T_{aa}'\big[\,0.5(1-T_r') + (1-F_{sp})\,T_r'(1-T_{as}')\,\big]\\
I_r &= C_2\,(1 - T_r^{0.95})/2\\
I_a &= C_2\,T_r^{1.5}\,(1 - T_{as})\,F_s\\
I_g &= (I_{d\lambda}\cos z + I_r + I_a)\,\dfrac{\rho\,\rho_a}{1 - \rho\,\rho_a}
\end{aligned}\tag{M-22}
$$

$$
\boxed{\,I_{s\lambda} = (I_r + I_a + I_g)\,C_s\,}\tag{M-23\ (\textit{Bird Eq. 3‑1})}
$$

**Ground albedo.** The C source interpolates a 6-band spectral reflectivity $\rho(\lambda)$; **v1 uses a gray
$\rho = \text{atm.albedo}$** for all bands (spectral-albedo library deferred). The golden reference (TAPE1)
itself sets all six bands to $0.2$, so the gray path reproduces it exactly. Note $I_g$ couples the ground
into the *horizontal* diffuse even with no tilt — physically real (sky↔ground multiple reflection); the §8
energy-rescale to EPW DHI absorbs it.

### 7.7 Tilted-receiver mode (golden-test only; production uses tilt $=0$)

For the golden test, with surface tilt $\beta$, incidence $\theta_i$, $c_t=\cos\beta$, $c_i=\cos\theta_i$
(*Bird Eq. 3‑18*, beam fraction $f_b = I_{d\lambda}/H_{0\lambda}R_v$):

$$
I_{s\lambda}^{\text{tilt}} = \underbrace{I_{\text{tot}}\,\rho\tfrac{1-c_t}{2}}_{\text{ground onto tilt}}
  + \underbrace{I_{s\lambda} f_b\,\tfrac{c_i}{\cos z}}_{\text{beam-correlated}}
  + \underbrace{I_{s\lambda}(1-f_b)\tfrac{1+c_t}{2}}_{\text{isotropic sky}},\qquad I_{\text{tot}}=I_{d\lambda}\cos z + I_{s\lambda}\tag{M-24}
$$

In production $\beta=0$ → this branch is skipped → the record stores **horizontal sky-truth** (M‑19, M‑23).
Receiver-plane assembly for real receivers is **Radiance's job** on the transport path (§10, spec §6) —
though an optional pure-Python façade projector now also exists alongside it; see the note below.

> **Optional Python façade projector (`receiver.py`, not on the transport path).** The claim above is the
> *transport* contract and still holds for any Radiance run. Since it was written, an opt-in projector has
> been added that transposes the record's horizontal diffuse onto an oriented façade in Python —
> `receiver.oriented_diffuse_for_receiver(record, surface_az, tilt=90.0, mode=…)` — over the same
> Reinhart/Tregenza **MF:1 145-patch** dome and cosine-weighted integrator the validation scripts use, so
> production and analysis share one integrator. Three modes: `isotropic` (one colour for all façades, the
> historical behaviour; magnitude = the isotropic view factor), `perez` (Layer A angular magnitude only,
> colour still single), and `single_scatter` (Layer A magnitude × Layer B per-direction colour ratio).
>
> **Layer A** is the Perez 1993 relative luminance $l(\zeta,\gamma)=(1+a\,e^{b/\cos\zeta})(1+c\,e^{d\gamma}+e\cos^2\gamma)$,
> ported verbatim from Radiance `gendaylit.c` (`perez_distribution.py`, with its own Kasten 1965 air mass
> and $E_0 = 1367$ W·m⁻² — distinct from the §8.1 Kt constant 1361). **Layer B** is a first-order
> single-scatter colour ratio combining a Rayleigh $\lambda^{-4}$ lobe with a Henyey–Greenstein aerosol
> lobe, dome-mean-normalised and damped toward isotropy as $1+\eta(R-1)$ (`sky_radiance.py`).
>
> ⚠️ **Honesty.** $g = 0.65$ (the §6 `aerosol_g`) and $\eta = \texttt{DEFAULT\_ETA} = 0.5$ — and η is
> **the one fitted free parameter** in this layer. η is **empirical**: it was fitted against an internal
> dataset that is not published with this toolkit, and the fit constrains it to an **interval,
> η ∈ [0.19, 0.69]** (median-matching value 0.458), not a point. Any claim that η is "fitted" must carry
> the interval. Layer B is **`code-only`** — a first-order construction with no external standard — and this whole
> projector is validation/analysis-grade, not part of the canonical record.

### 7.8 Units & resolution caveat

Engine output is W m⁻² µm⁻¹ throughout (`units=1`); the µm→nm conversion happens only at resample (§9). The
122-point grid has only **34 points in 380–780 nm** (10 nm spacing in blue/green — fine for the melanopic
band; 20–26 nm in red — interpolation-bound). The record's provenance records that the 1 nm output is
**upsampled, not natively resolved** in the red.

### 7.9 The complete engine procedure

The full algorithm, mirroring `spectrl2_2.c` (geometry-as-input variant). Setup runs once; the transmittance
physics (§7.4–7.6) runs per wavelength. The **only** v1 deviation from the C is the gray ground reflectivity
(the native 6-band interpolation is shown for fidelity, marked).

```
ALGORITHM E  Spectrl2Engine.compute(atm, geo)
INPUT   AtmosphericState atm, SolarGeometry geo
OUTPUT  ClearSkySpectra {wavelength_nm[122], direct_normal[122], sky_diffuse_horizontal[122]}, W·m⁻²·µm⁻¹
─────────────────────────────────────────────────────────────────────────────
# ── night guard ──
cz ← cos(geo.zenith)
if geo.zenith ≥ 90° or cz ≤ 0 or geo.air_mass = ∞:  return zeros[122]

# ── setup (once) ──
m   ← geo.air_mass;  m_p ← m·atm.P/1013;  m_o ← 1.003454/√(cz² + 0.006908)          # (M-9, M-11)
g   ← atm.aerosol_g (assym, default 0.65);  ω₀ ← 0.945;  ω' ← 0.095
A_f ← ln(1−g);  AFS, BFS, F_s, F_sp  ← forward-scatter terms                         # (M-16)
# ground reflectivity — v1 uses a single scalar gray albedo (the C-native engine interpolates 6 bands):
ρ ← atm.ρ

# ── per-wavelength loop ──
direct[122], diffuse[122]
for i in 0..121:
    λ ← WL_UM[i];  H0 ← ET_H0[i]·geo.R_v;  (a_w,a_o,a_u) ← (ABS_H2O,ABS_O3,ABS_UMG)[i]   # (M-17)
    ω(λ)  ← ω₀·exp(−ω'·(ln(λ/0.4))²);   c_a ← atm.τ₅₀₀·(2λ)^(−atm.α)                  # (M-15, M-14)

    # beam transmittances (M-18) and primed diffuse-path transmittances (M-20):
    T_r,T_o,T_w,T_u,T_as,T_aa,T_a   ← …                                              # (M-18)
    T_r',T_w',T_u',T_as',T_aa'      ← …    (fixed M'=1.8)                             # (M-20)

    # direct normal (M-19):
    I_d ← H0·T_o·T_w·T_u·T_r·T_a;   direct[i] ← I_d

    # ρ(λ) = atm.ρ (scalar gray, set once above — the C reference would interpolate 6 bands here)

    # diffuse on horizontal (M-21..M-23):
    C₂ ← H0·T_o·T_w·T_u·cz·T_aa
    C_s ← (λ ≤ 0.45) ? (λ+0.55)^1.8 : 1
    ρ_a ← T_u'·T_w'·T_aa'·(0.5(1−T_r') + (1−F_sp)·T_r'·(1−T_as'))
    I_r ← C₂·(1 − T_r^0.95)/2;   I_a ← C₂·T_r^1.5·(1 − T_as)·F_s
    I_g ← (I_d·cz + I_r + I_a)·ρ·ρ_a/(1 − ρ·ρ_a)
    I_s ← (I_r + I_a + I_g)·C_s

    if tilt > 0 (golden only): I_s ← tilt transposition (M-24)
    diffuse[i] ← I_s

return ClearSkySpectra(wavelength_nm = WL_UM·1000, direct, diffuse, units="W/m^2/um")
```

The shipped Python engine uses a single scalar gray albedo $\rho(\lambda)=\text{atm.}\rho$, assigned once
before the wavelength loop (`spectrl2.py`). The C-native SPECTRL2 reference instead interpolates $\rho$ across
six reflectivity bands `wv[]`; but with a gray albedo every band is equal, so that interpolation is a no-op —
it reduces to this documented gray path and reproduces the all-bands-0.2 golden reference exactly.

---

## 8. Stage E — Cloud bridge (Nann–Riordan SEDES1)

**Module:** `cloud_modifier`. **Consumes:** the clear-sky `ClearSkySpectra` + EPW broadband $\mathrm{DNI},
\mathrm{DHI},\mathrm{GHI}$ + clearness $K_t$. **Produces:** all-sky `ClearSkySpectra` (full native range) +
provenance. Every physical engine is clear-sky; the EPW's DNI/DHI already include clouds. The modifier
reconciles them with a strict **energy / shape** split.

> **Source (M-25…M-29):** Nann & Riordan 1991, *Solar Spectral Irradiance under Clear and Cloudy Skies: Measurements and a Semiempirical Model (SEDES1)*, J. Appl. Meteorol. **30**:447 — clearness index §4/Table 3 (M-25), energy normalization Eq. 9 (M-27), CCM Eq. 11 (M-28).
> **Source (M-26):** Standard numerical quadrature (trapezoidal) — standard numerical method; implementation choice to serve the Nann & Riordan §8.2 bridge invariant.
> **Source (M-29):** Nann & Riordan 1991 (CCM shape term); diffuse renormalization is this implementation's mechanism — CCM fitted to global-horizontal in paper; renormalization applied to diffuse (see §8.3 caveat).

**Sources.** *Paper:* Nann & Riordan (1991), *Solar Spectral Irradiance under Clear and Cloudy Skies:
Measurements and a Semiempirical Model (SEDES1)*, J. Appl. Meteorol. **30**:447 — the clearness index (§4,
Table 3), the energy normalization (Eq. 9 → M‑27), and the cloud-cover modifier CCM (Eq. 11 → M‑28; A/B/C
curves in Fig. 11; class-mean $\bar R(\lambda)$ in Fig. 10; error budget Fig. 12). *Software:*
`src/hcl_core/cloud_modifier.py`; coefficients in `src/hcl_core/_sedes1_data.py` (digitized from Fig. 10).
The trapezoidal quadrature (M‑26) and the diffuse renormalization (M‑29, shape-only) are this
implementation's mechanics around the paper's model.

### 8.1 Clearness index

With broadband solar constant $1361\,\mathrm{W\,m^{-2}}$ (modern WMO value; a *normalization* constant
decoupled from any engine's internal ETR — SMARTS keeps its native 1367, SPECTRL2 its $H_{0\lambda}$ table):

$$
I_0 = 1361\,R_v,\qquad K_t = \operatorname{clamp}\!\Big(\frac{\mathrm{GHI}}{I_0\cos z},\,0,\,1.2\Big)\tag{M-25}
$$

$K_t=0$ at/below the horizon. (This is the SEDES1 cloud variable, *Nann §4*; Table 3 of the paper spans
$K_t\in[0.11,0.89]$, mean 0.67.)

### 8.2 Energy normalization — the bridge invariant (always on)

The broadband integral over the **full native range** (trapezoidal quadrature — *numerical method;
`cloud_modifier.broadband_integral`*, W m⁻² µm⁻¹ × µm → W m⁻²):

$$
\mathcal{B}[I] = \int_{300\,\text{nm}}^{4000\,\text{nm}} I(\lambda)\,d\lambda \approx \sum_i \tfrac12\big(I_i+I_{i+1}\big)(\lambda_{i+1}-\lambda_i)\tag{M-26}
$$

Per-component grey scale factors so the scaled spectra match EPW broadband (the **bridge invariant**) —
*Nann & Riordan 1991, Eq. 9 (per-component energy baseline):*

$$
k_{\text{dir}} = \frac{\mathrm{DNI}}{\mathcal{B}[I_{d\lambda}^{\text{clear}}]},\qquad
  k_{\text{dif}} = \frac{\mathrm{DHI}}{\mathcal{B}[I_{s\lambda}^{\text{clear}}]}\tag{M-27}
$$

$$
I_{d\lambda}' = k_{\text{dir}}\,I_{d\lambda}^{\text{clear}},\qquad I_{s\lambda}' = k_{\text{dif}}\,I_{s\lambda}^{\text{clear}}
$$

**Order matters:** the 380–780 visible slice is only ~40–50 % of broadband DNI, so matching a visible-only
integral to broadband DNI would over-scale ~2×. Therefore: integrate and scale on the **full range first**,
narrow to 380–780 *after* (§9). $k_{\text{dir}},k_{\text{dif}}$ and the clear-sky integrals are stored in
provenance so the invariant stays auditable from the visible-only record. If a clear-sky integral is ~0
(night), that component stays zero with $k=0$.

### 8.3 The cloud-cover modifier CCM(λ, Kt)

> **Source (M-28, M-28a):** Nann & Riordan 1991, Eq. 11 — A/B/C coefficients are figure-digitized from Fig. 10/11 only; no published table.

*Nann Eq. 11* — a per-wavelength quadratic in the clearness index:

$$
\mathrm{CCM}(\lambda, K_t) = A(\lambda) + B(\lambda)\,K_t + C(\lambda)\,K_t^2\tag{M-28}
$$

It is the ratio (all-sky spectral shape)/(clear-sky spectral shape) as a function of $K_t$ — clouds raise
relative transmission in the UV/blue (cloud "blueing"). At clear $K_t$ it is ≈1 (flat), so clear hours pass
through nearly unchanged.

**Coefficient derivation (figure-only source → digitization).** The paper derives $A,B,C$ from a **full
quadratic regression over all measured $R(\lambda)$ records** and publishes the result **only as the Fig. 11
curves** — never as a table — on a 300–1100 nm @10 nm grid (the paper states this is "an array consisting of
246 values"). The implementation does **not** digitize Fig. 11 directly. Instead it reconstructs the
coefficients from **Fig. 10**'s three class-mean $\bar R(\lambda)$ curves — sky classes *overcast / all /
clear* (Fig. 10 panels b / a / c) — each **assigned a representative clearness ($K_t = 0.25 / 0.50 / 0.70$;
this assignment is the implementation's choice, not the paper's — Table 3 is the PWV/$K_t$ range table, not a
class→$K_t$ map)** and solving the $3\times3$ Vandermonde system per wavelength:

$$
\begin{pmatrix}1 & K_1 & K_1^2\\ 1 & K_2 & K_2^2\\ 1 & K_3 & K_3^2\end{pmatrix}
  \begin{pmatrix}A\\B\\C\end{pmatrix} = \begin{pmatrix}\bar R_1\\ \bar R_2\\ \bar R_3\end{pmatrix}\tag{M-28a}
$$

Cross-check (passes): $B(400\,\text{nm})\approx -3.5$ matches Fig. 11; CCM$\to 1$ flat at clear $K_t$; CCM(blue)
$>$ CCM(red) at overcast $K_t$. Outside the digitized range the coefficients pass through as $(1,0,0)$,
i.e. CCM ≡ 1 (no reshape) — see §8.6.

> **⚠️ The production default is not the 9-anchor seed.** The text in §8.3 and §8.5 below describes the
> **9-anchor seed** derivation, which `_sedes1_data.py` retains **only as the `seed` variant**. The default
> is the faithful Fig. 11 WebPlotDigitizer digitization (A/B/C/σ on a 10 nm grid 330–1100 nm,
> `_sedes1_fig11.csv`) — `Sedes1Modifier(variant="reanchored")`. Provenance labels are **variant-aware** (`Sedes1Modifier._BASIS`, `cloud_modifier.py`): `reanchored`/`verbatim` emit
> `ccm_basis="fig11-faithful"`, `coeff_method="webplotdigitizer_fig11"`; `seed` emits `ccm_basis="seed-9anchor"`,
> `coeff_method="eyeballed_seed"`; `local` (§8.6) emits `ccm_basis="local-fit"`, `coeff_method="local_recalibration"`.
> Every variant also carries `ccm_variant=<variant>`, a `ccm_source` key (the local coeffs CSV path / fit
> metadata, `None` for non-local variants), and the regression uncertainty `ccm_sigma`/`ccm_sigma_mean` (see
> below). **See §8.6 for the provenance.**
>
> **Stored resolution ≠ paper resolution (seed variant).** What the seed held is a **9-anchor seed**
> (`SEED_WL_NM = [350, 400, 450, 500, 600, 700, 800, 950, 1050]` nm), linearly interpolated and endpoint-clamped
> — *not* the paper's 246-value 10 nm grid. So the seed coefficients are a coarse 9-point reconstruction of
> Fig. 10's class means, two reductions removed from the paper's regression (Fig. 11 → 246 values). The
> shipped default digitizes Fig. 11 directly at 10 nm (§8.6).

> **Fidelity caveats (documented, source-validated):**
>
> 1. **Global-fit applied to diffuse.** The paper fits CCM to *global*-horizontal $\bar R$ (its $\bar R$ uses
>    only global-horizontal measurements, ÷ clear-sky simulation, normalized at 630 nm). v1 **applies the CCM
>    shape to the diffuse component** and renormalizes to DHI. This is an approximation the paper does *not*
>    validate (the global ratio is diluted by the less-blue direct beam, so it slightly over-weights diffuse
>    blueing). Recorded in provenance as `ccm_basis="fig11-faithful"` for `reanchored`/`verbatim` (the `seed`
>    variant now records `ccm_basis="seed-9anchor"`).
>    **Status: addressable via `cloud_variant='local'` + a local fit** — fitting the CCM directly to
>    *measured diffuse* shape-ratios (rather than inheriting the paper's global-horizontal fit) removes this
>    approximation for the recalibrated site. See [`docs/recalibrating-cloud-ccm.md`](recalibrating-cloud-ccm.md).
> 2. **3-class solve ≠ full regression, at 9 anchors.** The paper's $A,B,C$ come from a quadratic regression
>    over *all* $R(\lambda)$ records (Fig. 11, 246 values); the $3\times3$ class-mean solve at **only 9
>    wavelengths** is a doubly coarser approximation, and Fig. 10's $\sigma$ is large in the overcast UV/blue.
>    Digitization uncertainty is real (provenance now `coeff_method="webplotdigitizer_fig11"` for
>    `reanchored`/`verbatim`; the `seed` variant now records `coeff_method="eyeballed_seed"`, retiring the legacy
>    `fig10_3class_solve` string), and the 9-anchor arrays are a seed (above), no longer the default.
>    **Status: addressable TWO ways.** (i) `cloud_variant='local'` + a local fit — `hcl_core.sedes1_fit.fit_ccm`
>    runs a full per-wavelength least-squares quadratic over every measured record on the record's own
>    wavelength grid, replacing both the 9-anchor coarseness and the 3-class solve with a direct regression
>    (see [`docs/recalibrating-cloud-ccm.md`](recalibrating-cloud-ccm.md)). (ii) ⚠️ **the digitisation is
>    avoidable outright** — the same regression is **tabulated** in Whitaker & Newmiller 1998
>    (NREL/SR-520-23942 Table 2-1) and ships opt-in as `Sedes2Modifier`, so "figure-digitised" describes this
>    *default*, not the state of the literature. Note (ii) is a **model swap, not a coefficient swap** (six
>    coefficients, a 1/cos z term, and NGH in place of $K_t$) — see §8.6(f).
> 3. **PWV omitted from the shape term.** PWV is a genuine SEDES1 input but enters the clear-sky baseline; its
>    dominant signature (~940 nm) is outside 380–780, so v1's shape term is driven by $K_t$ alone (not $w$).
>    **Status: documented Kt-only limit; a local fit inherits it** — `fit_ccm` regresses shape-ratio against
>    $K_t$ exactly as the paper does, so recalibration does not add a PWV term; this remains a structural
>    limit of the SEDES1 CCM form itself, not something a local refit can close.
> 4. **Germany-only, single-AOD fit, applied globally.** The CCM coefficients were fit to the **German site
>    only** (p. 458: the U.S. dataset "lacks sufficient data with $K_t$ < 0.6") with aerosol optical depth
>    fixed at **AOD₅₀₀ = 0.23** (Stuttgart). hcl-mcp applies them at every site/aerosol regime — a
>    site-transfer the paper neither intends nor validates.
>    **Status: addressable via `cloud_variant='local'` + a local fit** — fitting against a given site's own
>    measured diffuse spectra and Kt (any AOD regime) replaces the Germany/AOD₅₀₀=0.23 transfer with
>    coefficients native to that site. See [`docs/recalibrating-cloud-ccm.md`](recalibrating-cloud-ccm.md).
> 5. **CCM also absorbs SPECTRL2's own clear-sky bias.** Per the paper (p. 458), the CCM "also corrects errors
>    identified in section 4" — incorrect water-vapour/aerosol/ozone inputs and the ~10 % SPCTRAL2 bias below
>    400 nm. So the modifier is partly a clear-sky-model-bias sponge, **not pure cloud physics**.
>    **Status: documented; two independent corrections exist for clear-sky bias — do not stack them.** The
>    `reanchored` default (unity at clear $K_t$, §8.4/M-29a) and the optional clear-sky engine-bias layer
>    `clearsky_bias.py` (`K(λ)`, default-off, §8.6/P5, applied at build-record step 3a) both target this same
>    bias from different angles; a local CCM refit (caveat items above) does **not** remove this coupling —
>    a locally-fit CCM still partly absorbs whatever clear-sky bias is present in the measured-vs-reference
>    ratios it was fit against. Provenance flags both mechanisms when active (`ccm_variant`/`ccm_basis` for
>    the CCM choice, `clearsky_corrected` for the K(λ) layer), so a record can always be audited for whether
>    one or both are in effect.
> 6. **Summer/fall regression merged.** The paper computed $A,B,C$ *"separately for summer and fall"* to
>    improve the correlation; the implementation carries a single season-independent set.
>    **Status: addressable via `cloud_variant='local'` + a local fit** — fitting separate CCM CSVs from
>    season-partitioned measured data (e.g. one `fit_ccm` call per season, each written with
>    `write_ccm_csv`) and loading the matching one per `spectral_sky_from_epw`/`spectral_epw` call recovers
>    the paper's season-split intent; there is no seasonal switch built into the pipeline itself, so this is
>    a caller-side recalibration workflow. See [`docs/recalibrating-cloud-ccm.md`](recalibrating-cloud-ccm.md).
>
> In all cases the **energy-rescale (§8.2) keeps every hour broadband-correct regardless** — a weak/
> uncertain CCM degrades gracefully to a grey-cloud result, never a broadband error. The paper's own accuracy
> budget (Fig. 12): σ ≈ 5 % VIS clear, 7 % VIS overcast, up to 15 % in the UV and 18 % at the 940 nm
> water-vapour band.
>
> **Regression uncertainty is now surfaced, not just documented.** `Sedes1Modifier` (all variants) emits
> per-hour `ccm_sigma` (the fit's per-wavelength regression standard error at {400, 500, 600, 700} nm) and
> `ccm_sigma_mean` in record provenance — the same `sigma` column a local fit writes via
> `hcl_core.sedes1_fit.write_ccm_csv`. For the shipped `reanchored`/`verbatim`/`seed` variants this is the
> Fig. 10/11 digitization σ; for `cloud_variant='local'` it is the caller's own regression σ, so a
> sparse/narrow-$K_t$ local dataset is visible in the output record itself rather than only in an offline
> fit report. See [`docs/recalibrating-cloud-ccm.md`](recalibrating-cloud-ccm.md) for how to read it.

> **Related approaches & evidence the gap is real (context, ground no equation — see
> `literature-bibliography.md` §6):** the cloudy-sky spectrum is reached differently by Wang et al. 2025
> (*Renew. Energy* **256**:124417 — a measurement-trained XGBoost + sky-imager, "spectral skewness"), and
> Paudyal et al. 2024 (*Renew. Energy* **224**:120057 — measured high-latitude APE shows a bimodal
> clear/cloudy winter). They are **alternatives to** this SEDES1 bridge and independent evidence that
> spectral mis-estimation under cloud is real and climate-dependent — they do **not** validate these CCM
> coefficients (which remain figure-digitized and never measurement-validated, §13).

### 8.4 Diffuse reshape + renormalization (shape-only)

Apply CCM to the energy-normalized diffuse, clamp non-negative, then **renormalize back to DHI** so the bridge
invariant (M‑27) is preserved (shape-only — direct keeps its grey-scaled clear-sky shape). *Nann & Riordan
1991 supplies the CCM shape (Eq. 11); the renormalization is this implementation's mechanism
(`Sedes1Modifier.apply`) to keep the §8.2 bridge exact:*

$$
\tilde I_{s\lambda} = \max\!\big(0,\ \mathrm{CCM}(\lambda,K_t)\big)\,I_{s\lambda}',\qquad
  I_{s\lambda}'' = \tilde I_{s\lambda}\cdot \frac{\mathrm{DHI}}{\mathcal{B}[\tilde I_{s\lambda}]}\tag{M-29}
$$

> **Shipped default = `reanchored` (the operative $\mathrm{CCM}$ in M-29).** The $\mathrm{CCM}(\lambda,K_t)$ in
> M-28/M-29 above is the **`verbatim`** form. The production default `Sedes1Modifier(variant="reanchored")`
> evaluates instead the **re-anchored** modifier — divided by its own clear-$K_t$ value so it is unity at the
> clear point (a pure cloud term, with the clear-sky-engine bias handled separately by the §8.6 / P5 layer):
> $$\mathrm{CCM}'(\lambda,K_t) = \frac{\mathrm{CCM}(\lambda,K_t)}{\mathrm{CCM}(\lambda,\,K_{t,\text{clear}})},\qquad K_{t,\text{clear}} = 0.70\ (\texttt{KT\_CLEAR})\tag{M-29a}$$
> So in M-29 read $\mathrm{CCM} \to \mathrm{CCM}'$ for the default path. `verbatim` uses M-28 directly; `seed`
> uses the retired 9-anchor coefficients (§8.3). See §8.6 for the variant provenance and B(400) values.

If $K_t$ or the coefficients are unavailable, $\mathrm{CCM}\equiv 1$ (grey cloud) and only the energy-rescale
acts. Output: $(I_{d\lambda}',\,I_{s\lambda}'')$ on the full native range + provenance
$\{k_{\text{dir}},k_{\text{dif}},\mathcal{B}^{\text{clear}}_{\text{dir}},\mathcal{B}^{\text{clear}}_{\text{dif}},K_t,\text{ccm\_applied},\text{cloud\_model},\text{ccm\_basis},\text{coeff\_method},\text{ccm\_variant},\text{ccm\_source},\text{ccm\_sigma},\text{ccm\_sigma\_mean}\}$.

### 8.5 Algorithms

```
ALGORITHM B  broadband_integral(I[], λ_um[])           # trapezoid, W·m⁻²·µm⁻¹ × µm → W·m⁻²   (M-26)
  return Σ_{i} ½·(I[i]+I[i+1])·(λ_um[i+1] − λ_um[i])

ALGORITHM C  energy_normalize(clear, DNI, DHI)          # per-component grey bridge scale   (M-27)
  λ_um ← clear.wavelength_nm / 1000
  𝓑dir ← broadband_integral(clear.direct,  λ_um);  𝓑dif ← broadband_integral(clear.diffuse, λ_um)
  k_dir ← (𝓑dir > ε) ? DNI/𝓑dir : 0;   k_dif ← (𝓑dif > ε) ? DHI/𝓑dif : 0
  return scaled{direct·k_dir, diffuse·k_dif}, {k_dir,k_dif, clear_dni_bb:𝓑dir, clear_dhi_bb:𝓑dif}

ALGORITHM D  ccm_coeffs(λ_nm)                           # derive A,B,C from Fig.10 then interp   (M-28a)
  PREP (once, offline → _sedes1_data.py):
    SEED grid = [350,400,450,500,600,700,800,950,1050] nm   # 9 anchors only (placeholder; extend to 300@10nm)
    for each anchor wavelength w in the seed grid:
        solve  [1 K₁ K₁²; 1 K₂ K₂²; 1 K₃ K₃²]·[A B C]ᵀ = [R̄_overcast R̄_all R̄_clear]ᵀ   # Cramer's rule
        with (K₁,K₂,K₃) = (0.25, 0.50, 0.70)            # impl-assigned class clearness (NOT Table 3)
    store A_λ[], B_λ[], C_λ[]                            # 9-value arrays
  LOOKUP: linear-interpolate (A,B,C) at λ_nm within [330, 1100] nm; outside it return (1,0,0) → CCM≡1

ALGORITHM E′  Sedes1Modifier.apply(clear, DNI, DHI, GHI, Kt, geo)            # §8.2 + §8.4
  scaled, info ← energy_normalize(clear, DNI, DHI)                # always-on bridge invariant
  for each (λ, d) in scaled.diffuse:                             # CCM shape on the diffuse
      (A,B,C) ← ccm_coeffs(λ);   reshaped[λ] ← max(0, A + B·Kt + C·Kt²) · d
  renorm ← DHI / broadband_integral(reshaped, λ_um)              # restore DHI (shape-only)   (M-29)
  scaled.diffuse ← reshaped · renorm
  return scaled, info ∪ {Kt, ccm_applied:True, ccm_basis:"fig11-faithful",
                         coeff_method:"webplotdigitizer_fig11", ccm_variant:<variant>}
```
*(The pseudocode above traces the original seed derivation for reference; the shipped default loads the faithful
Fig. 11 coefficients and emits the `fig11-faithful` provenance shown here — see §8.6.)*

> **Grey-fallback provenance.** When the clearness index `Kt` is unavailable (`kt is None`), the CCM is skipped
> (`cloud_modifier.py:114-122`): only the always-on energy rescale runs, the diffuse keeps its clear-sky shape, and
> the emitted provenance strings are **`ccm_basis="grey-fallback"`**, **`coeff_method="none"`**, **`ccm_applied=False`**
> — distinct from the `fig11-faithful` / `webplotdigitizer_fig11` strings above.

Cramer's rule for the $3\times3$ in Algorithm D: with Vandermonde matrix $M$ and right-hand side $\mathbf r$,
$A=\det M_A/\det M$, etc., where $M_A$ is $M$ with column 0 replaced by $\mathbf r$ (columns 1,2 for $B,C$).

### 8.6 Coefficient provenance

**What ships.** The default A/B/C coefficients come from a **human-in-the-loop WebPlotDigitizer
digitization of Nann & Riordan (1991) Fig. 11** (and Fig. 10), on a 10 nm grid 320–1100 nm with a
per-coefficient σ. The 320 nm row digitizes A and C only — B is blank, outside reliable range — so the
*usable* CCM range, which requires all of A/B/C, is **330–1100 nm**; `ccm_coeffs` passes through
`(1,0,0)` outside it. The artifacts live at `docs/Coefficient provenance/`; of these only the coefficient
table `fig11_CCM_coefficients.csv` is redistributed — the `fig10_R_lambda.csv` reconstruction, the
interactive `spectral_cloud_modifier_dashboard.html` and the source PDF are not. The production
implementation loads them from `src/hcl_core/_sedes1_data.py`, and `Sedes1Modifier` supports
`verbatim` (faithful coefficients, unanchored), `reanchored` (faithful shape reanchored to clear-sky CCT,
**the default**), `seed` (the original 9-anchor approximation, retained for comparison) and `local`
(caller-supplied re-fitted coefficients).

**Why human-in-the-loop.** An automated 400 DPI trace of Fig. 11 was tried and **rejected**: it disagreed
with the paper's own published cross-check ($B(400\,\text{nm})\approx-3.5$) and found no cluster there.
The failure modes are inherent to a 1991 scan of four overlapping curves — y-axis ticks and the bottom
frame contaminate columns, the broken line styles drop pixels, inline letter labels sit on the curves, and
all four curves cross near 850–1000 nm. Shipping auto-traced numbers would have been fabricated precision.

**Why the seed variant is still coherent within the visible.** The final record is
`GRID_NM = 380..780 @1nm` (`hcl_core/spectral_sky.py`); CCM is evaluated on the native grid, then narrowed
to 380–780 for all α-opic work. Within **380–780 nm the 9-anchor seed is fully covered** (anchors at
400/450/500/600/700, interpolated from 350 & 800). Coefficients outside 380–780 enter only **second-order**,
via the DHI-renormalization integral (M-29).

**What the digitization revealed.** The seed B(400) = −3.55 is materially too steep — the faithful Fig. 11
value is **B(400) = −2.037** (the −3.5 value in the paper's published cross-check is actually near the
~340 nm value — the digitization gives **B(340) = −3.877** — not 400 nm). Verified Kt-sweep at Kt = 0.25
(diffuse CCT): seed → 16 763 K, faithful-verbatim → 11 982 K, faithful-reanchored → 14 601 K. The
clear-sky SPECTRL2 baseline **at this synthetic sweep condition** is 10 565 K before any cloud modifier.
⚠️ That figure belongs to the sweep's own fixture geometry (`test_kt_sweep_cct_regression`, arbitrary
coordinates) and is **not** a measure of the engine's clear-sky blue bias — it understates it. The
residual divergence after the faithful digitization reflects the SPECTRL2 clear-sky blue bias, which the
opt-in `clearsky_bias` K(λ) layer addresses, not the CCM coefficients.

**Two implementation caveats on the K(λ) layer.** First, `ClearSkyBiasCorrection.apply` reshapes on the
**engine's native grid — only 34 points across 380–780 nm** (§7.8) — and `build_record` resamples to 1 nm
*afterwards*, so K is sampled at ~12 nm spacing, not at all 401 wavelengths; applying the same K
post-resample is a different operation and is not a reachable route. Second, the artifact is **keyed per
engine**: `_ART` maps only `"spectrl2"` to a shipped K(λ) CSV, so `engine="smarts"` with the correction
enabled yields **no correction and no error** — `clearsky_corrected: False` is reported honestly, but
nothing raises.

Caveats 4–6 in §8.3 (Germany-only/AOD 0.23, SPECTRL2-bias absorption, season-merge) are inherent to the
SEDES1 fit itself and are unchanged by re-digitization.

**Where the coefficients are also tabulated.** Of the sources that describe SEDES1/SEDES2, only one prints
usable numbers:

| Source                          | What it gives                        | Coefficients as numbers?                                           |
| ------------------------------- | ------------------------------------ | ------------------------------------------------------------------ |
| Nann & Riordan 1991 (SEDES1)    | CCM$=A+B K_t+C K_t^2$, Eq. 11      | **No** — only Fig. 11 curves (246 values, plotted)          |
| Nann & Emery 1992 (SEDES2)      | 4 modifiers/wavelength × zenith bin | **No** — statistically derived, site-dependent, not printed |
| NREL/TP-520-47277 (2010)        | uses SEDES2 code for PV mismatch     | **No** — points to "NREL's SEDES2 code"                     |
| Bartlett et al. 1998            | own BRGC cloud model                 | **No** — cites Nann, reproduces nothing                     |
| **Whitaker & Newmiller 1998**   | **SEDES2 CCM, Table 2-1, 320–1050 nm @10 nm** | **YES — 74 rows, tabulated.** NREL/SR-520-23942, free, no copyright restriction |

**SEDES2 is a different model, not a drop-in fix.** Nann & Emery 1992 replaces SEDES1's single $K_t$
quadratic with **four cloud-cover modifiers per wavelength, binned by solar zenith**, statistically
re-derived and *"slightly site dependent"* (built on Stuttgart DWD data 1987–1989; output 300–1400 nm
@10 nm, extended to 2500 nm in the NREL code). It is arguably a **better** model — Nann found a zenith
dependence the SEDES1 quadratic cannot represent — but adopting it is a **model swap with new
provenance**, not a recovery of the SEDES1 numbers.

**The SEDES2 code is not public; the coefficients did not need it.** Per pvlib issue
[#1669](https://github.com/pvlib/pvlib-python/issues/1669), implementations exist — Bill Marion's C# (used
in TP-520-47277), a Python translation by @shirubana, both descended from the original **ZSW Fortran dated
1 Aug 1992** — but all were shared via private communication, never committed to a public repo or merged
into pvlib. A GitHub-wide code search returns **zero** public copies. The coefficients, however, are
tabulated in a free PDF and **ship here** as `Sedes2Modifier`.

**Source.** Whitaker, C.M. & Newmiller, J.D. (1998), *Photovoltaic Module Energy Rating Procedure — Final
Subcontract Report*, **NREL/SR-520-23942, Table 2-1, pp. 19–20**
(<https://docs.nrel.gov/docs/legosti/old/23942.pdf>) — 74 rows, 320–1050 nm at 10 nm, a US Government
contractor report distributed without copyright restriction. Transcribed from the primary PDF with four rows
spot-checked against a visual read of the rendered page (320, 640, 760, 1050 — the latter two being where the
text-layer OCR was damaged). The retrieval-and-transcription provenance record is held in an internal
validation tree that is not part of this repository; the values themselves ship in
`src/hcl_core/_sedes2_data.py`, and `tests/test_sedes2.py` pins them against the primary source, asserting
the shipped module cannot drift from it.


**⚠️ It is more than a coefficient swap — the model form differs in TWO structural ways**, which is why it
ships as a separate class (`Sedes2Modifier`, `src/hcl_core/cloud_modifier.py`) rather than a `Sedes1Modifier`
variant:

1. **Six coefficients, not three — there is a zenith term** (report Eq. 2-39):

$$\mathrm{CCM}(\lambda, \mathrm{NGH}, z) = \Big(A_1 + \tfrac{A_2}{\cos z}\Big) + \Big(B_1 + \tfrac{B_2}{\cos z}\Big)\mathrm{NGH} + \Big(C_1 + \tfrac{C_2}{\cos z}\Big)\mathrm{NGH}^2$$

   The shipped three-term $A + B K_t + C K_t^2$ has no way to represent this, so in SEDES1 the zenith
   dependence is absorbed into the fitted $A/B/C$.

2. **The independent variable is NGH, not the clearness index $K_t$** (report Eq. 2-43):

$$\mathrm{NGH} = \frac{H_{H,\mathrm{meas}}}{H_{s,H,\mathrm{est}} + H_{d,\mathrm{est}}\cos z}$$

   measured broadband global horizontal over the **estimated clear-sky** global horizontal.
   `cloud_modifier.clearness_index` divides by the **extraterrestrial** horizontal instead. Under clear sky
   NGH → 1 while $K_t$ → ~0.7, so they are **not interchangeable even approximately**. NGH is clamped to
   $[0,\,1.5]$ (and returns `None` when `clear_ghi` is absent or $\le 10^{-9}$, rather than dividing by ~0
   and reshaping on noise). Accordingly
   `Sedes2Modifier.apply` **refuses to run** without a clear-sky GHI reference (and where $\cos z \le 0.05$,
   since $1/\cos z$ diverges), falling back to a grey unity CCM rather than silently evaluating the polynomial
   off its fitted domain.

**No published figure has moved.** SEDES2 is **opt-in**; nothing in `src/` constructs it, and every §5/§6
figure computed with the SEDES1 default still reproduces byte-identically. ⚠️ **It is not reachable over
MCP**: the `cloud_variant` argument accepts only `reanchored`/`verbatim`/`seed`/`local`, every one of which
builds a `Sedes1Modifier`. Using SEDES2 means constructing it directly in Python — and supplying the
clear-sky GHI reference it needs for NGH.

> 🚨 **The trap on the injection route — "refuses to run" does not mean "raises".** `record_from_epw` and
> `annual_records` both accept a `modifier=` argument, so a caller *can* inject `Sedes2Modifier()` as a
> first-class parameter. **But `build_record` never passes `clear_ghi=`** (`spectral_sky.py:110` — the `modifier.apply` call), and
> `Sedes2Modifier.apply` needs it to form NGH. Injected through the pipeline as it stands, the modifier
> therefore takes its **grey path** — `ccm_applied: False`, diffuse keeps its clear-sky shape, the
> energy-rescale still exact — rather than raising. The refusal is a refusal to *evaluate the polynomial on
> the wrong variable*, not an exception. So **a caller who simply swaps the modifier gets an un-reshaped
> diffuse, not SEDES2, and no error says so.** Read `ccm_applied` before quoting any overcast number as
> SEDES2-derived. Supplying the NGH denominator needs a clear-sky GHI reference an EPW cannot provide.

That is deliberate: adopting SEDES2
**changes overcast colour and requires a re-run before any overcast number is re-quoted**. It is also
**not validated** — no overcast figure in these docs has been recomputed under it.

**What this retires, and what it does NOT.** Of the six §8.3 fidelity caveats, the **digitisation** caveat (2)
becomes avoidable — the coefficients are tabulated rather than eyeballed. ⚠️ **Caveat (4), the
German-site-only framing, is NOT wrong and must not be "corrected" to say four sites**: Nann & Riordan measured at
four sites, but p. 448 states data from the **German site** were used to develop the clear- and cloudy-sky
semiempirical model, so the *fit* is German-site-only. Two further facts read from that source **strengthen**
existing caveats rather than retiring them: the SEDES station measured on a **48° south-tilted plane**, so
caveat (1)'s "fit to global, applied to diffuse" is really *tilted*-global; and the instrument was a **LI-COR
LI-1800**, 10 nm step / 6 nm bandpass, with ~4 % stated absolute uncertainty over 400–1000 nm. ⚠️ The 1040 nm
and 1050 nm rows are **byte-identical in Table 2-1** — verified in the source PDF, not a transcription
artefact — so the terminal 10 nm carries no independent information.

**Local recalibration closes the site-transfer caveats, not the structural ones (`sedes1_fit`).**
`Sedes1Modifier(variant="local", coeffs=, sigma=)`, backed by the pure-Python fitter
`hcl_core.sedes1_fit.fit_ccm`/`write_ccm_csv`/`load_ccm_csv`, lets a caller re-derive $A,B,C,\sigma$ per
wavelength from their own measured diffuse spectra + $K_t$ (any site, any season split, any aerosol regime)
instead of inheriting the Fig. 10/11 digitization. This directly addresses caveats **#1, #2, #4, #6** above
(global-fit-on-diffuse, 3-class/9-anchor coarseness, Germany/AOD₅₀₀=0.23 transfer, season-merge) — each
becomes a property of the caller's own dataset rather than a fixed inheritance from the paper. Caveats **#3**
(Kt-only shape term, no PWV) and **#5** (CCM/clear-sky-bias coupling) are **not** closed by recalibration —
#3 is intrinsic to the CCM's functional form, and #5 is inherited by any CCM (shipped or local) fit against
real diffuse spectra, because SPECTRL2's own clear-sky bias is baked into the measured-vs-clear ratio being
fit. The regression's own per-wavelength $\sigma$ is carried through to record provenance
(`ccm_sigma`/`ccm_sigma_mean`, §8.3) for both the shipped and local variants, so recalibration quality is
auditable from the output record. Full workflow: [`docs/recalibrating-cloud-ccm.md`](recalibrating-cloud-ccm.md).

---

## 9. Stage F — Resample to the canonical record

**Module:** `spectral_sky.resample_to_1nm` + `SpectralSkyRecord`. The **only** place the µm→nm conversion
lives. Linear interpolation of the native (full-range) spectra onto the 1 nm grid
$\Lambda = \{380, 381, \dots, 780\}$ (401 points), then the unit conversion:

> **Source (M-30):** Standard spectroradiometry unit identity (W m⁻² µm⁻¹ = 10⁻³ W m⁻² nm⁻¹); linear interpolation (unit identity; no primary publication).

**Sources.** *This implementation* (`src/hcl_core/spectral_sky.py`): no external model — the spectral-radiometry
unit identity $1\,\text{W m}^{-2}\mu\text{m}^{-1}=10^{-3}\,\text{W m}^{-2}\text{nm}^{-1}$ plus standard linear
interpolation. The 380–780 nm @1 nm grid matches the project's α-opic convention (CIE S 026, §11).

$$
I(\lambda_k)\big[\text{W m}^{-2}\text{nm}^{-1}\big] = 0.001 \cdot \operatorname{lerp}\!\big(I^{\text{native}};\ \lambda_k\big),\qquad \lambda_k\in\Lambda\tag{M-30}
$$

The factor $0.001$ is exactly the per-µm → per-nm magnitude change ($1\ \text{W m}^{-2}\mu\text{m}^{-1} =
10^{-3}\ \text{W m}^{-2}\text{nm}^{-1}$). The frozen, self-describing `SpectralSkyRecord` carries
`direct_normal[401]`, `sky_diffuse_horizontal[401]`, the broadband dict, the `AtmosphericState`, the
`SolarGeometry`, and the full provenance (engine, cloud model, native resolution, bridge residuals, night /
`night_but_epw_nonzero` flags).

**Closure diagnostics (the two residual keys).** `build_record` records both, so the bridge invariant is
auditable per record rather than assumed:

$$
\texttt{bridge\_residuals} = \Big(\textstyle\int I_{d\lambda}\,d\lambda - \mathrm{DNI},\ \int I_{s\lambda}\,d\lambda - \mathrm{DHI}\Big),
\qquad
\texttt{ghi\_epw\_residual} = (\mathrm{DNI}\cos z + \mathrm{DHI}) - \mathrm{GHI}
$$

The first pair (keys `direct_bb` / `diffuse_bb`) should be ~0 by construction — it confirms the §8.2
energy-rescale actually held on this row. The second is an **independent** cross-check of the EPW's own
three columns against each other and is *not* forced to zero: a non-zero value means the EPW's DNI/DHI/GHI
are mutually inconsistent at that hour, which the pipeline reports rather than reconciles. At night both
residual pairs are identically zero because no rescale ran.

```
ALGORITHM F  resample_to_1nm(spectra)                  # the ONE µm→nm boundary   (M-30)
  gx ← spectra.wavelength_nm                            # native grid (nm), ascending, 300..4000
  for λ in GRID_NM = {380,381,…,780}:                   # 401 points
      direct[λ]  ← interp(gx, spectra.direct,  λ) · 0.001    # W·m⁻²·µm⁻¹ → W·m⁻²·nm⁻¹
      diffuse[λ] ← interp(gx, spectra.diffuse, λ) · 0.001
  return direct[401], diffuse[401]

  interp(gx, ys, x):                                    # linear, endpoint-clamped, binary search
      if x ≤ gx[0]: return ys[0];  if x ≥ gx[-1]: return ys[-1]
      lo,hi ← 0, len-1;  while hi−lo > 1: mid←(lo+hi)//2; (gx[mid] ≤ x) ? lo←mid : hi←mid
      t ← (x − gx[lo])/(gx[hi] − gx[lo]);  return ys[lo] + t·(ys[hi] − ys[lo])
```

**Night & twilight contract.** If $z\ge90^\circ$ the record is zeroed with `night=True`. ⚠️ The engine is
**not** skipped: `build_record` calls `engine.compute` *before* testing `night` (`spectral_sky.py:84-86`)
and discards the result on the night branch. This is numerically inert — `Spectrl2Engine.compute` has its
own night guard (§7.9) and returns zeros for the same condition — but it means a night hour costs a full
122-wavelength engine call, so the night path is a correctness short-circuit, not a performance one. Because geometry uses the mid-interval hour, an hour-ending row whose mid-interval sun is below
the horizon zeroes even if the EPW reports nonzero radiation; that case sets `night_but_epw_nonzero=True`
(diagnostic — the energy is genuinely below-horizon at the sampled instant).

---

## 10. Stage G — Ground reflection & receivers

**Function:** `ground_for_receiver`. SPECTRL2/SMARTS emit **no clean ground array** (ground is folded into
their diffuse via multiple reflection). A horizontal up-facing surface sees **no** ground; a ground-reflected
term is real only for tilted/vertical receivers. The canonical record stays **sky-truth, horizontal**.

> **Source (M-31):** Liu & Jordan 1963 isotropic-sky lineage (as in pvlib `poa_ground_diffuse`); Bird & Riordan 1986 §3.

**Sources.** *Model:* the isotropic ground-reflected view-factor term, as in `pvlib.irradiance.poa_ground_diffuse`
(Liu & Jordan 1963 isotropic-sky lineage); the "ground folded into the diffuse" fact is Bird & Riordan
(1986) §3 (and §11 #2 of the design spec). *Software:* `src/hcl_core/spectral_sky.ground_for_receiver`;
receiver-plane transposition is delegated to Radiance transport (design-spec §6), not computed here.

Spectral ground-glow input for the Radiance ground hemisphere — spectral GHI × spectral albedo × isotropic
view factor (*pvlib `poa_ground_diffuse` form*):

$$
G(\lambda) = \big[\,I_{d\lambda}\cos z + I_{s\lambda}\,\big]\cdot \rho(\lambda)\cdot \frac{1-\cos\beta}{2}\tag{M-31}
$$

$\beta=0$ (horizontal) → zeros; $\beta=90^\circ$ (vertical eye) → factor $0.5$ (half-hemisphere ground). This
is the **ground-glow coloring input**, *not* a finished receiver irradiance: Radiance transport performs the
sky-diffuse transposition (horizontal→tilted) and the direct cosine-projection (spec §6). The view factor is
isotropic (azimuth-independent), so there is no orientation argument in v1. Spectral albedo $\rho(\lambda)$
uses a gray fallback in v1 (surface-typed library = refinement). $\mathrm{GHI}=I_{d\lambda}\cos z + I_{s\lambda}$
is derived from the authoritative DNI/DHI; any mismatch with the EPW GHI column is logged.

---

## 11. Stage H–J — Consumers: channels, reconstruction, circadian metrics

### 11.1 Channels & reference SPDs (Track A)

> **Note:** the CIE D-series sky templates that this pipeline replaces are grounded by CIE 15:2004 *Colorimetry* (S₀/S₁/S₂ eigenvectors). The Perez all-weather sky (embedded in `gendaylit`/`gendaymtx`) follows Perez et al. 1990/1993; the model lives inside Radiance, not recomputed in Python.

- `to_channels(record, channel_type)` bins each component into the existing 3- or 9-band channels via
  `bin_average` (channel_type 0 → `BINS_3=[[587,780],[499,587],[380,499]]` in r,g,b order; 1 → 9 ascending
  bins), feeding `colored_sky`.
  > **The channels are only half the handoff.** `colored_sky` paints these channels onto a Perez sky
  > whose sun position it derives *independently*, from its own `hour` argument read as a **wall-clock
  > instant** — whereas this record's geometry was computed at the **mid-interval** hour (§5, `h−0.5`).
  > Passing the same integer hour to both therefore paints a spectrum computed for one sun position
  > onto a dome traced from another, **7.5° of diurnal arc away**, with no error raised. Thread the
  > record's own geometry alongside the channels — `sun_zenith_deg=rec.geometry.zenith_deg`,
  > `sun_azimuth_deg=rec.geometry.azimuth_deg` (taken verbatim; `colored_sky` converts to gendaylit's
  > `-ang` altitude/from-South convention internally) — so one ephemeris is authoritative for both the
  > spectrum and the geometry it is traced through.
- `to_reference(record)` returns the two 401-value reference SPDs $(\text{sky\_spd}=I_{s\lambda},
  \text{sun\_spd}=I_{d\lambda})$ for `reconstruct_spectrum`. The physical SPDs replace the D-series sky / air-
  mass sun **templates** as the *reshaping shapes*; the Radiance transport still supplies the per-bin
  **totals**. Each bin's total energy is preserved (reshape-within-bin), so the bin-energy invariant is
  untouched.

### 11.2 CIE S 026 α-opic metrics (the circadian payload)

> **Source (M-32…M-34):** CIE S 026/E:2018, *System for Metrology of Optical Radiation for ipRGC-Influenced Responses to Light* — α-opic irradiance (M-32), ELR (M-33), EDI / mel-EDI (M-34) — normative s_α / K^D65 verified vs the official CIE α-opic Toolbox + DIS 026/E:2018 infosheet; full standard prose remains paywalled.
> **Source (M-33, photopic):** CIE 1924 V(λ); 683 lm/W maximum luminous efficacy.
> **Source (M-34, D65 reference):** CIE D65 illuminant per CIE 15 / CIE Standard Colorimetry — D65 locus verified vs CIE 15:2004 Colorimetry.

**Sources.** *Standards:* CIE S 026/E:2018, *System for Metrology of Optical Radiation for ipRGC-Influenced
Responses to Light* — the five α-opic action spectra $s_\alpha$, ELR (M‑33) and EDI (M‑34); CIE 1924 $V(\lambda)$
and the 683 lm/W maximum luminous efficacy; CIE D65 illuminant (the EDI reference). *Software:*
`src/hcl_core/alpha_opic.py` (the CIE S 026 α-opic math with the §9.3a/§9.3b fixes documented in `hcl-methodology.md`); action-spectra
and $V(\lambda)$/D65 tables in `src/hcl_core/data.py`.

**Module:** `alpha_opic`. From a spectral irradiance $E_\lambda$ on the 1 nm grid (step $\Delta\lambda=1$ nm),
for each α-opic action spectrum $s_\alpha(\lambda)$ (α ∈ {S-cone, M-cone, L-cone, rhodopic, **melanopic**}) —
*CIE S 026:2018:*

$$
E_\alpha = \sum_{i} E_\lambda(\lambda_i)\,s_\alpha(\lambda_i)\,\Delta\lambda\qquad[\text{W m}^{-2}]\tag{M-32}
$$

Photopic illuminance ($V(\lambda)$, 683 lm/W — *CIE 1924*) and the α-opic equivalent-luminance ratio (ELR,
mW/lm — *CIE S 026:2018*):

$$
E_v = 683\sum_i E_\lambda(\lambda_i)\,V(\lambda_i)\,\Delta\lambda,\qquad \mathrm{ELR}_\alpha = \frac{E_\alpha}{E_v}\cdot 1000\tag{M-33}
$$

The **equivalent daylight illuminance** normalizes by the same ratio computed for the D65 illuminant
(*CIE S 026:2018; D65 per CIE 15*),
$K^{D65}_\alpha = \big(\sum_i E^{D65}_\lambda s_\alpha\,\Delta\lambda\big)\big/\big(683\sum_i E^{D65}_\lambda V\,\Delta\lambda\big)\cdot 1000$:

$$
\boxed{\ \text{EDI}_\alpha = \frac{E_\alpha\cdot 1000}{K^{D65}_\alpha}\ }\qquad\Rightarrow\quad \textbf{mel-EDI} = \text{EDI}_{\alpha=\text{mel}}\ [\text{lx}]\tag{M-34}
$$

This is the program's headline output: the melanopic equivalent daylight illuminance of the reconstructed
sky, now resting on physically-derived spectra instead of templates.

```
ALGORITHM G  alpha_opic_from_spd(E_λ[401], α)          # CIE S 026 (alpha_opic.py)   (M-32..M-34)
  Δλ ← 1 nm;  s_α ← ALPHA_ARRAYS[α]        # α: 1=S,2=M,3=L,4=rhodopic,5=melanopic
  E_α   ← Σ_i E_λ[i]·s_α[i]·Δλ                                            # α-opic irradiance  (M-32)
  E_v   ← 683·Σ_i E_λ[i]·V[i]·Δλ                                         # photopic illuminance (lx)
  ELR_α ← (E_v>0) ? (E_α/E_v)·1000 : 0                                   # equivalent-lum ratio (mW/lm)
  K_D65 ← (Σ_i D65_ELR[i]·s_α[i]·Δλ)/(683·Σ_i D65_ELR[i]·V[i]·Δλ)·1000    # D65 reference ELR (M-33)
  EDI_α ← (E_α>0) ? (E_α·1000)/K_D65 : 0                                 # equivalent daylight illum (lx) (M-34)
  return {E_alpha:E_α, ELR:ELR_α, EDI:EDI_α}            # α=5 → mel-EDI
```

(The melanopic case $\alpha=5$ gives **mel-EDI**. The D65 reference integrals are precomputed; the
implementation also offers a numpy fast path that produces identical rounded results.)

---

## 12. Parallel engines (oracle & native)

### 12.1 SMARTS 2.9.5 oracle

**Sources.** *Manual:* Gueymard, *SMARTS 2.9.5* (Simple Model of the Atmospheric Radiative Transfer
of Sunshine) — users manual (card layout, IOUT codes) + the distribution's
worked `Examples/` (deck + IOUT verified; the SMARTS distribution is kept outside this published repo). *Method paper:* Gueymard (2001), *Parameterized transmittance
model for direct beam and circumsolar spectral irradiance*, Solar Energy **71**:325. *Software (this repo):*
`src/hcl_core/spectral_engine/smarts.py`.

**Module:** `spectral_engine/smarts`. Capability-gated (`SMARTSPATH`). Generates a 17-card free-format deck
(LF-terminated, apostrophe-quoted strings), runs the binary in a fresh temp dir (SMARTS refuses to overwrite
its output files), and parses `smarts295.ext.txt`. The atmosphere maps as: `ISPR=1` station pressure;
`USSA`; `IH2O=0` explicit $w$; `IO3=0` explicit $u_{O_3}$; `S&F_RURAL` aerosol; `ITURB=0` `TAU5`$=\tau_{500}$;
`IALBDX=-1` fixed $\rho$; `ITILT=0`; `IMASS=0` → enter $(z,\gamma_s)$; 280–4000 nm; `IPRT=2`, `IOUT 1 2 3`.

**Verified against the distribution's Examples:** IOUT codes **2 = `Direct_normal_irradiance`** and **3 =
`Difuse_horizn_irradiance`** (the *pure* variants, distinct from the `+circumsolar` codes 9/10 used in
Examples 1/6) → output columns `Wvlgth | ET | direct-normal | diffuse-horizontal`. The parser reads
col 0/2/3. **Units:** SMARTS emits W m⁻² **nm⁻¹**, so the engine multiplies by 1000 → W m⁻² µm⁻¹, making the
§9 resampler's ÷1000 correct for *every* backend. Fidelity note: with the **default** `aerosol="rural"` deck the
Ångström exponent is **not** a SMARTS input (it comes from the `S&F_RURAL` model); only the $\tau_{500}$
magnitude is set. **Resolved, opt-in (D-20):** `aerosol="user"` (the `smarts_aerosol` MCP tool arg on
`spectral_sky_from_epw`/`spectral_epw`) emits `AEROS='USER'` (Card 8) plus a Card 8a (`ALPHA1 ALPHA2 OMEGL GG`),
making $\alpha$ (`atm.angstrom_alpha`) and $g$ (`atm.aerosol_g`) settable SMARTS inputs — an 18-card deck instead
of 17. Default remains `aerosol="rural"`, byte-identical to before.

```
ALGORITHM H  SmartsEngine.compute(atm, geo)            # capability-gated oracle
  if not smarts_available(): raise RuntimeError        # SMARTSPATH unset → caller degrades
  run_dir ← fresh temp dir;  symlink the binary's data tree into it   # SMARTS won't overwrite outputs
  write build_deck(atm, geo) → run_dir/smarts295.inp.txt              # 17 cards, LF, IOUT "1 2 3"
  run [SMARTSPATH] in run_dir  (timeout 120 s)
  (wl_nm, direct, diffuse) ← parse_ext_output(run_dir/smarts295.ext.txt)   # cols 0 / 2 / 3
  rm run_dir
  return ClearSkySpectra(wl_nm, direct·1000, diffuse·1000, units="W/m^2/um")   # nm⁻¹ → µm⁻¹ (×1000)
```

### 12.2 Native Radiance `gensdaymtx`

> **Source (gensdaymtx sky model):** Perez et al. 1990/1993 all-weather sky luminance/radiance (primary sources verified) — model lives inside Radiance; not recomputed in Python.
> **Source (OPAC aerosol):** OPAC continental aerosol standard reference climatology.

**Sources.** *Software:* Radiance 6.1a (Greg Ward / LBNL) — `gensdaymtx` (spectral extension of `gendaymtx`)
and `rcomb`, verified against the upstream Radiance 6.x source (kept outside this published repo); flag/IOUT semantics verified against the
binary's parser. *Underlying sky model:* Perez all-weather sky (Perez et al. 1993) as used by gendaymtx, with
OPAC continental aerosol spectral shape. *Software (this repo):* `src/hcl_radiance/spectral_native.py`.

**Module:** `hcl_radiance/spectral_native`. Capability-gated (detects `gensdaymtx` on PATH; degrades to
emitting the command plan otherwise). EPW → 20-band spectral sky matrix → melanopic collapse.

> **Live validation.** The live run executes under Radiance 6.1a (2026-05-05) installed at
> `/usr/local/radiance/bin`. NCOMP=20 confirmed (NROWS=146 sky patches). The native 20-band spectrum agrees
> with the offline Python SPECTRL2 engine within a loose envelope — per-band normalized mean ≈2.5 %, Pearson
> correlation 0.987; mel/phot: native 0.987 vs Python 1.015, no spectral inversion. This is a
> **shape-agreement validation, not a calibrated baseline**: native output is W sr⁻¹ m⁻² per sky patch while
> the Python engine produces W m⁻² nm⁻¹ irradiance — absolute broadband magnitudes are incommensurable and
> are not asserted.

$$
\texttt{gensdaymtx -m\ N\ [-d|-s]\ [-g <refl>]\ -oa\ site.epw} \;\longrightarrow\; \texttt{rcomb -c }k_1\dots k_{20}
$$

> ⚠️ **Not `rcomb -c M`.** `build_rcomb_melanopic_cmd` (`spectral_native.py:34`) **deliberately** emits
> explicit per-band CIE S 026 coefficients rather than Radiance's own `-c M` shorthand. `-c M` returns an
> **equal-energy-normalised melanopic lux (EML)**, not mel-EDI: verified live on a D65 spectrum
> in descending band order, `-c M` reads **1.081× true mel-EDI (8.1 % high)**, with `-c M`/`-c Y` = 1.098
> (essentially the Lucas ratio). That is a definitional difference in what the flag computes, not a
> Radiance defect. The shipped coefficients are
> $k_i = \big(\textstyle\sum_{\lambda\in\text{band }i} s_{\text{mel}}(\lambda)\big) / (\Delta\lambda_i \cdot K^{D65}_{\text{mel}})$
> with $K^{D65}_{\text{mel}} = 1.3262\times10^{-3}$ (`spectral_native.py:161,190`), and they must be fed in
> the `.smx`'s **descending** band order (§12.2 band-order note) — feeding ascending components instead
> reads 0.774× and is the mirror of the same trap.

> **Note.** `-g` takes a **single scalar** gray ground reflectance
> (`grefl = atof(argv[++i])`, `gensdaymtx.c:647`), **not** an `r g b` triple — the earlier `[-g r g b]`
> form in this box was wrong. The implementation rejects a tuple with `TypeError` (as-built D-25).

Location/time come from the EPW header (`gensdaymtx` reads `.epw` directly). **Only implemented flags** are
used (`-m -d -s -g -n -r -u -i -p -o -v -h`); the usage string's `-c/-O/-A/-D/-M` are **not** parsed and abort
the run. Output is radiometric W sr⁻¹ m⁻², 20 bands on a **UNIFORM 380–780 nm @20 nm grid** (NCOMP=NSSAMP=20,
`gen/atmos.h:17`; the 20 nm interval is `gen/atmos.c:169`) — the same grid as the nominal hcl `BAND_EDGES_20`. (The header's `WAVELENGTH_SPLITS` is the legacy
4-value RGB partition `780 588 480 380`, color.c:94 — NOT band edges.) `reconcile_to_native_bands(values_401, ncomp)`
re-bins the Python 1 nm spectrum onto that NCOMP-derived uniform grid for interop; for ncomp=20 it reproduces
`band_average` exactly (a confirmation, not a correction). Atmosphere fidelity: broadband AOD + cloud cover are read per-timestep from the EPW; only the aerosol
*spectral shape* (OPAC continental) + water-vapor/ozone are canned. Runtime needs `mie_ca.dat` on `RAYPATH`.

> **Band-order finding (live validation).** The `.smx` matrix body stores its 20 spectral
> components **descending** in wavelength (red→blue), consistent with `WAVELENGTH_SPLITS = 780 588 480 380`.
> Consumers of the raw `.smx` body **must reverse** the component vector (`[::-1]`) to obtain ascending
> 380→780 nm order before interoperating with the nominal hcl `BAND_EDGES_20` grid. Un-reversed data yield
> Pearson r ≈ −0.70; reversed, r ≈ +0.987. The current test helper applies this reversal; no production
> `.smx`-body reducer exists yet.

```
ALGORITHM I  run_gensdaymtx(epw, work_dir, mf, mode, run)   # run-or-emit; runs live where Radiance 6.1a present
  cmd ← build_gensdaymtx_cmd(epw, mf, mode, ground_refl)          # implemented flags only
  status ← radiance_spectral_status()                             # shutil.which("gensdaymtx")
  if not (run and status.available):
      return {ran:False, commands:[cmd > sky.smx, build_rcomb_melanopic_cmd(sky.smx)],  # explicit S 026 k_i, NOT -c M
              reason:"gensdaymtx absent; ensure mie_ca.dat on RAYPATH, then run"}   # degrade, not error
  run cmd → work_dir/sky_spectral.smx   (timeout: caller-supplied, default None = no cap)
  header ← parse_smx_header(read whole file)                     # {ncomp, nrows, ncols, rgb_partition}
  return {ran:True, ok:True, smx:path, header}                   # failure → {ran:True, ok:False, error, returncode}
  # Track-C interop: reconcile_to_native_bands(values_401, header.ncomp) re-bins onto the uniform NCOMP grid.
```

---

## 13. Validation methodology & error budget

**Sources.** *Golden:* `SPCTRAL2_OUTPUT.txt` + `spectest.c` inline NREL values (Bird & Riordan 1986).
*Cross-engine oracle:* SMARTS 2.9.5 (Gueymard) and pvlib `spectrl2`. *Measured:* SKYSPECTRA dataset, Zenodo
**8147546** (Berlin/Beijing/Granada/Singapore/Vaulx-en-Velin horizontal spectral-irradiance tables).
*Envelope:* Nann & Riordan (1991), Fig. 12. *Software:* `src/hcl_core/spectral_validate.py` +
`tests/test_skyspectra.py`. The drift-vs-templates check reuses `spectral_reconstruct.reconstruction_divergence`.

How "physical, not assumed" is earned (spec §7):

1. **Golden port test (the gate).** The SPECTRL2 port reproduces `SPCTRAL2_OUTPUT.txt` (122 pts of
   global/direct/diffuse, geometry pre-resolved) to **<0.05 % (direct) / <0.01 % (diffuse)** in the visible.
   Confirmed: every C constant and equation (M‑14…M‑24) matches `spectrl2_2.c` 1:1, and all six golden rows
   match byte-for-byte, with the column identity $\text{global}=I_{d\lambda}\cos\theta_i + I_{s\lambda}$ holding.
2. **Cross-engine band.** SPECTRL2 vs SMARTS vs pvlib agree within a documented envelope on clear hours
   (`compare_engines`, mean/max % difference over 380–780 nm).
3. **Bridge invariant.** The cloud modifier's full-range scaled spectra integrate to EPW DNI/DHI exactly
   (M‑27); the stored $k_{\text{dir}},k_{\text{dif}}$ + clear-sky integrals make it checkable from the
   visible-only record.
4. **Measured (SKYSPECTRA, Zenodo 8147546).** Reconstructed mel-EDI vs the dataset's measured global/diffuse
   horizontal spectral-irradiance tables. **Envelope (Nann–Riordan Fig. 12):** σ ≈ **8 % VIS** overall
   (≈5 % clear, ≈7 % overcast), ~15 % UV, ~18 % at the 940 nm water band — 8 % VIS is the headline tolerance.
5. **Drift vs templates.** `reconstruction_divergence` reports how far physics moves the circadian metrics
   from today's D-series output, per EPW.

**Dominant error sources, ranked:** (a) the SEDES1 CCM digitization + global→diffuse approximation (§8.3) —
the largest, bounded by the always-on energy-rescale; (b) red-band upsampling from the 20–26 nm native grid
(§7.8); (c) atmospheric defaults when EPW columns are missing (AOD especially — an Ångström anchor conversion
and a van Heuklon ozone climatology are now available opt-in, see §6, D-3/ozone); (d) ozone at the 300 DU
default (sub-percent for mel-EDI; `ozone_mode="climatology"` is opt-in). The SMARTS path is **binary-gated** (`$SMARTSPATH` unset → emit-only) but received
its **live validation**: compiled from the SMARTS source distribution, kept outside this published repo (the shipped Mac binary is dead
PowerPC), it agrees with the Python SPECTRL2 engine to ~1.5–2 % direct / ~3–5 % diffuse at r≈0.99 on a clear
Athens hour (see `docs/spectral-engine-comparison.md`). The native Radiance `gensdaymtx` path received its **live
validation** under Radiance 6.1a (NCOMP=20, Pearson 0.987 vs SPECTRL2 — loose shape agreement;
see §12.2). Both are *validations, not calibrated baselines* — neither is yet checked against measured sky
spectra.

> **Corroborating context (ground no equation — see `literature-bibliography.md` §6):**
> Abreu, Gueymard, Canhoto & Costa 2023 (*Sol. Energy* **252**:309) shows that gridded/reanalysis AOD and
> Ångström α agree only moderately/poorly with ground truth and that DNI is the most AOD-sensitive output —
> directly corroborating ranked error source (c) and the EPW-AOD-defaults posture; it also notes even
> research-grade clear-sky validation is bounded by ~1.8 % irradiance-measurement bias, which *strengthens*
> the "never measurement-validated" honesty flag. Louche, Simonnot, Iqbal & Mermier 1988 (*Sol. Energy*
> **41**:273) is a published precedent for exactly the MBE/RMSE-against-station-broadband validation the
> bridge invariant (M‑27) embodies. Neither sources any engine equation.

---

## 14. Degradation contract

- **Night / below-horizon:** record zeroed, `night=True` (the engine still runs and its zero result is
  discarded — §9), (and `night_but_epw_nonzero` at
  twilight, §9).
- **Malformed/short EPW rows:** skipped with a logged reason; a run reports how many timesteps were dropped.
- **Missing atmosphere fields:** documented defaults (§6) with the substitution recorded in provenance;
  never a hard failure.
- **Engine / binary absent:** capability-gated paths degrade to the existing template-based reconstruction
  and flag `engine='templates(fallback)'`; Track A's physics source defaults **off**, so absence of a
  physical engine never breaks existing callers.
- **Weak/uncertain CCM:** degrades to grey cloud; the energy-rescale keeps broadband DNI/DHI exact.

---

## 15. Appendix — equation ↔ source cross-reference

> **Equation-numbering convention (Bird & Riordan).** The "N-M" labels in the table below (e.g. Eq. 2-1, 3-17) follow the SERI/NREL `spectrl2_2.c` C-source section numbering; the original Bird & Riordan 1986 paper uses a single continuous scheme (Eqs. 1–30). See the bibliography for full details.
>
> ⚠️ **The `spectrl2_2.c:NNN` line numbers below are UPSTREAM references, not in-repo ones.** No C source
> ships in this repository — the port's Python realisation is `hcl_core/spectral_engine/spectrl2.py`, and
> that is where each equation should be read. The C citations are retained because they record exactly which
> upstream lines the port was transcribed from, and the equation labels (Eq. 2-1, 3-17, …) resolve against
> the published paper independently of any file.

| This doc         | Bird & Riordan 1986 / C source         | Quantity                                   |
| ---------------- | -------------------------------------- | ------------------------------------------ |
| M‑14            | Eq. 2‑7 /`spectrl2_2.c:355`         | aerosol optical depth$c_a(\lambda)$      |
| M‑15            | Eq. 3‑16 /`:351`                    | single-scatter albedo$\omega(\lambda)$   |
| M‑16            | Eq. 3‑12…3‑14 /`:312‑318`        | forward-scatter AFS/BFS/$F_s$/$F_{sp}$ |
| M‑18 (Rayleigh) | Eq. 2‑4 /`:361`                     | $T_r$                                    |
| M‑18 (ozone)    | Eq. 2‑9 /`:364`                     | $T_o$                                    |
| M‑18 (water)    | Eq. 2‑8 /`:367`                     | $T_w$                                    |
| M‑18 (uniform)  | Eq. 2‑11 /`:370`                    | $T_u$                                    |
| M‑18 (aerosol)  | Eq. 3‑9,3‑10,2‑6 /`:373‑379`     | $T_{as},T_{aa},T_a$                      |
| M‑19            | Eq. 2‑1 /`:399‑402`                | direct-normal$I_{d\lambda}$              |
| M‑20            | §3.1 primed /`:382‑391`            | $T_r',T_w',T_u',T_{as}',T_{aa}'$         |
| M‑21            | Eq. 3‑17 /`:411‑413`               | $C_s$                                    |
| M‑22            | Eq. 3‑5,3‑6,3‑7,3‑8 /`:414‑416` | $I_r,I_a,I_g,\rho_a$                     |
| M‑23            | Eq. 3‑1 /`:417`                     | diffuse$I_{s\lambda}$                    |
| M‑24            | Eq. 3‑18 /`:435‑444`               | tilt (golden only)                         |

| This doc       | Nann & Riordan 1991  | Quantity                                          |
| -------------- | -------------------- | ------------------------------------------------- |
| M‑25          | §4, Table 3         | clearness index$K_t$                            |
| M‑27          | Eq. 9 (energy)       | per-component bridge scale                        |
| M‑28 / M‑28a | Eq. 11, Figs. 10–11 | $\mathrm{CCM}(\lambda,K_t)$ + coefficient solve |

| This doc     | Other source                                 | Quantity                                      |
| ------------ | -------------------------------------------- | --------------------------------------------- |
| M‑1…M‑5   | Cooper 1969 (`weather.solar_zenith`)       | declination, EoT, hour angle, zenith, azimuth |
| M‑6         | Spencer 1971 / NREL SOLPOS                   | Earth-radius-vector$R_v$                    |
| M‑7         | van Heuklon 1979 (`spectrl2_2.c:278‑299`) | optional ozone climatology$u_{O_3}$         |
| M‑8         | Kasten & Young 1989                          | relative air mass$m$                        |
| M‑9, M‑11  | Bird & Riordan 1986                          | $m_p$, ozone air mass $m_o$               |
| M‑12        | Gueymard 1994 (pvlib)                        | precipitable water (T, RH)                    |
| M‑13        | Reitan 1963                                  | precipitable water (dew point)                |
| M‑31        | pvlib`poa_ground_diffuse`                  | ground-glow term                              |
| M‑32…M‑34 | CIE S 026:2018 (`alpha_opic.py`)           | α-opic irradiance, ELR, EDI / mel-EDI        |

### Algorithm index

| Alg             | §       | Routine                                                                                   | Role                                        |
| --------------- | -------- | ----------------------------------------------------------------------------------------- | ------------------------------------------- |
| 0 / 0a / 0b     | 3.1–3.3 | `record_from_epw` / `build_record` / `annual_records`                               | master flow: timestep, orchestrator, annual |
| S               | 5        | `solpos.compute`                                                                        | solar geometry                              |
| A               | 6        | `atmosphere.derive`                                                                     | atmospheric state + provenance              |
| E               | 7.9      | `Spectrl2Engine.compute`                                                                | clear-sky engine (full procedure)           |
| B / C / D / E′ | 8.5      | `broadband_integral` / `energy_normalize` / `ccm_coeffs` / `Sedes1Modifier.apply` | cloud bridge                                |
| F               | 9        | `resample_to_1nm`                                                                       | µm→nm + 1 nm grid                         |
| G               | 11.2     | `alpha_opic_from_spd`                                                                   | CIE S 026 mel-EDI                           |
| H               | 12.1     | `SmartsEngine.compute`                                                                  | SMARTS oracle                               |
| I               | 12.2     | `run_gensdaymtx`                                                                        | native Radiance run-or-emit                 |
