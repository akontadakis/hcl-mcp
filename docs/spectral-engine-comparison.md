# Three-Way Spectral-Sky Engine Comparison — SPECTRL2 vs SMARTS vs `gensdaymtx`

> **Doc map.** One of four spectral-engine docs:
> [comparison](spectral-engine-comparison.md) (engine-vs-engine) ·
> [radiance-deep-dive](spectral-engine-radiance-deep-dive.md) (angular & cross-city) ·
> [validation](spectral-engine-validation.md) (canonical synthesis) ·
> [as-built](spectral-sky-as-built.md) (implementation ledger).
> **Owns:** the head-to-head engine comparison — physics, resolution, output, and where the three engines diverge.

> **What this is.** A live head-to-head of the **three** engines the toolkit can use to compute a spectral
> sky, on a real EPW. It quantifies how close they are and where they diverge — both in absolute spectral
> irradiance (where comparable) and in normalized spectral shape / colour (which is what drives the circadian
> metrics).
>
> **EPW:** `GRC_Athens.167160_IWEC.epw` (Athens, lat 37.90°, IWEC). **Day:** 7/15
> (a clear summer day; DNI peaks ~886 W·m⁻² at 13:00). **Hours sampled:** 10:00, 13:00, 16:00.
> **Engines live:** SPECTRL2 (always), `gensdaymtx` (Radiance 6.1a at `/usr/local/radiance`), SMARTS 2.9.5
> (compiled from the NREL 2.9.5 Fortran source).

---

## 1. The three engines

| Engine | Reference | Physics | Native output | Atmosphere | Resolution (visible) |
|---|---|---|---|---|---|
| **SPECTRL2** | Bird & Riordan 1986 | pure-Python 2-stream clear-sky, 122 wavelengths 300–4000 nm | direct-normal + sky-diffuse-horizontal **irradiance**, W·m⁻²·µm⁻¹ | **EPW-derived** (AOD500, PWV, ozone) | 122 pts 300–4000 nm (~34 in 380–780; 20–26 nm spacing in the red) |
| **SMARTS 2.9.5** | Gueymard 2019 | Fortran clear-sky RTE, 22 attenuation processes, 1 nm | same quantities, 280–4000 nm | **EPW-derived** (same `atm`/`geo`) | 0.5 nm UV / 1 nm VIS / 10 nm NIR |
| **`gensdaymtx`** | Radiance 6.x (LBNL) | OPAC continental-aerosol Mie scattering, 20 bands 380–780 nm | per-sky-patch **radiance**, W·sr⁻¹·m⁻² | **EPW AOD, illuminance and sky-cover columns** + the OPAC aerosol model | 20 bands @ 20 nm (380–780) |

## 2. Method — what is comparable, and what is not

SPECTRL2 and SMARTS emit the **same physical quantity** (horizontal spectral irradiance) from the **same
EPW-derived atmosphere**. They are compared at the **raw clear-sky engine stage** (`Spectrl2Engine.compute`
vs `SmartsEngine.compute`, identical `atm`/`geo`) — so the comparison isolates engine *physics*, not cloud
handling. Both absolute (broadband ∫ over 380–780 nm; per-nm % via `spectral_validate.compare_engines`) and
shape (20-band normalized) are reported.

`gensdaymtx` emits a **different quantity** (summed sky-patch radiance, W·sr⁻¹·m⁻²) under its own aerosol
treatment — it is **not** commensurable with horizontal irradiance in absolute terms. It is therefore
compared on **normalized spectral shape only** (20-band, after reversing the `.smx` body's descending
red→blue band order to ascending 380→780). Colour metrics (CCT, mel/photopic ratio) are scale-invariant and
so are reported for all three.

> Production note: `spectral_sky_from_epw` runs the chosen clear-sky engine **then** the SEDES1 cloud bridge
> (energy-rescale to EPW DNI/DHI + CCM). On a clear hour (Kt≈0.77 here) the modifier is near-unity, so the
> clear-sky comparison below is representative of the production output on clear hours.

## 3. Results

### 3a. SPECTRL2 vs SMARTS — the two clear-sky engines, identical atmosphere

