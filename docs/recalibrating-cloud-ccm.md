# Recalibrating the SEDES1 cloud CCM from your own measurements

> **Companion to:** [`spectral-sky-methodology.md`](spectral-sky-methodology.md) §8.3/§8.6 (the CCM, its
> fidelity caveats, and how `ccm_sigma` is surfaced in provenance). Read that section first for the physics;
> this document is the practical how-to for fitting your own coefficients.

## Why you would do this

The shipped SEDES1 cloud-cover modifier `CCM(λ,Kt) = A(λ) + B(λ)·Kt + C(λ)·Kt²` (`reanchored` default,
`verbatim`, `seed`) is digitized from Nann & Riordan 1991's Fig. 10/11 — a German site (Stuttgart), a single
aerosol regime (AOD₅₀₀ = 0.23), a global-horizontal (not pure-diffuse) fit, and a season-merged regression.
If you have your own measured diffuse spectra for a site, you can re-fit `A,B,C` (and their regression
uncertainty `σ`) directly against that data and use the result in place of the shipped coefficients. This
closes the *site-transfer* caveats (fit is Germany-only / single-AOD / global-fit-on-diffuse / season-merged)
— it does **not** close the caveats that are structural to the CCM's functional form (Kt-only, no PWV term;
partial absorption of clear-sky-engine bias). See the caveat-by-caveat status table in
[`spectral-sky-methodology.md` §8.3](spectral-sky-methodology.md#83-the-cloud-cover-modifier-ccmλ-kt) for
which is which.

> **⚠️ Before you fit: check whether you actually need to.** Two of the caveats above have a second escape
> route that needs no measurements at all. The digitisation is **avoidable** — the same Nann & Riordan
> regression is **tabulated** in Whitaker & Newmiller (1998), NREL/SR-520-23942 Table 2-1 (74 rows,
> 320–1050 nm at 10 nm, free), and ships opt-in as `Sedes2Modifier`. That form additionally carries a
> **1/cos z zenith term** the three-term SEDES1 quadratic cannot express. See
> [`spectral-sky-methodology.md` §8.6(f)](spectral-sky-methodology.md).
>
> **Which to choose.** SEDES2 is still a **German-site fit** — it closes the *digitisation* and *zenith*
> caveats but **not** site transfer. A local fit is the only route that closes site transfer, so if you have
> your own measured spectra for your own site, this document is still the one you want. ⚠️ SEDES2 is a **model
> swap, not a drop-in**: its independent variable is **NGH** (measured GHI over *estimated clear-sky* GHI),
> not the clearness index `Kt` this how-to fits against, so the `Kt` values from Step 1 **cannot** be fed to
> it — under clear sky NGH → 1 while `Kt` → ~0.7. `Sedes2Modifier.apply` refuses to run without a clear-sky
> GHI reference rather than evaluating on the wrong variable. ⚠️ It is also **not reachable through the
> `cloud_variant` argument used in Step 3** — that accepts only the four SEDES1 variants — so SEDES2 means
> constructing the class directly in Python, not a parameter change to the calls below.

## What you need

For each measurement hour you want to fit against:

1. **A measured diffuse spectral power distribution (SPD)** — spectral sky-diffuse irradiance across some
   wavelength range, as a list of values aligned to a common wavelength grid. Relative-shape SPDs are fine —
   `fit_ccm` normalizes each spectrum by its own sum before taking a ratio, so absolute calibration is not
   required.
2. **The clear-sky reference diffuse shape at that same hour** — the diffuse spectrum the pipeline's clear-sky
   engine would have produced (SPECTRL2 or SMARTS) for that hour's atmosphere and solar geometry, *before* any
   cloud modifier is applied, on the same wavelength grid as your measurement. This is what the CCM's ratio is
   taken against (`(measured shape) / (clear-sky shape)`).
3. **The clearness index `Kt`** for that hour — `Kt = GHI / (I0_normal · cos(zenith))`, clamped to `[0, 1.2]`
   (`hcl_core.cloud_modifier.clearness_index`). If you have broadband GHI and solar geometry for the hour you
   can compute this directly, or read the pipeline's own `Kt` for that EPW hour from a
   `spectral_sky_from_epw` call's `broadband.clearness_kt` field if the hour lines up with an EPW record
   you're already using. (`atmosphere_from_epw` returns only the atmospheric state — it carries no
   `broadband` block, so it cannot supply `Kt`.)

