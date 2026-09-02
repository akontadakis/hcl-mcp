# HCL Engine — Methodology & Mathematics

> **Status:** whole-system scientific reference for the `hcl-mcp` engine.
>
> **Purpose:** the *scientific* counterpart to the code. Where [technical-reference.md](technical-reference.md)
> reviews the modules and [operating-guide.md](operating-guide.md) explains how to run the server, this
> document states the **physics, the equations, the reference provenance, and the end-to-end numerical flow** of the core Human-Centric-Lighting computations: the spectral foundation, α-opic / CIE S 026 metrics, the nvRD alerting model, broadband→spectrum reconstruction, electric-lighting photometry, daylight controls, the 2-phase annual daylight-coefficient transport, and the compliance thresholds.
>
> **Companion:** the EPW → physically-derived spectral-sky pipeline (atmosphere, solar geometry, SPECTRL2, SMARTS, SEDES1 cloud bridge) has its own dedicated treatment in
> [spectral-sky-methodology.md](spectral-sky-methodology.md); this document **cross-references** it rather than repeating its equations (M-n). Equations here are numbered **(H-n)**.
>
> **Literature grounding:** the spectral and circadian methods implement published models directly from primary literature (see [literature-bibliography.md](literature-bibliography.md)). Where deliberate fixes, figure digitizations, or unexplained legacy constants arise, the divergence is stated, not hidden — see §14.

---

## 0. How to read this document

The engine is not one chain but **two coupled computational domains**, and the document is organized around
them (§3 draws the dataflow):

- **Domain A — the spectral / circadian metric chain.** A spectral power distribution (SPD) or a set of
  spectral channels → photopic & colour metrics → α-opic irradiance / EDI / ELR → derived circadian ratios.
  This is point-wise: one spectrum in, one bundle of metrics out.
- **Domain B — the annual spatial transport → dosimetry chain.** Geometry + materials + weather →
  per-sensor, per-timestep irradiance (Radiance 2-phase DDS) → reconstruction back to a spectrum →
  the nvRD alerting model and time-above-threshold dosimetry.

Reconstruction (§9) is the **bridge**: it turns Domain B's broadband transport result back into a Domain A spectrum so the same α-opic machinery applies.

Each section gives **(i)** what it consumes and produces, **(ii)** the governing equations with their source citation, **(iii)** the constants, and **(iv)** the numerical caveats that bound accuracy. Equations are numbered **(H-n)** for cross-reference. **H-34…H-36 are intentionally unassigned** — they were retired with the melanopic source-attribution engine that moved to a companion study (§12bis). The numbering is deliberately *not* compacted, because source code, the technical reference and the bibliography cite H-numbers by value. Citations name the source and the implementation site as
`module.function` (with line numbers as of this writing); line numbers drift, function names do not.

