# HCL-MCP — Canonical Literature Bibliography & Citation Style Guide

> **Status:** Wave-0 foundation artifact. Date: 2026-06-20.
> **Purpose:** Single source of truth for every Wave-1 doc-reframing task. Every method in
> `hcl-mcp/docs/` must carry a citation and grounding status that resolves to a row in the
> master table below. All Wave-1 agents conform to the style guide in §2.
>
> **Grounding-status vocabulary (exactly four values):**
> - `in-corpus` — the primary source has been obtained and the method was verified directly against it (cite author/year + equation/page).
> - `external-standard` — canonical published standard/source, cited from its normative text but not independently reproduced/verified here (e.g. EN 12464-1:2021, EN 17037:2018). ⚠️ **IES LM-83-12 was this line's example until 2026-08-14 and is no longer** — its primary source has since been obtained, so it now reads `in-corpus`; see the acquisition ledger below.
> - `lineage-only` — appears only in Lark/VB with no primary-literature derivation (e.g. `1/107`). Flagged.
> - `approximate` — literature-derived but with documented uncertainty (e.g. figure-digitized SEDES1 A/B/C).

---

## 1. Corpus Verification Notes (Task 1 Steps 1–2)

**needs-verification resolution:**

| Entry | Decision | Evidence |
|---|---|---|
| Inanici, Brennan & Clark 2015 | **in-corpus** | Confirmed: Inanici, Brennan & Clark 2015, *Spectral Daylighting Simulations: Computing Circadian Light*, BS2015 Hyderabad proceedings. |
| Pierson, Aarts & Andersen 2021 (prev. mislabeled "Gkaintzatzi-Masouti / SimAUD 2021") | **in-corpus** (corrected 2026-06-20) | The paper is **Pierson, Aarts & Andersen 2021, *Validation of Spectral Simulation Tools for the Prediction of Indoor Daylight Exposure*, Proc. 17th IBPSA Building Simulation Conf. (BS2021), Bruges, pp. 1765, DOI 10.26868/25222708.2021.30583** — i.e. **BS2021, not SimAUD**, and authored by Pierson/Aarts/Andersen (no Gkaintatzi-Masouti). Distinct from the Pierson et al. 2022/23 EPFL validation work also verified. |

**external-standard spot-checks (Step 2):**
A Wave-0 corpus scan found none of these primary papers present (Perez, Reinhart, Tregenza, Skartveit, Walkenhorst, CIE S 026, Amundadottir), so all were `external-standard`. **Updated 2026-06-20:** the primary papers for all of them have since been obtained and verified, so they are now `in-corpus` — Perez 1993+1990, Tregenza 1987 + Reinhart & Walkenhorst 2001 (sky patches), Skartveit & Olseth 1992 + Walkenhorst 2002 (sub-hourly), CIE S 026 normative companion (α-opic Toolbox), and Amundadottir (journal versions). See §5. The sky-patch and sub-hourly *models* still execute inside Radiance/Daysim, but their primary papers have now been verified.

---

## 2. Master Citation Table

Columns: `ID(s)` = the H-n / M-n equation(s) it grounds (or "—" for standards/compliance); `Method` = what it computes; `Code location` = primary source file(s); `Primary source` = author year; `Eq./page` = equation or section; `Grounding status`.

### 2A. Solar Geometry (M-1…M-8)

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| M-1 | Solar declination δ | `hcl_core/solpos.py` | Cooper 1969, *The absorption of radiation in solar stills*, Sol. Energy **12**(3):333–346 | Eq. in §2 | `in-corpus` — verified vs primary source |
| M-2, M-3 | Equation of time, apparent solar time, hour angle | `hcl_core/solpos.py` | Cooper 1969 / Duffie & Beckman *Solar Engineering of Thermal Processes* (standard EoT formulation) | Standard EoT | `external-standard` |
| M-4 | Solar zenith angle | `hcl_core/solpos.py` (≡ `weather.solar_zenith`) | Cooper 1969 | Cos-z equation | `in-corpus` — verified vs primary source |
| M-5 | Solar azimuth (clockwise from North) | `hcl_core/solpos.py` | Iqbal 1983, *An Introduction to Solar Radiation* | Standard solar geometry | `external-standard` |
| M-6 | Earth-radius-vector R_v | `hcl_core/solpos.py` | Spencer 1971, *Fourier series representation of the position of the Sun*, Search **2**:172 (via NREL SOLPOS) | Eq. for R_v (1/r² series) | `in-corpus` — verified vs primary source (`Fourier paper.md`, verbatim transcription; original CSIRO *Search* note never issued as PDF) |
| M-7 | Ozone climatology (opt-in; default = 300 DU) | `atmosphere.van_heuklon_ozone` (pure-Python; mirrors the SPECTRL2 upstream `spectrl2_2.c:278–299`, no C source bundled) | van Heuklon 1979, *Estimating atmospheric ozone for solar radiation models*, Sol. Energy **22**:63–68 | Eq. (4) + Table 1 | `in-corpus` — **verified vs primary source**: the hemisphere-specific A/β/C/D/F/G/H/I/J constants map verbatim to Eq. (4) / Table 1 (NH F=−30 → spring-max), independently re-confirmed by Karavana-Papadimou 2013 eq. (2) (§6) — **caveat:** the paper's *body* prints D=0.9856 but **Table 1 uses 0.9865**, which the implementation follows. **Now COMPUTED opt-in** (2026-07 atmospheric-physics-refinements): default still the 300 DU constant (byte-identical), `ozone_mode="climatology"` computes the lat/lon/day climatology (see as-built D-2). *Note: the plan's first transcription used a wrong symmetric phase (summer-max) — corrected to the authoritative Table 1 coefficients; see spectral-sky-methodology.md §6.* |
| M-8 | Relative optical air mass (Kasten–Young) | `hcl_core/solpos.py` | Kasten & Young 1989, *Revised optical air mass tables and approximation formula*, Appl. Opt. **28**:4735 | Table/eq. | `in-corpus` — verified vs primary source |

### 2B. Atmospheric State (M-9, M-11–M-13)

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| M-9, M-11 | Pressure-corrected & ozone air mass | `hcl_core/spectral_engine/spectrl2.py` | Bird & Riordan 1986 (`spectrl2_2.c`) — m_p = m·P/1013; m_o from §2 | Eqs. 2-x (C source) | `in-corpus` — verified vs primary source |
| M-12 | Precipitable water from T/RH (Gueymard 1994) | `hcl_core/atmosphere.py` (pvlib formulation) | Gueymard 1994, *Analysis of monthly average atmospheric precipitable water and turbidity in Canada and Northern United States*, Sol. Energy **53**:57 | Eq. for w | `in-corpus` — verified vs primary source |
| M-13 | Precipitable water from dew point (Reitan 1963, fallback) | `hcl_core/atmosphere.py` | Reitan 1963, *Surface dew point and water vapor aloft*, J. Appl. Meteorol. **2**:776 | Eq. for w | `in-corpus` — primary source obtained (scanned image-only AMS PDF) |

> **Equation-numbering convention (SPECTRL2 / Bird & Riordan).** SPECTRL2 equation labels of the form "N-M" (e.g. 2-1, 3-17) follow the SERI/NREL `spectrl2_2.c` C-source section numbering that the implementation ports; the original Bird & Riordan 1986 paper uses a single continuous scheme (Eqs. 1–30), so a paper reader should map by model term, not by the C-source label.

### 2C. SPECTRL2 Clear-Sky Engine (M-14…M-24)

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| M-14 | Aerosol optical depth (Ångström law) | `hcl_core/spectral_engine/spectrl2.py` | Bird & Riordan 1986, J. Climate Appl. Meteorol. **25**:87 | Eq. 2-7 | `in-corpus` — verified vs primary source |
| M-15 | Single-scattering albedo ω(λ) | `hcl_core/spectral_engine/spectrl2.py` | Bird & Riordan 1986 | Eq. 3-16 | `in-corpus` — verified vs primary source |
| M-16 | Aerosol forward-scatter terms (AFS, BFS, Fs, Fsp) | `hcl_core/spectral_engine/spectrl2.py` | Bird & Riordan 1986 | Eqs. 3-12…3-14 | `in-corpus` — verified vs primary source |
| M-17 | Extraterrestrial spectral irradiance × R_v | `hcl_core/spectral_engine/spectrl2.py` | Bird & Riordan 1986 (H_0λ table; R_v from Spencer 1971); the 122-row table itself is `SPCTRAL2_TAPE2`, documented at length in **SERI/TR-215-2436** (Bird & Riordan 1984 — full citation recovered from Riordan 1986 ref. [1]) | A[5][122] table | `in-corpus` — verified vs primary source |
| M-18 | Beam transmittances T_r, T_o, T_w, T_u, T_as, T_aa, T_a | `hcl_core/spectral_engine/spectrl2.py` | Bird & Riordan 1986 | Eqs. 2-4, 2-6, 2-8, 2-9, 2-11, 3-9, 3-10 | `in-corpus` — verified vs primary source |
| M-19 | Direct-normal spectral irradiance I_dλ | `hcl_core/spectral_engine/spectrl2.py` | Bird & Riordan 1986 | **Eq. 2-1** | `in-corpus` — verified vs primary source |
| M-20 | Primed diffuse-path transmittances (M'=1.8) | `hcl_core/spectral_engine/spectrl2.py` | Bird & Riordan 1986, §3.1 | Eqs. 3-x (fixed M'=1.8) | `in-corpus` — verified vs primary source |
| M-21 | Small-λ forward-scatter correction C_s(λ) | `hcl_core/spectral_engine/spectrl2.py` | Bird & Riordan 1986 | Eq. 3-17 | `in-corpus` — verified vs primary source |
| M-22 | Diffuse components I_r, I_a, I_g (Rayleigh, aerosol, ground back-scatter) | `hcl_core/spectral_engine/spectrl2.py` | Bird & Riordan 1986 | Eqs. 3-5, 3-6, 3-7, 3-8 | `in-corpus` — verified vs primary source |
| M-23 | Sky-diffuse spectral irradiance I_sλ (horizontal) | `hcl_core/spectral_engine/spectrl2.py` | Bird & Riordan 1986 | **Eq. 3-1** | `in-corpus` — verified vs primary source |
| M-24 | Tilted-receiver transposition (golden-test only) | `hcl_core/spectral_engine/spectrl2.py` | Bird & Riordan 1986 | Eq. 3-18 | `in-corpus` — verified vs primary source |