To get (2) for an EPW-anchored hour without re-deriving atmosphere/geometry by hand, call the same building
blocks the pipeline itself uses:

```python
from hcl_core import atmosphere, solpos, epw_hourly
from hcl_core.spectral_engine import resolve_engine
from hcl_core.epw_location import parse_epw_location

loc = parse_epw_location("mysite.epw")                      # {"latitude", "longitude", "time_zone"}
rows = epw_hourly.parse_epw_hourly("mysite.epw")             # list of per-row dicts
row = epw_hourly.row_for(rows, month=6, day=15, hour=13)     # hour is EPW hour-ENDING (1-24)

geo = solpos.compute(month=row["month"], day=row["day"], hour=row["hour"] - 0.5,   # mid-interval
                      latitude=loc["latitude"], longitude=loc["longitude"],
                      time_zone=loc["time_zone"])
atm = atmosphere.derive(row)
clear = resolve_engine("spectrl2").compute(atm, geo)   # ClearSkySpectra: .wavelength_nm, .sky_diffuse_horizontal
```

`clear.sky_diffuse_horizontal` on `clear.wavelength_nm` (native µm-grid wavelengths, in nm) is the reference
clear-sky diffuse shape for that hour — interpolate it (or your measured SPD) onto a common wavelength grid
before fitting.

## Step 1 — assemble aligned arrays

Build three parallel lists, one entry per measurement hour, all on the same `wavelength_nm` grid:

- `spectra[i]` — your measured diffuse SPD for hour `i` (a list of values at each wavelength in
  `wavelength_nm`)
- `reference_shapes[i]` — the clear-sky diffuse shape for hour `i` (same grid)
- `kt_values[i]` — the clearness index for hour `i`

```python
wavelength_nm = [380 + 10 * k for k in range(41)]   # e.g. 380..780 @10nm; pick a grid matching your data
spectra = [...]            # list of lists, one per measured hour
reference_shapes = [...]   # list of lists, one per measured hour (same grid, from the clear-sky engine)
kt_values = [...]          # one Kt per measured hour
```

## Step 2 — fit

```python
from hcl_core.sedes1_fit import fit_ccm, write_ccm_csv

fit = fit_ccm(spectra, kt_values, reference_shapes, wavelength_nm)
write_ccm_csv("my_site_ccm.csv", fit)
```

`fit_ccm` runs, independently at each wavelength, a per-λ least-squares quadratic
`(shape-ratio) = A + B·Kt + C·Kt²` over all your measurement hours (pure-Python normal equations, no
dependency beyond the standard library), and reports the regression's standard error `sigma` at each
wavelength alongside `A, B, C`. Wavelengths with fewer than 3 usable points (after dropping any hour where a
spectrum sums to zero/negative) fall back to the pass-through `(A, B, C, sigma) = (1, 0, 0, 0)` — i.e. "no
cloud effect, no fit" rather than a fabricated extrapolation.

`write_ccm_csv` writes a CSV with header `wavelength_nm,A,B,C,sigma` (plus a leading `#`-commented
description line) — the same schema `Sedes1Modifier`'s shipped coefficient tables use internally, and the
schema `load_ccm_csv` expects back.

## Step 3 — use it

Pass the fitted CSV to `spectral_sky_from_epw` (or `spectral_epw`) with `cloud_variant='local'`:

```python
spectral_sky_from_epw(
    epw="mysite.epw", month=6, day=15, hour=13,
    cloud_variant="local",
    ccm_coeffs="my_site_ccm.csv",
)
```

Internally this loads your CSV via `hcl_core.sedes1_fit.load_ccm_csv` (linear-interpolated per wavelength,
clamped to `(A,B,C)=(1,0,0)`/`σ=0` outside your fitted wavelength range) and constructs
`Sedes1Modifier(variant="local", coeffs=..., sigma=...)`. Every other tool argument (`engine`,
`surface_tilt_deg`, `ozone_mode`, etc.) behaves exactly as documented for the default path — `cloud_variant`
only swaps which `A,B,C,σ` feed the diffuse reshape step.

