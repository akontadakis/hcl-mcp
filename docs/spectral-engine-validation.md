# Spectral-Engine Validation — corrections, external cross-validation and honest bounds

> **Doc map.** One of four spectral-engine docs:
> [comparison](spectral-engine-comparison.md) (engine-vs-engine) ·
> [radiance-deep-dive](spectral-engine-radiance-deep-dive.md) (angular & cross-city) ·
> [validation](spectral-engine-validation.md) (corrections & external cross-validation — canonical) ·
> [as-built](spectral-sky-as-built.md) (implementation ledger).
> **Owns:** the optional correction layers (faithful SEDES1 CCM, anisotropic diffuse wrapper, clear-sky bias), the external SKYSPECTRA cross-validation, and the error budget.

> **One source of truth.** This document records the three optional correction layers the spectral-sky
> pipeline ships — a faithful SEDES1 cloud modifier, an anisotropic diffuse wrapper, and an optional
> clear-sky bias correction — together with the external SKYSPECTRA cross-validation and the error
> budget. Every headline number below is reproduced by a committed test or an inline analysis. The
> three engine docs link here.
>
> ⚠️ **Scope note.** Two of these layers (the anisotropy damping η, and the clear-sky warming `K(λ)`)
> are **empirical**: they were fitted against an internal measured dataset that is **not published
> with this toolkit**. The layers, their defaults and their code paths are here; the fitting dataset
> and the measured comparison tables are not. Treat the fitted values as shipped defaults with a
> stated provenance, not as reproducible-from-this-repo results.
>
> **Companions:** [`spectral-engine-comparison.md`](spectral-engine-comparison.md) (engine-vs-engine),
> [`spectral-engine-radiance-deep-dive.md`](spectral-engine-radiance-deep-dive.md) (the `gensdaymtx` path),
> [`spectral-sky-methodology.md`](spectral-sky-methodology.md) (the pipeline). The digitized CCM
> coefficients ship as
> [`Coefficient provenance/fig11_CCM_coefficients.csv`](Coefficient%20provenance/fig11_CCM_coefficients.csv);
> the interactive provenance dashboard is not redistributed.

## 2. SEDES1 cloud modifier — faithful Fig. 11 coefficients

The shipped seed was an eyeballed 9-anchor approximation. The human-in-the-loop WebPlotDigitization of
Nann & Riordan (1991) Fig. 11 (`docs/Coefficient provenance/`) replaced it with faithful A/B/C + σ. The seed's
blue coefficient was ~75 % too steep: **B(400) = −3.55 (seed) → −2.04 (faithful)** (the −3.5 the methodology
once used as corroboration is actually the ~345 nm value). The default is the **re-anchored, pure-cloud
CCM**, `CCM'(λ,Kt) = CCM(λ,Kt)/CCM(λ,0.70)` — unity at clear by construction, carrying no clear-sky bias.

Verified Kt-sweep (committed regression `test_kt_sweep_cct_regression`):

| Kt | seed | faithful (verbatim) | faithful (re-anchored) |
|---|---|---|---|
| 0.70 (clear) | 10 564 K | 9 258 K | 10 565 K |
| 0.25 (overcast) | **16 763 K** | **11 982 K** | **14 601 K** |

The faithful coefficients materially reduce the seed's over-blueing, but ⚠️ **"~halve" is the wrong
summary for the shipped variant.** Measured against the sweep's own clear-sky anchor (10 565 K), the excess
falls **6 198 → 4 036 K, a 35 % reduction** under the shipped `reanchored` default. The halving belongs to
the *verbatim* variant (16 763 → 11 982 K), which is **not** shipped — and even that is a 77 % reduction if
quoted against the same 10 565 K anchor rather than its own 9 258 K one. The two anchors must not be mixed.

**Five fidelity caveats on the CCM, carried even with the faithful coefficients** (this list does not map
one-to-one onto methodology §8.3, which keeps six items; cite §8.3 by *name* rather than by number):
(1) the ratio was fit to *global* spectra but is applied to *diffuse*; (2) PWV is omitted from the
shape term; (3) a Germany-only AOD≈0.23 fit is applied globally; (4) the CCM also absorbs SPECTRL2's
clear-sky blue bias (which the optional `K(λ)` of §5 separates out); (5) summer and fall regressions are
merged. These bound the *spectral-shape* uncertainty; the energy-rescale (broadband DNI/DHI match) stays
exact regardless.

