# Building Radiance 6.1a — the one Radiance version (full toolset)

Radiance is an **external dependency — no Radiance source or binary is included in this repository**.
Obtain RADIANCE 6.1a from <https://www.radiance-online.org/> (the build these notes were written against
is commit `39b99660`; confirm the version via `src/rt/VERSION` in the unpacked tree). **6.1a is a
superset**: one build yields BOTH the classic daylight / electric / glare pipeline AND the native
spectral tools. This is the single Radiance the project requires — it satisfies the old `≥ 5.4` floor and
the `gensdaymtx` 6.x path at once.

## Build (macOS / Linux, CMake) — FULL toolset

Run these from inside the unpacked Radiance source tree:

```
mkdir build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=$HOME/radiance6
make                # ALL targets — not just the spectral subset
make install
```

This installs the full classic pipeline AND the spectral tools from one tree. `discover.py`'s `_REQUIRED` —
the set `radiance_status()` reports as found/missing — is exactly the **17 binaries** `oconv rtrace rpict pcomb gendaylit gendaymtx rfluxmtx dctimestep rcontrib pfilt pvalue getinfo falsecolor epw2wea obj2rad xform ies2rad`, and a full `make install` provides all
of them, so `missing` goes empty. `ies2rad` (electric) and `obj2rad`/`xform` (OBJ import) are now part of that set; `evalglare` (glare) is NOT in `_REQUIRED` — it
is still needed (by the glare path, discovered separately from `ies_radiance.py`) and a plain `make` builds it too. The
spectral set is `gensdaymtx rcomb rmtxop`. (The GUI tools need libtiff/Qt/X11 and are OFF by default; the HCL
pipeline does not use them.)

> **Models implemented by the Radiance binaries built here** (`external-standard` — model lives in Radiance;
> not recomputed in Python):
>
> - `gendaylit` / `gendaymtx` — Perez et al. 1990/1993 all-weather sky luminance/radiance model
>   (*Sol. Energy* **44**:271 / Perez 1993 adaptation).
> - `gendaymtx -m` — Reinhart/Tregenza sky-vault patch discretization (Reinhart 2001 MF subdivisions
>   of Tregenza 1987 dome; 145 patches at MF:1, 5185 at MF:6).
> - `gensdaymtx` — Perez 1990/1993 sky + OPAC continental aerosol spectral shape (20-band NCOMP=20
>   uniform 380–780 nm grid).

> If you only need the spectral path, the minimal subset still builds:
> `make rtrad gensdaymtx rcomb rtrace rcontrib rmtxop dctimestep`. For the adoption (one Radiance for
> everything) build the full toolset above.

## Build (Windows)

Use the official 6.x release binaries from
[github.com/LBNL-ETA/Radiance/releases](https://github.com/LBNL-ETA/Radiance/releases), or build from the
LBNL source with Visual Studio Build Tools (C++ workload → MSVC) + CMake + Git: open a Developer prompt,
`cmake .. -G "NMake Makefiles" -DCMAKE_INSTALL_PREFIX=C:\radiance6`, `nmake`, `nmake install`. Add
`C:\radiance6\bin` to **PATH** and set **RAYPATH** to `C:\radiance6\lib`.

## Runtime setup (REQUIRED)

- Put the install `bin` on `PATH` **ahead of any old Radiance**: `export PATH=$HOME/radiance6/bin:$PATH`
  (or point `HCL_RADIANCE_BIN` at the `bin` dir instead of editing PATH — `discover.py` checks it first).
- `gensdaymtx` needs `mie_ca.dat` reachable on `RAYPATH`, else it aborts at startup:
  `export RAYPATH=.:$HOME/radiance6/lib`
- First `gensdaymtx` run precomputes per-AOD atmosphere tables (slow; parallelize with `-n`).
- **A full-year EPW is many minutes of CPU.** `gensdaymtx` processes *every* hour of the weather tape, so an
  8760-hour annual file at `mf=1`, NCOMP=20 runs ≈10+ min. The `spectral_sky_native` MCP tool therefore takes a
  `timeout` param (default **`None` = no cap**) and returns a graceful `{timed_out:True}` on expiry instead of
  crashing — trim the EPW to the hours you need for a fast point-in-time sky. (See `spectral-sky-as-built.md`
  §3.27/D-29.)

## Notes

- Use only implemented flags (`-m -d -s -g -n -r -u -i -p -o -v -h`); the usage string lists `-c/-O/-A/-D/-M`
  which are NOT parsed and abort the run.
- Atmosphere: broadband AOD + cloud cover are read from the EPW; aerosol *spectral shape* (OPAC continental)
  + water vapor/ozone are fixed — physically richer than D-series templates, not SMARTS-grade site tuning.
- The matrix `WAVELENGTH_SPLITS` header is the legacy 4-value RGB partition (`780 588 480 380`, color.c:94),
  NOT band edges. The 20 native bins (NCOMP=NSSAMP=20) are a UNIFORM 380–780nm @20nm grid (atmos.c:169) — which
  equals the Phase-5 nominal `BAND_EDGES_20`. Use `spectral_native.reconcile_to_native_bands(values_401, ncomp)`
  to re-bin onto that NCOMP-derived uniform grid for Track-C interop; for ncomp=20 it reproduces `band_average`
  exactly, so reconciliation confirms (not corrects) the nominal grid. (spec §8, §11 #9 — the feared gap does not exist.)