### 2D. Cloud Bridge — SEDES1 (M-25…M-29)

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| M-25 | Clearness index K_t | `hcl_core/cloud_modifier.py` | Nann & Riordan 1991, J. Appl. Meteorol. **30**:447 | §4, Table 3 | `in-corpus` — verified vs primary source |
| M-26 | Broadband integral (trapezoidal quadrature) | `hcl_core/cloud_modifier.py` | Numerical method (this implementation) | — | `lineage-only` — standard numerical quadrature (implementation choice); serves the Nann & Riordan 1991 §8.2 bridge invariant but is not a method named in the paper |
| M-27 | Energy normalization k_dir / k_dif (bridge invariant) | `hcl_core/cloud_modifier.py` | Nann & Riordan 1991 | Eq. 9 | `in-corpus` — verified vs primary source |
| M-28, M-28a | Cloud-cover modifier CCM(λ, Kt) = A + B·Kt + C·Kt² and Vandermonde coefficient solve | `hcl_core/cloud_modifier.py`, `hcl_core/_sedes1_data.py` | Nann & Riordan 1991 | Eq. 11; **A/B/C from Fig. 10/11 only — no published table** | `approximate` — figure-digitized; the **shipped default** (`cloud_variant="reanchored"`) is a faithful 10 nm digitization of the Fig. 11 A/B/C/σ curves (330–1100 nm), reanchored to unity at clear Kt; cross-check: the faithful digitization gives **B(400 nm) = −2.04** (`_sedes1_fig11.csv`; the retired seed's −3.55 was materially too steep — its ≈−3.5 slope belongs to the ~340 nm region, B(340) = −3.88). The earlier 3-class Vandermonde solve from Fig. 10 R̄(λ) curves (9-anchor seed) — a **historical seed-construction step, not live code** (only its output `SEED_A/B/C` survives in `_sedes1_data.py`; no linear-algebra solve remains there) — is retained only as the opt-in `cloud_variant="seed"`. The CCM is now also locally re-fittable from caller-supplied data (`cloud_variant="local"` via `hcl_core/sedes1_fit.py`, `fit_ccm`/`write_ccm_csv`/`load_ccm_csv`), and its Fig. 11 regression σ is surfaced in provenance (`ccm_sigma`/`ccm_sigma_mean`). Sourcing investigation (no machine-readable source exists): methodology §8.6 |
| M-29 | Diffuse reshape + renormalization (shape-only) | `hcl_core/cloud_modifier.py` | Nann & Riordan 1991 (shape term); renormalization is this implementation's mechanism | Eq. 11 + §8.2 | `approximate` — CCM applied to diffuse (paper fits global-horizontal); renormalization keeps DHI exact |

### 2E. Resample & Record (M-30…M-31)

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| M-30 | Resample to 1 nm canonical grid; µm→nm unit conversion | `hcl_core/spectral_sky.py` | Standard spectroradiometry unit identity (W m⁻² µm⁻¹ = 10⁻³ W m⁻² nm⁻¹); linear interpolation | — | `external-standard` (unit identity) |
| M-31 | Ground reflection for tilted/vertical receivers | `hcl_core/spectral_sky.ground_for_receiver` | Liu & Jordan 1963 isotropic-sky lineage (as in pvlib `poa_ground_diffuse`); Bird & Riordan 1986 §3 | Isotropic view-factor form | `external-standard` |

> **Corroborating (in-corpus, grounds no transcribed equation):** Petržala, Komár & Kocifaj 2017,
> *An advanced clear-sky model for more accurate irradiance and illuminance predictions for arbitrarily
> oriented inclined surfaces*, Renewable Energy **106**:212.
> Its Eq. 11 is the **identical** isotropic ground-reflection form `(ρ/2)(1−cos β)·G_H`, independently
> corroborating **M-31**'s Liu & Jordan lineage; its Eq. 12 corroborates the illuminance-via-V(λ)
> luminous-efficacy integration (cf. **H-6**). It is an **alternative** (single-scattering radiance-field
> over the sky dome) to the **M-24** tilted-transposition, **not** a source of Bird & Riordan Eq. 3-18 —
> do not cite it to ground M-24. Catalogued in §6.

### 2F. α-opic / CIE S 026 (M-32…M-34, H-3…H-12)

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| H-3 | Luminous efficacy constant K_m = 179 lm/W (Radiance broadband) | `hcl_core/data.py:28` | Radiance convention (integral of 683·V(λ) over Radiance white spectrum) | LUMINOUS_EFFICACY constant | `external-standard` |
| H-2, H-4 | Channel binning (3- and 9-band); channel-weighted lux E^(m) | `hcl_core/data.py`, `hcl_core/metrics.py` | Inanici, Brennan & Clark 2015, *Spectral Daylighting Simulations: Computing Circadian Light*, BS2015 | §2–3 (9-channel layout, weights) | `in-corpus` — verified vs primary source |
| H-5, M-32 | α-opic irradiance E_α = Σ E(λ)·s_α(λ)·Δλ | `hcl_core/alpha_opic.py` | CIE S 026/E:2018, *System for Metrology of Optical Radiation for ipRGC-Influenced Responses to Light* — normative s_α via the official CIE α-opic Toolbox v1.049a (CIE Div. 6, DOI 10.25039/S026.2018.UG); action-spectra origin: Lucas et al. 2014 | Eq. for E_α | `in-corpus` (companion) — verified vs the official CIE α-opic Toolbox v1.049a User Guide + DIS 026/E:2018 infosheet; action-spectra origin Lucas et al. 2014. **Full standard prose remains paywalled `external-standard`** |
| H-6, M-33 | Photopic illuminance E_v (exact per-nm path, 683 lm/W) | `hcl_core/alpha_opic.py:72` | CIE S 026/E:2018 (α-opic Toolbox); CIE 1924 V(λ); 683 lm/W maximum luminous efficacy | Eq. for E_v | `in-corpus` (companion) — verified vs CIE S 026 α-opic Toolbox; CIE 1924 V(λ) `external-standard` |
| H-7, M-33 | α-opic efficacy of luminous radiation ELR_α | `hcl_core/alpha_opic.py` | CIE S 026/E:2018 (α-opic Toolbox) | Eq. for ELR | `in-corpus` (companion) — verified vs CIE S 026 α-opic Toolbox |
| H-8 | D65 reference ELR K_α^D65 | `hcl_core/alpha_opic.py` | CIE S 026/E:2018 (α-opic Toolbox supplies the normative K^D65 reference values); D65 illuminant per CIE 15:2004 | K^D65 table | `in-corpus` (companion) — verified vs CIE S 026 α-opic Toolbox User Guide + D65/CIE 15 locus (CIE 15:2004 Colorimetry) |
| H-9, M-34 | α-opic equivalent daylight illuminance EDI_α (→ mel-EDI) | `hcl_core/alpha_opic.py:77` | CIE S 026/E:2018 (α-opic Toolbox) | Eq. for EDI | `in-corpus` (companion) — verified vs CIE S 026 α-opic Toolbox |
| H-10 | Channel-path irradiance reconstruction: I_i = (179/683)·(1/107)·C_i | `hcl_core/alpha_opic.py:50` | **No published derivation** — appears only in Lark/VB (`melanopic_calcs.bas:40`) | — | **`lineage-only`** — the `(179/683)·(1/107)` scalar cancels only in ELR and in **same-path EDI *ratios***, but **scales absolute E_α and absolute EDI/mel-EDI** (EDI = E_α·1000/K_α^D65 with a source-independent K_α^D65, so EDI ∝ E_α; verified ×10 channels → ×10 EDI) and biases the nonlinear nvRD sigmoid; absolute channel-path E_α, mel-EDI and R_D are unvalidated (~100 % vs SPD path) |
| H-11 | Melanopic daylight efficacy ratio mel-DER | `hcl_core/spectral_metrics.py` | CIE S 026/E:2018 (ELR normalized to D65; α-opic Toolbox) | Ratio definition | `in-corpus` (companion) — verified vs CIE S 026 α-opic Toolbox |
| H-12 | EML ↔ mel-EDI conversion: EML = 1.103 · mel-EDI | `hcl_core/spectral_metrics.py`; `data.py:41` (EML_PER_MEDI) | *Human-Centric Lighting: Foundational Considerations and a Five-Step Design Process* (Five-Step HCL) | Eq. 3 | `in-corpus` — verified vs primary source |
| — | FOV / field-of-view ipRGC directional weighting | `hcl_radiance/image_commands.py:38` (`_FOV` weights), `hcl_radiance/masks.py` | Khademagha et al. **2018**, *A multidirectional spectral measurement method and instrument to investigate non-image-forming effects of light*, Meas. Sci. Technol. **29**(8):085902 (+ Khademagha et al. 2016 review *Implementing NIF effects of light in the built environment*) | Multidirectional/FOV measurement & weighting | `in-corpus` — verified vs primary sources (Khademagha et al. 2018 + 2016). **Note:** prior "2021" attribution was a year slip — corrected to 2018/2016 |

**9-channel / OPN5 neuropic channel scheme:**

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| H-4 (OPN5 vector) | OPN5 neuropic 9-channel weight vector (90.5 % in b1, 380–419 nm); 9-channel/OPN5 scheme | `hcl_core/data.py` | **Jung, Cheng, Brennan & Inanici 2023**, *Multispectral Lighting Simulation Approaches for Predicting Opsin-driven Metrics and their Application in a NICU*, BS2023 | §2–3 (9-channel layout + OPN5 scheme) | `in-corpus` — verified vs primary source. **Note:** the "90.5 % in b1" concentration was previously attributed inline to "Kojima 2011", but no resolvable Kojima 2011 entry exists in this bibliography; the value is corroborated by code (`W_NEUROPIC_9[0]=0.905130569`, `data.py:24`) and the OPN5 vector is grounded here in Jung et al. 2023. Treat the "Kojima 2011" attribution as **unresolved** unless a full reference is added |

> **Critical grounding note:** Jung et al. 2023 grounds the **9-channel/OPN5 channel scheme** (the division of the spectrum into 9 wavebands and the OPN5 neuropic weighting), NOT the α-opic integral formula E_α (H-5/M-32). The integral E_α and the action spectra s_α are CIE S 026:2018 — now `in-corpus` via the official CIE α-opic Toolbox companion (CIE S 026 α-opic Toolbox User Guide + DIS 026/E:2018 infosheet; the full standard prose itself remains paywalled `external-standard`). The `(179/683)·(1/107)` scalar in H-10 is `lineage-only`. Do not attribute E_α to Jung 2023.

### 2G. nvRD Alerting Model (H-13…H-19)

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| H-13 | Effective ipRGC irradiance I_eff (390–700 nm window, ×311 multiplier) | `hcl_core/nvrd.py` | Amundadottir, Lockley & Andersen 2016, *Unified framework to evaluate non-visual spectral effectiveness of light for human health*, Light. Res. Technol. (published nvRD model) | §(spectral effectiveness) | `in-corpus` — verified vs primary source (LRT 2016 post-print) |
| H-14 | History transform H_t (log domain, SMA **1.7 h — the LH window**, applied to raw I_eff; 260.7 = 118.5×2.2) | `hcl_core/nvrd.py` | Amundadottir, Lockley & Andersen 2016 (LRT); 260.7 constant per EPFL thesis 2016 | §(temporal cascade) | `in-corpus` (model) — LRT 2016 post-print; **260.7 constant traces to the EPFL thesis (`external-standard`)** |
| H-15 | Adaptive threshold σ_t = σ_0 · 2^(H_t − 1) | `hcl_core/nvrd.py` | Amundadottir, Lockley & Andersen 2016 (LRT) | §(adaptive threshold) | `in-corpus` — LRT 2016 post-print |
| H-16 | z_eff scaling factor (310/683)·(1/118.5)·(1/1.42)·0.91 = 0.0024545715 | `hcl_core/nvrd.py`; `data.py:37` | EPFL thesis 2016 constant (no separate published derivation) | Constants | `external-standard` — the 260.7 and z_eff constants have no derivation beyond the thesis; LRT 2016 gives the model structure but not these magic constants |
| H-17 | Hill response r_t = 1 / (1 + (σ_t / I_eff)^n); n=3.55 | `hcl_core/nvrd.py` | Amundadottir, Lockley & Andersen 2016 (LRT); n=3.55 per thesis | §(Hill function) | `in-corpus` (form) — LRT 2016 post-print; **n=3.55 traces to the EPFL thesis (`external-standard`)** |
| H-18 | Output smoothing R_D(t) = EMA_2.3[r_t]; RD_cum = cumtrapz | `hcl_core/nvrd.py` | Amundadottir, Lockley & Andersen 2016 (LRT) | §(output smoothing) | `in-corpus` — LRT 2016 post-print |
| H-19 | Time-above-threshold dosimetry T_≥θ | `hcl_core/dosimetry.py` | Amundadottir, Lockley & Andersen 2016 (LRT) / standard dosimetry | — | `in-corpus` — LRT 2016 post-print |

> **nvRD grounding & caveat:** The nvRD model structure (H-13…H-19) is now `in-corpus` via Amundadottir,
> Lockley & Andersen 2016, *Unified framework…*, LRT — the published form of the model; the immersive-FOV application is corroborated by Amundadottir,
> Rockcastle, Khanie & Andersen 2017, *A human-centric approach…*, Build. Environ. **113**:5. The specific magic constants
> (260.7, z_eff, n=3.55; H-14/H-16/H-17) trace only to the **EPFL PhD thesis 2016 №7146** (`external-standard`,
> not acquired). R_D remains **relative only**: the `(179/683)·(1/107)` factor (H-10) propagates into I_eff and
> does NOT cancel in the nonlinear sigmoid, so absolute channel-path R_D is unvalidated. Validated against
> night-time electric-light studies; daytime envelope ≈ ±20 % (Pierson et al. 2023, *Validation of
> spectral simulation tools in the context of ipRGC-influenced light responses of building occupants*).

### 2H. Broadband → Spectrum Reconstruction (H-1, H-20…H-22)

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| H-1 | SPD parsing, canonical 380–780 nm @1 nm grid, linear end-extrapolation | `hcl_core/spd.py` | Lark CIE-Toolbox SPD handling (Inanici 2015 lineage) | — | `lineage-only` (parsing convention; no primary paper) |
| H-20 | Enhanced (reference-shaped) reconstruction: redistribute bin energy by reference shape | `hcl_core/spectral_reconstruct.py` | This implementation's extension of Lark faithful reconstruction | — | `lineage-only` (extension; no primary publication) |
| H-21, H-22 | CIE D-series reference SPD: S(λ) = S₀ + m₁S₁ + m₂S₂; m₁/m₂ from (x,y) on daylight locus | `hcl_core/_recon_data.py` | CIE 15:2004, *Technical Report: Colorimetry, 3rd ed.* — Judd–MacAdam–Wyszecki D-series eigenvectors S₀/S₁/S₂ + daylight locus (eigenvectors identical in CIE 15:2018, 4th ed., which the code comments reference) | Eqs. for m₁, m₂ (split at 7000 K) | `in-corpus` — verified vs CIE 15:2004 Colorimetry; edition-invariant D-series basis |
| — | Analytic daylight / RGB→D-series spectral upsampling (legacy template reconstruction path basis) | `hcl_core/spectral_reconstruct.py` (referenced) | Preetham, Shirley & Smits 1999, *A Practical Analytic Model for Daylight*, SIGGRAPH 1999 | Analytic daylight model | `in-corpus` — verified vs primary source |

### 2I. Electric-Lighting Photometry (H-23…H-26)

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| H-23 | Effective candela I_eff = I_raw · mult · ballast · pfactor | `hcl_core/ies.py` | ANSI/IESNA LM-63-02, *Standard File Format for the Electronic Transfer of Photometric Data* | §data-line-1 field definitions | `in-corpus` — verified vs primary source (LM-63-02) |
| H-24 | Zonal-flux integration ΔΦ_i = Ī(v_i) · 2π(cos v₁ − cos v₂) | `hcl_core/ies.py` | **IES zonal-lumens (zonal-cavity) method — IES Lighting Handbook** (LM-63-02 supplies the *input photometric fields* only, **not** this flux-integration formula) | Zonal-lumens / zone solid angle | `external-standard` — standard photometry; the 2π(cos θ₁ − cos θ₂) zone solid angle is **not** part of the LM-63 file-format spec |
| H-25 | Efficacy = Φ_rated / W_in; LOR = Φ_total / Φ_rated | `hcl_core/ies.py` | **Generic photometric definitions (IES Lighting Handbook / CIE nomenclature)** — LM-63-02 supplies rated lumens & watts but does **not** define efficacy/LOR | Standard definitions | `external-standard` — standard photometric quantities (not LM-63-02 definitions) |
| H-26 | ies2rad colorization / placement: `-m` scale, `-c R G B`, `!xform` | `hcl_radiance/ies_radiance.py` | ANSI/IESNA LM-63-02 + Radiance `ies2rad` (Ward / LBNL) | ies2rad manual | `in-corpus` — LM-63-02 format `in-corpus`; `ies2rad` mechanics remain Radiance-tool convention |

### 2J. Daylight Controls (H-27…H-29)

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| H-27 | Light-deficit fraction f_L | `hcl_core/lighting_controls.py` | EnergyPlus Engineering Reference §7.3.5, *Daylighting Calculations* | §7.3.5 | `external-standard` |
| H-28 | Lamp-power fraction f_P (ContinuousOff / Stepped control) | `hcl_core/lighting_controls.py` | EnergyPlus Engineering Reference §7.3.5 | §7.3.5 | `external-standard` |
| H-29 | Zone power F_P; annual energy P_elec | `hcl_core/lighting_controls.py` | EnergyPlus Engineering Reference §7.3.5 | §7.3.5 | `external-standard` |

### 2K. Annual Daylight Transport — 2-Phase DDS (H-30)

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| H-30 | 2-phase DDS: E_annual = D_sky · S_sky + D_sun · S_sun | `hcl_radiance/annual*.py` | Subramaniam 2017, *Daylighting Simulations with Radiance using Matrix-based Methods*, LBNL | §2-phase decomposition | `in-corpus` — verified vs primary source |
| H-30 (sky) | Reinhart/Tregenza sky-vault patch discretization (145 patches MF:1 / 5185 solar discs MF:6) | `hcl_radiance/annual*.py`; `gendaymtx -m` | Tregenza 1987, *Subdivision of the sky hemisphere for luminance measurements*, Light. Res. Technol. **19**(1):13–14 (145-patch base dome); Reinhart & Walkenhorst 2001, *Validation of dynamic RADIANCE-based daylight simulations…*, Energy Build. **33**(7):683–697 (MF subdivisions) — implemented in Radiance `gendaymtx` | MF:1/MF:6 basis | `in-corpus` — verified vs primary sources (Tregenza 1987 + Reinhart & Walkenhorst 2001); discretization realized in Radiance |
| H-30 (sky model) | Perez 1990/1993 all-weather sky luminance/radiance (embedded in gendaylit/gendaymtx) | `hcl_radiance/annual*.py` → Radiance `gendaylit`, `gendaymtx` | Perez, Seals & Michalsky 1993, *All-weather model for sky luminance distribution — preliminary configuration and validation*, Sol. Energy **50**:235; Perez, Ineichen, Seals, Michalsky & Stewart 1990, *Modeling daylight availability and irradiance components from direct and global irradiance*, Sol. Energy **44**(5):271–289 | All-weather model | `in-corpus` — verified vs primary sources (Perez 1993 + Perez 1990). Model still lives inside Radiance (not recomputed in Python) |
| H-30 (DC origin) | The daylight coefficient itself — per-sensor scalar illuminance contribution per sky patch, D_α(x), summed over the discretized vault | `hcl_radiance/annual*.py` (the D matrices) | Tregenza & Waters 1983, *Daylight coefficients*, Light. Res. Technol. **15**(2):65–71 | pp. 65–71 (definition) | `in-corpus` — primary source obtained & verified (2026-07-13). **Origin of the DC concept; the coefficient is a scalar per sensor per patch, carrying no directional index** |
| H-30 (DDS) | Daylight-coefficient **DDS** model (dynamic daylight simulation; direct-sun coefficients split from the diffuse vault) as executed by Daysim `gen_dc`/`ds_illum` | `hcl_radiance/annual*.py` → Daysim | Bourgeois, Reinhart & Ward 2008, *Standard daylight coefficient model for dynamic daylighting simulations*, Build. Res. & Inf. **36**(1):68–82 | DDS model | `in-corpus` — primary source obtained & verified (2026-07-13). Model still lives inside Daysim (not recomputed in Python); companion to Subramaniam 2017 above |

### 2L. Native Spectral Sky (gensdaymtx, SMARTS)

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| — | SMARTS 2.9.5 oracle clear-sky spectral engine | `hcl_core/spectral_engine/smarts.py` | Gueymard 2019, *The SMARTS spectral irradiance model after 25 years*, Sol. Energy **187**:233 (+ SMARTS 2.9.5 user manual) | Full model | `in-corpus` — verified vs Gueymard 2019 + SMARTS 2.9.5 manual |
| — | Native `gensdaymtx` spectral path (OPAC continental aerosol, NCOMP=20 bands) | `hcl_radiance/spectral_native.py` → Radiance 6.1a `gensdaymtx` | Perez, Seals & Michalsky 1993 all-weather sky (in gensdaymtx); OPAC continental aerosol spectral shape | Radiance 6.1a source | Perez 1993 sky model now `in-corpus`; OPAC aerosol = `external-standard` standard reference climatology; both still realized inside Radiance |
| — | Skartveit–Olseth / Walkenhorst 2002 stochastic sub-hourly decomposition (Daysim `ds_shortterm`) | `hcl_daysim` → Daysim binary | Skartveit & Olseth 1992, *The probability density and autocorrelation of short-term global and beam irradiance*, Sol. Energy **49**(6):477–487; Walkenhorst, Luther, Reinhart & Timmer 2002, *Dynamic annual daylight simulations based on one-hour and one-minute means of irradiance data*, Sol. Energy **72**(5):385–395 (implemented in Daysim `ds_shortterm`) | ds_shortterm model | `in-corpus` — verified vs primary sources (Skartveit & Olseth 1992 + Walkenhorst 2002); model realized in Daysim |

### 2M. Colour Metrics (CCT/Duv)

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| — | CCT and Duv (SPD → CIE 1931 XYZ → CIE 1960 UCS → Ohno 2013 inversion) | `hcl_core/spectral_metrics.py` → `colour-science` library | Ohno 2013, *Practical Use and Calculation of CCT and Duv*, LEUKOS **10**:47 | Ohno 2013 inversion | `in-corpus` — verified vs primary source; realized via `colour-science` (Mansencal et al.) |

### 2N. Sky Luminance Reconstruction (Chain/Dumortier/Fontoynont 1999)

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| — | Luminance→CCT→SPD reconstruction (sky colour from spatial luminance) | `hcl_core/spectral_reconstruct.py` (template path) | Chain, Dumortier & Fontoynont 1999, *A comprehensive model of luminance, CCT and spectral distribution of skylight*, Sol. Energy **65**:285 | §2–3 (luminance → CCT → S₀/S₁/S₂) | `in-corpus` — verified vs primary source |

### 2O. Glare / UGR

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| — | Glare DGP / UGR (Daylight Glare Probability / Unified Glare Rating) | `hcl_radiance/ies_radiance.py` → Radiance `evalglare -d` | Wienold & Christoffersen 2006, *Evaluation methods and development of a new glare prediction model for daylight environments with the use of CCD cameras*, Energy Build. **38**:743; CIE 117 (UGR) | DGP/UGR definitions | DGP source `in-corpus` — verified vs primary source; model realized in Radiance `evalglare`. CIE 117 (UGR) remains `external-standard` |

### 2P. Daylight Availability Metrics (now computed — 2026-07)

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| — | UDI, sDA, ASE (Useful Daylight Illuminance, Spatial Daylight Autonomy, Annual Sunlight Exposure) — **now computed** (+ cDA, DF) | `hcl_core/daylight_metrics.py` (metrics); `hcl_radiance/daylight_factor.py` (DF); `hcl_core/compliance.py` (thresholds) | Nabil & Mardaljevic 2005, *Useful daylight illuminance: a new paradigm for assessing daylight in buildings*, Light. Res. Technol. **37**(1):41–59 (UDI paradigm) / 2006, *Useful daylight illuminances: a replacement for daylight factors*, Energy Build. **38**(7):905–913; IES LM-83-12 | UDI/sDA/ASE definitions | Nabil & Mardaljevic 2005/2006 `in-corpus` — verified vs primary sources; IES LM-83-12 `in-corpus` (⚠️ **upgraded from `external-standard` 2026-08-14** — primary source obtained); **now computed** (2026-07). **Provenance caveats:** (a) **cDA** (continuous Daylight Autonomy) is uncited above — it originates from **Rogers 2006** (Architectural Energy Corp., SPOT) / Reinhart, Mardaljevic & Rogers 2006, *Dynamic daylight performance metrics for sustainable building design*, LEUKOS **3**(1):7–31; add that reference for cDA. (b) The code's UDI bin edges **300/3000 lx** (supplementary 100–300, autonomous 300–3000, exceed ≥3000) are the **Mardaljevic, Andersen, Roy & Christoffersen 2012** refinement, **not** the Nabil–Mardaljevic 100–2000 lx paradigm cited here — a code-default divergence from the cited sources |

### 2Q. Compliance Thresholds

| ID(s) | Method | Code location | Primary source | Eq./page | Grounding status |
|---|---|---|---|---|---|
| — | Circadian mel-EDI thresholds (250/10/1 lx daytime/evening/sleep) | `hcl_core/compliance.py` | Brown et al. 2022, *Recommendations for daytime, evening, and night-time indoor light exposure*, PLoS Biol. **20**:e3001571 | Consensus table | `in-corpus` — verified vs primary source |
| — | Integrative-lighting recommendations (corroborates mel-EDI threshold rationale) | `hcl_core/compliance.py` (context) | CIE, *Position Statement on Integrative Lighting — Recommending Proper Light at the Proper Time*, 3rd ed. (2024-08) | Whole statement | `in-corpus` — verified vs primary source; corroborating recommendation, not a transcribed threshold |
| — | Mel-EDI circadian thresholds Annex B.5.3 | `hcl_core/compliance.py` | ISO/CIE 8995-1:2025, *Light and Lighting — Lighting of Workplaces, Part 1: Indoor* | Annex B.5.3 | `in-corpus` — verified vs primary source |
| — | Indoor task lighting criteria (Ēm, UGR_L, Uo, Ra) | `hcl_core/compliance.py` | EN 12464-1:2021, *Light and Lighting — Lighting of Work Places, Part 1: Indoor* | Task criteria table | `external-standard` |
| — | Daylight provision target/minimum illuminances | `hcl_core/compliance.py` | EN 17037:2018, *Daylight in Buildings* | Target/minimum table | `external-standard` |
| — | Melanopic EDI point thresholds (150/240 EML → mel-EDI equiv.) | `hcl_core/compliance.py` | WELL Building Standard v2, Feature L03 Circadian Lighting Design (IWBI) | L03 criteria | `external-standard` |

---

## 3. Style Guide

Every Wave-1 doc applies these four reusable snippet formats. Format definitions are canonical; paste verbatim, fill in `<…>` placeholders.

### 3.1 Citation snippet (leads every method section)

```
> **Source:** <Primary author year> — <eq/section>. <Grounding status>.
```

**Example (M-19 direct-normal):**
```
> **Source:** Bird & Riordan 1986, Eq. 2-1. in-corpus (verified vs primary source).
```

**Example (α-opic integral H-5):**
```
> **Source:** CIE S 026/E:2018. external-standard (not in local corpus).
```

**Example (SEDES1 CCM M-28):**
```
> **Source:** Nann & Riordan 1991, Eq. 11. approximate — A/B/C figure-digitized from Fig. 10/11; no published table.
```

### 3.2 Lineage note

```
> **Lineage:** Lark v3.0 (`<source file>`) implements the same method; retained here as cross-validation, not as the source of truth.
```

**Example:**
```
> **Lineage:** Lark v3.0 (`spectrl2_2.c` constants verbatim) implements SPECTRL2; retained here as cross-validation, not as the source of truth.
```

### 3.3 Gap flag (for lineage-only values)

```
> **Grounding gap:** <value> has no published derivation (appears only in Lark/VB `<file:line>`); treat as implementation lineage. <Consequence, e.g. absolute value unvalidated; ratios unaffected>.
```

**Example (the 1/107 factor):**
```
> **Grounding gap:** The `(179/683)·(1/107)` scalar (H-10) has no published derivation; appears only in Lark/VB `melanopic_calcs.bas:40`; treat as implementation lineage. Cancels exactly in ELR and EDI (ratios unaffected); does NOT cancel in absolute E_α or the nonlinear nvRD sigmoid — absolute channel-path mel-EDI and R_D are unvalidated. Use the SPD path (H-5) for absolute irradiance.
```

### 3.4 Reframe rule

Every method section **MUST** be structured in this order:

1. **Citation snippet** (§3.1 above) — the primary-literature source leads.
2. **Equation** — the governing math (transcribed from the named source).
3. **Code realization** — how the equation is realized in the named module/function.
4. **Lineage note** (§3.2) — Lark/VB as cross-validation, if applicable.
5. **Gap flag** (§3.3) — only where a value is `lineage-only` or `approximate`.

The project's identity in all method-section headers reads as: **"implements <method> per <Author Year>"**, never as "port of Lark" or "source file is the spec."

---

## 4. Known Corpus Gaps (for Wave-2 honesty audit)

The following items are referenced in the engine but have **not been obtained as primary sources**. Every occurrence in the docs must carry `external-standard` and must NOT be presented as if the primary source had been verified directly:

> **Acquisition update 2026-06-20:** 13 primary sources obtained and verified. Resolved out of this list: Kasten & Young 1989,
> Ohno 2013, Perez 1993, Subramaniam 2017, Wienold & Christoffersen 2006, Brown et al. 2022, Preetham 1999,
> Amundadottir (journal versions), Khademagha 2018/2016. Remaining gaps below are mostly paywalled
> CIE/ISO/EN standards and the textbook-canonical solar formulae.

- CIE S 026/E:2018 (α-opic action spectra, K^D65) — **normative s_α + K^D65 now `in-corpus`** via the official CIE α-opic Toolbox companion (toolbox User Guide + DIS 026/E:2018 infosheet, primary sources obtained & verified); action-spectra origin Lucas et al. 2014 also `in-corpus`. **Only the full standard prose CIE S 026/E:2018 itself remains paywalled `external-standard`** (the toolbox carries the machine-readable normative values the code uses)
- ~~CIE 15 (D-series S0/S1/S2, daylight locus, M1/M2)~~ → **`in-corpus`** (CIE 15:2004 Colorimetry, 3rd ed.; eigenvectors identical to the 4th-ed. 2018 the code comments cite — primary source obtained & verified). Used in H-21/H-22 (+ Preetham 1999 analytic-daylight basis also `in-corpus`)
- ~~Cooper 1969 (solar declination)~~ → **`in-corpus`** (primary source obtained & verified) (M-1, M-4)
- ~~Spencer 1971 (Earth-radius-vector) — M-6~~ → **`in-corpus`** (`Fourier paper.md`, verbatim transcription obtained & verified; original CSIRO *Search* note never issued as PDF)
- ~~Kasten & Young 1989 (air mass) — M-8~~ → **`in-corpus`** (primary source obtained & verified)
- ~~Gueymard 1994 (precipitable water) — M-12~~ → **`in-corpus`** (primary source obtained & verified)
- ~~Reitan 1963 (dew-point PWV fallback) — M-13~~ → **`in-corpus`** (primary source obtained; scanned image-only AMS PDF)
- ~~van Heuklon 1979 (ozone climatology) — M-7~~ → **`in-corpus`** (primary source obtained & verified)
- ~~Ohno 2013 (CCT/Duv inversion)~~ → **`in-corpus`** (primary source obtained & verified)
- ~~Perez et al. 1990/1993 (all-weather sky)~~ → **both now `in-corpus`** (Perez 1993 + Perez 1990, primary sources obtained & verified); model still embedded in gendaylit/gendaymtx
- ~~Tregenza 1987 / Reinhart 2001 (sky-vault patches)~~ → **`in-corpus`** (Tregenza 1987 + Reinhart & Walkenhorst 2001, primary sources obtained & verified); discretization still in gendaymtx
- ~~Skartveit & Olseth / Walkenhorst 2002 (sub-hourly decomposition)~~ → **`in-corpus`** (Skartveit & Olseth 1992 + Walkenhorst 2002, primary sources obtained & verified); model still in Daysim
- ~~Wienold & Christoffersen 2006 (DGP)~~ → **`in-corpus`** (primary source obtained & verified); model still embedded in evalglare
- ~~Subramaniam 2017 (2-phase DDS)~~ → **`in-corpus`** (primary source obtained & verified)
- ~~Nabil & Mardaljevic 2005/2006 (UDI)~~ → **`in-corpus`** (Nabil & Mardaljevic 2005 LRT + 2006 Energy Build., primary sources obtained & verified); metrics now computed (§2P)
- ~~IES LM-63 — referenced; not obtained~~ → **`in-corpus`** as ANSI/IESNA LM-63-02 (primary source obtained & verified) — H-23…H-26
- ~~IES LM-83-12 — referenced-not-computed; not obtained~~ → **`in-corpus`** (primary source obtained: *Approved Method: IES Spatial Daylight Autonomy (sDA) and Annual Sunlight Exposure (ASE)*, IES LM-83-12) — and **now computed** by the `lm83_daylight` tool, which operates blinds on the standard's own §2.2.6 trigger. ⚠️ `lm83_method_conformant` is **always false by design**: §§2.2.8–2.2.11 (glazing, obstructions, reflectances, furniture) are out of scope, so glazing runs at raw `tvis`, biasing sDA up — read `conditions.departures`. ⚠️ Superseded in later IES practice by **LM-83-23**, which is *not* obtained.
- EN 12464-1:2021 — referenced; not obtained (external-standard)
- EN 17037:2018 — referenced; not obtained (external-standard)
- WELL v2 L03 — referenced; not obtained (external-standard)
- ~~Brown et al. 2022~~ → **`in-corpus`** (primary source obtained & verified) (+ CIE Integrative-Lighting position statement 2024, `in-corpus`)
- **Amundadottir 2016**: nvRD **model now `in-corpus`** via the journal versions (Amundadottir, Lockley & Andersen 2016 LRT post-print + Amundadottir, Rockcastle, Khanie & Andersen 2017 Build. Environ. post-print, primary sources obtained & verified); the **EPFL thesis №7146** (full constant derivations: 260.7, z_eff, n=3.55) is **still `external-standard`** (not acquired)
- ~~Khademagha "2021" (FOV/directional ipRGC)~~ → **`in-corpus`** as Khademagha et al. **2018** (primary source obtained & verified) + 2016 review; **year attribution corrected**
- ~~Gkaintzatzi-Masouti et al. / Pierson 2021 SimAUD~~ → **`in-corpus`** — actually **Pierson, Aarts & Andersen 2021, BS2021** (IBPSA), DOI 10.26868/25222708.2021.30583 (primary source obtained & verified; attribution corrected; see §1)
- **SEDES1 CCM coefficients A/B/C (M-28)** — *primary source obtained* (Nann & Riordan 1991, `in-corpus`), **but the coefficients themselves are figure-only**: the paper publishes them solely as the Fig. 11 curves (246 values, plotted, never tabulated). The **shipped default** is a faithful 10 nm digitization of those Fig. 11 A/B/C/σ curves (330–1100 nm, reanchored to unity at clear Kt) — a documented `approximate`; the earlier **9-anchor seed** reconstructed from Fig. 10's class means survives only as the opt-in `cloud_variant="seed"`. A 2026-06-22 investigation (computational digitization attempt; SEDES2 + NREL TP-520-47277 + Bartlett 1998 search; GitHub/pvlib code search) found **no machine-readable source anywhere**; decision = keep the figure-validated digitization. The CCM is now also locally re-fittable from caller-supplied data (`cloud_variant="local"` via `hcl_core.sedes1_fit`), with its Fig. 11 regression σ surfaced in provenance. Full record: [spectral-sky-methodology.md](spectral-sky-methodology.md) §8.6.

---

## 5. Primary-Source Index (methods grounding)

For convenience, the full list of primary sources that supply grounding for this engine:

| Source | Methods grounded |
|---|---|
| Bird & Riordan 1986, *Simple solar spectral model for direct and diffuse irradiance on horizontal and tilted planes at the Earth's surface for cloudless atmospheres*, J. Climate Appl. Meteorol. **25**:87 (SPECTRL2) | M-9, M-11, M-14…M-24 |
| Nann & Riordan 1991, *Solar spectral irradiance under clear and cloudy skies: measurements and a semiempirical model*, J. Appl. Meteorol. **30**:447 (SEDES1) | M-25…M-29 |
| Inanici, Brennan & Clark 2015, *Spectral Daylighting Simulations: Computing Circadian Light*, Proc. BS2015, Hyderabad (Lark origin / spectral channels) | H-2, H-4 (channel layout) |
| Jung, Cheng, Brennan & Inanici 2023, *Multispectral Lighting Simulation Approaches for Predicting Opsin-driven Metrics and their Application in a NICU*, Proc. BS2023 (OPN5 / NICU) | H-4 (OPN5 neuropic scheme) |
| Chain, Dumortier & Fontoynont 1999, *A comprehensive model of luminance, CCT and spectral distribution of skylight*, Sol. Energy **65**:285 (luminance→CCT→SPD) | sky SPD reconstruction |
| Gueymard 2019, *The SMARTS spectral irradiance model after 25 years*, Sol. Energy **187**:233 | SMARTS oracle engine |
| Gueymard — SMARTS 2.9.5 user manual | SMARTS deck format |
| Ward 2024 — HyperSpec Radiance tutorial | gensdaymtx 20-band native path |
| *Human-Centric Lighting: Foundational Considerations and a Five-Step Design Process* (Five-Step HCL) | H-12 (EML ↔ mel-EDI) |
| ISO/CIE 8995-1:2025, *Light and Lighting — Lighting of Workplaces, Part 1: Indoor* | Compliance thresholds Annex B.5.3 |
| Pierson et al. 2022/23, *Validation of spectral simulation tools in the context of ipRGC-influenced light responses of building occupants* | nvRD ±20 % accuracy envelope |
| Kasten & Young 1989, *Revised optical air mass tables and approximation formula*, Appl. Opt. **28**:4735 | M-8 |
| Perez, Seals & Michalsky 1993, *All-weather model for sky luminance distribution — preliminary configuration and validation*, Sol. Energy **50**:235 | H-30 (sky model); gensdaymtx native path |
| Preetham, Shirley & Smits 1999, *A Practical Analytic Model for Daylight*, SIGGRAPH 1999 | H-21/H-22 (analytic-daylight / RGB→D-series basis) |
| Lucas et al. 2014, *Measuring and using light in the melanopsin age*, Trends Neurosci. **37**(1):1 | H-5 (α-opic action-spectra **origin**; normative curves remain CIE S 026 external) |
| Amundadottir, Lockley & Andersen 2016, *Unified framework to evaluate non-visual spectral effectiveness of light for human health*, Light. Res. Technol. (published nvRD model) | H-13…H-19 (nvRD model structure) |
| Amundadottir, Rockcastle, Khanie & Andersen 2017, *A human-centric approach…*, Build. Environ. **113**:5 (immersive FOV) | H-13…H-19 application; FOV (§2F) |
| Subramaniam 2017, *Daylighting Simulations with Radiance using Matrix-based Methods*, LBNL | H-30 (2-phase DDS) |
| Ohno 2013, *Practical Use and Calculation of CCT and Duv*, LEUKOS **10**:47 | CCT/Duv (§2M) |
| Brown et al. 2022, *Recommendations for daytime, evening, and night-time indoor light exposure*, PLoS Biol. **20**:e3001571 | circadian mel-EDI thresholds (§2Q) |
| Wienold & Christoffersen 2006, *Evaluation methods and development of a new glare prediction model for daylight environments with the use of CCD cameras*, Energy Build. **38**:743 (DGP) | DGP (§2O) |
| Khademagha et al. 2018, *A multidirectional spectral measurement method and instrument to investigate non-image-forming effects of light*, Meas. Sci. Technol. **29**(8):085902 | FOV / directional ipRGC (§2F) |
| Khademagha et al. 2016, *Implementing non-image-forming effects of light in the built environment: a review on what we need*, Build. Environ. (NIF effects review) | FOV / directional ipRGC context (§2F) |
| CIE 2024, *Position Statement on Integrative Lighting — Recommending Proper Light at the Proper Time*, 3rd ed. | circadian recommendations context (§2Q) |
| CIE Div. 6 — α-opic Toolbox v1.049a User Guide (DOI 10.25039/S026.2018.UG) | H-5…H-9, H-11, M-32…M-34 (normative s_α + K^D65 companion to CIE S 026:2018) |
| CIE — DIS 026/E:2018 infosheet (scope, 5 photoreceptor functions, FOV/age) | CIE S 026 scope/definitions companion |
| Cooper 1969, *The absorption of radiation in solar stills*, Sol. Energy **12**(3):333–346 | M-1, M-4 (solar declination, zenith) |
| Perez, Ineichen, Seals, Michalsky & Stewart 1990, *Modeling daylight availability and irradiance components from direct and global irradiance*, Sol. Energy **44**(5):271–289 | H-30 (sky model; companion to Perez 1993) |
| Skartveit & Olseth 1992, *The probability density and autocorrelation of short-term global and beam irradiance*, Sol. Energy **49**(6):477–487 | sub-hourly decomposition (§2L) |
| Walkenhorst, Luther, Reinhart & Timmer 2002, *Dynamic annual daylight simulations based on one-hour and one-minute means of irradiance data*, Sol. Energy **72**(5):385–395 | sub-hourly decomposition (§2L) |
| Reinhart & Walkenhorst 2001, *Validation of dynamic RADIANCE-based daylight simulations for a test office with external blinds*, Energy Build. **33**(7):683–697 | H-30 (MF sky-patch subdivisions) |
| Tregenza 1987, *Subdivision of the sky hemisphere for luminance measurements*, Light. Res. Technol. **19**(1):13–14 | H-30 (145-patch base dome) |
| Nabil & Mardaljevic 2005, *Useful daylight illuminance: a new paradigm for assessing daylight in buildings*, Light. Res. Technol. **37**(1):41–59 | UDI (§2P, now computed) |
| Nabil & Mardaljevic 2006, *Useful daylight illuminances: a replacement for daylight factors*, Energy Build. **38**(7):905–913 | UDI (§2P, now computed) |
| Pierson, Aarts & Andersen 2021, *Validation of Spectral Simulation Tools for the Prediction of Indoor Daylight Exposure*, Proc. BS2021 (IBPSA), DOI 10.26868/25222708.2021.30583 | spectral-simulation validation context |
| CIE 15:2004, *Technical Report: Colorimetry*, 3rd ed. (D-series S₀/S₁/S₂, daylight locus) | H-21/H-22 (D-series reference SPD); H-8 (D65 locus) |
| Spencer 1971, *Fourier series representation of the position of the Sun*, Search **2**(5):172 (`Fourier paper.md`, verbatim transcription; via NREL SOLPOS) | M-6 (Earth-radius vector 1/r²); also corroborates M-17 (H₀λ × R_v) |
| van Heuklon 1979, *Estimating atmospheric ozone for solar radiation models*, Sol. Energy **22**(1):63–68 | M-7 (ozone climatology u_O3; Eq. 4 / Table 1 verified verbatim) |
| Gueymard 1994, *Analysis of monthly average atmospheric precipitable water and turbidity in Canada and Northern United States*, Sol. Energy **53**(1):57 | M-12 (precipitable water from T/RH) |
| Reitan 1963, *Surface Dew Point and Water Vapor Aloft*, J. Appl. Meteorol. **2**(6):776 (scanned image-only) | M-13 (precipitable water from dew point, fallback) |
| ANSI/IESNA LM-63-02, *Standard File Format for the Electronic Transfer of Photometric Data* | H-23…H-26 (IES photometry format, zonal-flux, efficacy/LOR, ies2rad) |
| Tregenza & Waters 1983, *Daylight coefficients*, Light. Res. Technol. **15**(2):65–71 | H-30 (origin of the daylight coefficient; scalar per sensor per patch) |
| Bourgeois, Reinhart & Ward 2008, *Standard daylight coefficient model for dynamic daylighting simulations*, Build. Res. & Inf. **36**(1):68–82 | H-30 (the DDS model executed inside Daysim; companion to Subramaniam 2017) |

> **See also §6** for in-corpus (context) sources that ground **no** equation — clear-sky / spectral-irradiance
> context & validation literature, listed separately so they are never mistaken for method sources.

---

## 6. Context & Corroborating Literature (sources that ground no M-/H- equation)

A cohort of **clear-sky solar / spectral-irradiance, luminous-efficacy, and measured-spectral-variability**
literature was consulted on 2026-06-20. These are corroborating sources that **ground no transcribed
equation**: they **motivate and corroborate** the engine but supply **no equation transcribed in the code**
— the spectral physics remains Bird & Riordan 1986 (SPECTRL2, M-9…M-24), Nann & Riordan 1991 (SEDES1,
M-25…M-29), and Gueymard 2019 (SMARTS). None carries an M-/H- ID and **none may be cited as a method
source.** Grounding column reads `in-corpus (context)` — a consulted source that grounds no transcribed
equation (distinct from the four method-grounding values in the header; `in-corpus (context)` means *the
source was consulted but grounds no transcribed equation*, not *it sources an equation*).

| Source | Role / what it corroborates | Grounding |
|---|---|---|
| Bird, Riordan & Myers 1987 — *Investigation of a cloud-cover modification to SPCTRAL2*, SERI/TR-215-3038 | **The SPCTRAL2 cloud lineage, and the reason it stayed open.** Establishes the normalise-to-measured-broadband-then-compare procedure the SEDES1 bridge inherits, and the design constraint that a usable modifier must run on broadband + meteorological data rather than cloud microphysics. Also publishes SPCTRAL2's own clear-sky accuracy: **10 % UV / 5 % VIS / 6 % NIR** against instrument uncertainties of ≈6/7/10 %. ⚠️ **Its conclusion is negative** — *"Results indicate the possible form of the spectral corrections; however, we must analyze additional data to develop a spectral transmission function for cloudy-sky conditions."* SERI did **not** deliver a working cloud modifier in 1987, which is why Nann & Riordan 1991 remains the only semi-empirical bridge available and why M-28's single-campaign caveat cannot be escaped by an earlier source. | `in-corpus (context)` |
| Riordan 1986 — *Spectral solar irradiance models and data sets*, *Solar Cells* **18**:223 | **Bibliographic anchor for the SPECTRL2 report number.** Its reference [1] gives the full citation of **SERI/TR-215-2436 (Bird & Riordan 1984)** — the report `spectral_engine/spectrl2.py` cites in its docstring, previously undocumented in this corpus. Independently corroborates the clear-sky sensitivity ranking behind the EPW-derived atmospheric state (air mass, turbidity, water vapour dominant; turbidity biting hardest in the visible and worse on the direct beam), and records that in 1986 cloud-cover modifiers were still awaiting the measurements needed to build them. | `in-corpus (context)` |
| Cannon 1986 — *Spectral solar irradiance instrumentation and measurement techniques*, *Solar Cells* **18**:233 | Companion to Riordan 1986 from the same 1985 SERI workshop (its reference [16]). **Context only.** Corroborates that spectral measurement carries instrument-specific uncertainty that must be stated rather than assumed away. | `in-corpus (context)` |
| Xie & Sengupta 2018 — FARMS-NIT **Part I (clear-sky)**, *Sol. Energy* **174**:691 | Clear-sky **alternative** to SPECTRL2; **corroborates** SMARTS-as-clear-sky-oracle (it too takes its atmospheric optical properties from SMARTS). | `in-corpus (context)` |
| Xie, Sengupta & Wang 2019 — FARMS-NIT **Part II (cloudy-sky)**, *Sol. Energy* **188**:799 | **The closest published alternative to the SEDES1 cloud bridge**, and a physically stronger one: a three-layer (upper-clear / cloud / lower-clear) analytic RTE solution over six photon paths, 2002 bands 0.28–4.0 µm, with cloud BTDF/transmittance/reflectance from a 32-stream DISORT lookup table — within 2–3 % of DISORT. ⚠️ **Not adoptable here, for two structural reasons**: it is driven by **cloud optical thickness + cloud effective particle size** (satellite retrievals an EPW does not carry and which cannot be recovered from hourly DNI/DHI), and it is **not constrained to reproduce the driving file's broadband energy** — the invariant this pipeline is built on. Also omits aerosol scattering beneath cloud (p. 801), and no public implementation of the *narrowband* model exists (the NREL FARMS release is the **broadband** model of Xie, Sengupta & Dudhia 2016 — GHI/DNI/DHI only, no spectral component). Frames why SEDES1 stays semi-empirical rather than physical. | `in-corpus (context)` |
| Gueymard & Thevenard 2009 — REST2 broadband DB, *Sol. Energy* **83**:1998 | **Corroborates** the EPW→AOD/PWV/ozone/albedo input set and its sensitivity ranking (AOD & PWV dominate; ozone/NO₂/pressure near-negligible). REST2 ≠ engine's SPECTRL2. | `in-corpus (context)` |
| Abreu, Gueymard, Canhoto & Costa 2023, *Sol. Energy* **252**:309 | **Validation/benchmark.** Corroborates the §13 caveat that atmospheric-input quality bounds DNI accuracy (gridded/reanalysis AOD & α unreliable; even research-grade clear-sky validation is ~1.8 % bias-bound). | `in-corpus (context)` |
| Gueymard 1993 — 11-model clear-sky benchmark, *Sol. Energy* **51**:121 | **Corroborates** that aerosol turbidity (then PWV) dominates clear-sky accuracy → justifies the engine's EPW AOD/PWV emphasis. Physical > empirical. | `in-corpus (context)` |
| Louche, Simonnot, Iqbal & Mermier 1988, *Sol. Energy* **41**:273 | **Validation context** (Bird-Hulstrom broadband, the genealogical predecessor of SPECTRL2); published precedent for the engine's broadband-energy validation of clear-sky DNI/DHI. ω₀≈0.95 constant stand-in. | `in-corpus (context)` |
| Gueymard 1989 — two-band CPCR2, *Sol. Energy* **43**:253 | **Lineage/context.** Parameterized two-band predecessor in the Gueymard→SMARTS lineage; opposite methodological choice to the engine's full-spectral SPECTRL2. | `in-corpus (context)` |
| López & Gueymard 2007 — efficacy ANN, *Sol. Energy* **81**:929 | **Context/alternative.** ANN luminous-efficacy surrogate trained on SMARTS; a lossy alternative to the engine's exact 683·V(λ) per-nm integral (H-6). Confirms PWV as dominant efficacy driver. Not in pipeline. | `in-corpus (context)` |
| Petržala, Komár & Kocifaj 2017, *Renew. Energy* **106**:212 | **Corroborates M-31** (identical isotropic ground-reflection form) + illuminance-via-V(λ); **alternative** to M-24 transposition. Most technically substantive of the cohort — cross-ref at §2E. | `in-corpus (context)` |
| Wang et al. 2025 — spectral skewness (SSIE-SO), *Renew. Energy* **256**:124417 | **Alternative** to the SEDES1 cloud bridge (measurement-trained XGBoost + sky-imager); independently flags clear-sky-model spectral mis-estimation under cloud. Needs inputs an EPW lacks. | `in-corpus (context)` |
| Paudyal et al. 2024 — APE distributions, N. Europe, *Renew. Energy* **224**:120057 | **Context.** Documents real high-latitude measured spectral variability (bimodal clear/cloudy winter); corroborates AM & PWV as dominant SPECTRL2 atmospheric drivers. PV band 350–1050 nm ≠ engine 380–780 nm. | `in-corpus (context)` |
| Berger, Bathiebo, Kieno & Awanou 1992, *Renew. Energy* **2**:139 | **Context only — wrong band.** Thermal-IR (4–40 µm) longwave sky-emissivity vs altitude (LOWTRAN 6); grounds none of the engine's shortwave equations. Mild support for dew-point as a PWV proxy (cf. M-12/M-13). | `in-corpus (context)` |
| Gueymard 2019 — SMARTS after 25 years, *Sol. Energy* **187**:233 | **Not context — method source.** Already `in-corpus` as the SMARTS-oracle grounding (§2L); listed here only to note it is a method source, not a context-only entry. | `in-corpus` (SMARTS oracle) |
| Jain 1988 — accurate monthly extraterrestrial irradiation & sunshine duration, *Solar & Wind Technology* **5**(1):41–53 | **Context.** Transcribes the Spencer 1971 Fourier series for declination & eccentricity (the same δ/R_v formulae used at M-1/M-6); a worked tabular corroboration, not the primary Spencer source. | `in-corpus (context)` |
| Skartveit, Olseth & Tuft 1998 — hourly diffuse-fraction model with variability & albedo correction, *Sol. Energy* **63**(3):173–183 | **Context.** The improved successor to Skartveit & Olseth 1992 (§2L); corroborates the diffuse/beam decomposition lineage but is not the `ds_shortterm` source. | `in-corpus (context)` |
| Ng, Adam, Inayatullah & Ab Kadir 2014 — solar radiation on diversely oriented surfaces & optimum tilts, *Int. J. Energy Environ. Eng.* **5**:5 | **Context.** Tilted-surface transposition via the K_T model (Malaysian tropical latitude); an applied alternative to the M-24/M-31 transposition, grounds no transcribed equation. | `in-corpus (context)` |

> **Round-4 additions (2026-06-21).** 22
> further consulted sources; none grounds a transcribed M-/H- equation, **none may be cited as a method
> source.** (Paudyal et al. 2024, also in the round-4 inbox, is a **duplicate** of the existing row above and
> was not re-filed.)

| Source | Role / what it corroborates | Grounding |
|---|---|---|
| Yang, Liu & Wu 2026 — *Review of solar spectral irradiance modelling at ground level: current methods and ML opportunities*, *Energy* **344**:139967 (`Review-of-solar-…2026`) | **Review/landscape.** Surveys physical + ML ground-level spectral models; positions the engine's SPECTRL2/SMARTS choice within the field. G-15-adjacent. | `in-corpus (context)` |
| Potočnik, Pajek & Košir 2024 — *Experimental investigation of the impact of model complexity on indoor daylight spectral simulations*, *Dev. Built Environ.* **20**:100543 (`Experimental-investigation-…2024`) | **Validation.** Quantifies how geometry/material model complexity affects indoor daylight **spectral** sim accuracy; corroborates §2G fidelity caveats. | `in-corpus (context)` |
| Ma & Yang 2026 — *Evaluating TabPFN for reconstructing spectral solar irradiance from broadband observations*, *J. Atmos. Solar-Terr. Phys.* **284**:106836 (`Evaluating-TabPFN-…2026`) | **Alternative.** ML broadband→spectral reconstruction baseline; a data-driven alternative to the engine's H-20/H-22 reconstruction. | `in-corpus (context)` |
| Torres-Ramírez, Elizondo, García-Domingo, Nofuentes & Talavera 2015 — *Modelling the spectral irradiance distribution in sunny inland locations using an ANN-based methodology*, *Energy* **86**:323 (`Modelling-the-spectral-…2015`) | **Alternative.** ANN spectral-distribution surrogate; lossy alternative to physical SPECTRL2 (M-14…M-24). | `in-corpus (context)` |
| del Campo-Ávila, Piliougine, Morales-Bueno & Mora-López 2019 — *A data mining system for predicting solar global spectral irradiance*, *Renew. Energy* **133**:828 (`A-data-mining-system-…2019`) | **Alternative.** Data-mining spectral predictor for thin-film PV response bands; not in the engine pipeline. | `in-corpus (context)` |
| Zhang, Chaudhary, Rodríguez-Gallegos & Rahman 2025 — *Advancements in solar spectral irradiance modelling for PV systems: a ML approach utilising on-site data*, *Next Energy* **8**:100320 (`Advancements-in-solar-…2025`) | **Alternative/landscape.** On-site ML spectral modelling for PV; corroborates the field direction, grounds no equation. | `in-corpus (context)` |
| Zamalloa-Jara, Sevillano-Bendezú, Ulbrich, Nofuentes, Grieseler & Töfflinger 2023 — *Overirradiance conditions and their impact on the spectral distribution at low- and mid-latitude sites*, *Sol. Energy* **259**:99 (`Overirradiance-…2023`) | **Cloud-spectral (G-13).** Measured cloud-enhancement spectral shifts; bears on the SEDES1 cloud bridge (M-25…M-29) but needs inputs an EPW lacks. | `in-corpus (context)` |
| Martínez-Chico, Batlles & Bosch 2011 — *Cloud classification in a mediterranean location using radiation data and sky images*, *Energy* **36**:4055 (`Cloud-classification-…2011`) | **Cloud-spectral (G-13).** Cloud classification from radiation + sky imagery; needs sky-imager inputs an EPW lacks. | `in-corpus (context)` |
| Serrano & Boscà 2013 — *Selection of cloudless sky conditions by applying solar global ultraviolet irradiance measurements*, *Atmos. Res.* **132–133**:291 (`Selection-of-cloudless-…2013`) | **Clear/cloudy partition.** UV-based cloudless-sky detection; corroborates the clear-vs-cloudy split feeding K_t (M-25). | `in-corpus (context)` |
| Ruiz-Arias, Alsamamra, Tovar-Pescador & Pozo-Vázquez 2010 — *Proposal of a regressive model for the hourly diffuse solar radiation under all sky conditions*, *Energy Convers. Manag.* **51**:881 (`Proposal-of-a-regressive-…2010`) | **Diffuse fraction.** All-sky diffuse-fraction regression; corroborates the diffuse/beam decomposition lineage (cf §2L). | `in-corpus (context)` |
| Kaskaoutis & Kambezidis 2009 — *The diffuse-to-global and diffuse-to-direct-beam spectral irradiance ratios as turbidity indexes in an urban environment*, *J. Atmos. Solar-Terr. Phys.* **71**:246 (`The-diffuse-to-global-…2009`) | **Turbidity driver.** Spectral ratios as turbidity indices; corroborates AOD/turbidity dominance (M-14; EPW AOD emphasis). | `in-corpus (context)` |
| Ogunjobi & Kim 2004 — *Ultraviolet (0.280–0.400 µm) and broadband solar hourly radiation at Kwangju, South Korea: correlation with AOD and clearness index*, *Atmos. Res.* **71**:193 (`Ultraviolet-…2004`) | **Atmospheric drivers.** Corroborates AOD & clearness-index as dominant drivers (M-14/M-25). | `in-corpus (context)` |
| Jacovides, Tymvios, Assimakopoulos & Kaltsounides 2007 — *The dependence of global and diffuse PAR radiation components on sky conditions at Athens, Greece*, *Agric. For. Meteorol.* **143**:277 (`The-dependence-…2007`) | **Band-partial context.** PAR-band (400–700 nm) diffuse/global vs sky condition; corroborates diffuse-fraction & sky dependence. | `in-corpus (context)` |
| de la Casinière, Grenier, Cabot & Werneck-Faga 1993 — *Altitude effect on the clearness index in the French Alps*, *Sol. Energy* **51**(2):93 (`Altitude-effect-…1993`) | **Clearness-index context.** K_t vs altitude via Ångström turbidity; corroborates M-25 sensitivity (complements Berger 1992). | `in-corpus (context)` |
| Maskarenj, Deroisy & Altomonte 2022 — *A new tool and workflow for the simulation of the non-image-forming effects of light*, *Energy Build.* **262**:112012 (`A-new-tool-…2022`) | **Alternative NIF tool.** Independent NIF-simulation workflow; corroborates the §2F/§2G application (distinct from Pierson — UCLouvain/BBRI). | `in-corpus (context)` |
| Nazari, Matusiak & Stefani 2023 — *Utilising spectral lighting simulation technique for evaluating transmitted daylight through glazing: exploring the non-visual effects and colour appearance*, *Heliyon* **9**:e20436 (`Utilising-…2023`) | **NIF + colour application.** Spectral-sim of glazing transmission for NIF + colour appearance; corroborates §2F/§2G + CCT (§2M). | `in-corpus (context)` |
| Hao, Xu & Schlangen 2024 — *Evaluation and optimization of annual light variations for visual and non-visual effects within a ground-floor middle school classroom*, *J. Build. Eng.* **98**:111293 (`Evaluation-and-optimization-…2024`) | **nvRD application.** Annual visual/non-visual daylight optimization; corroborates §2G. | `in-corpus (context)` |
| Xu, Gao & Wu 2025 — *The visual and non-visual effects of annual daylighting performance on middle school students: a longitudinal field survey*, *Energy Build.* **331**:115364 (`The-visual-and-non-visual-…2025`) | **nvRD field study.** Longitudinal field corroboration of annual nvRD/daylight effects; §2G application. | `in-corpus (context)` |
| Wu, Chen, Xu, Yao & Lin 2024 — *Visual and non-visual effects in micro-space luminous environments with visual display terminals*, *Build. Environ.* **256**:111492 (`Visual-and-non-visual-…2024`) | **nvRD application.** NIF effects in micro-space/VDT environments; §2G application context. | `in-corpus (context)` |
| Lee, Matusiak, Geisler-Moroder, Selkowitz & Heschong 2022 — *Advocating for view and daylight in buildings: next steps*, *Energy Build.* **265**:112079 (`Advocating-…2022`) | **Motivation.** Daylight/view position paper; motivates the daylight-provision framing (§2P/§2Q), grounds no equation. | `in-corpus (context)` |
| Ghosh, Norton & Duffy 2017 — *Effect of sky conditions on light transmission through a suspended particle device switchable glazing*, *Sol. Energy Mater. Sol. Cells* **160**:134 (`Effect-of-sky-…2017`) | **Tangential.** Daylight transmission through switchable glazing under varying sky; glazing-transmission context only. | `in-corpus (context)` |
| Yin, Zhang, Xie, Yang, Tan, Lin & Liu 2026 — *Modeling of longwave radiation on coastal building façades based on field measurements*, *Build. Environ.* **287**:113859 (`Modeling-of-longwave-…2026`) | **Context only — wrong band.** Thermal-IR longwave façade radiation; grounds none of the engine's shortwave equations (cf. Berger 1992). | `in-corpus (context)` |

> **SEDES1 coefficient-sourcing cohort (2026-06-22).** Consulted while investigating whether the SEDES1 A/B/C (M-28) could be replaced with a
> machine-readable source rather than the figure-digitized 9-anchor seed. Full record in
> [spectral-sky-methodology.md](spectral-sky-methodology.md) §8.6. None tabulates the coefficients.

| Source | Role / what it corroborates | Grounding |
|---|---|---|
| Nann & Emery 1992 — *Spectral effects on PV-device rating* (SEDES2), *Sol. Energy Mater. Sol. Cells* **27**:189 (`1-s2.0-0927024892900832-main`) | **SEDES2 primary source.** The successor to SEDES1 (M-25…M-29): replaces the single $K_t$ quadratic with **4 cloud-cover modifiers/wavelength × zenith bin**, statistically re-derived, *"slightly site dependent"* (Stuttgart DWD 1987–89; 300–1400 nm). Second-source confirmation of the §8.3 Germany/site caveat; documents a zenith dependence the implemented SEDES1 model omits. Adopting it = model swap, not an M-28 fix. | `in-corpus (context)` |
| Marion et al. (NREL/TP-520-47277, 2010) — *Preliminary Investigation of Methods for Correcting for Variations in Solar Spectrum* (`Preliminary-Investigation-…`) | **SEDES2 application.** Uses NREL's SEDES2 code for PV spectral-mismatch correction (300–2500 nm). Confirms SEDES2-code existence but **tabulates no coefficients**. | `in-corpus (context)` |
| Bartlett, Wood & Bowker 1998 — *The spectral effects of clouds on solar irradiance*, *J. Geophys. Res. Oceans* **103**:31017 (`…1998…Bartlett…`) | **Alternative cloud-spectral model.** Own BRGC parameterization; cites Nann & Riordan but reproduces none of the SEDES1 coefficients. Independent evidence cloud spectral mis-estimation is real. | `in-corpus (context)` |

> **Atmospheric-physics-refinements cohort (2026-07-04).** Consulted/filed while implementing the four
> opt-in atmosphere refinements (D-3 AOD anchor, D-7 aerosol asymmetry *g*, D-20 SMARTS settable α, and the
> van Heuklon ozone climatology — now **computed** opt-in via `ozone_mode="climatology"`, see §2B / M-7).
> None grounds a transcribed M-/H- equation; the van Heuklon coefficients remain the M-7 primary
> (van Heuklon 1979, §5). Filed under `Literature/01-solar-geometry-atmosphere/` (ozone) and
> `Literature/11-context-corroborating/`.

| Source | Role / what it corroborates | Grounding |
|---|---|---|
| Karavana-Papadimou, Kambezidis et al. 2013 — *Model for estimating atmospheric ozone content over Europe for use in solar radiation algorithms*, *Global NEST J.* **15**(2):152–162 (`152-162_1020_Karavana-Papadimou_15-2`) | **Ozone corroboration (M-7).** Reproduces the original van Heuklon 1979 model **verbatim** as its eq. (2), independently confirming the NH coefficients (A=150, C=40, **F=−30**, β=1.28, J=235) the pure-Python `van_heuklon_ozone` now uses — i.e. maximum ozone in NH **spring**, not summer. (Its eq. (4) European **recalibration** — J=260, A=76.3 — is a *different*, unadopted model.) Caught + fixed a plan-level phase bug; see spectral-sky-methodology.md §6 and as-built D-2. | `in-corpus (context)` |
| Herman et al. 1993 — *Ozone depletion at northern and southern latitudes derived from Nimbus-7 TOMS*, *J. Geophys. Res. Atmos.* (20 Jul 1993) (`…1993…Herman…Ozone depletion…`) | **Ozone climatology corroboration.** TOMS-measured total-ozone latitude/season structure; corroborates the van Heuklon spring-max / autumn-min phase the M-7 fix restored. | `in-corpus (context)` |
| Balakrishnan, Diakite-Kortlever, Dumortier et al. — *SKYSPECTRA: an opensource data package of worldwide spectral daylight* (`OP26-BalakrishnanPriji`) | **Measured-spectral dataset (validation).** The methods paper for the SKYSPECTRA dataset (Zenodo 8147546) already used as the P4 external spectral cross-check (`skyspectra.py`, §2L / technical-reference §skyspectra). Provides measured spectral daylight for validation; grounds no equation. | `in-corpus (context)` |
| Papachristopoulou 2023 — *Solar radiation/energy forecasting and measurement applications: the role of clouds and aerosols* (PhD thesis, Nat. & Kapodistrian Univ. of Athens) (`PhD_thesis_PapachristopoulouK_final`) | **Athens atmosphere context.** Clouds + aerosols in solar-radiation forecasting over Athens; corroborates the engine's AOD/cloud emphasis and the measured-validation context. | `in-corpus (context)` |
| Annear 2007 — *A comparison of five models for estimating clear-sky solar radiation*, *Water Resources Research* **43** (`Water Resources Research - 2007 - Annear…`) | **Clear-sky benchmark.** Five-model clear-sky solar-radiation comparison (broadband); corroborates the clear-sky-modelling emphasis (parallel to the Gueymard 1993 11-model benchmark above). Grounds no engine equation. | `in-corpus (context)` |

> **July-2026 non-visual/metrology cohort (filed 2026-07-13).** Six papers added to the corpus in July 2026 and
> evaluated end-to-end against the engine in an internal proposal document (not part of this
> repository), which lists them as P1–P6.
> **None grounds a transcribed M-/H- equation and none may be cited as a method source** — every capability they
> would feed is still a proposal (Plans A–D, recorded in the project's planning notes outside this repository). Their present value is
> **corroboration** (they independently reconfirm `K^D65_mel,v = 1.3262 mW/lm` and the `EML = 1.103 × mel-EDI`
> factor at H-12, and they confirm the `1/107` channel-path constant is lineage-only, not a bug — §6.4) plus
> **validation anchors and guardrails**. Headline verdict of that evaluation: the **EPW→spectral-sky physics needs
> no upgrade** from these papers — P1's cloud attenuation is *spectrally neutral*, i.e. **weaker** than the
> wavelength-dependent SEDES1 CCM (M-25…M-29); do not regress to it. The gains are in the temporal/circadian layer.
> Filed under `06-alpha-opic-circadian/` (P3, P5, P6), `07-nvrd-nonvisual-models/` (P4),
> `08-daylight-transport-sim/` (P2) and `11-context-corroborating/` (P1).

| Source | Role / what it corroborates | Grounding |
|---|---|---|
| Katsikogiannis, Isabella, Santbergen & Ziar 2026 — *Tracing rays from leaves to sky: multispectral, penumbra-aware irradiance modeling for agrivoltaic orchards*, *Appl. Energy* **420**:128087 (`1-s2.0-S0306261926007397-main`) | **Adjacent-domain alternative — no physics gain (P1).** Builds a SMARTS→Perez multispectral sun/sky dome for agrivoltaics, i.e. the same lineage as our sky path, and reports the same ≈5 % SMARTS benchmark. **Weaker on cloud** (spectrally-neutral attenuation, self-flagged "may be biased") and its dome is *spectrally isotropic* (one spectrum, intensity-scaled) — a limitation to confirm we do **not** share, not a gain. Contributes two optional non-sky items: a Fibonacci-lattice solar-disk sampling for penumbra (render/glare only) and a GHI→DNI/DHI decomposition path (CAELUS/GISPLIT). | `in-corpus (context)` |
| Alight & Jakubiec 2026 — *An ipRGC-influenced/Non-Visual Spectral Occupant Model (iNSOM) for lighting design, Part 1: Light simulation method*, *Light. Res. Technol.* **58**:6–22, DOI 10.1177/14771535251368379 (`alight-jakubiec-2025-…part-1-light`) | **Closest peer method (P2).** Annualized melanopic-irradiance simulation combining daylight + electric + **screen** light — the last of which we do not model (proposed as a third attribution source). Its occupant evaluation uses **cosine-weighted corneal (vertical-eye) irradiance with no retinal-FOV weighting**, which is the standards-aligned convention our metric ladder now leads with (hcl-methodology.md §12bis.2); it is the external basis for **never thresholding** the Khademagha FOV weighting. Grounds no equation. | `in-corpus (context)` |
| Schlangen & Price 2021 — *The lighting environment, its metrology, and non-visual responses*, *Front. Neurol.* **12**:624861, DOI 10.3389/fneur.2021.624861 (`fneur-12-624861`) | **CIE S 026 metrology corroboration (P3).** Tutorial-grade restatement of the α-opic quantities; independently reconfirms `K^D65_mel,v = 1.3262 mW/lm` (⇔ 1 W/m² = 754 lx mel-EDI, M-32…M-34 / H-5…H-9) and gives `mel-EDI = 0.9058 × EML`, corroborating **H-12** (`EML = 1.103 × mel-EDI`). Also the source of the **Didcot** measured-daylight spectra proposed as an external validation anchor. Confirms existing constants; changes none. | `in-corpus (context)` |
| Jakubiec & Alight 2026 — *An ipRGC-influenced/Non-Visual Spectral Occupant Model for lighting design, Part 2: Photobiological model implementation*, *Light. Res. Technol.* **58**:23–46, DOI 10.1177/14771535251368380 (`jakubiec-alight-2025-…part-2-photobiological`) | **Highest-value gap-definer (P4).** Drives melatonin, circadian phase, alertness (KSS) and reaction time from annual melanopic irradiance via coupled ODEs (Postnova/Abeysuriya/Tekieh) — a **temporal capability the engine does not have**; our nvRD (H-13…H-19) is a static per-timestep response. Documents the **dual-saturation problem**: alerting half-saturates ≈57 lx while melatonin 95 %-suppression needs ≈754 lx mel-EDI (13×), so one nvRD scalar cannot represent both. **The ODEs are not printed in this paper** — they were extracted separately into an internal port spec (not part of this repository) from the authors' GPL-3.0 repo (`C38C/NIF_Photobiology`), which may serve **only as a validation oracle**; any port must be clean-room from the primary papers. Grounds no equation *yet* (Plan C). | `in-corpus (context)` |
| Huang, Li & Dai 2024 — *Comparative analysis of circadian lighting models: melanopic illuminance vs. circadian stimulus*, *Opt. Express* **32**(17):29494, DOI 10.1364/OE.532207 (`oe-32-17-29494`) | **Metric-choice justification (P5).** 241-point cross-team melatonin-suppression benchmark in which **mel-EDI matches or beats Circadian Stimulus in aggregate** — including on the CS authors' own data, and decisively on the 60-min monochromatic set (R²_adj 0.958 vs 0.693). *Honest caveat: CS 1.0 did edge melanopic on the 30-min subset (0.717 vs 0.541).* Independently gives `mel-EDI = 0.9063 × EML`, matching our **H-12** 1.103 exactly (1/0.9063). Justifies leading with mel-EDI; CS parity remains optional and must never be trusted over mel-EDI. | `in-corpus (context)` |
| Trinh, Bodrogi & Khanh 2023 — *Determination and measurement of melanopic equivalent daylight (D65) illuminance (mEDI) in the context of smart and integrative lighting*, *Sensors* **23**(11):5000, DOI 10.3390/s23115000 (`sensors-23-05000-v3`) | **Empirical guardrail on the reconstruction path (P6).** From 4214 SPDs, fits the melanopic daylight-efficacy ratio to chromaticity alone: `mDER = 0.53806·e^(2.3212z) − 0.37585·e^(−0.85808z)`, `z = 1 − x − y` (**note the minus sign**; ≈0.96 at D65). Proposed as an independent numeric cross-check on the **channel-path** `1/107` reconstruction (H-10, §6.4) — *not* a replacement basis, and **only valid inside its envelope (Ra ≥ 80)**, which excludes screens. Its Darmstadt daylight spectra are a second proposed validation anchor. Grounds no equation *yet* (Plan A). | `in-corpus (context)` |

> **Imageless-annual-exposure cohort.** 26 papers assembled for a companion study on imageless
> melanopic exposure (a separate repository, not part of this one) and mirrored into this corpus. Two are **method sources** and were promoted to §2K/§5 (Tregenza & Waters 1983, the origin of the daylight
> coefficient; Bourgeois, Reinhart & Ward 2008, the DDS model Daysim executes) — they are **not** repeated below. The
> remaining **24 ground no M-/H- equation** and may not be cited as method sources. The authoritative per-paper
> assessment (with verified quotes, benchmark numbers and the "must-distinguish" analysis) is the imageless project's
> own ledger, `literature/LITERATURE-GAPS.md`, which is not part of this repository;
> the table below is the corpus-level index into it. Filed under `06-alpha-opic-circadian/` (circadian annual metrics),
> `07-nvrd-nonvisual-models/` (directionality), `08-daylight-transport-sim/` (DC/matrix transport),
> `09-electric-lighting-glare/` (the imageless-glare lineage) and `11-context-corroborating/`.
>
> **Standing caution from that ledger:** Wasilewski's `raytraverse` is **prior art for the per-point directional
> daylight-coefficient basis** — it stores rays with direction + solid angle + *a vector of source coefficients*. Any
> future claim in this repo that a per-point directional DC basis is novel is **false**. What remains open is the
> **spectral** dimension, which Wasilewski et al. 2022 explicitly park ("the spectral dimension is not considered here").

| Source | Role / what it corroborates | Grounding |
|---|---|---|
| Jones 2019 — *Fast climate-based glare analysis and spatial mapping*, Proc. IBPSA BS2019, 982–988, DOI 10.26868/25222708.2019.210267 | **The parent imageless method.** The DGP-from-daylight-coefficients formulation the imageless melanopic engine transposes. MBE < 8 %, RMSE < 10 %; rcontrib `-ab 8` brightness / `-ab 1` contrast; glare cut L_p > 2000 cd/m², θ_p < 90°. Grounds the *imageless paper*, no engine equation. | `in-corpus (context)` |
| Wasilewski, Grobe, Wienold & Andersen 2022 — *Efficient simulation for visual comfort evaluations*, *Energy Build.* **267**:112141 | **Prior art for the directional DC basis** (`raytraverse` light field), and the source of the verbatim "the spectral dimension is not considered here". Cite this journal paper, not the thesis. Photometric throughout (melanopic/circadian: 0 hits). | `in-corpus (context)` |
| Wasilewski, Grobe, Schregle, Wienold & Andersen 2021 — *Raytraverse: navigating the lightfield*, Proc. SimAUD 2021 | Companion priority cite for the light-field framing (position 3, direction 2, wavelength, time; "1 band: photopic luminance"). ⚠️ Preprint carries a **placeholder DOI** — resolve the ACM DOI before citing. | `in-corpus (context)` |
| Wasilewski 2023 — *Traversing time-dependent light fields for daylight glare evaluation*, EPFL Thèse N° 10118 | The `raytraverse` thesis. Prior art for the directional-basis object; cite the journal papers in preference, the thesis only for source listings. | `in-corpus (context)` |
| Wasilewski, Wienold & Andersen 2022 — *Critical comparison of annual glare methods*, Proc. BuildSim Nordic 2022 | **Published photopic precedent for the imageless-vs-raytraverse-vs-image benchmark**: imageless DGP RMSE 0.06–0.10, MSD +0.04…+0.07. Characterises imageless DGP's `DCtotal` as **cosine-weighted** — a single fixed kernel. ⚠️ No venue/DOI printed on p.1 — confirm before citing. | `in-corpus (context)` |
| Wasilewski, Grobe, Wienold & Andersen 2019 — *Critical literature review of spatio-temporal glare*, *SDAR J.* **7**(1) Art. 4, DOI 10.21427/87r7-kn41 | Surveys spatio-temporal glare methods by the daylight dimension each collapses. **Records no spectral extension anywhere in 2007–2019** — the negative-evidence citation for the imageless paper's novelty claim. | `in-corpus (context)` |
| Jones & Reinhart 2017 — *Experimental validation of ray tracing as a means of image-based visual discomfort prediction*, *Build. Environ.* **113**:131–150 | **Licenses render-as-ground-truth.** DGP classification 93–99 % vs HDR photography; geometry and source luminance dominate error, `-ab`/`-lr` 5–6 suffice. **Photopic only** — a melanopic extension inherits transport accuracy, *not* validation. | `in-corpus (context)` |
| Geisler-Moroder & Knoflach 2025 — *DGP critique for small sources*, *Light. Res. Technol.* **57**:604–631, DOI 10.1177/14771535251314413 | DGP's contrast term over-rates small bright sources (L² vs linear ω); proposes DGM. **Does not invalidate the large-surface regime** — DGM ≡ DGP above the size threshold. | `in-corpus (context)` |
| Geisler-Moroder et al. 2026 — *Glare with sun in the field of view (DGM)*, *Buildings* **16**(2):249, DOI 10.3390/buildings16020249 | Lab + simulation validation of DGM. Evidence that the directional kernel is an actively contested, **separable** design choice. | `in-corpus (context)` |
| Tian & Zhao 2023 — 21st Radiance Workshop (journal: Zhao & Tian, *Build. Environ.* **242**:110598) | Accelerates the direct-sun component with `rpict` at exact sun positions — **per-pixel, image-based**, the opposite of imageless. Contrast citation. | `in-corpus (context)` |
| Wienold et al. 2021 — *Simplified annual glare evaluation under EN 17037*, Proc. IBPSA BS2021 | Annual-glare strategies under EN 17037. Positioning / metric framing. | `in-corpus (context)` |
| Radiance `dcglare` man page | The reference implementation of imageless DGP and its **matrix contract** — the cross-check oracle. Installed at `/usr/local/radiance/bin/dcglare`. | `in-corpus (context)` |
| Konis 2017 — *A novel circadian daylight metric for building design and evaluation*, *Build. Environ.* **113**:22–38 | **MUST-DISTINGUISH — the closest ancestor of a spatial circadian-autonomy metric.** Radiance+Daysim, 0.5 m grid @ 1.2 m, **8 fixed gaze vectors reported at the BEST vector**, 250 EML threshold, 07:00–10:00 boolean, Circadian Effective Area. Explicitly *not* Lark (uses a 1.00–1.10 illuminance→EML factor). Any worst-gaze metric must state the contrast with his best-gaze rule. | `in-corpus (context)` |
| Konis 2019 — *Circadian Design Assist Tool (CDAT)*, *Sol. Energy* **191**:449–458 | **MUST-DISTINGUISH.** Lark-based; `Max.CF` = **best** gaze again. | `in-corpus (context)` |
| Acosta, Leslie & Figueiro 2017 — *Analysis of circadian stimulus allowed by daylighting in hospital rooms*, *Light. Res. Technol.* **49**(1):49–61 | Early **"CS autonomy"** (% of days CS ≥ 0.35 for ≥ 1 h). Rea CS model, single plane, fixed forward gaze — predecessor to a directional melanopic autonomy. ⚠️ Author manuscript, venue not printed — verify before citing. | `in-corpus (context)` |
| García-Martín, Campano, Acosta & Bustamante 2025 — *Dynamic daylight metrics review*, *Appl. Sci.* **15**(15):8243 | Review positioning **Circadian Stimulus Autonomy** among dynamic daylight metrics (Rea CS lineage). State-of-the-art framing. | `in-corpus (context)` |
| Bellia, Fragliasso, Seraceni & Sodano 2023 — *Integrative lighting in a cell office*, *J. Daylighting* **10**:192–203 | Electric-lighting integrative design, EN 12464-1 vs mel-EDI. Metric framing only. | `in-corpus (context)` |
| *Simplified modelling of integrative lighting*, Proc. IBPSA BS2023 | Simplified annual integrative-lighting modelling — distinguish-from. | `in-corpus (context)` |
| Inanici & Hashemloo 2017 — *Simulation techniques for sky modeling*, *Build. Environ.* **113**:220–231 | ⚠️ **NOT Konis 2017** — same volume, different paper. Argues vertical illuminance is a poor proxy because it **discards the luminance distribution in the visual field** — the motivation for retaining a directional L(ω,t). Backbone citation for annual luminance maps. | `in-corpus (context)` |
| Sepúlveda, Bueno, Wang & Wilson 2021 — *Benchmark of annual glare risk*, *Build. Environ.* **201**:108006 | Benchmark conventions: **`-ab 4`** best accuracy/CPU for rtrace E_v/DGP; sun-position sampling cuts CPU up to 86 %. Corroborates our annual-run parameter choices. | `in-corpus (context)` |
| Geisler-Moroder, Lee & Ward 2017 — *Validation of the five-phase method*, Proc. IBPSA BS2017, 1523–1531 | Five-phase validation; DGP within 10 % of measured. Grounds direct-sun handling in matrix workflows. | `in-corpus (context)` |
| Ward et al. 2022 — *Daylight simulation workflows with measured BSDFs*, *Energy Build.* **259**:111890 | Matrix workflows with measured BSDFs. **Distinguish:** their directional resolution lives at the *aperture* (BSDF); an eye-centred basis puts it at the *view sphere*. | `in-corpus (context)` |
| Smirnova, Boos, Budak & Ilyina 2023 — *Lighting quality and visibility*, *Light & Engineering* **31**(4):4–13, DOI 10.33383/2022-096 | **Independent corroboration of the directional-kernel reading.** Builds lighting quality on the spatial-angular luminance distribution at the observer point (Kajiya + local-estimation MC), with a weight of *"the same physical meaning as the position index"* — reaching the same kernel slot from computer graphics. Photopic, non-annual, no DC basis. | `in-corpus (context)` |
| Lindelöf 2007 — *Bayesian optimization of visual comfort*, EPFL Thèse N° 3918 | **Historical only.** Explicitly *abandoned* per-point daylight coefficients (§4.2) for a two-parameter illuminance regression. No threat; documents the road not taken. | `in-corpus (context)` |

> **Future code work (out of scope under the current DOCS-ONLY constraint), flagged for the record:**
> Petržala 2017's Eq. 12 is a near drop-in route from the engine's existing spectral DNI/DHI to
> **tilted/vertical (façade) illuminance**; FARMS-NIT's UV/visible multiple-scattering correction and
> REST2 as an independent broadband oracle are candidate validation aids (⚠️ **as a validation aid only** —
> FARMS-NIT Part II is not a candidate *replacement* for SEDES1, since its cloud inputs are absent from an
> EPW and the public FARMS code is broadband-only; see its row above); spectral skewness / APE are
> cheap shape-diagnostics for a future measured-spectrum validation harness. None is a current change.

---

*Companion documents:* [hcl-methodology.md](hcl-methodology.md) (H-n equations) · [spectral-sky-methodology.md](spectral-sky-methodology.md) (M-n equations) · [spectral-sky-as-built.md](spectral-sky-as-built.md) (D-1..D-28 deviations).