A sixth, standalone concern: the default's coefficients are **figure-digitised rather than read from a
table**. The 3×3 Vandermonde/Cramer solve over Fig. 10's class-mean curves was the **seed** construction
step, retained only as the opt-in `cloud_variant="seed"`; the shipped `reanchored` default reads the
faithful Fig. 11 A/B/C/σ digitisation directly (10 nm grid, `_sedes1_fig11.csv`) with **no linear-algebra
solve at all**.

> **A tabulation of these coefficients exists, so the digitisation concern is avoidable.**
> **Whitaker & Newmiller (1998), NREL/SR-520-23942, Table 2-1, pp. 19–20** tabulates them — 74 rows at
> 10 nm, 320–1050 nm, a US Government contractor report distributed without copyright restriction.
> ⚠️ **This is not a coefficient swap.** The tabulated model is structurally different in two ways,
> which is why it ships as a **separate opt-in class** `Sedes2Modifier`, not a `Sedes1Modifier`
> variant: it carries **six coefficients with a 1/cos z zenith term** the three-term form cannot
> express, and its independent variable is **NGH** (measured GHI over *estimated clear-sky* GHI), not
> the clearness index $K_t$ — under clear sky NGH → 1 while $K_t$ → ~0.7, so feeding one where the
> other is expected evaluates the polynomial off its fitted domain. `Sedes2Modifier.apply` therefore
> **refuses to run** without a clear-sky GHI reference, falling back to a grey unity CCM rather than
> guessing.
>
> **No figure in this document depends on it.** SEDES2 is opt-in and nothing in `src/` constructs it.
> ⚠️ Adopting it **changes overcast colour and requires a re-run before any overcast number is
> re-quoted** — the §2 Kt-sweep table and the §5a error budget are SEDES1 figures.
>
> **What this retires, and what it does NOT.** The global-fit-on-diffuse caveat (1) and the
> blue-bias-absorption caveat (4) are unaffected. The **digitisation** concern becomes avoidable, but
> ⚠️ **the Germany-only caveat (3) stands exactly as written and must not be "corrected"**: Nann &
> Riordan measured at four sites, yet the paper (p. 448) states data from the **German site** were used
> to develop the model, so the *fit* is German-site-only. Two further facts from the source
> **strengthen** the caveats: the SEDES station measured on a **48° south-tilted plane** (so "fit to
> global, applied to diffuse" is really *tilted*-global), and the instrument was a **LI-COR LI-1800** at
> 10 nm step / 6 nm bandpass with ~4 % stated absolute uncertainty over 400–1000 nm.

## 3. Anisotropic diffuse wrapper

The isotropic engines are constitutionally blind to façade orientation: they predict one diffuse colour for
all façades, with a residual spread of **1.4 K** — numerically zero. That figure is a numerical result and
not a measurement, being the spread of **SPECTRL2's own predicted** façade CCTs.

The optional wrapper (`src/hcl_core/{perez_distribution,sky_radiance,
receiver}.py`) gives them orientation-dependent colour as a **consumer** of the canonical record (engines
untouched): a Perez-1990/93 achromatic magnitude layer (coefficients ported verbatim from the upstream Radiance
`gendaylit.c` — the Radiance source checkout is kept outside this published repo) carrying a single-scattering, **colour-only** spectral ratio whose anisotropy arises solely from
the Rayleigh-vs-aerosol ratio varying with scattering angle (a wavelength-independent phase gives **zero**
colour swing — verified to machine precision).

| Façade-colour spread, clear shaded (afternoon) | CCT spread |
|---|---|
| `isotropic` mode (today) | 0 K (one colour) |
| `single_scatter`, raw (η = 1) | ~6900 K at this hour — raw first-order overshoots |
| `single_scatter`, **η = 0.5 fitted** | **~1676 K** |

The single damping knob **η = 0.5** (the one fitted parameter, regression-locked, provenance-tracked) brings
the spread into a physically plausible range; raw first-order single-scatter omits multiple-scattering
graying and overshoots, so it is damped toward isotropy. ⚠️ η is **empirical**: it was fitted against the
internal dataset named in the scope note above, and the fit constrains it to an **interval,
η ∈ [0.19, 0.69]**, not a point (best-fit point value 0.458, which the data cannot resolve from 0.5). Any
claim that η is "fitted" must carry the interval. The afternoon **E > N > W** ordering (eastern sky ≈ 90°
from the sun, Rayleigh-blue) emerges as a physical consequence of geometry, not hardcoded. `isotropic` mode
stays bit-identical to today.

## 4. SKYSPECTRA external cross-validation

An independent, **no-glazing**, multi-city, includes-cloudy check against the open SKYSPECTRA dataset
(Zenodo 8147546, CC BY-NC-ND 4.0; raw kept out of git). Data availability splits the two checks
across two cities:

- **CCM cloudy slope (Vaulx-en-Velin, FR-VLX horizontal):** measured clear 5816 K → overcast 6455 K, a
  **modest +639 K** overcast-minus-clear shift over a large balanced sample — consistent with the **re-anchored
  CCM**, not the seed's steep blue blow-up.
- **Anisotropy ordering (Berlin, DE-BLN patch radiance — the only city with directional scans):** measured
  patch CCT is **bluer away from the sun in 4/4 clear days** (median far − near = **+4697 K**) — the Rayleigh
  anti-solar maximum the §3 wrapper reproduces; isotropic engines predict 0.

Both checks are no-glazing and independent of the internal fitting dataset, so the wrapper's anisotropy
direction and the re-anchored CCM's gentle slope are not artifacts of one site.

The reduction script (`data/skyspectra/derived/skyspectra_validate.py`) writes two aggregate tables:
`skyspectra_ccm_slope.csv` (FR-VLX clear 5816 K / n = 2087 → overcast 6455 K / n = 2082, **+639 K**) and
`skyspectra_validate.csv` (DE-BLN, positive on 4/4 clear days, median **+4697 K**). The FR-VLX sample is
4169 clear-or-overcast measurements. The raw stays local and git-ignored under CC BY-NC-ND; only summary
statistics are committed.

## 5. Clear-sky bias correction — optional, default-off

Even with a perfect cloud modifier, the SEDES1-bridged colour runs too blue, because the **clear-sky
baseline** is already too blue before any cloud term is applied. `src/hcl_core/clearsky_bias.py`
provides an **optional, default-off** per-engine spectral warming `K(λ)`, inserted before the cloud modifier
and renormalised to preserve broadband energy (shape-only). `K(λ)` is unity outside 380–780 nm.

⚠️ `K(λ)` is **empirical**: the shipped curve was derived from the internal dataset named in the scope
note above, and its derivation is not reproducible from this repo. It is applied **shape-only**, on
unit-area-normalised spectra on both sides, so the source dataset's absolute scale never enters the
correction.

The layer is **default-off / opt-in**; with the default, every current output is **bit-identical**.
⚠️ **Any figure computed with `clearsky_bias` enabled is affected by the curve in force at the time and
should be recomputed after any change to it.**

## 5a. Engine accuracy envelope

**Error budget (Nann & Riordan 1991 Fig. 12; methodology §13).** The post-bridge spectral
uncertainty is **σ ≈ 8 % across the visible** (≈5 % clear, ≈7 % overcast), rising to **~15 % in the
UV** and **~18 % at the 940 nm water band** — the known weak spot. Every CCT/mel-DER comparison in
these docs sits inside that envelope.

The SPECTRL2 direct beam is golden (<0.05 % vs the Fortran reference). Its residual diffuse blue bias is
**not** aerosol-tuning (an AOD sweep makes it worse) but the isotropic-diffuse-on-tilt geometry confound —
the §3 anisotropy wrapper and the §5 `K(λ)` target exactly this.

## 7. Status & honest bounds

- **Validated live:** all coefficients/corrections are pure-Python and tested live; the full suite is green
  (**1918 passed / 7 skipped**). Radiance/SMARTS/SKYSPECTRA-dependent paths are capability-gated.
- **η and `K(λ)` are empirical, and their fitting dataset is not published here.** Both are shipped
  defaults with a stated provenance, not results this repo can reproduce. η is constrained to the
  **interval η ∈ [0.19, 0.69]**, not a point. Never present either as a first-principles value.
- **`ASSUMED_UNCOATED_DOUBLE_VT = 0.80`** is a stated assumption a caller may override, not a measured
  transmittance; see the glazing honesty boundary in the methodology.
- **Out of scope:** engine internals, absolute-EDI validation, finer-MF `gensdaymtx`. ⚠️ **SEDES2 is
  no longer out of scope** — it ships as the opt-in `Sedes2Modifier` on tabulated coefficients
  (Whitaker & Newmiller 1998, NREL/SR-520-23942 Table 2-1) — see §2's note. It is **not validated**
  against any measured overcast figure here, and adopting it requires a re-run before any overcast
  number is re-quoted.