`ccm_coeffs` is required (and only meaningful) when `cloud_variant='local'`; omitting `cloud_variant`
entirely, or passing `'reanchored'`, `'verbatim'`, or `'seed'`, uses the shipped coefficients and ignores
`ccm_coeffs`. The pipeline default — omitting `cloud_variant` — is byte-identical to before this feature
existed.

## Reading `ccm_sigma` in the output

Every `Sedes1Modifier` variant — shipped or local — now emits per-hour `ccm_sigma` (a small dict sampled at
{400, 500, 600, 700} nm) and `ccm_sigma_mean` in the record's `provenance`. For `cloud_variant='local'` these
are *your* regression's standard errors, carried straight through from the `sigma` column you wrote in Step 2
via `load_ccm_csv`.

> ⚠️ **Direct Python callers: pass `sigma=` explicitly.** `Sedes1Modifier.__init__` does
> `self._sigma_fn = sigma or ccm_sigma` (`hcl_core/cloud_modifier.py:108`), so a `Sedes1Modifier(variant="local",
> coeffs=…)` constructed **without** `sigma=` silently reports the **shipped Fig. 11** regression σ alongside
> your locally-fitted `A,B,C` — a provenance mismatch, since the σ then describes a different fit than the
> coefficients do. The MCP path (`cloud_variant="local"` + `ccm_coeffs=`) always passes both, because
> `load_ccm_csv` reads the `sigma` column you wrote in Step 2; this only bites callers constructing the class
> directly in Python.

**A wide `ccm_sigma` is an honest result, not a bug.** If your measured dataset is small, or spans a narrow
range of `Kt` (e.g. mostly-clear or mostly-overcast hours, with few points in between), the per-wavelength
quadratic fit is poorly constrained and `sigma` will be large — that is the fit correctly reporting that it
doesn't have enough information to pin down `A,B,C` tightly, not a defect in `fit_ccm`. Treat a large
`ccm_sigma`/`ccm_sigma_mean` as a signal to gather more measurements (ideally spanning the full `Kt` range
from overcast to clear) before trusting the local CCM's shape at that wavelength, rather than as something to
silence or work around.

## A worked example exists, but stands separately

An illustrative site-specific fitting script exists alongside a private validation dataset **outside
this repository**. That script and its data are **not required** to follow this how-to — everything above is self-contained using
only the public `hcl_core.sedes1_fit` API, `hcl_core.atmosphere`/`solpos`/`spectral_engine` for building the
clear-sky reference shape, and your own measured data. If you do have a directly comparable dataset (measured
diffuse SPDs with known clock hours and coincident broadband GHI), the workflow is exactly Steps 1–3 above:
compute `Kt` per hour, get the clear-sky reference shape per hour, `fit_ccm`, `write_ccm_csv`, then pass
`cloud_variant='local'` + `ccm_coeffs=<your CSV>`.

One lesson worth carrying over: **relative (non-absolute-calibrated) measured SPDs are sufficient**
for this workflow, because `fit_ccm` only ever uses shape ratios (each spectrum normalized by its own sum,
`sedes1_fit.py:63-66`) — you do not need an absolutely-calibrated spectroradiometer. This is a property of
the **fit**, not of any particular dataset, and it holds whatever you feed it. An absolute scale that is
self-consistent but not traceable therefore costs this workflow nothing, precisely because the fit is
scale-invariant.

What you do need is a **`Kt` range wide enough to constrain the quadratic** — a dataset concentrated at
high `Kt` (mostly clear/thin-cloud hours), with few or no thick-overcast (low-`Kt`) hours, will fit but will
report wide `σ` at exactly the wavelengths and `Kt` regimes it under-samples. That is the expected, honest
behavior described above, not a reason to avoid recalibrating — a wide-`σ` local fit with real site data is
still more informative (and auditable) than silently trusting the shipped Germany/AOD₅₀₀=0.23 coefficients
for a site they were never fit to.
