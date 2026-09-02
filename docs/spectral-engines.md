# The spectral engines — what they are, and which ones you have to build

Four named pieces produce a spectral sky in this project. They are **not four interchangeable
alternatives**: two are clear-sky engines, one is a cloud modifier that runs *on top of* a clear-sky
engine, and one is a separate Radiance-native path with a different output contract. This page is the
map. It exists mainly to answer one recurring question — *"where is the build doc for SPECTRL2 and
SEDES?"* — whose answer is that **there isn't one, and there shouldn't be**: those two are pure Python
inside this repository and need no installation at all.

| Piece | Role | External? | Setup doc |
|---|---|---|---|
| **SPECTRL2** | clear-sky engine (default) | ❌ in-repo Python | *none needed — see [§1](#1-spectrl2--enginespectrl2)* |
| **SMARTS 2.9.5** | clear-sky engine (opt-in) | ✅ Fortran, NREL | [smarts-build.md](smarts-build.md) |
| **SEDES1 / SEDES2** | cloud modifier over a clear-sky engine | ❌ in-repo Python | *none needed — see [§3](#3-sedes1--sedes2--the-cloud-bridge-not-an-engine)* |
| **`gensdaymtx`** | Radiance-native spectral sky (separate contract) | ✅ C, LBNL | [radiance-6-build.md](radiance-6-build.md) |

**The rule this table encodes:** a build doc exists when, and only when, the model is implemented by a
program written by somebody else that you must obtain and compile. SPECTRL2 and SEDES are implemented
*here*, in this repository, in Python, and are exercised by this repository's own test suite. There is
no binary, no `$PATH` entry, no environment variable, and nothing that can be misconfigured.

---

## 0. How the pieces stack

A spectral sky record is built in two stages, and confusing them is the single most common misreading
of this subsystem:

```
      STAGE 1 — clear sky                    STAGE 2 — all sky
  ┌───────────────────────────┐        ┌──────────────────────────────┐
  │  SPECTRL2   (default)     │        │  energy rescale (ALWAYS on)  │
  │      or                   │  ───▶  │      ∫ = EPW DNI / DHI       │
  │  SMARTS     (opt-in)      │        │  + SEDES CCM (diffuse shape) │
  └───────────────────────────┘        └──────────────────────────────┘
        ClearSkySpectra                        the shipped record
        W·m⁻²·µm⁻¹, native grid                1 nm, 380–780, W·m⁻²·nm⁻¹
```

Stage 1 answers *what would the spectrum be under a cloudless sky with this atmosphere?* Both engines
answer it and nothing else — **SMARTS is clear-sky only, and so is SPECTRL2**. Stage 2 is what makes the
result an *actual* sky for an actual EPW hour: it forces the broadband integrals onto the EPW's measured
DNI/DHI, then reshapes the diffuse spectrum for cloud. Stage 2 runs identically whichever engine fed it.

So **SEDES is never a substitute for SPECTRL2 or SMARTS.** It is the layer after them.

The Radiance-native `gensdaymtx` path sits outside this diagram entirely — see [§4](#4-gensdaymtx--the-radiance-native-path).

---

## 1. SPECTRL2 — `engine="spectrl2"`

**Model.** The Bird & Riordan (1986) clear-sky spectral irradiance model — a faithful pure-Python
transcription of `spectrl2_2.c` (units=1), with the C constants carried over verbatim (Rayleigh
`1.3366`, uniform-gas `118.3`). Per-wavelength Beer–Lambert transmittances plus a single-pass diffuse
decomposition. Reference: Bird & Riordan 1986; SERI/TR-215-2436.

**Where.** [`src/hcl_core/spectral_engine/spectrl2.py`](../src/hcl_core/spectral_engine/spectrl2.py) —
about 100 lines. The 122-wavelength absorption table (extraterrestrial H₀ + H₂O / O₃ / uniform-mixed-gas
coefficients, generated from `SPCTRAL2_TAPE2.txt` and identical to the C `A[5][122]`) is a Python literal
in [`_spectrl2_data.py`](../src/hcl_core/spectral_engine/_spectrl2_data.py).

**Output.** `ClearSkySpectra` on the native 122-point grid spanning 300–4000 nm, in W·m⁻²·µm⁻¹.
Resampling to the project's 1 nm / 380–780 nm record is the resampler's job
(`hcl_core.spectral_sky`), never the engine's.

### Build / install

**None. There is nothing to build.** Concretely, the module:

- imports only `math` and its own data table — **no `numpy`, no `subprocess`, no file I/O**;
- reads **no** external data file at runtime (the table is inlined Python);
- consults **no** environment variable;
- has **no** capability gate — `resolve_engine("spectrl2")` is documented as *always available*.

If Python runs, SPECTRL2 runs. The project floor is `requires-python = ">=3.11"`. This is exactly why
it is the default engine, and why there is no `spectrl2-build.md` to go looking for.

**Verify** (this stands in for a "build check"):

```bash
cd hcl-mcp
uv run --extra dev pytest tests/test_spectrl2.py tests/test_spectrl2_data.py \
                        tests/test_spectrl2_aerosol_g.py -q
```

Nothing skips here for want of a binary — contrast SMARTS, where most of the suite is capability-gated.

### Tunables

Solar geometry is **passed in** (`SolarGeometry`); the engine has no native solar-position code. Aerosol
asymmetry `g` comes from `atm.aerosol_g` (formerly a `0.65` literal, now parameterized), and ground
albedo `atm.albedo` is applied grey across all six SPECTRL2 bands.

---

## 2. SMARTS 2.9.5 — `engine="smarts"`

**Model.** Gueymard's high-accuracy clear-sky spectral radiative-transfer code. The higher-fidelity
reference against which SPECTRL2 is cross-checked.

**Where.** Wrapper at [`src/hcl_core/spectral_engine/smarts.py`](../src/hcl_core/spectral_engine/smarts.py);
the model itself is an **external Fortran binary you must compile**.

### Build / install

**Required, and non-trivial.** → **[smarts-build.md](smarts-build.md)**

In brief, and only as a pointer to that doc: no SMARTS source or binary ships in this repository; you
obtain the 2.9.5 distribution from NREL; that distribution's prebuilt Mac executable is **PowerPC** and therefore dead on
any current Mac, so you compile from the Fortran source with `gfortran` after stripping CRLF line endings
and flipping `batch=.FALSE.` to `.TRUE.`; then you point `$SMARTSPATH` at the **executable file** — not
its directory.

> ⚠️ A set-but-wrong `$SMARTSPATH` is worse than an unset one. `resolve_engine("smarts")` raises early
> and distinguishes the two cases via `smarts_misconfigured()`, precisely so this fails loudly rather
> than silently degrading. See smarts-build.md.

**Verify:**

```bash
SMARTSPATH="$HOME/smarts/smarts295bat" uv run --extra dev pytest tests/test_smarts.py -q
```

Without a binary this suite **skips** rather than fails — which is the behavioural difference from
SPECTRL2 that the separate build doc exists to explain.

### Tunables

`aerosol="rural"` (default, the SMARTS `S&F_RURAL` model, a 17-card deck) or `aerosol="user"` (an 18-card
deck adding Card 8a for a settable Ångström α + asymmetry g). Selected through the MCP layer as
`smarts_aerosol="user"`. Full detail — including which knobs remain pinned (`IATMOS='USSA'`, OMEGL at a
fixed `0.95`) — is in smarts-build.md.

---

## 3. SEDES1 / SEDES2 — the cloud bridge, **not** an engine

This is the piece most likely to be misfiled, so state it plainly:

> **SEDES is not selectable as `engine=`.** `resolve_engine()` accepts exactly two names, `"spectrl2"`
> and `"smarts"`, and raises `ValueError` on anything else. SEDES is a *modifier* applied to whichever
> of those two ran.

**Where.** [`src/hcl_core/cloud_modifier.py`](../src/hcl_core/cloud_modifier.py), with coefficient tables
in [`_sedes1_data.py`](../src/hcl_core/_sedes1_data.py) (+ the committed `_sedes1_fig11.csv`) and
[`_sedes2_data.py`](../src/hcl_core/_sedes2_data.py). Local re-fitting lives in
[`sedes1_fit.py`](../src/hcl_core/sedes1_fit.py).

**What it does.** Two halves, and only the first is exact:

1. **Energy rescale — always on, engine-independent.** Grey-scales the clear-sky direct and diffuse so
   their broadband integrals over the full native range equal the EPW's DNI and DHI (SEDES1 Eq. 9
   neutral baseline). This half is arithmetic, and it is exact.
2. **Spectral CCM — the shape half.** Reshapes the *diffuse* spectrum by a cloud-cover modifier, then
   renormalizes back to DHI so the bridge invariant from half 1 survives. This half carries real
   uncertainty and is the honest caveat of the whole subsystem.

### SEDES1 (the shipped default)

`CCM(λ, Kt) = A(λ) + B(λ)·Kt + C(λ)·Kt²` — Nann & Riordan (1991), Eq. 11, driven by the clearness index
Kt. The A/B/C coefficients (and a per-λ regression σ) are a **faithful human-in-the-loop WebPlotDigitizer
digitization of the paper's Fig. 11** on a 10 nm grid over 330–1100 nm, because the paper plots those
curves and never tabulates them.

Four variants, via `cloud_variant=` on the MCP tools:

| `cloud_variant` | What it is |
|---|---|
| `reanchored` *(default; same as omitting)* | CCM reanchored to unity at clear Kt = 0.70 — a **pure** cloud term carrying no clear-sky bias of its own |
| `verbatim` | the faithful Fig. 11 CCM as published (also carries a clear-sky-bias correction) |
| `seed` | the legacy eyeballed 9-anchor seed — **over-blues the cloudy sky ~2×**, kept only for comparison |
| `local` | your own coefficients; requires `ccm_coeffs=<path to a fitted CSV>` |

For `local`, see **[recalibrating-cloud-ccm.md](recalibrating-cloud-ccm.md)** — that doc is the closest
thing SEDES has to a "setup" guide, and it is about *fitting your own data*, not installing anything.

### SEDES2 (opt-in, and a **model swap**)

`CCM(λ, NGH, z) = (A1 + A2/cos z) + (B1 + B2/cos z)·NGH + (C1 + C2/cos z)·NGH²` — the **tabulated** form
of the same regression, from Whitaker & Newmiller (1998), NREL/SR-520-23942, Table 2-1.

Do **not** read this as "SEDES1 with better numbers." Two structural differences make it a different
model, which is why it is a separate class rather than a variant:

1. **Six coefficients with a 1/cos(z) zenith term.** The three-term form cannot express this; there, the
   zenith dependence is absorbed into A/B/C.
2. **The independent variable is NGH, not Kt.** NGH is measured GHI ÷ *estimated clear-sky* GHI; Kt
   divides by the *extraterrestrial* horizontal. Under clear sky NGH → 1 while Kt → ~0.7, so **they are
   not interchangeable even approximately.**

> 🚨 `Sedes2Modifier` is **not reachable via `cloud_variant`** — nothing in `src/` constructs it; it is
> injected as `modifier=`. And without a `clear_ghi` reference (which `build_record` does **not** pass)
> it silently takes a grey, un-reshaped path rather than raising. **Check `ccm_applied` before quoting
> any overcast number as SEDES2-derived.**

### Build / install

**None, for either.** Pure Python plus one committed CSV that ships in the package. No binary, no
environment variable, no external download. The one *optional* step is supplying your own fitted
coefficients for `cloud_variant="local"`.

**Verify:**

```bash
cd hcl-mcp
uv run --extra dev pytest tests/test_cloud_modifier.py tests/test_sedes1_data.py \
                        tests/test_sedes1_fit.py tests/test_sedes2.py \
                        tests/test_server_cloud_variant.py -q
```

`tests/test_sedes2.py` pins the transcribed table against the primary PDF and asserts the committed CSV
and the shipped module cannot drift apart.

---

## 4. `gensdaymtx` — the Radiance-native path

**Not part of the `resolve_engine()` family, deliberately.** It has a different output contract — a band
matrix, not a 1 nm record — and its own MCP tool (`spectral_sky_native`).

**Model.** Perez 1990/1993 sky plus an OPAC continental aerosol spectral shape, on a 20-band uniform
380–780 nm grid (NCOMP = 20).

### Build / install

**Required.** → **[radiance-6-build.md](radiance-6-build.md)**. One Radiance 6.1a build yields both the
classic daylight/electric/glare pipeline and the spectral tools. Note the runtime requirement that
`RAYPATH` reach `mie_ca.dat`, or `gensdaymtx` aborts at startup.

---

## Choosing

- **Default to SPECTRL2.** Zero setup, and within ~7 % of SMARTS for most HCL work.
- **Reach for SMARTS** when you want the higher-fidelity clear-sky reference and are willing to build it.
- **You do not choose SEDES** — the cloud bridge runs either way. You choose its *variant*, and the
  default is the right one unless you are recalibrating against measured spectra.
- **`gensdaymtx`** when you want Radiance's own native spectral sky rather than this pipeline's record.

## Deeper reading

| Topic | Doc |
|---|---|
| Full model derivations, provenance, honesty flags | [hcl-methodology.md](hcl-methodology.md) §9.4a |
| Spectral-sky design history, the Fig. 11 digitization investigation, SEDES2 discovery | [spectral-sky-methodology.md](spectral-sky-methodology.md) §8 |
| Module-by-module as-built record | [spectral-sky-as-built.md](spectral-sky-as-built.md) |
| Fitting your own CCM coefficients | [recalibrating-cloud-ccm.md](recalibrating-cloud-ccm.md) |
| Literature provenance per model element | [literature-bibliography.md](literature-bibliography.md) |