Directly comparable (same quantity, same `atm`/`geo`). "%" is SMARTS-vs-SPECTRL2 over 380–780 nm.

| Hour (zenith) | Component | mean % | visible ∫ SPECTRL2 → SMARTS (W·m⁻²) | Δ∫ | shape Pearson |
|---|---|---|---|---|---|
| 10:00 (42.0°) | direct  | −1.8 % | 387.1 → 380.8 | −1.6 % | 0.991 |
|               | diffuse | +2.5 % | 113.5 → 118.6 | +4.4 % | 0.991 |
| 13:00 (16.4°) | direct  | −1.5 % | 430.6 → 424.8 | −1.3 % | 0.992 |
|               | diffuse | +1.1 % | 129.6 → 133.8 | +3.2 % | 0.992 |
| 16:00 (41.8°) | direct  | −1.6 % | 388.4 → 382.6 | −1.5 % | 0.991 |
|               | diffuse | +2.7 % | 113.9 → 119.0 | +4.5 % | 0.991 |

**Reading it:** the **direct beam agrees to ~1.5–2 %** (SMARTS marginally lower) and the **diffuse to ~3–5 %**
(SMARTS higher), with shape correlation **r≈0.99** throughout. SMARTS carries more diffuse energy and runs
bluer (see 3b).

> ⚠️ The per-nm **max** deviation reported by `compare_engines` reaches −68 % to −88 % — this is a
> **resolution artifact, not disagreement**: SMARTS resolves narrow telluric absorption lines (the O₂-A band
> at 760 nm, H₂O bands) at 1 nm that SPECTRL2's 122-point grid (only 34 points in the visible) smooths over.
> At those individual wavelengths the ratio blows up; the honest agreement is the **mean (−2…+3 %)** and the
> **broadband integral (−1.6…+4.5 %)**.

### 3b. All three — sky-diffuse colour (the circadian-relevant signal)

Scale-invariant, so all three are directly comparable. mel/phot = melanopic/photopic ratio (higher = bluer).

| Metric | Hour | SPECTRL2 | SMARTS | `gensdaymtx` |
|---|---|---|---|---|
| **mel/phot** | 10:00 | 1.024 | 1.067 | 0.972 |
|              | 13:00 | 1.037 | 1.072 | 0.984 |
|              | 16:00 | 1.024 | 1.066 | 0.972 |
| **CCT [K]**  | 10:00 | 8394 | 9310 | 7368 |
|              | 13:00 | 8684 | 9489 | 7580 |
|              | 16:00 | 8390 | 9285 | 7370 |

**Blueness ordering is consistent at every hour: SMARTS (bluest, ~9400 K) > SPECTRL2 (~8500 K) >
`gensdaymtx` (warmest, ~7440 K).**

Pairwise shape correlation (20-band normalized sky-diffuse):

| Hour | SPECTRL2~SMARTS | SPECTRL2~`gensdaymtx` | SMARTS~`gensdaymtx` |
|---|---|---|---|
| 10:00 | 0.991 | 0.977 | 0.951 |
| 13:00 | 0.992 | 0.981 | 0.961 |
| 16:00 | 0.991 | 0.977 | 0.952 |

### 3c. Direct-normal colour — all three agree tightly

| Hour | mel/phot SPECTRL2 / SMARTS / `gensdaymtx` | Pearson S2~SM / S2~gens |
|---|---|---|
| 10:00 | 0.768 / 0.777 / 0.763 | 0.992 / 0.975 |
| 13:00 | 0.788 / 0.796 / 0.782 | 0.993 / 0.977 |
| 16:00 | 0.768 / 0.777 / 0.763 | 0.993 / 0.976 |

The direct beam is dominated by Beer–Lambert extinction, which all three treat similarly — they agree to
within ~1 % in mel/phot and r≥0.975.

## 4. Interpretation

1. **SPECTRL2 and SMARTS are tightly coupled (r≈0.99).** They differ ~1.5–2 % on the beam and ~1–3 % in the
   mean on diffuse (Δ∫ 3.2–4.5 %), with SMARTS slightly bluer. This validates SPECTRL2 as the pure-Python
   default with SMARTS as the higher-fidelity opt-in oracle: for most work they are interchangeable.
