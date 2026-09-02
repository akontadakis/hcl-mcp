# Building SMARTS 2.9.5 — the spectral radiative-transfer oracle (`engine="smarts"`)

SMARTS 2.9.5 (Gueymard) is the high-accuracy clear-sky spectral engine behind `engine="smarts"` on
`spectral_sky_from_epw` / `spectral_epw` / `annual_nvrd(physical_sky=True)`. It is **opt-in and
capability-gated**: the pure-Python `engine="spectrl2"` default needs nothing, and SMARTS is only invoked
when you select it AND `$SMARTSPATH` points at a runnable `smarts295bat` binary.

> **First live-validated 2026-06-21.** Before this, the SMARTS path was *wired but never run against a real
> binary*. The NREL distribution's prebuilt Mac binary is **PowerPC** (`Mach-O executable ppc`) — dead on Apple
> Silicon and modern Intel macOS (no Rosetta for PPC) — so SMARTS has to be **compiled from that distribution's
> Fortran source**. Once built (steps below) and `$SMARTSPATH` is set, the repo's own gated cross-check
> (`tests/test_smarts.py::test_smarts_cross_check_clear_sky`, SMARTS vs the Python SPECTRL2 engine) runs and
> passes, and the three-engine comparison in [`spectral-engine-comparison.md`](spectral-engine-comparison.md)
> reproduces. This is a *first validation*, not a calibrated baseline.

---

## Source