Symbol conventions: wavelength λ is in **nm** throughout the core (the engine's native unit; the µm domain lives only inside the spectral-sky engines — see the companion doc). The canonical visible grid is **380–780 nm at 1 nm = 401 points**. Irradiances are spectral (per-nm) unless written as a broadband integral.

---

## 1. Nomenclature


| Symbol        | Meaning                                                           | Units            |
| --------------- | ------------------------------------------------------------------- | ------------------ |
| λ            | wavelength                                                        | nm               |
| E(λ)         | spectral irradiance                                               | W·m⁻²·nm⁻¹ |
| V(λ)         | CIE 1931 photopic luminous efficiency (2° observer)              | —               |
| Eᵥ           | photopic illuminance                                              | lx               |
| s_α(λ)      | CIE S 026 α-opic action spectrum (α ∈ {sc, mc, lc, rh, mel})   | —               |
| E_α          | α-opic irradiance                                                | W·m⁻²         |
| ELR_α        | α-opic efficacy of luminous radiation                            | mW·lm⁻¹       |
| K_α^D65      | D65 reference α-opic ELR                                         | mW·lm⁻¹       |
| EDI_α        | α-opic equivalent daylight illuminance                           | lx               |
| mel-EDI       | melanopic EDI (α = mel)                                          | lx               |
| mel-DER       | melanopic daylight efficacy ratio                                 | —               |
| EML           | equivalent melanopic lux                                          | lx               |
| Cᵢ           | spectral channel value (3- or 9-band)                             | rel.             |
| wᵢ           | per-channel metric weight                                         | —               |
| K_m           | luminous efficacy constant (Radiance) = 179                       | lm·W⁻¹        |
| I_eff         | effective ipRGC irradiance (nvRD input)                           | (model units)    |
| s_ipRGC(λ)   | ipRGC spectral sensitivity (390–700 nm)                          | —               |
| R_D           | nvRD relative response                                            | ∈[0,1]          |
| RD_cum        | cumulative nvRD response                                          | response·h      |
| σ, EI50, n   | nvRD adaptive threshold, half-response irradiance, Hill slope     | —               |
| Iᵥ           | candela (luminous intensity)                                      | cd               |
| Φ            | luminous flux                                                     | lm               |
| f_L, f_P, F_P | controls light-deficit, lamp power, zone power fractions          | —               |
| Kt            | clearness index                                                   | —               |
| DNI, DHI, GHI | direct-normal / diffuse-horizontal / global-horizontal irradiance | W·m⁻²         |

---

## 2. Reference provenance

Primary sources are cited inline at each method. Each method section below leads with its citation snippet.


| Ref                                                                                                                                        | Source                                                                                                                                                                                    | Code site                                                                                                            | What it supplies                                                                                                                                                                                                                                                                                                                    |
| -------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CIE S 026/E:2018**                                                                                                                       | *System for Metrology of Optical Radiation for ipRGC-Influenced Responses to Light*                                                                                                       | action spectra in`hcl_core/_spectra.py`, math in `hcl_core/alpha_opic.py`                                            | The five α-opic action spectra, E_α, ELR, EDI, the K^D65 references (H-5…**H-9**). *(H-10, the `(179/683)·(1/107)` channel-reconstruction scalar, has no CIE S 026 derivation — implementation lineage only; see the H-10 grounding note.)* (companion: CIE α-opic Toolbox + DIS 026/E:2018 infosheet; full prose paywalled). |
| **Inanici, Brennan & Clark 2015**                                                                                                          | *Spectral Daylighting Simulations* (IBPSA Building Simulation 2015)                                                                                                                       | weights`hcl_core/data.py`                                                                                            | The 3-/9-channel binning + per-channel photopic/melanopic weights (H-2, H-4).                                                                                                                                                                                                                                                       |
| **Jung, Cheng, Brennan & Inanici 2023**                                                                                                    | *Multispectral Lighting Simulation Approaches for Predicting Opsin-driven Metrics*, BS2023                                                                                                |                                                                                                                      | 9-channel/OPN5 neuropic channel scheme and OPN5 weight vector (H-4).                                                                                                                                                                                                                                                                |
| **Amundadottir 2016**                                                                                                                      | M.L. Amúnadóttir,*Light-driven model for identifying indicators of non-visual health potential in the built environment* (EPFL thesis)                                                  | `hcl_core/nvrd.py`; constants `hcl_core/data.py`                                                                     | The nvRD effective-irradiance, filter cascade and adaptive sigmoid (H-13…H-19). nvRD model grounded in Amundadottir et al. 2016/2017 (journal versions); the EPFL-thesis constants (260.7, z_eff, n=3.55) trace only to the thesis.                                                                                                |
| **Pierson, Aarts & Andersen 2023**                                                                                                         | *Validation of spectral simulation tools in the context of ipRGC-influenced light responses of building occupants*                                                                        |                                                                                                                      | The accuracy envelope on ipRGC/nvRD predictions; reconstruction error bounds (§9, §14).                                                                                                                                                                                                                                           |
| **Five-Step HCL process**                                                                                                                  | *Human-Centric Lighting: Foundational Considerations and a Five-Step Design Process*                                                                                                      |                                                                                                                      | EML ↔ mel-EDI conversion, Eq. 3 (H-12).                                                                                                                                                                                                                                                                                            |
| **ISO/CIE 8995-1:2025**                                                                                                                    | *Light and Lighting — Lighting of Workplaces, Part 1: Indoor*                                                                                                                            |                                                                                                                      | Circadian daytime/evening/sleep/night mel-EDI thresholds, Annex B.5.3 (§13).                                                                                                                                                                                                                                                       |
| **Brown et al. 2022**                                                                                                                      | *Recommendations for daytime, evening, and night-time indoor light exposure*, PLoS Biol. **20**:e3001571                                                                                  | cited in`hcl_core/compliance.py`                                                                                     | The 250 / 10 / 1 lx mel-EDI consensus (§13).                                                                                                                                                                                                                                                                                       |
| **WELL v2 (IWBI)**                                                                                                                         | *WELL Building Standard v2*, Feature L03 Circadian Lighting Design                                                                                                                        | thresholds`hcl_core/compliance.py`                                                                                   | Melanopic EDI point thresholds (§13).                                                                                                                                                                                                                                                                                              |
| **EN 12464-1:2021**                                                                                                                        | *Light and Lighting — Lighting of Work Places, Part 1: Indoor*                                                                                                                           | task table`hcl_core/compliance.py`                                                                                   | Ēm / UGR_L / Uo / Ra task criteria (§13).                                                                                                                                                                                                                                                                                         |
| **EN 17037:2018**                                                                                                                          | *Daylight in Buildings*                                                                                                                                                                   | `hcl_core/compliance.py`                                                                                             | Daylight-provision target/minimum illuminances (§13).                                                                                                                                                                                                                                                                              |
| **IES LM-63**                                                                                                                              | *ANSI/IESNA LM-63-02 Standard File Format for Photometric Data*                                                                                                                           | parser`hcl_core/ies.py`                                                                                              | Photometric web, candela scaling, zonal flux (§10) (`IES.pdf`).                                                                                                                                                                                                                                                                    |
| **IES LM-83-12**                                                                                                                           | *Spatial Daylight Autonomy (sDA) and Annual Sunlight Exposure (ASE)*                                                                                                                      | computed`hcl_core/daylight_metrics.py`; thresholds `hcl_core/compliance.py`                                          | sDA/ASE definitions (now**computed**, §12.5).                                                                                                                                                                                                                                                                                      |
| **Subramaniam 2017**                                                                                                                       | S. Subramaniam,*Daylighting Simulations with Radiance using Matrix-based Methods*                                                                                                         | `hcl_radiance/annual*.py`                                                                                            | The 2-phase DDS (daylight-coefficient + direct-sun) method (§12).                                                                                                                                                                                                                                                                  |
| **Reinhart & Tregenza**                                                                                                                    | sky-vault patch subdivision (MF Reinhart subdivisions of the Tregenza dome)                                                                                                               | `gendaymtx -m`, `reinhart*.cal`                                                                                      | 145 patches (MF:1) / 5185 solar discs (MF:6) (§12) (Tregenza 1987 + Reinhart & Walkenhorst 2001; realized in Radiance).                                                                                                                                                                                                            |
| **Perez et al. 1990**                                                                                                                      | all-weather sky luminance/radiance model                                                                                                                                                  | Radiance`gendaylit`/`gendaymtx` (embedded)                                                                           | Sky radiance distribution (§12.2) (Perez 1990/1993; model lives in Radiance).                                                                                                                                                                                                                                                      |
| **EnergyPlus Engineering Ref.**                                                                                                            | continuous / stepped daylight-dimming control logic                                                                                                                                       | `hcl_core/lighting_controls.py`                                                                                      | f_L / f_P control curves (§11).                                                                                                                                                                                                                                                                                                    |
| **Bird & Riordan 1986; Nann & Riordan 1991; Kasten & Young 1989; Gueymard 1994; van Heuklon 1979; Reitan 1963; Spencer 1971; Cooper 1969** | clear-sky spectrum, cloud bridge, air mass, PWV (Gueymard) + dew-point PWV fallback (Reitan), ozone climatology (van Heuklon), Earth-radius vector (Spencer), declination/zenith (Cooper) | see[spectral-sky-methodology.md](spectral-sky-methodology.md) §2; `hcl_core/{solpos,atmosphere,spectral_engine}.py` | The EPW→sky physics (cross-referenced, §9.4/§9.5; M-1…M-34).                                                                                                                                                                                                                                                                    |

The remaining corpus sources (virtual-environment CCT studies, multi-primary LED
control, retrofit/energy optimization, fuzzy visual-comfort indices, etc.) are **corpus/context** on HCL
applications; they motivate the engine but do not supply equations transcribed here. The 2026-06-20 addition of a **clear-sky solar / spectral-irradiance, luminous-efficacy, and measured-spectral-variability** cohort (Gueymard 1989/1993/2009, Louche 1988, Berger 1992, López & Gueymard 2007, Abreu 2023, Xie & Sengupta 2018 FARMS-NIT Part I, Petržala 2017, Wang 2025, Paudyal 2024) is likewise **corpus/context** — it corroborates the spectral-sky pipeline (companion doc) but grounds no transcribed equation; catalogued in [literature-bibliography.md](literature-bibliography.md) §6.

---

## 3. Process overview & dataflow

```
 DOMAIN A — spectral / circadian metric chain (point-wise)
 ─────────────────────────────────────────────────────────
   SPD path/text  ──spd.parse_spd──►  {nm: value}[401]  (380–780 @1nm)
        │                              │
        │                              ├─bin_average──► channels[3|9]
        │                              │
        ├─spectral_metrics────────────►  CCT, Duv, mel-DER, melanopic ratio   (§5,§7)
        │
        └─alpha_opic_from_spd─────────►  {E_α, ELR_α, EDI_α}  for α∈{sc,mc,lc,rh,mel}   (§6)
                                         (channels path: alpha_opic_from_channels, §6.4)

 DOMAIN B — annual transport → dosimetry chain (spatial, per timestep)
 ─────────────────────────────────────────────────────────────────────
   geometry + materials + EPW
        │
        ├─(subhourly .wea, Daysim) ─────────────────────────────┐
        ▼                                                        │
   2-phase DDS (Radiance)                                        │
     Phase 1 sky-diffuse :  rfluxmtx ⊗ gendaymtx(-m1,145,colored)│
     Phase 2 sun-direct  :  rcontrib ⊗ gendaymtx(-5 .533 -d -m6) │   (§12)
        │                          (combine: element-wise sum)   │
        ▼                                                        │
   per-sensor, per-timestep channels[3|9]  (RGB)                 │
        │                                                        │
        ├──spectral_reconstruct──► E(λ)[401]  (faithful | enhanced)   (§9 — the BRIDGE)
        │        │
        │        └──► α-opic suite per timestep  (re-enters Domain A)
        ▼
   nvrd(E(λ) series, Δt) ──► R_D[t], RD_cum     (§8)
   dosimetry.hours_above_threshold(mel-EDI series) ──► hours ≥ threshold

 CONSUMERS (both domains)
 ────────────────────────
   compliance.check_compliance(mel-EDI, Eᵥ, …)  ──► WELL / Brown / ISO-CIE / EN verdicts   (§13)
   lighting_controls  ──► f_P, zone power, annual kWh   (§11)
   ies / ies_radiance ──► luminaire photometry, Radiance light sources, UGR   (§10)
```

The **physical** alternative to the §9 statistical reconstruction — deriving E(λ) from atmospheric physics
rather than redistributing a broadband channel — is the EPW spectral-sky pipeline, documented separately
([spectral-sky-methodology.md](spectral-sky-methodology.md)). It is opt-in (`physical_sky=True`) and feeds the
same nvRD/α-opic consumers.

---

## 4. Domain A — the spectral foundation

**Module:** `hcl_core/spd`, `hcl_core/data`. **Consumes:** a `.spd` file path, SPD text, or (λ, value) pairs. **Produces:** a
401-point 1 nm dict, and optional 3-/9-channel averages.

> **Source:** SPD grid and parsing convention — Inanici, Brennan & Clark 2015. Parsing convention; no primary paper mandating this grid.

### 4.1 Canonical SPD grid

The canonical representation is a dict keyed by **integer nm over 380–780 (401 keys)**. Parsing
(`spd.parse_spd`):

1. tokenize on comma/tab/whitespace, drop non-numeric rows;
2. clip to 380 ≤ λ ≤ 780;
3. **linear end-extrapolation** to the grid edges using the first/last adjacent gradient (not flat hold):
   $$
   E(380) = E_1 - \frac{E_2-E_1}{\lambda_2-\lambda_1}(\lambda_1-380), \qquad
     E(780) = E_{n} + \frac{E_n-E_{n-1}}{\lambda_n-\lambda_{n-1}}(780-\lambda_n) \tag{H-1}

   $$

   (each extrapolated edge value is clamped to $\max(0.0,\,\cdot)$ to avoid unphysical negative irradiance, `spd.py`; and when only a single in-range sample exists the gradient is undefined, so the edges degrade to a flat hold of that one value);
4. linear-interpolate to the 1 nm grid; snap sub-integer collisions round-half-to-even (**last-write-wins** onto the nearest 1 nm node, `spd.py:87`; a sub-integer segment whose rounded span $n\le0$ skips the $/n$ interpolation and emits only its endpoint, `spd.py:75-80`). **After** collapsing, the two grid anchors $E(380)$ and $E(780)$ are **re-pinned** to their original endpoint values (`spd.py:91-92`) so a fractional row that rounds onto 380/780 cannot displace the extrapolated boundary values from H-1;
5. backfill any missing integer key by linear interpolation so exactly 401 keys exist.

No normalization is applied — values are preserved (relative or absolute), since the α-opic ratios (§6) are scale-invariant and the absolute paths need physical magnitude.

### 4.2 Channel binning

> **Source:** Inanici, Brennan & Clark 2015, §2–3 (9-channel layout and weights).

Two band layouts (`hcl_core/data`):

**9-channel** (b1,b2,b3,g1,g2,g3,r1,r2,r3), edges in nm:

$$
[380,419]\,[419,459]\,[459,499]\,[499,529]\,[529,558]\,[558,587]\,[587,608]\,[608,630]\,[630,780]

$$

**3-channel** native source order (r,g,b): $[587,780]\,[499,587]\,[380,499]$, reordered **ascending**
(b,g,r) at the α-opic boundary (`alpha_opic`, the §9.3b fix) so channels align to true wavelength ranges.

Bins are **inclusive on both ends** (`lo ≤ k ≤ hi`): boundary wavelengths are deliberately double-counted, consistent with the Inanici 2015 channel definition. This returns the **mean over the closed band**, not a partitioned total, so a sample on a shared edge legitimately belongs to both adjacent band-means and no energy is double-counted. Channel value is the mean of the per-nm values in the band:

$$
C_i = \frac{1}{N_i}\sum_{\lambda\in\text{bin}_i} E(\lambda) \tag{H-2}

$$

> **No rounding (`spd.bin_average`).** The result is returned at **full precision**. The original Lark port
> rounded each band mean to 3 decimals; that was removed deliberately, because 3 dp is an *absolute* quantum
> of 5·10⁻⁴ and therefore **scale-dependent**. It was harmless on the preset SPDs it was written for (native
> scale ~75–113, error 5·10⁻⁴ %) but corrupting on absolute spectral irradiance, which is what
> `spectral_emit.to_channels` feeds in: real sky/sun records run 0.02–1.3 W·m⁻²·nm⁻¹, and a relative luminaire
> SPD normalised later can sit near 0.01, where the worst band error reaches **~13 %**. Removing it is inert
> for every existing consumer — the `validation.binning_fidelity` and `tests/test_spd.py` goldens come from a
> linear ramp whose true band means are exactly representable, so they are unchanged to the digit. The §6.4
> channel reconstruction is a flat linear scalar and so was never calibrated to the rounding precision.

> **Caveat (3-channel divergence).** The ascending reorder makes the 3-channel output **intentionally differ
> from the naive descending-order result** (a descending-bin ordering mis-aligns channels against the action spectra); the 9-channel path is unaffected. Recorded as the §9.3b fix.

---

## 5. Domain A — photopic & colour

**Module:** `hcl_core/alpha_opic` (photopic illuminance), `hcl_core/spectral_metrics` (colour),
`hcl_core/metrics` (channel-weighted lux).

### 5.1 Luminous efficacy constant

> **Source:** Radiance broadband luminous efficacy convention (integral of 683·V(λ) over the Radiance white spectrum).

$$
K_m = 179\ \text{lm·W}^{-1} \quad (\texttt{LUMINOUS\_EFFICACY},\ \texttt{data.py:28}) \tag{H-3}

$$

This is the Radiance broadband luminous efficacy (the integral of 683·V(λ) over the Radiance white spectrum),
used by the channel-weighted metrics; the per-nm photopic path uses the exact 683 lm/W peak (H-6).

### 5.2 Channel-weighted lux (3-/9-band)

> **Source:** Inanici, Brennan & Clark 2015, §2–3 (per-channel photopic and melanopic weight vectors).
> **Source (OPN5 neuropic vector):** Jung, Cheng, Brennan & Inanici 2023, §2–3 (9-channel OPN5 neuropic weight vector; 90.5 % concentrated in b1). *(The "90.5 % in b1" figure was previously attributed inline to "Kojima 2011", which has no resolvable bibliography entry — treat as unresolved; the value is corroborated in code, `data.py:24`.)*

For a metric m with per-channel weights $w^{(m)}_i$ (`hcl_core/metrics`):

$$
E^{(m)} = K_m \sum_i w^{(m)}_i\,C_i \tag{H-4}

$$

9-channel photopic and melanopic weight vectors (`data.py`):

$$
w^{\text{phot}}_9 = [0.0003,\,0.009098397,\,0.055590209,\,0.164071102,\,0.250355905,\,0.259754249,\,0.130177072,\,0.081085718,\,0.049591265]

$$

$$
w^{\text{mel}}_9 = [0.0119,\,0.1784,\,0.4165,\,0.268843,\,0.1033,\,0.019,\,0.0017,\,0.000296,\,0.000061]

$$

$\sum w^{\text{mel}}_9 = 1.000$ exactly; $\sum w^{\text{phot}}_9 = 1.000023917$ — the one deliberately non-unity
column (validation tolerance ±5·10⁻⁵). The photopic weights are stored at **9 dp** (`data.py:21-22`); quoting
them truncated to 6 dp reproduces the sum only to ±10⁻⁸ and is not the value the code applies. A `neuropic`
(OPN5) 9-channel vector also exists, $w^{\text{neur}}_9 = [0.905130569,\,0.0948,\,0.000069431,\,0,\dots,0]$ —
concentrated **90.5131 %** in b1 (380–419 nm), summing to 1.0 (attribution unresolved — see the OPN5 source
note above).

3-channel weights: $w^{\text{phot}}_3=[0.265,0.670,0.065]$, $w^{\text{mel}}_3=[0.0021,0.3911,0.6068]$ (**r,g,b** — the native `bin_average` source order, `spd.py`, `BINS_3` = `[[587,780],[499,587],[380,499]]` at `data.py:15`). The channel-lux path (`metrics._dot`) applies these positionally with **no reorder**, so the peak photopic weight 0.670 sits on green and the peak melanopic weight 0.6068 on blue. The `[r,g,b]→[b,g,r]` ascending reorder happens **only** in the α-opic path (§9.3b, `alpha_opic.py`), never here.

> **Output contract (`metrics.py`).** `circadian_metrics(channels, channel_type, spd=None)` returns `{photopic_lux, melanopic_lux, neuropic_lux}` for 9-channel input (`channel_type=1`) but only `{photopic_lux, melanopic_lux}` for 3-channel (`channel_type=0`) — **neuropic is intentionally undefined for 3-channel**. Channel-vector length is enforced (exactly 9 or 3) and any `channel_type ∉ {0,1}` raises `ValueError` (closes a silent-misroute path).
>
> **Every result also carries `mel_edi`, `mel_der` and `mel_der_source`** (plus `mel_der_note` on the inferred route, and `source_mel_der` + `transport_ratio` on the transported route). **`melanopic_lux` is NOT S 026 mel-EDI:** the former is $K_m$ × the melanopic-weighted channel sum, the latter is $E_v \cdot \text{mel-DER}$, and the two differ by D65's own binned melanopic/photopic ratio **1.0996639** on the 9-bin route (~9%; the 3-bin route's ratio is **1.0432035**, a different number — the ratio is a property of the binning, not a universal constant). This ratio is **not a hardcoded literal**: `metrics._d65_ratio(channel_type)` derives it at runtime from the bundled D65 spectrum and the active bins, deliberately, so that the two stay consistent if the bin edges ever move. Since every circadian standard is written in mel-EDI, passing one where the other is expected misstates the scored quantity — and near a threshold it **flips the verdict**: a measured eye point reading `melanopic_lux` 260.65 "passes" Brown's ≥250 lx while its true mel-EDI of 237.03 fails. `compliance` stamps `quantity` on every result so an artifact cannot be ambiguous afterwards, but that is a label of what the caller claimed, not a detector — only reading `mel_edi` here prevents the error.
>
> **mel-DER is a property of the spectrum AT THE POINT, never at the lamp** (ADR-0006). A supplied `spd` is read as *the source spectrum feeding these channels*, not as the answer: the transport between the two is recovered from the channels themselves as $T_i = c_i / \overline{S}_i$ (the per-bin ratio of the measured channels to the source's own bin averages), and mel-DER is then computed from $S(\lambda)\cdot T_i$ — the source's full 1 nm structure, which the nine channel averages cannot represent, weighted by the transport the simulation actually applied. This is exact *within the engine's model*: where the transport really is piecewise-constant per bin, it reproduces $\text{mel-DER}(S\cdot T)$ to 0.0000%. `mel_der_source="spd_transported"`, and `source_mel_der` + `transport_ratio` are returned alongside so the shift the room imposed is visible rather than folded away.
>
> Handing back the *source* mel-DER instead is correct only where the source **is** the point — characterising a luminaire, `spectral_metrics(spd=…)`, or an engine-vs-engine sky comparison. After light crosses any spectrally selective surface it is wrong by the size of the spectral shift: measured worst error **12.74%** over 6 sources × 3 transports, against **0.73%** for the transported route. Because the transported route collapses *exactly* to $\text{mel-DER}(S)$ when nothing shifts the spectrum, it is a strict generalisation — the source-characterisation case is unchanged to `rel=1e-9`.
>
> **Without `spd`**, mel-DER can only be inferred from the binned channel averages (`mel_der_source="binned_channels"`, carrying `mel_der_note`): exact for D65 by construction, **~0.13% for daylight** (the Athens equinox sky spectrum), ~1.5% for other smooth spectra, but up to **~8% high for a narrow-band fluorescent** whose emission lines fall inside a single bin. Binning cost scales with spectral smoothness, so the 8% figure belongs to line spectra, which daylight never is. (A third route, `spd_source_untransported`, falls back to the source value and says so when no channel carries light in a band the source emits — a dark point.)

> **Grounding note:** Jung et al. 2023 grounds the **9-channel/OPN5 channel scheme** (the division of the spectrum into 9 wavebands and the OPN5 neuropic weighting). The α-opic integral E_α (H-5) and the action spectra s_α are CIE S 026:2018 (companion — CIE α-opic Toolbox), not Jung 2023.

### 5.3 Colour: CCT and Duv

> **Source:** Ohno 2013, *Practical Use and Calculation of CCT and Duv*, LEUKOS **10**:47. Realized via `colour-science` library.

`spectral_metrics.cct_duv` routes the SPD through the `colour-science` library:
SPD → CIE 1931 XYZ (2° observer) → CIE 1960 UCS (u, v) → **CCT + Duv via the Ohno 2013 inversion**
(`colour.uv_to_CCT`). Golden anchors: D65 → 6502.7 K, Duv ≈ +0.0032; CIE A → 2855.7 K, Duv ≈ 0.

> CRI / Rf is **not computed** in the core; references to color rendering appear only as compliance criteria (Ra in EN 12464-1, §13), not as a calculated metric.

---

## 6. Domain A — α-opic / CIE S 026

**Module:** `hcl_core/alpha_opic`. **Consumes:** SPD (exact path) or channels (approximate path).
**Produces:** for each action spectrum α, the triple {E_α, ELR_α, EDI_α}.

The five action spectra s_α (S-cone, M-cone, L-cone, rhodopic, melanopic) are 401-point 380–780 nm @1 nm curves; cones carry leading zeros below ~390 nm.

### 6.1 α-opic irradiance

> **Source:** CIE S 026/E:2018, *System for Metrology of Optical Radiation for ipRGC-Influenced Responses to Light* — Eq. for E_α. (companion: CIE α-opic Toolbox + DIS 026/E:2018 infosheet; full prose paywalled). Action spectra in `hcl_core/_spectra.py`; integral in `alpha_opic._from_irradiance_pure`.

With Δλ = 1 nm:

$$
E_\alpha = \sum_{\lambda} E(\lambda)\,s_\alpha(\lambda)\,\Delta\lambda \tag{H-5}

$$

### 6.2 Photopic illuminance (exact per-nm path)

> **Source:** CIE S 026/E:2018 (companion); CIE 1924 V(λ) + 683 lm/W maximum luminous efficacy.

$$
E_v = 683 \sum_{\lambda} E(\lambda)\,V(\lambda)\,\Delta\lambda \quad(\texttt{alpha\_opic.py:72}) \tag{H-6}

$$

### 6.3 ELR, the D65 reference, and EDI

> **Source:** CIE S 026/E:2018 — Eqs. for ELR_α, K_α^D65, EDI_α. (companion).

α-opic **efficacy of luminous radiation** (a ratio → scale-invariant):

$$
\text{ELR}_\alpha = \frac{E_\alpha}{E_v}\cdot 1000 \quad[\text{mW·lm}^{-1}] \tag{H-7}

$$

The **D65 reference ELR**, computed once per action spectrum from the embedded D65 spectrum `D65_ELR`:

$$
K_\alpha^{D65} = \frac{\sum_\lambda E_{D65}(\lambda)\,s_\alpha(\lambda)}{683\sum_\lambda E_{D65}(\lambda)\,V(\lambda)}\cdot 1000 \tag{H-8}

$$

α-opic **equivalent daylight illuminance** (as implemented, `alpha_opic.py:77`):

$$
\text{EDI}_\alpha = \frac{E_\alpha\cdot 1000}{K_\alpha^{D65}} \quad[\text{lx}] \tag{H-9}

$$

The CIE S 026 reference K^D65 constants (the engine recomputes them from its bundled spectra and asserts
agreement < 0.5 % against these published values, `validation.py`):


| α                            | S-cone | M-cone | L-cone | rhodopic | melanopic  |
| ------------------------------- | -------- | -------- | -------- | ---------- | ------------ |
| $K_\alpha^{D65}$ [mW·lm⁻¹] | 0.8173 | 1.4558 | 1.6289 | 1.4497   | **1.3262** |

> **Independently corroborated (2026-07).** Three sources outside the CIE line reconfirm the melanopic constant
> $K_{mel}^{D65} = 1.3262$ mW·lm⁻¹ (⇔ 1 W·m⁻² = 754 lx mel-EDI): Schlangen & Price 2021 (*Front. Neurol.* 12:624861),
> Jakubiec & Alight 2026 (iNSOM Part 2) and Trinh et al. 2023 (*Sensors* 23:5000). The SPD path already uses exactly
> this value. **No change** — recorded so it is not re-litigated.

### 6.4 The channel path and the 1/107 constant

> **Source:** CIE S 026/E:2018 (action spectra and integral definition). (companion).

When only channels are available (Domain B output), irradiance is reconstructed by flat step-expansion (`alpha_opic._reconstruct_irradiance`), each channel spread across its bin with intensity

$$
I_i = \frac{179}{683}\cdot\frac{1}{107}\cdot C_i = 0.0024493370\cdot C_i \quad(\texttt{alpha\_opic.py:50}) \tag{H-10}

$$

This is the **§9.3a fix**: computing `(179/683)*(1/107)` under integer division yields 0, zeroing every α-opic output — float literals restore the intended computation.

> **Grounding gap:** The `(179/683)·(1/107)` scalar (H-10) has no published derivation; appears only in `melanopic_calcs.bas:40`; treat as implementation lineage. It cancels exactly in **ELR** (the ratio E_α/E_v) and in any ratio of two **same-path** EDIs, but does **not** cancel in absolute E_α, in absolute EDI/mel-EDI, or in the nonlinear nvRD sigmoid — absolute channel-path E_α, mel-EDI and R_D are unvalidated. Use the SPD path (H-5) for absolute irradiance.
>
> **Reviewed against the 2026-07 literature — still lineage-only, still not a bug.** `1/107 ≈ 9.35` mW·lm⁻¹ is *not* a
> corrupted form of the CIE `K_mel^D65 = 1.3262` mW·lm⁻¹; they are different quantities, and no source in the corpus
> derives the former. The caveat above stands as written. An **independent numeric guardrail** on this channel path is
> available but **not yet implemented**: Trinh et al. 2023 fit the melanopic daylight-efficacy ratio to chromaticity
> alone, on 4214 SPDs (R² = 0.96795),
>
> $$\text{mDER}(z) = 0.53806\,e^{2.3212 z} - 0.37585\,e^{-0.85808 z},\qquad z = 1 - x - y$$
>
> with $z$ the CIE 1931 z-chromaticity. It evaluates to ≈0.96 at D65 and ≈0.42 at illuminant A, tracking the
> CIE-integrated `mel_der` within the fit residual, so it would give the channel path its first **external**
> anchor (today `spectral_reconstruct.reconstruction_divergence` only measures divergence *between
> reconstruction-method choices*, never distance from a ground truth). ⚠️ **Sign trap:** the second term is
> **subtracted**; collapsing the published coefficient shape $a e^{bz} - c e^{dz}$ into a literal
> $+0.37585\,e^{dz}$ yields ≈1.51 at D65 and would falsely flag D65 itself as a reconstruction defect.
> Divergence > **0.067802** (the in-sample 97 % CI on ΔmDER — a fit residual on the training spectra, *not* an
> independent test set) would be the defect threshold; end-to-end accuracy is ±3.3 % on mel-EDI. **Validity
> envelope (all four gates):** CCT ∈ [2201, 17815] K, 80 < CIE Ra < 100, −0.0147 < Duv < 0.0153,
> z ∈ [0.0797, 0.4792] (⇒ mDER ∈ [0.2784, 1.46]). Because the fit covers only high-CRI sources, it is a valid
> guardrail for **daylight and phosphor-white LED** but is **out-of-envelope for narrowband / blue-depleted
> sources**, which must not be gated on it.

> **Caveat (the 1/107 factor).** Its physical origin is undocumented in the source. Because EDI = E_α·1000/K_α^D65 with a **source-independent** K_α^D65 (recomputed only from the fixed D65 spectrum, `alpha_opic.py:74-77`), EDI is directly proportional to E_α and therefore scales linearly with this factor — it does **not** cancel in the absolute EDI. It cancels only in **ELR** (the ratio E_α/E_v) and in ratios of two same-path EDIs (e.g. mel-EDI/L-EDI), because it then scales numerator and denominator identically. Consequently the channel-path **absolute** EDI diverges from the exact SPD-path EDI by ~100 % (verified: ×10 channels → ×10 EDI; the `channel_vs_spd_alpha_opic` check is **informative-only** and does not gate, `validation.py:99-100` — it is expected to report `ok: False` on a healthy engine), while the ELR-type same-path ratio agrees to < 5 %. A **separate check does gate**, on bounded rather than exact agreement: `channel_vs_spd_divergence_bounded` (`validation.py:84`) fails the suite if absolute EDI divergence exceeds **300 %** or the ELR-ratio divergence exceeds **5 %** — so the known ~100 % offset is tolerated while a genuine regression is not. It likewise does not cancel in the nonlinear nvRD sigmoid (§8). **Use the SPD path (H-5) for absolute E_α / mel-EDI.**

---

## 7. Domain A — derived circadian ratios

**Module:** `hcl_core/spectral_metrics`, `hcl_core/data`.

> **Source:** CIE S 026/E:2018 — mel-DER definition (ELR normalized to D65). (companion).

**Melanopic daylight efficacy ratio** — melanopic ELR normalized to D65 (D65 ≡ 1 by construction):

$$
\text{mel-DER} = \frac{\text{ELR}_{\text{mel}}(\text{source})}{\text{ELR}_{\text{mel}}(D65)} \tag{H-11}

$$

Anchors (verified live against the shipped presets): D65 = 1.000, D50 = 0.847, CIE A = 0.496, LED-5000K = 0.818 (warm < cool, as expected; LED-4000K = 0.686, LED-3000K = 0.570). ⚠️ The first three are **CIE standard illuminants** (`colour-science`, authoritative standard data); the `LED_*` anchors are the **synthetic illustrative model** of §10.3a (`presets.preset_meta` reports `illustrative: True`) — they are legitimate golden anchors for *this engine's arithmetic*, not measured product data.

> **Source (EML ↔ mel-EDI):** *Human-Centric Lighting: Foundational Considerations and a Five-Step Design Process*, Eq. 3.

**Equivalent melanopic lux ↔ mel-EDI** (`spectral_metrics.eml_medi_convert`, Five-Step process Eq. 3):

$$
\text{EML} = 1.103\cdot\text{mel-EDI} \quad (\texttt{EML\_PER\_MEDI}=1.103,\ \texttt{data.py:41}) \tag{H-12}

$$

The conversion is **bidirectional**, selected by a `direction` argument: `"medi_to_eml"` applies $\times1.103$, `"eml_to_medi"` applies $\div1.103$ (result rounded to 2 dp); any other value raises `ValueError` (`spectral_metrics.py:44-50`).

> **Independently corroborated (2026-07).** H-12 previously rested on the Five-Step HCL process alone. Two independent
> sources now confirm it in the inverse direction: Schlangen & Price 2021 give mel-EDI = 0.9058 × EML and Huang, Li &
> Dai 2024 (*Opt. Express* 32:29494) give 0.9063 × EML ⇒ EML ≈ 1.104 × mel-EDI. Our 1.103 = 1/0.9063 matches Huang
> exactly. **No change.**

> **Relative-SPD scale guard.** `spectral_metrics.alpha_opic_from_spd` reshapes the exact §6 α-opic path to a flat `{s_edi…mel_edi}` dict and attaches a `scale_warning` when the SPD *looks* relative/normalized (peak value ≤ `_RELATIVE_PEAK_MAX = 1.5`). The warning deliberately states the scale is **indeterminate** — the values are consistent with BOTH a normalised/relative spectrum (in which case the `*_edi` values are shape indicators only) AND a genuinely absolute low-level one (in which case they are correct lux-scale EDIs) — and never asserts the input *is* relative (`_SCALE_WARNING`; peak-normalised-looking data can be absolute). The scale-invariant ratios mel-DER and the raw melanopic ratio are unaffected either way.

A raw **melanopic ratio** (`spectral_metrics.mel_photopic_ratio`; peak-normalized $\sum E\,s_{\text{mel}} / \sum E\,V$, D65 ≈ 0.906) is also exposed,
explicitly flagged in-code as a spectral-shape indicator only — not mel-EDI and not mel-DER.

---

## 8. Domain B — the nvRD alerting model

**Module:** `hcl_core/nvrd`. **Consumes:** a time series of per-nm spectra (or effective irradiance) at a
fixed timestep Δt. **Produces:** the relative non-visual direct response R_D(t) and its cumulative integral.

> **Source:** Amundadottir 2016, *Light-driven model for identifying indicators of non-visual health potential in the built environment* (EPFL PhD thesis) — nvRD model definition. nvRD model grounded in Amundadottir et al. 2016/2017 (journal versions); the EPFL thesis (full constant derivations) was not obtained. Constants in `data.py:36-37`.

### 8.1 Effective ipRGC irradiance

> **Source:** Amundadottir 2016, §(nvRD model) — effective irradiance definition, 390–700 nm window, ×311 multiplier. (model; Amundadottir et al. 2016 journal version).

The 401-point spectrum is windowed to **390–700 nm (311 points, indices 10:−80)** (`nvrd._slice_311`) and
weighted by the ipRGC sensitivity `IPRGC_SENS_WEIGHTING`, then trapezoid-integrated and scaled by the
source's literal ×311 multiplier (`nvrd.effective_irradiance`):

$$
I_{\text{eff}} = \Big[\textstyle\int_{390}^{700} E(\lambda)\,s_{\text{ipRGC}}(\lambda)\,d\lambda\Big]\cdot 311 \tag{H-13}

$$

### 8.2 The three-stage temporal cascade

> **Source:** Amundadottir 2016, §(nvRD temporal cascade) — three-filter cascade and adaptive threshold. (model); the 260.7 cascade constant traces to the EPFL thesis.

`nvrd.direct_response` applies three filters whose windows are fixed in hours and whose integer lengths
follow from Δt (`filters_h = (0.3, 1.7, 2.3)`):


| Stage | Filter                      | Window | Length @ Δt=0.1 h | Role                                                           |
| ------- | ----------------------------- | -------- | -------------------- | ---------------------------------------------------------------- |
| L1    | simple moving average       | 0.3 h  | 3                  | smooth I_eff → light-stimulus**ū** (Hill denominator, H-17)  |
| LH    | log-domain SMA + adaptation | 1.7 h  | 17                 | history**H** from raw I_eff → shifts threshold σ (H-14/H-15) |
| L2    | exponential moving average  | 2.3 h  | 23                 | smooth → output R_D                                           |

> **Three distinct series** (`nvrd.direct_response`): the raw I_eff, the L1-smoothed **light stimulus** $\bar u_t=\text{SMA}_{0.3}[I_{\text{eff},t}]$ (length 3, `nvrd.py:80`), and the log-domain **history** $H_t$ built from the *raw* I_eff over the LH window (length 17, `nvrd.py:56,81`). ū enters the Hill denominator (H-17); the raw I_eff drives both the history (H-14) and the final daylight gate. Earlier revisions of this table conflated L1 with the history — the code applies the history SMA over the **1.7 h LH** window, not the 0.3 h L1 window.

**History transform** (LH window, log domain, clamped ≥ 0 — over the *raw* I_eff series, not the L1-smoothed stimulus):

$$
H_t = \max\!\big(0,\ \text{SMA}_{1.7}\!\big[\log_{10}(I_{\text{eff}}\cdot 260.7)\big]\big),\qquad 260.7 = 118.5\times 2.2 \quad(\texttt{nvrd.py:56,70,81}) \tag{H-14}

$$

**Adaptive threshold** (the prior-light memory shifts σ exponentially):

$$
\sigma_t = \sigma_0\cdot 2^{\,H_t - 1},\qquad
  \sigma_0 = \text{EI50}\cdot z_{\text{eff}} = 106\cdot 0.0024545715 = 0.260185 \tag{H-15}

$$

$$
z_{\text{eff}} = \tfrac{310}{683}\cdot\tfrac{1}{118.5}\cdot\tfrac{1}{1.42}\cdot 0.91 = 0.0024545715 \quad(\texttt{data.py:37}) \tag{H-16}

$$

**Hill response** (slope n = 3.55; the light stimulus is the **L1-smoothed** $\bar u_t$, but the daylight gate keys on the *raw* I_eff):

$$
r_t = \begin{cases}\dfrac{1}{1 + (\sigma_t / \bar u_t)^{\,n}} & I_{\text{eff},t} > 0\\[2mm] 0 & I_{\text{eff},t} = 0\end{cases},\qquad \bar u_t=\text{SMA}_{0.3}[I_{\text{eff},t}] \quad(\texttt{nvrd.py:80-83}) \tag{H-17}

$$

**Output smoothing** and **cumulative response**:

$$
R_D(t) = \text{EMA}_{2.3}[r_t],\qquad \text{RD}_{\text{cum}} = \int R_D(t)\,dt \approx \text{cumtrapz}(R_D,\,t) \tag{H-18}

$$

### 8.3 Timestep contract and dosimetry

> **Source:** Amundadottir 2016 — timestep contract (Δt = 0.1 h, filter-length constraint). (model).
> **Source (dosimetry):** Standard dosimetry — time-above-threshold accumulation.

The model is validated at Δt = 0.1 h (6 min) → odd filter lengths (3, 17, 23). The implementation **rejects** any Δt
that yields an even filter length (which would silently misalign the convolution) and any Δt > 0.3 h, with a
clear error — the Amundadottir 2016 source hardcoded 0.1 h; exposing Δt created this failure surface.

Time-above-threshold dosimetry (`dosimetry.hours_above_threshold`) credits each qualifying sample its **own**
timestep $\Delta t$, clamped by the actual forward gap so a genuinely short final interval stays exact:

$$
T_{\ge\theta} = \sum_{i:\,\text{mel-EDI}_i \ge \theta}\min\!\big(\Delta t,\ \text{HOY}_{i+1}-\text{HOY}_i\big),\qquad \theta_{\text{default}}=250\ \text{lx} \tag{H-19}

$$

> **Why not the forward gap alone.** $\text{HOY}_{i+1}-\text{HOY}_i$ is exact only on a *contiguous* series.
> Analysis periods are gapped — `weather.decompose` emits occupied hours only, and for a multi-month period it
> repeats a fixed day/hour window across months — so a bare forward difference charges the last sample of every
> block the entire non-occupied gap. A three-day 08:00–18:00 window then reads 59 h instead of 33 h, and a
> Jun–Aug window reads 1475 h instead of 33 h. The error comes wholly from the gaps, so it does **not** shrink
> with a finer timestep. `min(\text{forward}, \text{backward})` does not fix it either: for the *first* sample of
> a block the backward gap is also the overnight gap.

> **Determining $\Delta t$ (`dosimetry.py`).** An explicit `step_hours` wins — `run_annual` threads
> `timestep_min/60`. Otherwise $\Delta t$ is the **modal** positive HOY gap: a real timestep recurs once per
> sample while block/overnight/inter-month gaps appear at most once per block, so the most frequent gap is the
> nominal step (ties break to the smaller). Every sample, first and last alike, contributes $\Delta t$; a
> single-sample series contributes `step_hours` if given, else 1.0 h. Result is `round(total, 4)` and requires
> `len(mel-EDI) == len(HOY)`. This matches `daylight_metrics.annual_sunlight_exposure`, which takes an explicit
> `step_hours` and is gap-immune by construction.

> **Quantity.** $T_{\ge\theta}$ is scored on CIE S 026 **mel-EDI**, never on `melanopic_lux` — the latter is
> larger by D65's own melanopic/photopic ratio (≈1.0997 on the 9-bin route) and, because the comparison is
> $\ge$, substituting it manufactures compliance.

> **Caveats.** (1) R_D is **relative only** — the 1/107 factor (§6.4) propagates linearly into I_eff and does not cancel in the nonlinear sigmoid; the model is validated against night-time electric-light studies, with a daytime envelope on the order of ±20 % (Pierson 2023). (2) The 260.7 pre-scaling and z_eff have no documented derivation beyond the source constants; they are transcribed, not re-derived. (3) ⚠️ **Executed ≠ validated.** The annual nvRD run *has* now been executed on a real EPW file (2026-08-12: two 35,040-step runs on the Athens IWEC year, see the §14 matrix), so the earlier "never executed" caveat is retired — but caveats (1) and (2) are untouched by that, and no run makes R_D an absolute scale.

---

## 9. The bridge — broadband → spectrum reconstruction

**Module:** `hcl_core/spectral_reconstruct`, data `hcl_core/_recon_data`. **Consumes:** Domain B channels
(sky + sun). **Produces:** a 401-point E(λ) that re-enters Domain A.

> **Source (faithful reconstruction):** H-10 channel expansion (CIE S 026 integral convention). Implementation-specific step-expansion; no primary publication for this exact channel→spectrum method.
> **Source (enhanced reconstruction, sky reference):** CIE 15 / CIE Standard Colorimetry — Judd–MacAdam–Wyszecki D-series S0/S1/S2 eigenvectors. (CIE 15:2004 Colorimetry).
> **Note:** the enhanced (reference-shaped) method is this implementation's extension of the faithful reconstruction.

Validation envelope: Pierson et al. 2023.

### 9.1 Faithful (flat) reconstruction

Each channel is expanded flat across its bin using H-10; the result reproduces the Radiance transport's
per-bin totals exactly. Crude across the steep melanopic 459–558 nm region.

### 9.2 Enhanced (reference-shaped) reconstruction

> **Source:** CIE 15 / Judd–MacAdam–Wyszecki eigenvectors (D-series S0/S1/S2) — H-21/H-22 reference shapes. (CIE 15:2004 Colorimetry).

Redistribute each bin's energy by a reference spectral shape while preserving the bin integral:

$$
E_{\text{enh}}(\lambda) = E_{\text{bin}}\cdot\frac{R_{\text{ref}}(\lambda)}{\sum_{\lambda'\in\text{bin}}R_{\text{ref}}(\lambda')},\qquad
  \int_{\text{bin}} E_{\text{enh}} = \int_{\text{bin}} E_{\text{flat}}\ (\text{exact}<10^{-9}) \tag{H-20}

$$

> **Operator safeguards (D-18, `spectral_reconstruct.py:37-57`).** The reference shape is first clamped non-negative, $R^+(\lambda)=\max(0,R_{\text{ref}}(\lambda))$ — an irradiance spectrum is physically non-negative, and a mixed-sign D-series reference with a positive bin sum would otherwise leak negative per-nm values. If $\sum_{\text{bin}}R^+=0$ the bin degrades to the **uniform/flat** distribution (enhanced ≡ faithful for that bin), so the operator is total-preserving and non-negative *by construction*. The flat reconstruction fills $(\text{hi}-\text{lo})$ values per bin plus one appended 780 nm point; `_bin_spans` extends the last bin's span to index 401 so the per-bin re-summation tiles all 401 indices exactly once (`:21-35`).

The energy-preservation invariant guarantees enhanced reconstruction can never contradict the Radiance transport. Reference shapes:

- **Sky:** an explicit input SPD, a per-timestep CIE D-series from CCT, or default D65.
- **Sun:** an explicit SPD, an air-mass-dependent direct-normal solar template, or neutral.

**CIE D-series** (`_recon_data.dseries_spd`, standard CIE 15 / Judd–MacAdam–Wyszecki eigenvectors S0,S1,S2 on a 10 nm anchor grid, valid 4000–25000 K):

$$
S(\lambda) = S_0(\lambda) + m_1 S_1(\lambda) + m_2 S_2(\lambda) \tag{H-21}

$$

$$
m_1 = \frac{-1.3515 - 1.7703\,x + 5.9114\,y}{0.0241 + 0.2562\,x - 0.7341\,y},\qquad
  m_2 = \frac{0.0300 - 31.4424\,x + 30.0717\,y}{0.0241 + 0.2562\,x - 0.7341\,y} \tag{H-22}

$$

with (x, y) on the daylight locus from CCT (two cubics in 1/T, split at 7000 K).

**Air-mass solar template:** anchored representative direct-normal slopes (inspired by ASTM G173 / SMARTS, shape-only — the 760 nm O₂ dip is omitted), selected by a plane-parallel air mass $AM = 1/\cos z$ (z clamped to [0, 89]°) and interpolated between AM = 1.0 / 1.5 / 2.0 / 3.0 anchors.

### 9.3 The annual → nvRD assembly

`spectral_reconstruct.assemble_nvrd_rows` builds one **413-column** row per sensor-timestep for the nvRD driver: `[x,y,z, vx,vy,vz, month,day,hour, E_α, ELR, EDI, λ₀…λ₄₀₀]` — using 0-based column indices: the three α-opic columns (indices 9–11) are the melanopic (α = mel) triple from the summed sky+sun channels, and indices 12–412 (the last 401 columns) hold the chosen reconstruction. `nvrd()` consumes the 401-value spectrum and windows it to the 311-point ipRGC band (§8.1). The annual divergence report (`annual_nvrd`) compares faithful vs enhanced at the **first non-zero-sky timestep** (not midnight) and over the whole-year R_D series (mean/max absolute, final cumulative %).

> **Note (time-resolved on a live Daysim run; constant-zenith is now a fallback).** `generate_subhourly_wea`
> now parses the produced sub-hourly `.wea` and returns per-row `timestamps` + `solar_zeniths` (`_parse_wea_timestamps_and_zeniths`), and `annual_nvrd` feeds them into both reconstruction methods. So on a successful Daysim run the enhanced colored-sun is **time-resolved** (each timestep uses its own air-mass SPD,`AM = 1/cos z`). The **constant 30° zenith** is reached only in degraded mode — no Daysim / empty `.wea`
> (`solar_zeniths is None`), or, under `physical_sky`, the steps without physical spectra — and that case is surfaced honestly in `enhanced_solar_note`. The per-timestep zeniths come from `weather.solar_zenith`(a simplified constant-declination model), so absolute air-mass-reddening accuracy is bounded by that model.

### 9.4 Physical alternative — EPW → spectral sky (full)

> **Source (pipeline):** Bird & Riordan 1986 (SPECTRL2, M-14…M-24) + Nann & Riordan 1991 (SEDES1, M-25…M-29). Full derivation in [spectral-sky-methodology.md](spectral-sky-methodology.md) (M-1…M-34); the governing equations and the numerical flow are summarized here so this document is self-contained.
> **Note:** the statistical reconstruction of §9.1–9.3 is retained; this physical path is opt-in (`physical_sky=True`) and replaces the D-series/air-mass *templates* with per-nm physics, while the Radiance transport still supplies the per-channel totals.

The statistical reconstruction (§9.2) can be replaced by a physically-derived spectral sky built from the EPW itself: **EPW hourly row + LOCATION header → atmosphere → SPECTRL2 (or SMARTS) clear-sky → SEDES1 cloud bridge → 1 nm 380–780 nm record**. The cloud model is selectable via `cloud_variant` — `reanchored` (default) | `verbatim` | `seed` | `local` (`cloud_modifier.py:84-88`).

**Honesty boundary.** Only the SEDES1 *energy-rescale* is exact (it forces the broadband integrals to the EPW's measured DNI/DHI). The SPECTRL2 transmittances are golden-tested (<0.05% direct in the visible), but the **CCM shape is figure-digitized** and is *applied to the diffuse* although Nann & Riordan fit it to the *global* spectrum. The native `gensdaymtx` path and the SMARTS oracle are **validations, not calibrated baselines**; the anisotropic façade colour model (Layer B) is a first-order single-scatter construction with one fitted knob.

#### 9.4.1 Solar geometry (M-1…M-8, `solpos.py`)

DAYSIM site convention throughout: latitude north-positive, longitude **west-positive**, `time_zone` = standard meridian = −15°·UTC (`solpos.py:6`). Geometry is sampled at the **mid-interval** hour (`hour − 0.5`) because EPW is hour-ending (`spectral_pipeline.py:43,86`). **This convention does not propagate automatically into the Radiance sky.** `colored_sky` reads its own `hour` as a wall-clock instant and lets `gendaylit` re-derive the sun, so handing both tools the same integer leaves the spectrum and the traced sky 7.5° of diurnal arc apart. Pass the record's geometry through `colored_sky(sun_zenith_deg=…, sun_azimuth_deg=…)` to make one ephemeris authoritative for both (`sky.py:25-43`; D-27 in `spectral-sky-as-built.md` §3novies).

$$
\delta = 23.45^\circ\sin\!\Big(\tfrac{360(284+d)}{365}\Big)\ \text{(M-1, Cooper 1969, }solpos.py{:}50)

$$

$$
b=\tfrac{360(d-81)}{364},\quad \mathrm{EoT}=9.87\sin 2b-7.53\cos b-1.5\sin b\ [\min]\ \text{(M-2, }{:}51\text{-}52)

$$

$$
t_{\text{sol}}=h+\tfrac{4(\text{meridian}-\text{lon})+\mathrm{EoT}}{60},\quad H=15^\circ(t_{\text{sol}}-12)\ \text{(M-3, }{:}53\text{-}54)

$$

$$
\cos z=\sin\phi\sin\delta+\cos\phi\cos\delta\cos H\ \text{(M-4, Cooper 1969, }{:}57\text{-}59)

$$

Azimuth (M-5, Iqbal 1983) is `atan2` from south, rotated +180° mod 360 → N=0/E=90/S=180/W=270 (`:63-67`). Air mass (M-8, Kasten–Young 1989): $m=1/(\cos z+0.50572(96.07995-z)^{-1.6364})$, $=\infty$ for $z\ge90^\circ$ (`:23-28`). Earth-radius vector (M-6, Spencer 1971): $R_v=1.000110+0.034221\cos\Gamma+0.001280\sin\Gamma+0.000719\cos2\Gamma+0.000077\sin2\Gamma$, $\Gamma=2\pi(d-1)/365$, range ≈0.966–1.034 (`:37-40`).

> **Two solar-position routines ship, and they agree.** `weather.solar_zenith` (`weather.py:84-103`) is a
> second, independent implementation on the legacy `.wea`/Daysim path, carrying the same Cooper declination and
> equation of time. Its zenith is **byte-identical** to `solpos.compute().zenith_deg` — verified at max absolute
> difference **exactly 0.0** over 500 randomized (date, hour, lat, lon, tz) cases — so the spectral and legacy
> weather paths never disagree on sun position. Note the *air-mass* forms do diverge by design: `solpos` uses
> Kasten–Young 1989 (M-8) while the Perez port uses Kasten 1965 (H-31); they are different published models,
> not a drift. The §9.3 colored-sun reddening is bounded by `weather.solar_zenith`'s fidelity, which is this
> simplified constant-declination model — the residual caveat recorded in §14.

#### 9.4.2 Atmospheric state (M-7, M-12, M-13, `atmosphere.py`)

Precipitable water is **Gueymard 1994** (M-12, from T+RH, pvlib form; `:11-21`) primary, **Reitan 1963** (M-13): $W=\exp(-0.0392+0.0681\,T_{\text{dew}})$ cm (`:24-30`) fallback, else a fixed 1.5 cm (`:89`). The EPW precip-water column is deliberately ignored (`:97-98`). Documented defaults (`:60-66`): ozone **0.30 atm-cm (300 DU)**, Ångström α **1.14**, AOD500 **0.10**, pressure **1013.25 mbar**, albedo **0.20**, aerosol_g **0.65**; EPW pressure is Pa→mbar (÷100, `:134`). Resolution precedence is **override > EPW > default**, with per-field `{source,method,uncertainty}` provenance (`:118-126`).

Four **opt-in refinements**, all defaulting to byte-identical prior output:

- **van Heuklon 1979 ozone** (M-7, `ozone_mode="climatology"`): $\Omega=[J+(A+C\sin(D(d+F))+G\sin(H(\text{lon}+I)))\sin^2(B\cdot\text{lat})]/1000$ atm-cm; **hemisphere-specific** NH coefficients $J{=}235,A{=}150,C{=}40,D{=}0.9865,F{=}-30,G{=}20,H{=}3,B{=}1.28,I{=}20$ (lon>0) give the **NH spring-max**, independently confirmed vs Karavana-Papadimou 2013 (`:33-57,142-144`). Default `constant` keeps the 0.30 literal.
- **Settable aerosol asymmetry** `aerosol_g` (default 0.65, `_G_DEFAULT`, `:66,78,154`), consumed by SPECTRL2 (`spectrl2.py:36`).
- **Ångström AOD anchor** (M-14): $\tau_{500}=\text{AOD}\cdot(\text{anchor}/500)^{\alpha}$, no-op at None/500 nm (`:150-153`).
- **Settable SMARTS α** (`smarts_aerosol="user"`, D-20).

#### 9.4.3 SPECTRL2 clear-sky engine (M-9, M-11, M-14…M-24, `spectral_engine/spectrl2.py`)

Native 122-pt grid, 0.3–4.0 µm, **W/m²/µm**. Pressure air mass $m_p=m\,P/1013$ (M-9, `:31`); ozone air mass $m_o=1.003454/\sqrt{\cos^2 z+0.006908}$ (M-11, `:32`). Single-scattering albedo (M-15) $\omega(\lambda)=0.945\exp(-0.095(\ln(\lambda/0.4))^2)$ (`:13-14,56`); aerosol OD (M-14) $\tau_a(\lambda)=\tau_{500}(2\lambda)^{-\alpha}$ (`:57`). Beam transmittances (M-18): Rayleigh $T_r=\exp(-m_p/(\lambda^4(115.6406-1.3366/\lambda^2)))$ (Eq 2-4), ozone $T_o$ (Eq 2-9), water $T_w$ (Eq 2-8), uniform-gas $T_u$ with the 118.3 constant (Eq 2-11), aerosol $T_{as}/T_{aa}/T_a$ (`:59-65`). Forward-scatter AFS/BFS/Fsp/Fs (M-16, `:39-43`).

$$
I_{d\lambda}=H_0 R_v\,T_o T_w T_u T_r T_a\quad\text{(M-19, Eq 2-1, }{:}75\text{-}76)

$$

Sky-diffuse-on-horizontal (M-22/M-23, Eqs 3-1…3-8) = (Rayleigh + aerosol + ground-back-scatter)·$C_s$, with primed diffuse-path transmittances at fixed $M'=1.8$ (M-20) and $C_s=(\lambda+0.55)^{1.8}$ for $\lambda\le0.45$ µm else 1 (M-21, Eq 3-17) (`:68-85`). A tilt branch (M-24, Eq 3-18) is golden-test-only (`:87-93`). Night guard: $z\ge90^\circ$ / $\cos z\le0$ / non-finite air mass → zeros (`:25-28`).

**SMARTS** (Gueymard 2019) is a selectable, `$SMARTSPATH`-gated oracle emitting the same W/m²/µm contract (§7bis.6, technical-reference).

#### 9.4.4 SEDES1 cloud bridge (M-25…M-29, `cloud_modifier.py`)

Clearness index (M-25, Eq 6): $K_t=\mathrm{GHI}/(I_{0,\text{normal}}\cos z)$, clamped $[0,1.2]$ (`:12-17`).

**Half 1 — energy-rescale (always on, the exact bridge invariant, M-27 Eq 9).** Grey factors $k_{\text{dir}}=\mathrm{DNI}/\!\int\!\text{direct}$, $k_{\text{dif}}=\mathrm{DHI}/\!\int\!\text{diffuse}$ via trapezoidal quadrature (M-26) over the **full native µm grid, before** any narrowing, forcing $\int\text{direct}=\mathrm{DNI}$, $\int\text{diffuse}=\mathrm{DHI}$ (`:20-47`).

**Half 2 — CCM diffuse reshape (shape-only, M-28/M-29).** $\mathrm{CCM}(\lambda,K_t)=A(\lambda)+B(\lambda)K_t+C(\lambda)K_t^2$ (`:98-110`); default `reanchored`/`local` divide by $\mathrm{CCM}(\lambda,0.70)$ so it is unity at the clear $K_{T,\text{CLEAR}}=0.70$ — a pure cloud modifier (`:73,107-109`). Diffuse is multiplied by $\max(0,\mathrm{CCM})$ then **renormalized back to DHI** so the invariant survives (`:124-128`). If $K_t$ is None the CCM is skipped (grey fallback, `ccm_applied=False`; energy-rescale still guarantees broadband correctness, `:114-122`). A/B/C are digitized from Nann & Riordan 1991 Fig. 11 (**no table in that paper**; ⚠️ one exists in Whitaker & Newmiller 1998 — see §"Coefficients" below); the regression σ is surfaced in provenance (`ccm_sigma`/`ccm_sigma_mean`).

#### 9.4.5 Resample, record, ground-glow (M-30, M-31, `spectral_sky.py`)

`resample_to_1nm` (M-30) is the **ONE** place the µm→nm conversion lives: linear-interpolate onto `GRID_NM` (380–780 @1 nm, 401 pts, `:16`) then **×0.001** (W·m⁻²·µm⁻¹ → W·m⁻²·nm⁻¹, `:48-56`). `build_record` records closure diagnostics: `bridge_residuals` = $(\int\text{direct}-\mathrm{DNI},\ \int\text{diffuse}-\mathrm{DHI})$ and `ghi_epw_residual` = $(\mathrm{DNI}\cos z+\mathrm{DHI})-\mathrm{GHI}$ (`:116-117,122`). Night = $z\ge90^\circ$ or $\cos z\le0$ → all-zero record, flagged `night_but_epw_nonzero` at the twilight edge (`:83-103`). Spectral ground-glow (M-31, isotropic, Liu & Jordan lineage):

$$
g(\lambda)=[\,I_{d}(\lambda)\cos z+I_{s}(\lambda)\,]\cdot\rho(\lambda)\cdot\tfrac{1-\cos\beta}{2}\quad(spectral\_sky.py{:}59\text{-}73)

$$

— the ground-reflected input for the Radiance path, not a standalone receiver irradiance.

#### 9.4.6 Kt-normalization solar constant (`spectral_pipeline.py`)

`_SOLAR_CONSTANT = 1361.0` W/m² (WMO) forms $i_{0,\text{normal}}=1361\,R_v$ used **only** for the Kt normalization — deliberately decoupled from each engine's internal ETR (SMARTS 1367, SPECTRL2 its own `ET_H0` table); different roles, not a bug (`:12-15,55,95`). `record_from_epw`/`annual_records` chain parse → derive → compute → build_record and forward the atmosphere-refinement kwargs per row (`:18-99`). *(code-only rationale.)*

#### 9.4.7 Parallel engines (validation-grade, not baselines)

- **Native `gensdaymtx`** (`hcl_radiance/spectral_native.py`): EPW → 20-band (NSSAMP=20, uniform 380–780 nm) spectral sky matrix, capability-gated emit-or-run (`:89-160`). `ground_refl` is a **single scalar** gray reflectance, not r/g/b (`:18-27`); the header `WAVELENGTH_SPLITS = {780,588,480,380}` is the unrelated 4-value RGB partition (`:38-79`); the `.smx` body stores bands **descending** — reverse before use (`:46-53`). First live-validated 2026-06-20 (Pearson 0.987 vs Python SPECTRL2) — incommensurable units, a validation only.
- **Pure-Python Perez 1993 façade** (`perez_distribution.py` + `sky_radiance.py`, **test-only, not on the default path**): Layer A relative-luminance $l(\zeta,\gamma)=(1+a\,e^{b/\cos\zeta})(1+c\,e^{d\gamma}+e\cos^2\gamma)$ ported verbatim from Radiance `gendaylit.c` (`perez_distribution.py:12-92`, $\mathrm{SOLAR\_CONSTANT\_E}=1367$); Layer B single-scatter colour = $(550/\lambda)^4\cdot\tfrac34(1+\cos^2\Theta)+\text{aod\_ratio}\cdot(550/\lambda)\cdot\text{HG}$, dome-mean-normalized and damped by $1+\eta(r-1)$ (`sky_radiance.py:19-58`). **Honesty:** $\eta=0.5$ is the one fitted knob (`sky_radiance.py:12-16`); Layer B is `code-only` (first-order construction, no external standard).
- **`compare_engines`** (`spectral_validate.py:34-51`) reports mean/max relative-% direct+diffuse over the visible and **raises rather than clamp/extrapolate** when a grid doesn't span the band — the SMARTS-vs-SPECTRL2 cross-check.

#### 9.4.8 End-to-end numerical flow (units)

EPW row (`epw_hourly.py`: 0-based field indices GHI 13 / DNI 14 / DHI 15, sentinels→None, short/bad rows dropped-with-logged-reason) + LOCATION header → `atmosphere.derive` → `AtmosphericState` (τ500, α, W cm, O₃ atm-cm, P mbar, ρ, g) → `solpos.compute(hour−0.5)` → `SolarGeometry` (z°, azimuth°, m, $R_v$) → `engine.compute` → `ClearSkySpectra` (122-pt, W/m²/µm) → `modifier.apply` (energy-rescale to DNI/DHI + CCM reshape, native µm grid) → `resample_to_1nm` (×0.001) → `SpectralSkyRecord` (401-pt, 380–780 @1 nm, **W/m²/nm**, + broadband + bridge/GHI residuals + CCM provenance). Consumers: `to_reference`/`to_channels` (feed §9.2 reconstruct/colored-sky), `ground_for_receiver` (Radiance ground-glow), and the emit artifacts (`emit_spd_set`/`emit_band_matrix`/`emit_spectral_wea`/`emit_augmented_epw_sidecar`, `spectral_emit.py:58-132`).

### 9.4a The SEDES1 cloud bridge — energy-rescale + spectral CCM (`hcl_core/cloud_modifier.py`, `_sedes1_data.py`, `sedes1_fit.py`, `clearsky_bias.py`)

> **Note.** §9.4.4 above gives the in-flow SEDES1 summary; this section is the dedicated deep treatment (variants, local recalibration fitter, and the optional clear-sky bias layer).

> **Source:** Nann & Riordan 1991, *Solar spectral irradiance under clear and cloudy skies*, J. Appl. Meteorol. **30**:447 (SEDES1; literature-bibliography.md M-25…M-29). The CCM coefficients are **figure-digitized** from Fig. 11 (**no table in that paper**). ⚠️ **"No published table anywhere" is retired** — Whitaker, C.M. & Newmiller, J.D. (1998), *Photovoltaic Module Energy Rating Procedure — Final Subcontract Report*, **NREL/SR-520-23942, Table 2-1, pp. 19–20** (<https://docs.nrel.gov/docs/legosti/old/23942.pdf>) tabulates the same regression and ships as the opt-in `Sedes2Modifier`, a **model swap** (6 coefficients, 1/cos z, NGH not $K_t$), not a coefficient swap; the SEDES1 default is unchanged and byte-identical. See §"Coefficients" below. The `clearsky_bias` K(λ) layer below is **`code-only`** and **default OFF**.

The cloud bridge turns an EPW hour's measured broadband DNI/DHI/GHI plus a clear-sky engine spectrum into a cloud-consistent spectral sky. It has two halves, run on the engine's native W·m⁻²·µm⁻¹ grid *before* any narrowing to 380–780 nm (`cloud_modifier.py:112-138`).

**Clearness index.** The single cloud driver is

$$
K_t = \frac{\mathrm{GHI}}{I_{0,\text{normal}}\cdot\cos z},\quad \text{clamped to }[0,\,1.2],\ \text{= 0 at/below horizon}

$$

with $I_{0,\text{normal}} = 1361\cdot\text{ERV}$ (modern WMO solar constant, used **only** to normalize $K_t$; decoupled from each engine's internal ETR) (`cloud_modifier.py:12-17`; `spectral_pipeline.py:12,55`). Nann & Riordan label; the code comment cites Eq. 6, the bibliography cites §4/Table 3 (see drift).

**Half 1 — energy-rescale (always on, the "bridge invariant", the only exact half).** Each clear-sky component is grey-scaled so its **full-native-range** trapezoidal broadband integral equals the EPW value:

$$
k_{\text{dir}} = \frac{\mathrm{DNI}}{\int E_{\text{dir}}(\lambda)\,d\lambda},\qquad k_{\text{dif}} = \frac{\mathrm{DHI}}{\int E_{\text{dif}}(\lambda)\,d\lambda}

$$

(zero if the clear integral ≤ 1e-9). This forces $\int E'_{\text{dir}} = \mathrm{DNI}$ and $\int E'_{\text{dif}} = \mathrm{DHI}$ exactly (`cloud_modifier.py:29-47`, Nann & Riordan Eq. 9). The integral is trapezoidal quadrature — a numerical choice, not a paper method (`:20-26`).

**Half 2 — spectral CCM diffuse reshape (shape-only).** The diffuse is multiplied by the cloud-cover modifier

$$
\mathrm{CCM}(\lambda,K_t) = A(\lambda) + B(\lambda)\,K_t + C(\lambda)\,K_t^2

$$

then renormalized back to DHI so the bridge invariant survives the reshape (`cloud_modifier.py:106,123-128`, Nann & Riordan Eq. 11). Negative CCM values are floored at 0. Direct-normal is **not** reshaped.

**Reanchoring (the default).** Under `cloud_variant="reanchored"` (default, byte-identical to omitting it) the CCM is divided by its clear-sky value so it is unity at the clear reference $K_{T,\text{clear}} = 0.70$, making it a *pure cloud modifier* (the clear-sky engine bias is handled separately, below):

$$
\mathrm{CCM}'(\lambda,K_t) = \frac{\mathrm{CCM}(\lambda,K_t)}{\mathrm{CCM}(\lambda,0.70)}

$$

(`cloud_modifier.py:73,107-109`). The `local` variant reanchors identically; `verbatim` applies the un-reanchored Fig. 11 CCM; `seed` uses the retired 9-anchor approximation.

**Grey fallback.** When $K_t$ is `None`, the CCM is skipped entirely (`ccm_applied=False`, `ccm_basis="grey-fallback"`); the always-on energy-rescale still guarantees broadband correctness while the diffuse keeps its clear-sky shape (`cloud_modifier.py:114-122`).

**Coefficients.** $A/B/C$ (and per-λ regression σ) are a **faithful human-in-the-loop WebPlotDigitizer digitization of Fig. 11** on a **10 nm grid, effective 330–1100 nm** (78 points), with $(1,0,0)$ pass-through outside range (`_sedes1_data.py:19-29,44-50`). Representative values: $B(400)=-2.037$, $B(340)=-3.877$ (`_sedes1_fig11.csv`). **Honesty:** only the energy-rescale is exact; the CCM *shape* carries figure-digitization uncertainty, surfaced (not yet propagated into downstream error bars) as `ccm_sigma` (dict at 400/500/600/700 nm) and `ccm_sigma_mean` (`cloud_modifier.py:94-96,132,137`). Two further approximations from the module: the paper *fits* CCM to **global-horizontal** spectra but this code *applies* it to the **diffuse** (over-weights blueing slightly, unvalidated by the paper), and PWV is not a shape driver here ($K_t$ is the sole driver; the ~940 nm PWV signature is outside 380–780 nm). The legacy eyeballed 9-anchor seed (`SEED_WL_NM=[350,400,450,500,600,700,800,950,1050]`, over-blues ~2×) survives only as `cloud_variant="seed"` (`_sedes1_data.py:13,60-64`).

⚠️ **The digitization is a property of this default, not of the literature — a TABULATION exists.** Whitaker, C.M. & Newmiller, J.D. (1998), *Photovoltaic Module Energy Rating Procedure — Final Subcontract Report*, **NREL/SR-520-23942, Table 2-1, pp. 19–20** (74 rows at 10 nm, 320–1050 nm; free, no copyright restriction; <https://docs.nrel.gov/docs/legosti/old/23942.pdf>) tabulates the same Nann & Riordan regression — the report's own text (p. 20) states the coefficients "were derived from measured data using statistical analyses as described by Nann and Riordan, 1991", so it **is** the tabulation of the curves Fig. 11 plots. It ships here as the **opt-in `Sedes2Modifier`**.

It is a **model swap, not a coefficient swap**. The form differs in two structural ways, both read from the primary report rather than a secondary description. First, six coefficients carrying a **1/cos z zenith term** the three-term form cannot express (report Eq. 2-39):

$$
\mathrm{CCM}(\lambda,\mathrm{NGH},z) = \Big(A_1+\tfrac{A_2}{\cos z}\Big) + \Big(B_1+\tfrac{B_2}{\cos z}\Big)\mathrm{NGH} + \Big(C_1+\tfrac{C_2}{\cos z}\Big)\mathrm{NGH}^2 \tag{H-50}

$$

Second, the independent variable is **NGH**, not the clearness index (report Eq. 2-43):

$$
\mathrm{NGH} = \frac{H_{H,\text{meas}}}{H_{s,H,\text{est}} + H_{d,\text{est}}\cos z} \tag{H-51}

$$

— measured broadband global horizontal over the **estimated clear-sky** global horizontal, where `cloud_modifier.clearness_index` divides by the **extraterrestrial** horizontal instead. Under clear sky NGH → 1 while $K_t$ → ~0.7, so the two are **not interchangeable even approximately**, and the class refuses to run without a clear-sky GHI reference rather than evaluating on the wrong variable. **Nothing in `src/` constructs it and it is not reachable via `cloud_variant`**, so every figure here stays byte-identical (the full suite passes with the SEDES1 default unchanged); adopting it changes overcast colour and requires a re-run before any overcast number is re-quoted. The transcribed table is pinned against the primary source by `tests/test_sedes2.py`, which also asserts the committed CSV and the shipped module cannot drift apart.

⚠️ **How it is actually reached, and the trap on that route.** It is not a Python-internals escape hatch: `record_from_epw` and `annual_records` both take a `modifier=` argument (defaulting to `Sedes1Modifier()`, `spectral_pipeline.py:33,74`), so a caller injects `Sedes2Modifier()` as a first-class argument. **But `build_record` never passes `clear_ghi=`** (`spectral_sky.py:110`), and `Sedes2Modifier.apply` needs it to form NGH. Injected through the pipeline as it stands, the modifier therefore takes its **grey path** — `ccm_applied: False`, diffuse keeps its clear-sky shape, energy-rescale still exact — rather than raising. That is the class's deliberate refuse-to-guess design (it will not evaluate the polynomial on $K_t$), but it means **a caller who simply swaps the modifier gets an un-reshaped diffuse, not SEDES2**. Read `ccm_applied` before believing an overcast number came from it. The same grey path is taken at $\cos z \le 0.05$, where $1/\cos z$ diverges (`cloud_modifier.py:208`). Supplying the NGH denominator needs a clear-sky GHI reference an EPW cannot give — CAMS (CC-BY 4.0, doi:10.24381/5cab0912) provides one for 7 of the 10 paper cities. ⚠️ Two caveats it does **not** retire, both of which *strengthen* rather than relax the existing ones: the fit is still **German-site-only** (Nann & Riordan measured at **four** sites, but p. 448 states "data from the **German site** were used to show how to develop a clear- and cloudy-sky semiempirical model" — the *fit* is single-site, so this caveat is correct as written and must **not** be "corrected" to say four sites), and the SEDES station measured on a **48° south-tilted plane**, so "fit to global, applied to diffuse" is really *tilted*-global. The instrument was a **LI-COR LI-1800** (10 nm step / 6 nm bandpass, stated absolute uncertainty ~4 % over 400–1000 nm). What adopting SEDES2 *does* retire, once a re-run is done, is the **digitization** caveat alone: the coefficients become tabulated rather than eyeballed.

**Variants and provenance.** Constructed-validated (`ValueError` on unknown / on `local` without coeffs) (`cloud_modifier.py:84-88`); each records `ccm_variant` plus honest `ccm_basis`/`coeff_method`: `reanchored`/`verbatim` → `fig11-faithful`/`webplotdigitizer_fig11`; `seed` → `seed-9anchor`/`eyeballed_seed`; `local` → `local-fit`/`local_recalibration` + `ccm_source` (the CSV path) (`:77-82,132-137`).

**Local recalibration (`sedes1_fit.py`).** A caller can re-fit $A/B/C/\sigma$ from measured spectra. Per wavelength $\lambda_j$, least-squares (pure-Python 3×3 normal equations) of the **normalized diffuse shape-ratio**

$$
r_i = \frac{s_i[j]\big/\sum_k s_i[k]}{c_i[j]\big/\sum_k c_i[k]}

$$

(measured diffuse $s_i$ vs clear-sky reference $c_i$) against $K_{t,i}$, with $\sigma = \sqrt{\mathrm{SSE}/(n-3)}$ for $n>3$ (else 0), and $(1,0,0)$ pass-through for $<3$ samples (`sedes1_fit.py:26-45,48-70`). `write_ccm_csv`/`load_ccm_csv` round-trip the `wavelength_nm,A,B,C,sigma` schema; `load_ccm_csv` returns `(coeffs_fn, sigma_fn)` interpolators consumed by the `local` variant (`:73-117`). Provenance for this fitter is **code-only** (the CCM functional form is Nann & Riordan Eq. 11; the shape-ratio target and solver are this implementation's).

**Optional clear-sky engine-bias K(λ) — default OFF / opt-in (`clearsky_bias.py`).** SPECTRL2's clear-sky diffuse runs too blue before any cloud term is applied. This layer applies a per-engine spectral warming $K(\lambda)$, inserted before the cloud modifier and renormalised to preserve broadband energy (shape-only); $K(\lambda)$ is unity outside 380–780 nm. ⚠️ $K(\lambda)$ is **empirical**: the shipped curve was derived from an internal measured dataset that is not published with this toolkit, so its derivation is not reproducible from this repo. It is applied **shape-only**, on unit-area-normalised spectra on both sides, so that dataset's absolute scale never enters the correction. Two implementation caveats: `ClearSkyBiasCorrection.apply` reshapes on the engine's **native grid — only 34 points across 380–780 nm** — and `build_record` resamples to 1 nm *afterwards* (`spectral_sky.py:106-107` corrects, `:111` resamples), so K is sampled at ~12 nm spacing, not at all 401 wavelengths; and the artifact is **keyed per engine**, so `engine="smarts"` with the correction enabled yields no correction and no error (`clearsky_corrected: False` is reported honestly, but nothing raises). `enabled=False` by default so it is never silently on. This is **`code-only`** (no literature M-number).

**Numerical flow (units).** clear-sky spectrum (native W·m⁻²·µm⁻¹) + EPW DNI/DHI/GHI (W·m⁻²) → [optional K(λ) clear-diffuse warm, shape-only] → energy-rescale (k_dir/k_dif, native grid, exact ∫=DNI/DHI) → CCM diffuse reshape (dimensionless multiplier) → renorm diffuse back to DHI → downstream `resample_to_1nm` (×0.001 to W·m⁻²·nm⁻¹). Provenance dict carries `k_dir`/`k_dif`, clear-sky broadband integrals, `kt`, `ccm_applied`, `ccm_variant`/`ccm_basis`/`coeff_method`/`ccm_source`, `ccm_sigma`/`ccm_sigma_mean` (`cloud_modifier.py:46-47,118-122,134-137`). **Validation status:** the energy bridge is exact/validated; the CCM shape is figure-digitized (or, for `local`, locally re-fitted — still shape-only, σ-quantified but not error-bar-propagated); the K(λ) layer is unvalidated and default-off.

### 9.5 The atmospheric-state layer — EPW row → AtmosphericState

> **Note.** §9.4.2 gives the in-flow atmosphere summary; this section is the dedicated layer reference with the full PWV/ozone/AOD equations and the end-to-end field-resolution flow.

**Module:** `hcl_core/atmosphere`. **Consumes:** one parsed EPW hourly row dict + the EPW LOCATION header (lat/lon/day-of-year). **Produces:** a frozen `AtmosphericState` (`atmosphere.py:69-78`) — the scalar atmosphere the SPECTRL2/SMARTS clear-sky engines consume. This layer sits **upstream** of the §9.4 physical-sky pipeline: `spectral_pipeline.record_from_epw`/`annual_records` call `atmosphere.derive` once per timestep (`spectral_pipeline.py:49-51`, `:92-94`) before `engine.compute`.

> **Scope note.** This layer supplies only *scalar* state; it computes **no** wavelength-resolved scattering. Rayleigh optical depth (`115.6406 − 1.3366/λ²`), the ozone/aerosol transmittances, and the diffuse Rayleigh/aerosol components are all computed downstream in the SPECTRL2 engine from this state (cross-referenced as M-18/M-22; realized in `spectral_engine/spectrl2.py:59`, **not** in `atmosphere.py`).

`AtmosphericState` carries six physical fields plus provenance (`atmosphere.py:69-78`): `aod500` (AOD @ 500 nm, base-e), `angstrom_alpha` (Ångström exponent), `pw_cm` (precipitable water, cm), `ozone_atm_cm` (column ozone, atm-cm; 0.30 = 300 DU), `pressure_mbar`, `albedo` (broadband), and — since the atmospheric-physics-refinements pass — `aerosol_g` (asymmetry factor, appended last, `:78`). A per-field `provenance` dict `{field: {source, method, uncertainty}}` tags every value's origin; `uncertainty` is reserved (`None`) in v1 (`:156-160`).

**Resolution precedence.** Each field is resolved by the inner `resolve` helper as **override > EPW value > default** (`atmosphere.py:118-126`), tagging `source` as `override`/`epw`/`default` respectively. All four refinement kwargs default to values that reproduce byte-identical prior output (`derive(..., ozone_mode="constant", aod_anchor_nm=None, lat_deg=None, lon_deg=None, day_of_year=None)`, `:92-93`).

#### Precipitable water (PWV)

> **Source:** Gueymard 1994, *Analysis of monthly average atmospheric precipitable water and turbidity…*, Sol. Energy **53**:57 (M-12), primary; Reitan 1963, *Surface dew point and water vapor aloft*, J. Appl. Meteorol. **2**:776 (M-13), dew-point fallback.

PWV is taken from temperature+RH (Gueymard 1994, the pvlib formulation) when both are present, else from dew point (Reitan 1963), else a fixed 1.5 cm mid-latitude default (`_pw_and_provenance`, `atmosphere.py:81-89`). The **EPW precipitable-water column is deliberately ignored** (officially unreliable, `:97-98`).

With θ = T/273.15 and T = T_air + 273.15 K (`gueymard94_pw`, `:11-21`):

$$
W = 0.1\,\big(0.4976 + 1.5265\,\theta + e^{13.6897\,\theta - 14.9188\,\theta^3}\big)\cdot\Big(\tfrac{216.7\,\text{RH}}{100\,T}\,e^{22.330 - 49.140\,(100/T) - 10.922\,(100/T)^2 - 0.39015\,T/100}\Big)\ \ [\text{cm}]

$$

Reitan fallback (`reitan63_pw`, `:24-30`), an **approximate** monthly-mean fit applied to hourly dew points:

$$
\ln W = -0.0392 + 0.0681\,T_d \qquad [W \text{ in cm}]

$$

#### Ozone column — van Heuklon 1979 climatology (opt-in)

> **Source:** van Heuklon 1979, *Estimating atmospheric ozone for solar radiation models*, Sol. Energy **22**:63, Eq. (4)/Table 1 (M-7). Independently re-confirmed vs Karavana-Papadimou et al. 2013, Global NEST J. **15**(2):152, eq. 2.

Default (`ozone_mode="constant"`) is the literal 0.30 atm-cm (`_OZONE_DEFAULT`, `atmosphere.py:61`, `:146`). Opt-in `ozone_mode="climatology"` computes the column from latitude/longitude/day-of-year (`van_heuklon_ozone`, `:33-57`); an explicit `ozone_atm_cm` override always wins regardless of mode (`:139-141`). The model is **hemisphere-specific** (distinct coefficient sets, `:48-52`), not hemisphere-symmetric. With all trig args in degrees:

$$
\Omega\,[\text{matm-cm}] = J + \big(A + C\sin(D(\text{doy}+F)) + G\sin(H(\text{lon}+I))\big)\sin^2(B\cdot\text{lat}),\qquad \Omega_{\text{atm-cm}} = \Omega/1000

$$

Northern hemisphere (`:49-50`): J=235, A=150, C=40, D=**0.9865**, F=**−30** (spring-max), G=20, H=3, B=1.28, I=20 (if lon>0 else 0). Southern hemisphere (`:52`): J=235, A=100, C=30, D=0.9865, F=152.625, G=20, H=2, B=1.5, I=−75. (D uses Table 1's **0.9865**, not the paper body's 0.9856, per the bibliography M-7 note.) The J=235 base term alone is 0.235 atm-cm = 235 DU. On a full-year run, ozone varies by season because each row supplies its own `geo.day_of_year` (`spectral_pipeline.py:92-94`).

#### Aerosol — AOD, Ångström exponent, asymmetry g

> **Source (AOD spreading law):** Ångström turbidity law as used in Bird & Riordan 1986 (M-14). The default `angstrom_alpha` value and `aerosol_g` value are **code-only** (no external citation in `atmosphere.py`).

- **AOD @ 500 nm** — override > EPW `aod` (when present, treated as a 500 nm broadband proxy, `source="epw_broadband_proxy"`, `:138`) > `_AOD500_DEFAULT = 0.10` (clean-continental, pvlib default, `:63`).
- **Ångström exponent** — `_ALPHA_DEFAULT = 1.14` (`:62`, resolved with no EPW source, `:148`). **Code-only** default value.
- **Ångström AOD-anchor conversion (opt-in, D-3).** If `aod_anchor_nm` is supplied and differs from 500 nm (strict guard `abs(aod_anchor_nm − 500.0) > 1e-9`, `:150`), the supplied AOD is converted to τ₅₀₀ using the same α the engine spreads with, and provenance is retagged `method="angstrom_from_<nm>nm"` (`:150-153`):

$$
\tau_{500} = \tau_{\text{anchor}}\cdot\Big(\tfrac{\lambda_{\text{anchor}}}{500}\Big)^{\alpha}

$$

`None` or `500.0` is a strict no-op (pre-refinement identity behavior).

- **Aerosol asymmetry g (opt-in, D-7).** `aerosol_g` is a first-class `AtmosphericState` field (default `_G_DEFAULT = 0.65`, rural/continental SPECTRL2 forward-scatter default, `:66`, `:154`), settable via `derive(overrides={"aerosol_g": …})` or the `aerosol_g=` pipeline kwarg (`spectral_pipeline.py:90-91`). It replaces a former hard-coded engine literal and is consumed by `Spectrl2Engine` and the single-scatter façade. **Code-only** default value; not independently validated.

#### Pressure and albedo

- **Pressure** — override > EPW `pressure_pa` (converted Pa→mbar by ÷100, `source="pa_to_mbar"`, `:133-134`) > `_PRESSURE_DEFAULT = 1013.25` mbar (`:64`).
- **Albedo** — override > EPW `albedo` (**only if physically possible**) > `_ALBEDO_DEFAULT = 0.20` (`:65`, `:135`).
  A column value at or below `_ALBEDO_MIN_PHYSICAL = 0.01` is treated as **missing**, not as a measurement.
  IWEC and TMY2 files write a literal `0.000` for every hour as a de-facto "no data" marker instead of the data
  dictionary's `999.0` sentinel — **4 of the 11 EPWs bundled here do exactly that, Athens among them.** Nothing
  outdoors is a perfect absorber (fresh asphalt ≈0.04, calm deep water at high sun ≈0.03), so `0.000` cannot be
  real; taking it at face value zeroed the entire ground-reflected term — `spectral_sky_from_epw` returned a
  401-array of zeros at every tilt, and `server.py` broadcasts that as the default spectral albedo — while the
  provenance still claimed `source: "epw"`. The gate is enforced in `epw_hourly` (at the parse layer, so the
  three-way precedence reports `source: "default"` for free) **and** in `atmosphere.resolve` via a `valid=`
  predicate, which also covers a caller passing a hand-built row. An explicit override is always honoured, and a
  genuinely dark surface survives as EPW data (Chania's 0.07 still reads `source: "epw"`). See ADR-0004.

#### End-to-end numerical flow

```
EPW hourly row {dry_bulb_c, rh_pct, dew_point_c, pressure_pa, aod, albedo}  +  LOCATION {lat, lon}  +  doy
      │
      ▼ atmosphere.derive(row, overrides, ozone_mode, aod_anchor_nm, lat, lon, doy)   (atmosphere.py:92-171)
      ├─ pw_cm       ← Gueymard94(T,RH) | Reitan63(Td) | 1.5 cm     [cm]          (:128-131)
      ├─ pressure    ← EPW Pa/100 | 1013.25                          [mbar]        (:133)
      ├─ albedo      ← EPW | 0.20                                    [–]           (:135)
      ├─ aod500      ← EPW broadband proxy | 0.10                    [–, base-e]   (:138)
      ├─ ozone       ← override | van_heuklon(lat,lon,doy) | 0.30    [atm-cm]      (:139-147)
      ├─ angstrom_α  ← 1.14                                          [–]           (:148)
      ├─ (opt) aod500 ← aod500·(anchor/500)^α  if aod_anchor_nm      [–]           (:150-153)
      └─ aerosol_g   ← 0.65                                          [–]           (:154)
      ▼
   AtmosphericState  ──► engine.compute (SPECTRL2/SMARTS)  ──► ClearSkySpectra   (§9.4)
```

> **Honesty flags.** (1) The Reitan 1963 fallback is approximate — fit to monthly means, applied to hourly dew points (`:25-28`). (2) `angstrom_alpha=1.14` and `aerosol_g=0.65` are **code-only** defaults with no external citation in `atmosphere.py`; they are transcribed engineering defaults, not validated against measurement. (3) The van Heuklon climatology and the Ångström anchor conversion are **opt-in**; the shipped default path is byte-identical to the pre-refinement engine (constant 0.30 atm-cm ozone, no anchor conversion). (4) Per-field `provenance.uncertainty` is reserved `None` in v1 — no per-field uncertainty model yet (`:156-160`).

---

## 10. Domain B inputs — electric-lighting photometry

**Module:** `hcl_core/ies` (parse/derive), `hcl_radiance/ies_radiance` (Radiance conversion, glare).

> **Source:** ANSI/IESNA LM-63-02, *Standard File Format for the Electronic Transfer of Photometric Data*. (`IES.pdf`). Parser `hcl_core/ies.py`; Radiance conversion via `ies2rad`/`evalglare`.

### 10.1 IES LM-63 parsing and effective candela

> **Source:** ANSI/IESNA LM-63-02, §data-line-1 field definitions. (`IES.pdf`).

The parser reads the 10-field data-line-1 (lamp count, lumens/lamp, candela multiplier, vertical/horizontal angle counts, photometric type, units, dimensions) and the 3-field data-line-2 (ballast factor, ballast-lamp photometric factor `pfactor`, input watts); `TILT=INCLUDE` blocks are consumed in place to preserve indexing.
Effective candela:

$$
I_{\text{eff}} = I_{\text{raw}}\cdot \text{mult}\cdot \text{ballast}\cdot \text{pfactor} \tag{H-23}

$$

### 10.2 Zonal-flux integration

> **Source:** ANSI/IESNA LM-63-02 — zonal-cavity sum method. (`IES.pdf`).

Luminous flux by the zonal-cavity sum over the file's vertical extent, splitting any zone straddling 90° so down/up flux are apportioned correctly:

$$
\Delta\Phi_i = \bar{I}(v_i)\cdot 2\pi\,\big(\cos v_1 - \cos v_2\big),\qquad
  \Phi = \sum_i \Delta\Phi_i = \Phi_{\downarrow} + \Phi_{\uparrow} \tag{H-24}

$$

where $\bar I(v)$ is the mean candela across horizontal planes at vertical angle v. Golden (a synthetic
0–90° fixture): 2765.81 lm total, **all downward** ($\Phi_{\uparrow}=0$ — the fixture has no above-horizon
candela); a separate straddle-90° test exercises the hemisphere split ($\Phi_{\uparrow}>0$,
$\Phi_{\downarrow}+\Phi_{\uparrow}=\Phi$).

**Beam / field angles** are the full vertical angles at 50 % / 10 % of peak candela (symmetric half-angle interpolation about nadir); flagged `beam_field_reliable = False` for off-nadir or non-monotonic (batwing) distributions. **LOR / efficacy**:

$$
\text{efficacy} = \frac{\Phi_{\text{rated}}}{W_{\text{in}}},\qquad
  \text{LOR} = \frac{\Phi_{\text{total}}}{\Phi_{\text{rated}}}\ (\text{None for absolute photometry}) \tag{H-25}

$$

### 10.3 ies2rad conversion, colorization, placement

> **Source:** ANSI/IESNA LM-63-02 + Radiance `ies2rad` (Ward / LBNL). LM-63-02 format (`IES.pdf`); `ies2rad` mechanics remain Radiance-tool convention.

`ies2rad` applies `mult·ballast·pfactor` **internally**, so the user `-m` scale carries **only** user
scaling × maintenance factor — folding the photometric factors in would square them:

$$
\texttt{-m} = \text{multiplier}\times\text{maintenance\_factor} \tag{H-26}

$$

A 3-channel `-c R G B` colorizes at conversion, so the emitted light data line carries the channel triplet rather than the neutral `1 1 1`; `place_luminaires` wraps the result in Radiance `!xform`. The Y-up→Z-up Euler remap (rotX→rotX, inputZ→outputY, inputY→−outputZ) is exact only for **single-axis** rotations; compound aiming must pre-orient the `.rad`.

> ⚠️ **Engine dependency — the `A1` candela scale (2026-07-18).** `ies2rad` writes the IES file's
> candela scale into the emitted `brightdata` primitive as the argument **`A1`**, and applying it is
> the *engine's* job: `source.cal`'s `corr`/`flatcorr` carry the branch `corr(v) = noneg(if(AC-.5,
> A1*v, v))`, where `AC` (the real-argument count) is 1 for `ies2rad` brightdata, so the true branch
> applies `A1`. **Builds that resolve those functions to the compiled built-in `source_corr` return
> `v` instead of `A1·v`**, and every IES luminaire then emits at unit scale. The consequence is
> silent and large — a 4×L09 `office_room` grid reads **34 lx where it should read 494 lx**, and
> `evalglare` reports **UGR 0** because the sources fall below its glare-source threshold — with no
> error at any stage and no implausible intermediate value. The deficit equals each luminaire's own
> candela scale (**14.4× for the Glamox L09, 2.068× for the Ludwig Leuchten 2722-001**), so it is
> **not a single correction factor and affected results must be re-run, never rescaled**. Sky paths
> (`gensky`/`gendaymtx`) carry no `A1` and are unaffected. **The transport chain above is correct
> given an engine that honours `A1`** — do *not* fold `A1` into `color_luminaire`'s RGB, which would
> double-scale on a stock Radiance. Detection and the no-`sudo` `RAYPATH` correction are
> implementation, documented in [technical-reference.md](technical-reference.md) §4.1a; the operating
> instruction is [operating-guide.md](operating-guide.md) §2 (`HCL_RADIANCE_SHIM`).

> **Spectral (9-band) colorization.** For a spectral render the luminaire is colorized per pass by `luminaire.color_luminaire(rad, channels9, count)`, which substitutes the Radiance default light data line `3 1 1 1` with `3 r g b`, where `(r,g,b)` is the `count`-th RGB third of a 9-value channel list (`count` 0 = blue → channels 0–2, 1 = green → 3–5, 2 = red → 6–8). The substitution is anchored on the preceding `\n0\n0\n` and applied once so polygon vertices matching `3 1 1 1` are never recoloured (`\b` guards against `3 1 1 10`); three passes reconstruct the spectral emission — the electric analogue of the §12.2 colored-sky path. A separate **first-principles lumen-method fixture-sizing** engine (`fixtures.py`, `recommend_fixtures`) is **illustrative** planning-grade, not manufacturer photometry (unit-tested only; see [technical-reference.md](technical-reference.md) §8 and the `hcl_studio` notes). Its method is §10.3a below.

### 10.3a Lumen-method fixture sizing and the circadian solve (`fixtures.py`)

> **Source:** zonal-cavity lumen method (IES handbook convention); the CU table, the reflectance adjustment
> and the V/H ratio are **`code-only`** engineering defaults with no external citation. **Illustrative.**

**Visual sizing.** Room cavity ratio and the maintained-flux requirement (`:33-35`, `visual_flux_lm`):

$$
\text{RCR} = \frac{5\,h_{\text{cav}}(L+W)}{L\,W},\qquad
\Phi = \frac{E_m\,A}{UF\cdot MF} \tag{H-47}

$$

$UF$ is linearly interpolated over RCR from a 3-class × RCR 0–10 coefficient-of-utilization table
(`_CU_TABLE`, `:23-31`; `direct` runs 0.95→0.37), then scaled by a reflectance-adjustment factor that is
unity at the reference set $(\rho_c,\rho_w,\rho_f)=(0.70,0.50,0.20)$ and clamped (`:51-53`):

$$
f_\rho = \text{clamp}\big(1 + 0.5\,\Delta\rho_c + 0.4\,\Delta\rho_w + 0.1\,\Delta\rho_f,\ 0.6,\ 1.25\big),
\qquad UF = f_\rho\cdot UF_{\text{table}}(\text{RCR}) \tag{H-48}

$$

Layout is reconciled against a uniformity criterion $S \le \text{SHR}\cdot h_{\text{cav}}$ with
$\text{SHR}=\{\text{direct }1.5,\ \text{direct\_indirect }1.25,\ \text{indirect }1.0\}$ (`:180`).

**The circadian solve.** Vertical illuminance at the eye is estimated from the horizontal target by a fixed
ratio, daylight is credited, and the residual is turned into a *required* mel-DER (`:186-190`):

$$
E_{v,\text{eye}} = E_m\cdot r_{V\!/\!H},\qquad
\text{mel-DER}_{\text{req}} = \frac{\max(0,\ \text{mel-EDI}_{\text{target}} - \text{mel-EDI}_{\text{daylight}})}{E_{v,\text{eye}}} \tag{H-49}

$$

`solve_circadian_spectrum` (`:103`) then resolves that into three bands against
`MEL_DER_PHYSICAL_MAX = 1.2` (`:100`) and the illustrative palette maximum (≈0.82): **reachable by palette**
(names the lowest-CCT preset that meets it), **reachable but beyond the palette** (no example preset to name),
or **not reachable** — in which case the target cannot be met spectrally and the engine instead sizes extra
vertical light, $E_{v,\text{needed}} = \text{net mel-EDI}/1.2$, re-enters H-47, and flags both
`supplementary` and `glare_warning` (`:194-206`).

> **Honesty.** $r_{V\!/\!H}$ defaults to **0.4** (`:153`) and is called out in-code as *the dominant circadian
> uncertainty* in this engine: it is a room-geometry-dependent quantity being supplied as a scalar default,
> and every recommendation scales inversely with it. The palette it names is the **synthetic**
> `ILLUSTRATIVE_LED` model (a pump Gaussian + broad phosphor hump, `presets.py:23`, flagged
> `illustrative: True` with `source: "synthetic physical model (this package)"`) — **not measured product
> data, and not a datasheet substitute.** The 1.2 ceiling is a stated physical bound, not a measured one.

### 10.4 Surface materials — transmittance → transmissivity, and the glazing band

**Module:** `hcl_core/materials` (Radiance material emission), `hcl_core/glazing` (parametric glazing band).

> **Source:** Radiance `glass` material convention (Ward / LBNL) — the transmittance→transmissivity inversion.
> The four polynomial constants are Radiance-tool convention; **no primary publication** derives them here.
> Port of Lark *Convert SPD* (`materials.py:1`).

A Radiance `glass` primitive takes **transmissivity** $t_s$, not the measured **transmittance** $T_n$: the
former is the single-surface quantity Radiance re-applies at both faces, so handing it a datasheet
transmittance double-counts the Fresnel reflections. `materials.glass_transmissivity` performs the standard
inversion (`materials.py:5-15`), applied per channel before any `glass` primitive is written
(`write_material`, `:37`):

$$
t_s(T_n) = \frac{\sqrt{0.8402528435 + 0.0072522239\,T_n^{2}} - 0.9166530661}{0.003626119\,T_n},
\qquad t_s(0) \equiv 0 \tag{H-42}

$$

(result rounded to 3 dp; the $T_n=0$ branch is special-cased to avoid the $0/0$). This is the conversion the
§12.6 OBJ importer applies to every group typed as glass, and it is exposed directly as the
`glass_transmissivity` MCP tool. Opaque surfaces (`plastic`) take their channel reflectances through
unchanged — the inversion is **glass-only**.

**Parametric glazing band (`hcl_core/glazing`).** For *deconfounding* a measured SPD that genuinely passed
through glass, three representative spectral transmittance shapes are available on the 401-point grid, with
warmth (red/blue tilt) rising `clear` < `lowE_single` < `lowE_double` (`glazing.py:34-41`), where
$t=(\lambda-380)/400$:

$$
s_{\text{clear}}(\lambda)=1,\qquad
s_{\text{lowE\_single}}(\lambda)=0.85+0.15\,t,\qquad
s_{\text{lowE\_double}}(\lambda)=0.70+0.30\,t \tag{H-43}

$$

Each shape is rescaled so its **photopic visible transmittance** equals a target VT
(`_visible_transmittance`, `:44-49`):

$$
\text{VT} = \frac{\sum_\lambda T(\lambda)\,E_{D65}(\lambda)\,V(\lambda)}{\sum_\lambda E_{D65}(\lambda)\,V(\lambda)},
\qquad T(\lambda) = s(\lambda)\cdot\frac{\text{VT}_{\text{target}}}{\text{VT}[s]} \tag{H-44}

$$

> **Honesty boundary — these are ASSUMED, not measured.** `ASSUMED_UNCOATED_DOUBLE_VT = 0.80` (`glazing.py:31`)
> is a *stated assumption a caller may override*, not a derived value: the transmittance was never measured and
> no product datasheet exists. The curves are a **sensitivity band**, never a single ground truth, and any
> result sensitive to VT must state the value used.

### 10.5 Glare (UGR)

> **Source:** Wienold & Christoffersen 2006, *Evaluating glare in buildings*, Energy Build. **38**:743; CIE 117 (UGR). DGP (Wienold & Christoffersen 2006); CIE 117 (UGR) — model realized in Radiance `evalglare`.

`evalglare -d` emits a named-field header followed by values; the parser maps field-name → index rather than assuming a fixed column (so it returns the true UGR column, not a spurious `av_lum`≈274).

> **Status.** The electric/colorize/place/glare pipeline is **emit-/mock-tested**, not live-run-verified
> (no Radiance ≥ 5.x execution on the dev machine for these paths); the grid daylight path is the one live-verified anchor (§14). **Green pytest ≠ live-validated** for this pipeline.

---

## 11. Domain B consumers — daylight controls & energy

**Module:** `hcl_core/lighting_controls`.

> **Source:** EnergyPlus Engineering Reference §7.3.5, *Daylighting Calculations* — continuous/stepped dimming control logic.

**Light-deficit fraction** at a reference point (setpoint $I_{\text{set}}$ default 500 lx, EN 12464-1 office):

$$
f_L = \max\!\Big(0,\ \frac{I_{\text{set}} - I_{\text{tot}}}{I_{\text{set}}}\Big) \tag{H-27}

$$

(`workbook_compat` switches the I_tot = 0 boundary between f_L = 1 (EnergyPlus, full electric in darkness) and
f_L = 0 (spreadsheet reproduction).)

**Lamp power fraction** (default control = *ContinuousOff*; $f_{P,\min}=0.15$, $f_{L,\min}=0.05$):

$$
f_P = \begin{cases}
  f_{P,\min}\ (\text{or }0\text{ for ContinuousOff}) & f_L < f_{L,\min}\\[1mm]
  \dfrac{f_L + (1-f_L)\,f_{P,\min} - f_{L,\min}}{1 - f_{L,\min}} & f_L \ge f_{L,\min}
\end{cases} \tag{H-28}

$$

Stepped control with N steps (default 3): $f_P = (\lfloor N f_L\rfloor + 1)/N$ for $0<f_L<1$.

**Zone power**, with per-point area weights $W_i$ (uncontrolled remainder at full power), and energy:

$$
F_P = \sum_i f_{P,i}\,W_i + \Big(1 - \sum_i W_i\Big),\qquad
  P_{\text{elec}} = P_{\text{rated}}\cdot \text{sched}\cdot F_P \tag{H-29}

$$

Primary daylit-zone depth $= 2.5\,(h_{\text{window}} - h_{\text{task}})$ sets $W_{\text{primary}}$; annual energy
is $\sum_{\text{occupied}} P_{\text{elec}}/1000$ kWh (default schedule weekdays 08:00–18:00 ≈ 2610 h/yr).
Golden: elec_lights.xlsx reproduced exactly ($F_P=0.84968881$ at the pinned row).

---

## 12. Domain B core — annual daylight transport (2-phase DDS)

**Module:** `hcl_radiance/annual`, `annual_commands`, `annual_results`, `sky`, `grid`.

> **Scope note — the LM-83 three-phase path (2026-08-12).** The 2-phase DDS below is the transport
> behind `run_annual` / `annual_daylight`, which compute sDA/ASE on whatever shading the scene
> already has. The `lm83_daylight` tool uses a separate **three-phase** transport
> (`hcl_radiance/threephase`, `threephase_commands`, `aperture`; Klems glazing BSDF in
> `hcl_core/klems`) so operable blinds can be switched per LM-83-12 §2.2.6 (blinds deploy when >2 %
> of the grid sees direct sun, floored at 1 point; default blind = 5 % diffuse VLT), with the
> direct-sun pass and blind-state policy in `hcl_radiance/lm83_run` / `lm83_sun` and
> `hcl_core/lm83`. Its results carry `lm83_method_conformant` — **always false by design** today
> (glazing runs at raw `tvis`, §§2.2.8–2.2.11 out of scope, biasing sDA up) — plus
> `conditions.departures`. The metric arithmetic (§12.5) is shared; the tool surface is documented
> in the technical reference.

> **Source:** Subramaniam 2017, *Daylighting Simulations with Radiance using Matrix-based Methods*, LBNL — 2-phase DDS decomposition.
> **Source (sky-vault patches):** Reinhart 2001 (MF subdivisions of Tregenza 1987 dome) — implemented in Radiance `gendaymtx`. (Tregenza 1987 + Reinhart & Walkenhorst 2001; realized in Radiance).
> **Source (sky radiance model):** Perez et al. 1990, *Modeling daylight availability and irradiance components from direct and global irradiance*, Sol. Energy **44**:271 — all-weather sky model embedded in `gendaylit`/`gendaymtx`. (Perez 1990/1993) — model lives inside Radiance.

### 12.1 The two-phase decomposition

Annual per-sensor irradiance is the sum of an independently-transported **sky-diffuse** term and
**sun-direct** term:

$$
\mathbf{E}_{\text{annual}} = \underbrace{\mathbf{D}_{\text{sky}}\,\mathbf{S}_{\text{sky}}}_{\text{Phase 1}}
  + \underbrace{\mathbf{D}_{\text{sun}}\,\mathbf{S}_{\text{sun}}}_{\text{Phase 2}} \tag{H-30}

$$


|                    | Phase 1 — sky-diffuse                                                                          | Phase 2 — sun-direct                                                                            |
| -------------------- | ------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| coefficient matrix | $\mathbf{D}_{\text{sky}}\in\mathbb{R}^{n\times 145}$ (`rfluxmtx -I+`)                           | $\mathbf{D}_{\text{sun}}\in\mathbb{R}^{n\times 5186}$ (`rcontrib`)                               |
| sky matrix         | $\mathbf{S}_{\text{sky}}\in\mathbb{R}^{145\times 8760}$, `gendaymtx -m 1 -s -c R G B` (colored) | $\mathbf{S}_{\text{sun}}\in\mathbb{R}^{5186\times 8760}$, `gendaymtx -5 0.533 -d -m 6` (neutral) |
| octree             | unfrozen (allows diffuse bounce)                                                                | frozen`oconv -f` (fixed sun discs)                                                               |
| basis              | Reinhart MF:1 = 145 patches                                                                     | Reinhart MF:6 = 5185 solar discs (one per sky bin), 0.533° disc; the matrices carry 5186 columns/rows because rcontrib bin 0 is the ground                                                  |

`dctimestep` performs each matrix product; `annual_results.combine_sky_sun` adds the two per-timestep RGB
series element-wise (direct beam + diffuse = total — physically correct).

> **Why the sun matrix is spectrally neutral.** Colour enters the annual transport **only** through `gendaymtx -c` on the sky patches (`build_gendaymtx_sky`, `annual_commands.py:115`); the Phase-2 sun matrix is built with **no** `-c` (`build_gendaymtx_sun`, `annual_commands.py:135`) because `gendaymtx -c` cannot colour the direct solar disc. The sun-direct term therefore carries the correct *magnitude* but no spectral information. This is exactly why the annual→nvRD bridge uses `run_annual_separated` to keep sky-diffuse and sun-direct apart (§9.3): only the direct beam is re-coloured downstream — via the air-mass solar template (§9.2) or the physical spectrum (§9.4) — to recover a spectrum for melanopic reconstruction. The point-in-time colored sky/sun path (`colored_sky`, mode `spectra`) does its own per-channel colouring in Python (`sky.scale_solar`/`sky.sky_glow`), a separate mechanism from the annual `gendaymtx -c` path.

### 12.2 Sky radiance

The patch radiances come from Radiance's `gendaymtx`/`gendaylit`, which embed the **Perez 1990/1993 all-weather** coefficients (the `coeff_perez` luminance-coefficient array is the Perez, Seals & Michalsky 1993 all-weather configuration; Perez 1990 is the companion irradiance-components model — the bibliography grounds this with both, H-30); the implementation builds the command (geographic convention: latitude north-positive, longitude flipped to west-positive, meridian = −15°·UTC) but does not recompute Perez internally on the annual DDS path. *(An optional pure-Python Perez 1993 façade port does exist for the anisotropic single-scatter path — see §9.4.7.)*

**The Perez formulation, as ported.** The pure-Python façade port (`perez_distribution.py`, §9.4.7 — *test-only,
not on the default annual path*) carries the model explicitly, and is transcribed here because §12.2 otherwise
states no equations while §9.4 gives SPECTRL2 full treatment. Air mass is **Kasten 1965** (note: *not* the
Kasten–Young M-8 form used by `solpos`), and the two sky descriptors are clearness ε and brightness Δ
(`:38-56`):

$$
m = \frac{1}{\cos z + 0.15\,(93.885 - z)^{-1.253}},\qquad
\varepsilon = \frac{\dfrac{\text{DHI}+\text{DNI}}{\text{DHI}} + 1.041\,z^3}{1 + 1.041\,z^3},\qquad
\Delta = \frac{\text{DHI}\cdot m}{E_0\,\varepsilon_{\text{cc}}} \tag{H-31}

$$

with $z$ in radians for the $1.041z^3$ term and $E_0 = \texttt{SOLAR\_CONSTANT\_E} = 1367$ W·m⁻² (`:35`) — the
`gendaylit` value, deliberately distinct from the §9.4.6 Kt-normalization constant 1361. ε selects one of
**8 bins**, each supplying five parameters $(a,b,c,d,e)$ as four-term linear functions of $z$ and $Δ$ from the
`PEREZ_COEFF` array (`:16-33`, 8 × 5 × 4); bin 0 (the overcast end) takes special exponential/power forms for
$c,d,e$ rather than the linear one. The relative luminance of a sky element at zenith angle ζ and angle γ from
the sun is then (`:84-92`, ported verbatim from Radiance `gendaylit.c`):

$$
l(\zeta,\gamma) = \big(1 + a\,e^{\,b/\cos\zeta}\big)\big(1 + c\,e^{\,d\gamma} + e\cos^2\gamma\big),
\qquad \cos\zeta \ \text{clamped} \ \ge 0.01 \tag{H-32}

$$

This is **Layer A** (magnitude/angular distribution only — it carries no colour). **Layer B**
(`sky_radiance.py:19-58`) adds the per-direction spectral colour as a single-scatter ratio of a Rayleigh λ⁻⁴
lobe and a Henyey–Greenstein aerosol lobe, dome-mean-normalized and damped toward isotropy:

$$
R(\lambda,\Theta) = \Big(\tfrac{550}{\lambda}\Big)^{4}\cdot\tfrac34\big(1+\cos^2\Theta\big)
  + \text{aod\_ratio}\cdot\Big(\tfrac{550}{\lambda}\Big)\cdot \text{HG}(\Theta;g),
\qquad R_{\text{damped}} = 1 + \eta\,(R-1) \tag{H-33}

$$

> **Honesty — η is a fitted free parameter of a shipped model.** $g = \texttt{DEFAULT\_G} = 0.65$ (continental
> aerosol asymmetry, the same value as the §9.4.2 `aerosol_g`) and $\eta = \texttt{DEFAULT\_ETA} = 0.5$
> (`sky_radiance.py:12-16`). η is **the one tunable knob** in Layer B. It was re-fitted in P3.

### 12.3 The `.ill` matrix layout

`dctimestep` output is NROWS=points × NCOLS=timesteps × NCOMP=3; each data **row** is one sensor holding the full 8760 RGB triplets interleaved. `annual_results.parse_ill` chunks a sensor's row by NCOMP (read from the matrix header, with a fallback to 3 — `comp = ncomp or 3`, `annual_results.py:66`, not a hardcoded constant) to recover its 8760 `[R,G,B]` series — each row is one sensor's full timeseries; a naive line-per-timestep reading would collapse the year to a single step.

### 12.4 Grid (point-in-time) transport

The single-timestep grid path (`hcl_radiance/grid`, `rtrace`/`rfluxmtx`) is the **live-verified** anchor:
a uniform sky returns 562.345 lx = 179π at a horizontal sensor (Radiance 5.4), confirming the H-3 efficacy and the irradiance→illuminance handling end to end.

### 12.5 Daylight-availability metrics

> **Source:** Nabil & Mardaljevic 2005, *Useful daylight illuminance: a new paradigm for assessing daylight in buildings*, Light. Res. Technol. **37**(1):41–59 (UDI paradigm) / 2006, *Useful daylight illuminances: a replacement for daylight factors*, Energy Build. **38**(7):905–913; IES LM-83-12 — UDI/sDA/ASE definitions. Nabil & Mardaljevic 2005/2006; IES LM-83-12.

DA / cDA / UDI / sDA / ASE (Reinhart 2001; IES LM-83; Nabil & Mardaljevic 2006) are now **implemented**
as a photopic climate-based daylight-metrics family (`hcl_core/daylight_metrics.py`) computed from the
annual **Domain B** 2-phase DDS transport (§12.1, via `hcl_radiance/annual_daylight.run_annual_daylight`)
and the H-3/H-4 179·W_PHOTOPIC lux primitive, rather than the melanopic channel path. The **Daylight
Factor (DF)** is computed *separately* (`hcl_radiance/daylight_factor.py`) as a **point-in-time** `run_grid`
under a CIE Standard Overcast Sky (`gensky -c`) — **not** the annual DDS. The annual result continues to
also feed circadian dosimetry (§8.3) and compliance (§13). EN 17037 daylight-provision **target
illuminances** are defined as thresholds (§13); the new sDA/ASE machinery is a separate, standards-based
spatial evaluation and does not evaluate against the EN 17037 thresholds directly.

**Metric equations** (`daylight_metrics.py`). Over the occupied timestep set $O=\{i:\text{occ}_i>0\}$, $N_{\text{occ}}=|O|$, per point:

$$
\text{DA} = \frac{1}{N_{\text{occ}}}\,\#\{i\in O:E_i\ge\theta_{DA}\},\qquad
\text{cDA} = \frac{1}{N_{\text{occ}}}\sum_{i\in O}\min\!\Big(1,\tfrac{E_i}{\theta_{DA}}\Big),\qquad
\theta_{DA}=300\ \text{lx} \tag{H-40}

$$

UDI splits occupied hours into four half-open bins with edges $\ell=100$, $u_s=300$, $u_a=3000$ lx (`daylight_metrics.py:51-67`): fell-short $E<\ell$; supplementary $\ell\le E<u_s$; autonomous $u_s\le E<u_a$; exceeded $E\ge u_a$. *(The 300/3000 three-way split is the Mardaljevic et al. 2012 refinement of the Nabil–Mardaljevic 100–2000 lx paradigm — a code-default divergence from the cited 2005/2006 sources, see bibliography.)* The spatial rollups over $P$ points:

$$
\text{sDA} = \frac{1}{P}\,\#\{p:\text{DA}_p\ge f\},\ f=0.5\ (\text{sDA}_{300/50\%});\qquad
h_p=\!\!\sum_{i\in O,\,E^{\text{sun}}_i\ge\theta_{ASE}}\!\!\Delta t_h,\quad
\text{ASE}=\frac{1}{P}\,\#\{p:h_p>H\} \tag{H-41}

$$

with $\theta_{ASE}=1000$ lx, $H=250$ h, **strict** $>$ (ASE$_{1000,250}$). Point-in-time Daylight Factor (`daylight_factor.py:68`): $\text{DF}_p=100\cdot E^{\text{indoor}}_p/E^{\text{outdoor}}$ with $E^{\text{outdoor}}$ traced from a sky-only unobstructed upward point (not a fixed constant); uniformity $=DF_{\min}/DF_{\text{avg}}$.

**Numerical flow — the two lux matrices.** `run_annual_daylight` runs the standard 2-phase DDS for the **total** (sky+sun, ambient-bounced) per-point lux matrix (→ DA/cDA/UDI/sDA) and, when `ase=True` (default), a **second independent Radiance pass** with `rad_params` rewritten to `-ab 0` (`_force_direct_only`) for the **direct-sun-only** lux matrix that ASE consumes (`annual_daylight.py:13-27,65-92`). The two are never merged. `run_annual` never passes `ase_rad_params`, so its command chain stays byte-identical. Occupancy defaults to `lighting_controls.default_schedule` — 1.0 on weekday hours in [08:00, 18:00), else 0.0, HOY 0 = Monday ($\text{dow}=(h//24)\bmod 7$, 0–4 = Mon–Fri); `step_hours = timestep_min/60`. `daylight_metrics()` returns `{per_point, spatial, sDA_basis}` (a `partial_year=True` flag adds a **top-level** `partial_year` key, not nested under `spatial`). The `sDA_basis` block records what the sDA figure was computed on — the `shading_model=` kwarg, the occupied-hours count vs LM-83's 3650 h period, `lm83_conformant` (true only when no departure applies) and the `departures` list — so a DA-based spatial fraction cannot be mistaken for a submission-grade LM-83 sDA.

### 12.6 Scene ingestion from OBJ/CAD (`import_geometry`) — a transport-prep utility

> **Source:** Wavefront `.obj` format; Radiance `obj2rad`/`xform` (LBNL). Geometry conversion lives inside Radiance; **no new physics is introduced here.**

The materials-and-geometry **scene** the §12 transport consumes need not be hand-authored:
`hcl_radiance/geometry_import.import_geometry` ingests a Wavefront `.obj` plus a per-group `material_map` and emits a per-channel Radiance scene (`geometry_set` + `material_sets`) that drops directly into the §12 grid/annual pipelines. It adds **no equation** — per-group reflectances bind through the same channel machinery already defined here (scalar → flat `[v]*N`; a measured `spd` → the §4.2 `bin_average`; glass via the §10.4 transmittance→transmissivity conversion, H-42), and `obj2rad`/`xform` perform only geometry conversion plus a unit/up-axis rigid transform (`-s` to metres, `-rx 90` for Y-up). The §0 honesty boundary is preserved: the OBJ carries **no** spectral data, so every discovered material group must be mapped explicitly — an unmapped group **hard-fails** rather than receiving a silent default.

One Radiance-tool subtlety is load-bearing and **live-confirmed**: `obj2rad`'s `-m` mapfile matches its`Material` qualifier only to `usemtl` names, so the importer emits the `Group` qualifier for OBJs whose groups come from `g` (otherwise every face is silently dropped → empty scene) and `Material` when `usemtl` is present; a *mixed* OBJ with un-materialled faces hard-fails. A capability-gated test runs real `obj2rad` (Radiance 6.1a) and confirms a group-only OBJ emits polygons. The flow is exposed to MCP clients through the **`import_obj_room`** prompt and documented in full by the **`hcl://reference/geometry`** resource;
operation and the module map live in [operating-guide.md](operating-guide.md) §I and [technical-reference.md](technical-reference.md) §4.5.

The **v2 program (P5–P8) is now built & shipped** (2026-06-26) and, critically for *this* document,
**introduces no new physics** — it is convenience geometry and provenance layered additively on the same channel machinery. A named **surface library** + sidecar + `.mtl` *hints* make the map faster to author (library entries are flagged `illustrative`, never silently authoritative); **geometry-derived sensors **(`derive_sensors=True`) emit the work-plane grid, eye-level observers — at **both** seated (1.2 m) and standing (1.6 m) heights as `observer_sets` — and DGP views that the melanopic-EDI quantity needs — a *vertical-at-eye* number against a *physically-oriented* sky — so the imported room becomes a runnable study with no hand geometry. The same work-plane and eye points can instead be generated methodology-grade by `workplane_grid` (EN 12464-1 illuminance grid → `grid.pts`, now clipped to the true floor footprint including concave L/T/U rooms) and `observer_points` (workstation eye sensors → vertical-at-eye `.pts` + DGP `glare_views`, now footprint-checked), orchestrated together by the `place_sensors` prompt — which also chains the sibling **`photosensors`** tool (daylight-dimming reference sensors, a distinct sensor class from the mel-EDI eye points above) and the diagnostic **`preview_scene`** matplotlib PNG check (placement verification only, not a photometric render; see `docs/methodology.md`/`docs/methodology_renders.md`, outer repo). None of this introduces new physics — it is still convenience geometry. The **georeferencing** field `north_angle_deg` applies the final`xform -rz (−north_angle_deg)` (post-remap frame; spec §3.1) to every channel run, and the *same*`_to_world` transform places the auto-sensors, the per-aperture true-north azimuth/tilt report (area-weighted mean normal over each glass group), and the `type:"luminaire"` markers into one coordinate system — the single
correctness property that keeps the EDI number computed at the right place and orientation.

The **v3 program (correctness + provenance, 2026-06-26)** closes the loop further, still **adding no equation**: (i) `type:"ground"` surfaces now **couple to the sky** — the importer derives a 1 nm spectral albedo from the ground material (`ground_albedo`; `kind="spd"` from a real SPD, else a flat scalar broadcast) that feeds the spectral ground-glow term `ground_for_receiver` (companion doc, M-section) through the new`spectral_sky_from_epw(spectral_albedo=…)` override, so one reflectance drives both the scene polygon and the sky's ground reflection; (ii) `type:"context"` surfaces are **exterior shading** — they stay in the octree (cast shadows) but are excluded from the auto-sensor footprint and the room-size sanity check; (iii)`type:"luminaire"` groups now also emit a **drop-in `electric_lights` payload** (world-frame placement + the forwarded IES/SPD) that `run_grid`/`run_image` consume directly — they run `ies2rad`/colorize downstream, so
the importer adds no photometry of its own; (iv) the **provenance manifest** is now written as a
`manifest.json` sidecar **and** embedded as a `#`-comment header in each geometry `.rad`, so provenance travels with the file; (v) the annotated colored-by-material render (`annotate=True`) is now **live-validated** (`oconv→rpict→falsecolor` on Radiance 6.1a). The honesty boundary is unchanged: the OBJ still carries no spectral data, unmapped groups still hard-fail (with a structured discovery payload), and luminaire markers carry no photometry. The **measured-SPD path now exists** (a library entry is flagged`measured` only when it carries a citation **and** a readable SPD file), though the *shipped* catalog stays illustrative scalars pending measured data; the frame/glazing split, auto ground-plane *geometry* synthesis, BSDF apertures and glTF/IFC import remain deferred.

**Geometry health check (2026-07-23), still adding no physics.** `import_geometry` now embeds a `health` report (`result["health"]`); the sibling **`check_geometry`** tool computes the identical report standalone, from an OBJ + `material_map` alone — no Radiance binaries, no scene build — so a model can be audited before spending any compute on it. This is a **correctness gate over the geometry the §12 transport consumes**, not a new radiometric claim: it catches defects that would otherwise complete silently and hand back a plausible-looking number — non-finite (NaN/infinite) vertex coordinates, coplanar surfaces Radiance resolves non-deterministically per ray, a glazing face sitting inside an unbroken opaque wall (the room traces dark), duplicated or non-planar faces, an unclosed enclosure, degenerate faces, non-manifold edges, an OBJ with no vertex normals, and a model with no group typed `type:"floor"`. The severity contract is one sentence: `error` is reserved for findings that change traced physics (`COINCIDENT_SURFACES`, `WINDOW_WITHOUT_OPENING`, and now `NON_FINITE_COORDINATES` — a NaN or infinite vertex is not a guess about intent, it is a fact Radiance genuinely cannot trace), everything else is `warning` or `info`, an *inferential* check (one that guesses intent from geometry rather than proving a defect) may never be promoted to `error`, and every error/warning carries a mandatory `fix`. `import_geometry(strict=True)` raises `GeometryHealthError` (`.payload` is the same report) when the report holds any error-severity finding, and has no effect under `dry_run=True` — that path returns before materials are even bound, so no health report exists yet to raise on. Missing vertex normals is deliberately capped at `warning`, never `error`, for a reason worth pinning down here: **Radiance `polygon` primitives are two-sided**, and this pipeline emits only `plastic` and `glass` — never a one-sided primitive — so a face's winding-derived normal direction does not change what gets traced; the check exists only because normals are the sole *independent* corroboration of orientation, not because their absence is itself wrong. `NO_FLOOR_GROUP` is the same class of inferential check as the normals one: without a typed floor, derived heights and the interior reference fall back to an estimate rather than a measurement, which is usually right but is a guess, so it too is capped at `warning`. Unimplemented check categories (materials, apertures, winding/north conventions, most sensor and luminaire checks) are never silently skipped — they are named in `report["skipped"]` with a reason, and `report["confidence"]` records that interior-reference confidence is not yet computed at this tier. **Tolerances (all absolute physical lengths, `geometry_health.py:647`).** Coincident-surface detection buckets faces onto planes at `tol = 0.001` m (1 mm) with a `tol/2` inflation on the plane-normal axis and an in-plane zero-extent guard `eps = max(tol·10⁻⁶, 10⁻¹²)` (`:190-191`, `:225`); non-planarity uses `tol = 0.005` m (`:366`); window-in-wall uses `tol = 0.001` m (`:470`). Ceiling detection requires a fairly horizontal face, $n_z > 0.8$ (≈37° tilt, `sensor_methodology.py:46`). These are load-bearing rather than cosmetic: `COINCIDENT_SURFACES` is one of the three `error`-severity findings, so its 1 mm bucket decides whether a model is allowed to run under `strict=True`.

**The check never raises on any parseable OBJ.** Before this pass, a NaN or infinite vertex reached a bare `ValueError: cannot convert float NaN to integer` out of the plane-key computation — including through the standalone `check_geometry` MCP tool, so a scene that should have produced an audit instead produced a crash. Non-finite coordinates are now a reported finding (`NON_FINITE_COORDINATES`), and every other geometric check skips a face that references a non-finite vertex instead of tracing it — the health report always returns.

**Three Tier-0 corrections to the `_to_world` correctness property claimed above.** The preceding v2 paragraph asserts that the *same* `_to_world` transform placing the auto-sensors, the aperture azimuth/tilt report, and the luminaire markers into one coordinate system is "the single correctness property that keeps the EDI number computed at the right place and orientation." Three defects in exactly that property shipped and were subsequently found and fixed; recorded here because the claim above was, for a period, not actually true of the running code:

1. **`up_axis` case-sensitivity split the frame.** `_to_world`/`object_centroid` compared `up_axis` case-sensitively while `build_xform` compared it case-insensitively, so `up_axis="y"` (lower-case) correctly rotated the *traced* geometry to Z-up via `build_xform` but left every *derived* quantity — sensors, luminaires, footprint, aperture report — computed in the un-rotated Y-up frame. The scene and its own sensors disagreed about which axis was up. Fixed by normalising `up_axis` once, at a single helper (`_normalize_up_axis`, canonicalising to `"Y"`/`"Z"`), and validating it at the MCP entry points rather than comparing the raw string at each call site.
2. **Gaze direction depended on face winding.** The derived-observer gaze direction — the `-vd` of every DGP fisheye view, and the direction every eye observer looks — came from `mean_aperture_normal`, which derived it from the OBJ's own winding-determined face normal. A reversed-wound window face therefore pointed every observer and every fisheye view **180° away from the glazing, at the back wall**, silently. Because the standards-aligned circadian quantity is vertical-at-eye illuminance (§6/§13), this was a first-order error on mel-EDI, not a cosmetic one. It now derives the inward direction from the room centroid instead — reusing `sensor_daylight.glazing_wall`, the same centroid-based resolution `detect_interior` already relies on — and is winding-independent by construction.
3. **The interior reference silently fell back to the world origin.** `sensor_daylight._floor_centroid_xy` — the interior-reference `(x, y)` that "inward from the glazing" is measured against — used the centroid of the `type:"floor"` group when one was typed, but fell back to `(0.0, 0.0)`, the world origin, when none was. For a room actually centred on the origin this is invisible; for any room that is not, "inward" silently means "toward the origin" rather than "into the room." Measured on a room centred at `(100, 50)` with glazing on its −Y wall: the derived gaze came out `(-0.902, -0.433)` — 116° off, pointing outdoors — where `(0, 1)` was correct. Since this is the same `-vd` every DGP fisheye view uses and the direction every eye observer looks, and vertical-at-eye illuminance is the melanopic quantity (§6/§13), this was first-order on mel-EDI, same as defect 2. It now falls back to the centroid of non-context geometry instead of the origin (verified: the untyped-floor case now agrees with the typed case, `(0.0, 1.0)` in both). The fix is in a **shared helper** — `_floor_centroid_xy` also backs the `photosensors` daylight-dimming-sensor tool — so `photosensors` was corrected by the same change; it was re-verified unchanged on the reference `office_room` scene (same two zone points, weights `0.353571` × 2, `uncontrolled_fraction` `0.292858`), confirming only the previously-broken untyped-floor path moved. `check_geometry_health`'s new `NO_FLOOR_GROUP` finding (above) now also surfaces the untyped-floor case directly, as an advisory rather than a silent fallback.

All three defects are now closed; the "single correctness property" claim above holds for the current code. It did not hold for the code that shipped it.

### 12.7 Sensor-placement methodology — the calculation grid and the daylight zones

**Module:** `hcl_radiance/sensor_methodology` (EN 12464-1 grid), `hcl_radiance/sensor_daylight` (daylight
zones), `hcl_core/lighting_controls` (the §11 zone weights). **Adds no radiometric physics** — but the
choices here *change reported numbers*, so they belong in the methodology, not only in the operating guide.

#### 12.7.1 EN 12464-1 calculation grid (`workplane_grid`)

> **Source:** EN 12464-1:2021 — maximum grid spacing and the calculation-area border. Realized in
> `sensor_methodology.en12464_grid`.

The grid is laid on the **calculation area**: the interior footprint inset by a border
(`border_offset = 0.25` m default, `:180`), at work-plane height $z = z_{\text{floor,top}} + 0.8$ m (`:210`).
Maximum spacing follows the EN grading rule on the longer calculation-area dimension
$d=\max(L_x,L_y)$ (`:205`):

$$
p_{\max} = 0.2\cdot 5^{\,\log_{10} d}\ [\text{m}],\qquad
n_x = \lceil L_x/p\rceil,\quad s_x = L_x/n_x \tag{H-45}

$$

Points sit at **cell centres**, $x_i = c_{x0} + (i+\tfrac12)s_x$ (`:212-213`), so no point lands on the
calculation-area boundary. A caller-supplied `max_spacing` overrides $p_{\max}$ and is recorded as
`p_source="override"` rather than `"en_formula"`.

> **Load-bearing subtlety (`:199-201`).** $d$ is graded on the **calculation area**, *not* the interior
> extent. Taking $d$ from the larger interior yields a **more permissive** $p_{\max}$ than the standard
> sanctions — under-sampling, and in the **non-conservative** direction. Because grid spacing changes both
> $\bar{E}_m$ and $U_o$, this is a compliance-affecting choice (§13), not a cosmetic one.

The footprint clip (`footprint.py`) is boundary-**inclusive**: `clip_points` keeps a row iff it is inside the
polygon (ray-cast with an exact-arithmetic collinearity test) **and** at least `border` from any edge. Concave
L/T/U rooms are handled by the same predicate, so a grid never spills into a re-entrant corner.

#### 12.7.2 Daylight zones — ⚠️ two shipped rules that disagree

> **Source:** sidelighting zone convention (`sensor_daylight.daylight_zones`, `:67`); IES 2.5-rule as used by
> `lighting_controls.area_weights_from_geometry` (§11).

**Two different zoning helpers ship, and they produce different weights for the same room.** The engine
surfaces this rather than hiding it, and a reader comparing two savings figures must know which was used:

| Rule | Depths from the façade | Sensor | Zones |
| ------ | ------------------------ | -------- | ------- |
| `head_height` (default, `sensor_daylight`) | $1\cdot H_{\text{win}}$, $2\cdot H_{\text{win}}$ | $\tfrac23$ into each band | primary + secondary (+tertiary) |
| `ies_2.5` (`sensor_daylight`), = the §11 rule | $2.5\,(H_{\text{win}} - h_{\text{task}})$ | $\tfrac23$ of the depth | primary only |

Zone area weights are the depth of each band clipped to the room, over the room's total depth, measured
along the façade-inward normal (`_zone_area_weights`, `:144-173`):

$$
W_k = \frac{\max\!\big(0,\ \min(\text{far}_k,\,D) - \max(\text{near}_k,\,0)\big)}{D},
\qquad W_{\text{unctrl}} = 1 - \sum_k W_k \tag{H-46}

$$

with $D$ the interior depth along the inward normal. Two conventions matter and are deliberate: (i) the
denominator is the **occupied interior, not the floor slab** — a modelled slab runs under the walls, and that
strip is neither occupied nor lit, so measuring against it would understate every zone and overstate the
uncontrolled remainder that §11 bills at full power (`:151-155`); (ii) zone depths are rebased onto the
**glazing plane**, since $d_{\text{lo}}$ is the interior wall face a wall-thickness inside it — without the
rebase, zone 1 loses that strip and equal-depth zones come out unequal (`:166-169`).

> ⚠️ **The clash caps the answer, so quote $\sum W$ with every savings figure.** $\sum W_k$ is a hard ceiling
> on the achievable saving regardless of daylight, and the two helpers disagree about it for an identical
> room — a difference worth *tens of percent* of the reported saving. `lighting_controls` therefore echoes
> `sum_weights`, `uncontrolled_fraction` and a `coverage_note` in every result, precisely so the assumption is
> visible in the number that depends on it rather than inferable only from which helper the caller happened to
> pick (`lighting_controls.py:180-195`). **Verify $\sum W$ before believing a savings percentage.**

---

## 12bis. Domain B consumer — ipRGC FOV directional weighting

> **Status:** an eye-level consumer that reuses the §6 mel-EDI machinery and the §12 transport without introducing new radiometric physics. **12bis.2** applies Khademagha ipRGC field-of-view directional weighting to a point-in-time fisheye eye image. It is largely absent from the rest of this document; the operational walkthrough is [technical-reference.md](technical-reference.md) §4.4.
>
> Melanopic source attribution moved to a companion study, a separate repository outside this one. The subsection numbering below is retained so existing §12bis.2 references (source code, technical reference, bibliography) keep resolving.

### 12bis.2 ipRGC field-of-view directional weighting (`hcl_radiance/image*.py`, `hcl_radiance/masks.py`)

> **Note:** the "mask" here is a Khademagha ipRGC FOV mask on a fisheye eye image, NOT the glazing-opacity override used by the melanopic source attribution engine (now in a companion study) — they are separate subsystems.

**Consumes:** per-channel fisheye HDR eye renders (`rpict -vta -vh 180 -vv 180`, `image.py:16,40`). **Produces:** a directionally-weighted greyscale eye map and a cosine-weighted RGB eye irradiance (`rgb.txt`).

**Action-curve maps.** For 9-channel input, three single-pass `pcomb` expressions collapse the 9 channels into greyscale photopic / melanopic / neuropic luminance maps; the coefficients are the **H-4 9-channel weight vectors verbatim** (melanopic `(0.0119,0.1784,0.4165,0.268843,0.1033,0.019,0.0017,0.000296,0.000061)`; neuropic 90.5 % in b1), stored as exact decimal strings (`image_commands.py:15-35`).

**Regional ipRGC weights.** The eye map is split into four FOV regions weighted by ipRGC directional sensitivity,

$$
w_R = \{\text{upper\_inner}=2.06,\ \text{upper\_outer}=1.37,\ \text{lower\_inner}=0.34,\ \text{lower\_outer}=0.23\}, \tag{H-37}

$$

(`image_commands.py:38`). Each region *R* is masked and scaled, then the four masked images summed,

$$
E_{\text{w}}(px) = \sum_R w_R\,M_R(px)\,E_{\text{eye}}(px), \tag{H-38}

$$

via `pcomb` (threshold `if(ri(2)+bi(2)+gi(2)-0.01, w_R, 0)` then multiply, then 4-image sum; `image_commands.py:40-55`). $M_R$ is a binary region mask.

**Masks.** The faithful path uses the four shipped Khademagha `.hdr` masks, pfilt-resized to the render resolution because a pcomb dimension mismatch errors otherwise (`masks.py:15-29`, `image.py:58-62`). The filename ordering is **not** the H-37 weight ordering — `_MASK_NAMES` (`masks.py:4-5`) maps

$$
\texttt{upper\_inner}\!\to\!\texttt{1\_upper\_inner.hdr},\quad
\texttt{lower\_inner}\!\to\!\texttt{2\_lower\_inner.hdr},\quad
\texttt{upper\_outer}\!\to\!\texttt{3\_upper\_outer.hdr},\quad
\texttt{lower\_outer}\!\to\!\texttt{4\_lower\_outer.hdr}
$$

so files **2 and 3 are `lower_inner` and `upper_outer`** respectively. Reading the numbering as "1–4 in weight order" swaps the two middle regions and silently applies $w=1.37$ where $w=0.34$ belongs. Bind by region key, never by file index. If they are absent, an **APPROXIMATE** synthesis generates them — upper/lower split at the horizontal meridian (`yp−0.5`), inner/outer at 30° eccentricity in an angular fisheye (inner-cone constant 0.09 of the normalized 180° fisheye) — explicitly flagged *not a substitute for the validated Khademagha masks* (`masks.py:31-56`).

**Cosine-weighted eye irradiance.** The final scalar eye irradiance integrates the (weighted) fisheye over the hemisphere with the view-direction cosine and per-pixel solid angle,

$$
E_{\text{eye}} = \sum_{px} S(px)\,\big(\mathbf{D}(px)\!\cdot\!\mathbf{V}\big)\,E(px),\qquad \mathbf{D}\!\cdot\!\mathbf{V}>0, \tag{H-39}

$$

where $S$ is the pixel solid angle from `vwright` and $\mathbf{V}$ the view forward vector (`image_commands.py:57-65`). For 3-channel input `rgb.txt` is raw cosine-weighted RGB (feed to `circadian_metrics`); for 9-channel it is already melanopic-weighted (×179 for mel-lux, do not re-run `circadian_metrics` — double-counts; `image.py:24-30`).

**Honesty / status.** The FOV weights and pcomb logic are transcribed verbatim (the numeric weights are lineage-only; `image_commands.py:7,41`); the concept cites Khademagha et al. **2018/2016** (literature-bibliography.md line 112; the in-code year is `image_commands.py:37`). Synthesized masks are approximate and not publication-grade — but the **faithful** path (the four shipped Khademagha `.hdr` masks) has now been **live-run end-to-end**: a companion study rendered all four monitor-facing observers through this exact `fov_pcomb` pipeline with `masks_present` True in each `fish_*/masks` dir (a `verify_khademagha.py` run in that study), so the retinal eye-mel-EDI values it reports are validated-Khademagha, not synthesized. (The engine's *own* automated suite still exercises the command graph by emit/mock; the live evidence is the paper's production renders.)

> **How to read the FOV-weighted output (the metric ladder).** The directional weighting is a **non-standardized companion, never a threshold verdict**. WELL/Brown/CIE S 026 and iNSOM define the 250 lx circadian target on the **cosine-weighted corneal (vertical-eye) irradiance**, *not* on a retinally-weighted quantity — so the FOV-weighted value must be read comparatively (gaze-against-gaze, source-against-source), never held against 250 lx (a category error). A companion study operationalizes this as a three-rung ladder: **Rung 1** = cosine-vertical eye mel-EDI at the actual gaze (the standards-aligned default; `run_image` already emits this with `fov_weighting=False`); **Rung 2** = the *same* cosine-vertical quantity swept across many gaze azimuths/elevations (the multi-view realism mechanism); **Rung 3** = the validated-Khademagha FOV weighting here, reported comparatively and explicitly un-thresholded. The FOV weighting is therefore a **defensible opt-in** (its masks are validated), not the reporting default.

---

## 13. Consumers — compliance thresholds

**Module:** `hcl_core/compliance`. The engine evaluates measured mel-EDI (and photopic Eᵥ) against published criteria; thresholds are transcribed with their standard, and flagged where a standard has revised across versions.

> **Source (WELL v2):** WELL Building Standard v2, Feature L03 Circadian Lighting Design (IWBI).
> **Source (Brown 2022):** Brown et al. 2022, *Recommendations for daytime, evening, and night-time indoor light exposure*, PLoS Biol. **20**:e3001571.
> **Source (ISO/CIE 8995-1):** ISO/CIE 8995-1:2025, *Light and Lighting — Lighting of Workplaces, Part 1: Indoor*, Annex B.5.3.
> **Source (EN 12464-1):** EN 12464-1:2021, *Light and Lighting — Lighting of Work Places, Part 1: Indoor*.
> **Source (EN 17037):** EN 17037:2018, *Daylight in Buildings*.

**WELL v2, Feature L03 (melanopic EDI, vertical at eye, 9:00–13:00, ≥ 4 h):**


|          | Electric-only  | Daylight criteria met | Published EML equiv. (÷1.103) |
| ---------- | ---------------- | ----------------------- | -------------------------------- |
| 1 point  | ≥ 136 mel-EDI | ≥ 109 mel-EDI        | 150 / 120 EML                  |
| 3 points | ≥ 250 mel-EDI | ≥ 163 mel-EDI        | 275 EML (current) / 180 EML     |

(The 3-point electric threshold tracks the **current** IWBI criterion — ≥ 275 EML by noon for ≥ 4 h → 250 mel-EDI (`_WELL_L03`, `compliance.py:8`); the pilot-era 240 EML → 218 mel-EDI value is kept only as a provenance snapshot in `_WELL_L03_PUBLISHED_EML`. Flagged "verify against live WELL standard" because thresholds have changed between WELL versions.)

**Brown 2022 / ISO/CIE 8995-1:2025 Annex B.5.3 (mel-EDI, vertical at eye):**


| Period  | Criterion |
| --------- | ----------- |
| daytime | ≥ 250 lx |
| evening | ≤ 10 lx  |
| sleep   | ≤ 1 lx   |
| night   | ≤ 1 lx   |

> **Caveat.** Brown 2022 publishes THREE tiers (daytime / evening / sleep); the engine's "night" period is an **alias of the sleep tier (≤ 1 lx)**, not a looser fourth one — an earlier revision scored "night" at ≤ 10 lx, i.e. the evening limit, 10× the consensus night-time figure (`_CONSENSUS`, `compliance.py:28`). The engine applies the shared consensus set to **both** the Brown and ISO/CIE standards without distinguishing — a low-severity mis-attribution, noted here (the code does not flag it).

**EN 12464-1:2021 (indoor task lighting, mandatory).** An 8-task table of (Ēm, UGR_L, Uo, Ra), e.g. office writing/reading 500/19/0.60/80, technical drawing 750/16/0.70/80, corridor 100/28/0.40/40; immediate-surround grading (task ≥ 750 → surround ≥ 500; ≥ 500 → 300; ≥ 300 → 200; ≥ 200 → 200; and **below 200 lx the surround requirement equals the task Ēm** — `compliance.py:116-124`) and background ≥ ⅓·surround; wall/ceiling/cylindrical minima (50/30/50 lx, Uo ≥ 0.10). Flagged "[verify against EN 12464-1:2021 text]".

> **Decision logic (no vacuous pass).** With no task parameters supplied the verdict is `"incomplete"`, **not** a pass; a relationship supplied without the input needed to evaluate it (e.g. background without surround) is recorded `"incomplete"` and **blocks** the overall pass — the `_all_met` guard treats any non-`True`/non-`None` sub-key (`False` or `"incomplete"`) as blocking, so an unevaluated check can never green-light a design (`compliance.py:239-249,273-289`).

**EN 17037:2018 (daylight provision, non-circadian, informational).** Target illuminance on ≥ 50 % of the plane = 300 / 500 / 750 lx (minimum/medium/high); minimum on ≥ 95 % = 100 / 300 / 500 lx. Returned as `"n/a"`(definitions only — see §12.5).

**UL 24480** — out of scope (requires the Rea/LRC Circadian Stimulus, which the engine does not compute);
returns `"unsupported"`.

> **Note.** The **CS/CLA circadian-stimulus model is not implemented** in this codebase. The engine's circadian currency is mel-EDI (CIE S 026, §6) and nvRD (§8); UL 24480's CS-based criterion is therefore explicitly unsupported rather than approximated.

---

## 14. Numerical caveats & live-validation status

The engine's credibility rests on stating exactly what is exact, what is approximate, and what has actually been run live. Consolidated:

**Approximations & legacy constants**

- **The 1/107 factor (H-10).** Unexplained; cancels only in ELR and same-path EDI *ratios*, but scales absolute E_α **and absolute EDI/mel-EDI** (EDI ∝ E_α, source-independent K^D65) and biases the nonlinear nvRD R_D. Absolute channel-path E_α, mel-EDI and R_D are unvalidated (~100 % vs SPD path) — use the SPD path.
- **Channel binning** double-counts band edges (by design) and is coarse across the steep melanopic 459–558 nm region; enhanced reconstruction (§9.2) mitigates shape but not the underlying transport resolution.
- **Colored-sun air-mass reddening is time-resolved on a live Daysim run** (§9.3): `generate_subhourly_wea`
  surfaces per-timestep solar zeniths, consumed by `annual_nvrd`; a constant 30° zenith applies only in degraded mode (no Daysim / empty `.wea`). Residual caveat: the `weather.solar_zenith` model's fidelity.
- **nvRD pre-scaling (260.7) and z_eff** are transcribed source constants, not re-derived; R_D is relative, validated against night-time studies (daytime envelope ≈ ±20 %, Pierson 2023).
- **3-channel output** intentionally differs from the naive descending-order result (the §9.3b alignment fix); the 9-channel path is unaffected.
- **SEDES1 cloud CCM** (companion doc): the default (`cloud_variant="reanchored"`, byte-identical to omitting it) is a faithful 10 nm digitization of Nann & Riordan's Fig. 11 curves, reanchored to unity at clear Kt; only the always-on energy-rescale (∫ = DNI/DHI) is exact — the CCM *shape* still carries figure-digitization uncertainty, now quantified as a per-wavelength regression σ surfaced in provenance (`ccm_sigma`/`ccm_sigma_mean`) and locally re-fittable from your own data (`cloud_variant="local"` + `hcl_core/sedes1_fit.py`; see [recalibrating-cloud-ccm.md](recalibrating-cloud-ccm.md)). The legacy 9-anchor eyeballed seed survives only as the opt-in `cloud_variant="seed"`. ⚠️ A **tabulated** alternative also ships opt-in — `Sedes2Modifier` on Whitaker & Newmiller 1998 Table 2-1. **It is a MODEL swap, not a coefficient swap**, and must not be read as "the same CCM with better numbers": six coefficients carrying a **1/cos z zenith term** the three-term form cannot express, driven by **NGH** (measured ÷ *estimated clear-sky* GHI) rather than $K_t$ — the two are not interchangeable even approximately (clear sky: NGH → 1, $K_t$ → ~0.7). It is not reachable via `cloud_variant`; it is injected as `modifier=`, and **without a `clear_ghi` reference — which `build_record` does not pass — it silently takes a grey, un-reshaped path** (`ccm_applied: False`) rather than raising. Check `ccm_applied` before quoting any overcast number as SEDES2-derived. See §9.4a (H-50/H-51) for the model form and the Whitaker & Newmiller 1998 citation.
- **IES beam/field angles** are unreliable for off-nadir/batwing distributions (`beam_field_reliable=False`).

**Live-validation matrix**


| Path                                                    | Status                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Grid daylight (`rtrace`/`rfluxmtx`)                     | **Live-verified** — 562.345 lx = 179π (Radiance 5.4)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| α-opic / colour / metrics (Domain A)                   | Unit-tested + golden-pinned; K^D65 within < 0.5 % of CIE S 026                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| nvRD model                                              | Unit-tested + golden; **live annual run done (2026-08-12)** — `annual_nvrd` executed end to end twice (one per seated eye) on the Athens IWEC EPW at `timestep_min=15`, returning 35,040-step R_D and RD_cum series for both reconstructions through the tool call. The **model's** relative-only caveat below is unchanged by this: an executed run is not a validated absolute scale                                                                                                                                                     |
| Annual 2-phase DDS (`.ill` round-trip)                  | **Live-validated (2026-08-12)** — `annual_daylight` run twice over the full 8760 h Athens year on 45 points at two ambient settings, both returning inside the tool call; per-point metrics regenerated from the run's own `.ill` matrices through the package's own aggregation reproduce the tool's returns to full float precision                                                                                                                                                                                                     |
| LM-83 three-phase (`lm83_daylight`, §12 scope note)     | **Live-validated end to end (2026-08-12)** — view/transmission/daylight matrices + Klems glazing BSDF, LM-83 §2.2.6 blind operation (2 % trigger floored at 1 pt, default blind 5 % diffuse VLT). `lm83_method_conformant` is **always false by design** (raw `tvis`, §§2.2.8–2.2.11 out of scope, sDA biased up); departures disclosed in `conditions.departures`, never silently passed                                                                                                                                                  |
| Electric pipeline (ies2rad/colorize/xform) + glare      | **Live end-to-end (2026-07-18)** — `office_room` + 4×L09 via `run_grid`/`glare_ugr`: avg**494 lux** (min 363 / max 627), `total_wattage` 152 W, **UGR 19.24 / DGP 0.199**. ⚠️ Only after correcting the build's `A1` handling (§10.3): unpatched the same scene read ~34 lux and UGR 0. Magnitudes are right on an `A1`-honouring engine — **not** an absolute-photometry baseline against measurement. Verify with `radiance_status().source_cal` before quoting any electric number |
| OBJ/CAD geometry import (`obj2rad`/`xform`, §12.6)     | **Live-validated (Radiance 6.1a)** — 4 gated tests: `obj2rad→xform→oconv→rtrace`, north round-trip, IES-luminaire octree, `annotate` recolor render. Transport-prep only — **no new physics**                                                                                                                                                                                                                                                                                                                                            |
| Daysim sub-hourly adapter (`epw2wea` → `ds_shortterm`) | **Live end-to-end** — the runner prepends `HCL_DAYSIM_BIN` to `PATH` and shells out to installed Daysim binaries (`/usr/local/daysim/bin`, built 2026-06-27, `runner.py:18-20`), so `generate_subhourly_wea` and Daysim-backed `annual_nvrd` run on real EPWs. Only `build_daysim`'s own clone+cmake path is emit/unit-tested (binaries built out-of-band). The hourly→sub-hourly disaggregation is **not** reimplemented — `ds_shortterm` applies the Skartveit–Olseth 1992 / Walkenhorst et al. 2002 stochastic model inside the binary |
| Spectral-sky SPECTRL2 (companion)                       | Golden-validated < 0.05 % vs SPCTRAL2 PC kit; offline Python engine — no Radiance needed                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Spectral-sky native`gensdaymtx` (Radiance 6.1a)         | **First live validation done** — NCOMP=20; loose-envelope agreement vs Python (corr 0.987); validation, not a baseline                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Spectral-sky SMARTS oracle                              | **First live validation 2026-06-21** — compiled from the SMARTS 2.9.5 source, obtained separately (not shipped in this repo; arm64 — the distribution's Mac binary is dead PPC); gated cross-check passes, agrees with SPECTRL2 ~2% direct / ~7% diffuse, corr 0.99. Validation, not a baseline. Default env still emit-only ($SMARTSPATH unset). Settable Ångström α/`g` via `smarts_aerosol="user"` (D-20) live-smoke-checked (α-monotone), not calibrated — see smarts-build.md                                                                                                                          |
| `physical_sky` DDS flip                                 | Opt-in, default-off, shape-only;**not** live-validated                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |

---

*Companion documents:* [spectral-sky-methodology.md](spectral-sky-methodology.md) (the EPW→spectral-sky
physics, M-n equations) · [technical-reference.md](technical-reference.md) (module-level review & audit) ·
[operating-guide.md](operating-guide.md) (running the server) · [literature-bibliography.md](literature-bibliography.md) (canonical citation source).