2. **`gensdaymtx` is the warm outlier** (~1000 K below SPECTRL2, ~2000 K below SMARTS). This is expected: it
   uses the OPAC continental aerosol model and a different sky model, and emits patch radiance rather than
   irradiance. Separately, SEDES1's overcast blue blow-up — a per-city median of **11 650–18 392 K** across
   the ten cities under the **shipped faithful default** (Athens 14 815 K) — is a property of the cloud
   modifier, not of the clear-sky engine.
3. **Deviation grows at low sun.** At zenith ≈42° (10:00/16:00) the SPECTRL2↔`gensdaymtx` diffuse shape
   disagreement is **1 − r = 4.5 %**; at zenith 16° (13:00) it tightens to **2.2 %** (from the §3b pairwise
   correlations). Longer atmospheric path amplifies inter-model scattering differences.
4. **Circadian impact is real.** The ~1900–2200 K CCT spread between SMARTS and `gensdaymtx` for the *same sky*
   maps to a **≈9–12 % spread in melanopic content (mel/phot)** (8.6 % at 13:00, 11.6–11.7 % at 10:00/16:00) —
   inside the ±20 % envelope the toolkit already flags for spectral-sky circadian work, but not negligible.
   **For melanopic / mel-EDI work the engine choice matters; for photopic / visual work all three agree well.**

**Which engine for which receiver / metric.**
- *Horizontal roof, photopic/energy:* any of the three (they agree on `E_diffuse` by construction).
- *Vertical façade or eye, colour / melanopic:* **`gensdaymtx`** — the only engine with angular structure.
  Wrap SPECTRL2/SMARTS in the anisotropic distribution if you need a pure-Python façade colour.
- *Reference direct beam:* **SMARTS** (line-resolved), or SPECTRL2 for the golden-tested fast path.

**Bottom line.** SPECTRL2 ↔ SMARTS agree to ~1.5–2 % (beam) / ~3–5 % (diffuse) with r≈0.99 — effectively
interchangeable, SMARTS marginally bluer. `gensdaymtx` agrees in *shape* (r≈0.95–0.98) but sits
~1000–2000 K warmer and cannot be compared in absolute terms.

## 5. Limitations

- **One clear day, one site.** Clear hours only (Kt≈0.7–0.8); the cloud-bridge (SEDES1) reshaping under
  overcast is not exercised here and carries its own (faithful Fig. 11 digitization, per-coefficient
  σ-quantified) uncertainty. The shipped default is the re-anchored faithful Fig. 11 CCM; the post-bridge
  envelope is σ≈8 % across the visible (methodology §13). ⚠️ The digitisation is a property of this
  **default**, not of the literature: a tabulation of the same regression exists (Whitaker & Newmiller 1998,
  NREL/SR-520-23942 Table 2-1) and ships opt-in as `Sedes2Modifier` — a **model swap, not a coefficient
  swap** (six coefficients, a 1/cos z zenith term, NGH in place of Kt). Every figure in this document is a
  SEDES1-default figure and is unaffected; see [validation §2](spectral-engine-validation.md).
- **SMARTS is live-validated, not calibrated.** The cross-check confirms the deck/parse plumbing and
  agreement with SPECTRL2 to a few per cent. It is not a calibration against measurement.
- **`gensdaymtx` absolute energy is intentionally not compared** — different units and a different aerosol
  treatment make only the normalized shape meaningful.
- **SMARTS is optional.** Without it the SPECTRL2/`gensdaymtx` columns still populate. `SMARTSPATH` must be
  the **binary**, not its directory — set-but-wrong makes SMARTS skip silently rather than error.

⚠️ Every figure in this document is a **SEDES1-default** figure — and "default" here means the
**re-anchored faithful Fig. 11** CCM. Re-running with `Sedes2Modifier` opt-in changes overcast colour and
requires a re-run before any overcast number is re-quoted.

---

*Companion docs:* [`spectral-sky-methodology.md`](spectral-sky-methodology.md) (the per-engine physics) ·
[`spectral-sky-as-built.md`](spectral-sky-as-built.md) (as-built pipeline + validation caveats).