SMARTS is an **external dependency — no SMARTS source or binary is included in this repository**. Obtain
the SMARTS 2.9.5 distribution from NREL (<https://www.nrel.gov/grid/solar-resource/smarts.html>); Mac and
Linux archives are offered separately. Both carry the Fortran source (`Source_code/smarts295.f`) plus the
ancillary data trees (`Gases/`, `Albedo/`, `Solar/`, `CIE_data/`) the engine reads at runtime. The Mac
archive **ships no usable executable for arm64/x86_64 macOS** — build it yourself.

## Build (macOS arm64 / Intel, with `gfortran`)

Prereq: a Fortran compiler. `gfortran` ships with Homebrew GCC:

```bash
brew install gcc          # provides gfortran (e.g. /opt/homebrew/bin/gfortran)
```

Then extract, fix the source, and compile. Two source edits are required:

1. **Strip CRLF** — the bundled `.f` has classic-Mac `CRLF` line endings that confuse some toolchains.
2. **Enable batch mode** — `smarts295.f` ships with `batch=.FALSE.` (interactive prompts). The wrapper drives
   SMARTS non-interactively by writing `smarts295.inp.txt` into the run dir, so the binary **must** be built
   with `batch=.TRUE.` (else it blocks on stdin and the wrapper's 120 s subprocess timeout fires).

```bash
# from a scratch dir — SMARTS_295_Mac.tar.gz is the archive you downloaded from NREL.
# No SMARTS archive ships in this repository; there is no `hcl-mcp/Software/` directory.
tar xzf /ABSOLUTE/PATH/TO/YOUR/DOWNLOAD/SMARTS_295_Mac.tar.gz
cd SMARTS_295_Mac/Source_code

# 1. strip CRLF  2. flip batch=.FALSE. -> .TRUE.
LC_ALL=C perl -pe 's/\r$//' smarts295.f > smarts295_lf.f
LC_ALL=C perl -i -pe 's/^       batch=\.FALSE\./       batch=.TRUE./; s/^c       batch=\.TRUE\./c       batch=.FALSE./' smarts295_lf.f

# 3. compile (fixed-form F77; -std=legacy tolerates the legacy extensions)
gfortran -std=legacy -ffixed-line-length-132 -w -o ../smarts295bat smarts295_lf.f
file ../smarts295bat        # -> Mach-O 64-bit executable arm64
```

The binary **must stay beside its data trees** (`Gases/`, `Albedo/`, `Solar/`, `CIE_data/`) — SMARTS opens
them by relative path. The engine wrapper (`hcl_core/spectral_engine/smarts.py`) symlinks those sibling dirs
into a fresh temp run dir per call, so the binary only needs to live *inside* the unpacked `SMARTS_295_Mac/`
tree.

## Install & configure

Keep the whole unpacked tree (binary + data dirs) somewhere stable and point `$SMARTSPATH` at the binary:

```bash
# e.g. install under $HOME (or /usr/local/smarts if you have write access there)
cp -R SMARTS_295_Mac "$HOME/smarts"            # binary + Gases/ Albedo/ Solar/ CIE_data/
export SMARTSPATH="$HOME/smarts/smarts295bat"  # add to ~/.zshrc to persist
```

`$SMARTSPATH` must name the **executable file** (not the directory) — `smarts_available()` checks
`os.path.isfile(SMARTSPATH) and os.access(..., X_OK)`.

> On Apple Silicon the build above produces a native arm64 binary, so no Rosetta is needed. The PowerPC
> `smarts295bat` that NREL ships inside the archive is **not** usable — overwrite it with your build (the steps above write
> to `../smarts295bat`, replacing it in the tree).

## Verify

```bash
# the gated SMARTS tests now run (were skipped without a binary):
SMARTSPATH="$HOME/smarts/smarts295bat" \
  uv run --extra dev pytest tests/test_smarts.py -q
# test_smarts_cross_check_clear_sky + test_compute_returns_um_units_and_visible_band should PASS;
# test_compute_raises_without_binary SKIPS (it only runs when SMARTSPATH is unset).

# and the three-engine comparison reproduces (internal harness, not shipped —
# see "Reproducing the three-engine comparison" below):
SMARTSPATH="$HOME/smarts/smarts295bat" RAYPATH=".:/usr/local/radiance/lib" \
  PYTHONPATH=src python compare_three_engines.py
```

### Reproducing the three-engine comparison

`compare_three_engines.py` is part of an internal analysis harness that is **not included in this
repository** — it was untracked when the published tree was restricted to the shipping subset. The
comparison it performs is reproducible from the shipped code alone. Note that `resolve_engine()` accepts
only **two** names — `spectrl2` and `smarts` (`sedes` is a *cloud modifier* applied on top of a clear-sky
engine, not an engine you can resolve; see [spectral-engines.md](spectral-engines.md)). The third arm of
the comparison is the Radiance-native `gensdaymtx` path, which has its own tool and output contract.
Resolve each clear-sky engine via `resolve_engine()` and call `.compute(atm, geo)` on the same
`AtmosphereState` / geometry pair, then compare the returned spectral direct-normal and
diffuse-horizontal arrays band-by-band. The environment variables above are what the harness needs:
`SMARTSPATH` pointing at the **binary file** (not its directory) and `RAYPATH` for the Radiance
library.

## How the engine is invoked

`SmartsEngine.compute(atm, geo)` ([`hcl_core/spectral_engine/smarts.py`](../src/hcl_core/spectral_engine/smarts.py)):
builds a SMARTS deck (`build_deck`) for spectral direct-normal + diffuse-horizontal over 280–4000 nm
(IOUT 2/3), writes `smarts295.inp.txt` into a fresh temp dir with the data trees symlinked in, runs the binary
there (`subprocess.run([SMARTSPATH], cwd=run_dir, timeout=120)`), and parses `smarts295.ext.txt`
(`parse_ext_output`). Output is W·m⁻²·nm⁻¹, scaled ×1000 to the engine-uniform W·m⁻²·µm⁻¹ the resampler
expects. By **default** (`aerosol="rural"`, the SMARTS `S&F_RURAL` model) the deck is **17 cards** and the
Ångström exponent is **not** settable — it comes from the aerosol model itself (documented fidelity note in
`build_deck`); this default path is byte-identical to before this refinement.

### Settable Ångström α + asymmetry g (`aerosol="user"`, D-20, opt-in)

`build_deck(atm, geo, *, aerosol="rural")` also accepts `aerosol="user"`, and `SmartsEngine(aerosol="user")`
(or the `smarts_aerosol="user"` argument on the `spectral_sky_from_epw`/`spectral_epw` MCP tools, threaded via
`resolve_engine(engine, smarts_aerosol=...)`) selects it. Instead of the fixed `'S&F_RURAL' !Card 8 AEROS`
line, the deck emits:

```
'USER'                       !Card 8 AEROS
<alpha> <alpha> 0.95 <g>     !Card 8a ALPHA1 ALPHA2 OMEGL GG
```

where `<alpha>` is `atm.angstrom_alpha` (used for both ALPHA1 and ALPHA2 — no separate fine/coarse-mode split
is modeled) and `<g>` is `atm.aerosol_g` (default 0.65). OMEGL (single-scattering albedo) is a fixed `0.95`
literal, not currently derived from `atm` — a possible future seam if OMEGL needs to be settable too. Card 8a
is inserted immediately after Card 8 and before Card 9 (ITURB), so the deck becomes **18 cards** — everything
downstream (`parse_ext_output`, the ×1000 unit scale) is unaffected, since the deck is write-only input to the
binary.

A live smoke check (`$SMARTSPATH` set, not a persisted test) ran `SmartsEngine(aerosol="user").compute()` at
α=0.5 and α=2.0 for the same atmosphere/geometry (Athens, 21 Jun solar noon, AOD@500=0.2, g=0.65): direct-normal
output increased monotonically with α (≈5% ratio between the two bounds), and a `rural` (`S&F_RURAL`) run on
the same atmosphere landed between the two `user` bounds, as expected. This confirms Card 8a is actually
consumed by the SMARTS binary, not just generated — it is a smoke check, not a calibrated validation.

## Caveats

- **First validation, not a baseline.** SMARTS agrees with the Python SPECTRL2 engine to ~2 % (direct) / ~7 %
  (diffuse) in the visible with shape correlation r≈0.99 on a clear Athens hour
  (see [`spectral-engine-comparison.md`](spectral-engine-comparison.md)). That cross-validates the deck/parse
  plumbing; it does **not** calibrate SMARTS against measured sky spectra.
- **Clear-sky only.** SMARTS computes clear-sky spectra; the production pipeline still applies the SEDES1 cloud
  bridge (energy-rescale to EPW DNI/DHI + CCM) on top, exactly as for SPECTRL2 (the `cloud_variant`/`ccm_coeffs`
  CCM selection — including a locally re-fitted CCM — applies regardless of which clear-sky engine feeds it).
- **The deck pins `IATMOS='USSA'`.** The aerosol model is now selectable — `S&F_RURAL` (default, byte-identical)
  or `aerosol="user"`/`smarts_aerosol="user"` (resolved opt-in, D-20) for a settable Ångström α + asymmetry g,
  per "Settable Ångström α + asymmetry g" above. Site tuning of the reference atmosphere (`IATMOS='USSA'`) and
  OMEGL (fixed `0.95`) beyond EPW-derived AOD/PWV/ozone is still not exposed. For most HCL work SPECTRL2
  (default) is within ~7 % of SMARTS; reach for SMARTS when you want the higher-fidelity reference.
