# Installing the external engines — one checklist, then verify

**Read this file, then execute it.** It is written to be followed top-to-bottom by an agent or a
person. Every step ends in a **check** with an expected output. If a check fails, **stop at that
step** and fix it before moving on — a half-installed engine fails later, deep inside a simulation.

> **`hcl-mcp` bundles nothing.** No Radiance, no Daysim, no SMARTS — no binaries **and no source**.
> There is no `Software/` directory in this repository. Every engine below is downloaded from its own
> upstream and built or installed on your machine. The pure-Python spectral core needs none of them.

| Engine | Needed for | Skip it if | Full build doc |
|---|---|---|---|
| **Radiance 6.1a** | daylight, electric, glare, annual, native spectral sky | you only want the pure-Python spectral core (the tools then *emit* their command plans) | [radiance-6-build.md](radiance-6-build.md) |
| **Daysim** | sub-hourly weather, live `annual_nvrd` alertness transport | you do not run `annual_nvrd` / `generate_subhourly_wea` | — (built by the `build_daysim` tool) |
| **SMARTS 2.9.5** | `engine="smarts"` only | you use the default `engine="spectrl2"` (pure Python, always runs) | [smarts-build.md](smarts-build.md) |

Install order: **Radiance → Daysim → SMARTS**. Radiance unlocks the most tools; SMARTS the fewest.

---

## Step 0 — Prerequisites and baseline

```bash
uv --version                 # required: the Python runner
cmake --version              # required for Radiance and Daysim
git --version                # required for Daysim
gfortran --version           # required for SMARTS only
```

macOS: `xcode-select --install && brew install cmake git gcc` (Homebrew `gcc` provides `gfortran`).
Debian/Ubuntu: `sudo apt install build-essential cmake git gfortran`.
Windows: Visual Studio Build Tools (C++ workload), CMake, and Git.

**Check — the baseline, before any engine:**

```bash
cd hcl-mcp
uv sync --extra dev
uv run --extra dev pytest -q
```

Expected: **green, zero failures — with no engine installed at all.** On a bare machine that is
~1875 passed / 51 skipped; on a machine that already has Radiance, ~1919 passed / 7 skipped. The
difference is only how many engine-gated tests run rather than skip. **A skip is not a failure.**

**Any failure here is the Python install, not a missing engine — fix it before Step 1.**

---

## Step 1 — Radiance 6.1a

### 1.1 Get it

Two routes. Both give a usable 6.x. **6.1a is a superset** — one install covers the classic
daylight / electric / glare pipeline *and* the native spectral `gensdaymtx`.

- **Official release (fastest):** <https://github.com/LBNL-ETA/Radiance/releases> — pick a **6.x**
  build for your OS. An older `≥ 5.4` release covers only the classic pipeline and has **no**
  `gensdaymtx`.
- **From source (what these docs were written against):** get the 6.1a source from
  <https://www.radiance-online.org/>, then build the **full toolset**, not the spectral subset.

### 1.2 Build (source route, macOS / Linux)

From inside the unpacked Radiance source tree:

```bash
mkdir build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=$HOME/radiance6
make                 # ALL targets
make install
```

Windows: `cmake .. -G "NMake Makefiles" -DCMAKE_INSTALL_PREFIX=C:\radiance6`, then `nmake`,
`nmake install`.

On a downloaded macOS release, clear Gatekeeper quarantine before first run:
`xattr -dr com.apple.quarantine /usr/local/radiance`.

### 1.3 Set the environment

```bash
export PATH="$HOME/radiance6/bin:$PATH"      # must come BEFORE any older Radiance
export RAYPATH=".:$HOME/radiance6/lib"       # gensdaymtx aborts at startup without mie_ca.dat
```

Put both in `~/.zshrc` (or the MCP client's `env` block). Instead of editing `PATH`, you may point
`HCL_RADIANCE_BIN` at the `bin` directory — `discover.py` checks it first.

### 1.4 Check

```bash
rtrace -version                              # expect: RADIANCE 6.1a ... LBNL
which gensdaymtx rcomb rmtxop evalglare      # expect: four paths, all under your install

RAD_LIB="$(dirname "$(dirname "$(command -v rtrace)")")/lib"   # or "${RAYPATH##*:}"
ls "$RAD_LIB/mie_ca.dat" "$RAD_LIB/reinsrc.cal" "$RAD_LIB/reinhartb.cal" "$RAD_LIB/reinhart.cal"
```

> **The `which` line is not optional.** `radiance_status()` probes a fixed 17-binary set that
> contains `gendaymtx` but **not** `gensdaymtx`, `rcomb`, `rmtxop` or `evalglare`. So
> `missing: []` does **not** prove the spectral tools or the glare tool exist — only this `which`
> does. `gensdaymtx`/`rcomb`/`rmtxop` come from a full `make`; `evalglare` is discovered separately
> by name from `ies_radiance.py`, so it must be on `PATH`.

`reinsrc.cal` / `reinhartb.cal` / `reinhart.cal` drive the annual Reinhart path. If any is missing,
annual tools degrade to an honest emit envelope instead of running. Some 6.1a builds ship
`reinhart`/`reinhartb` but not `reinsrc.cal` — copy it into the Radiance `lib` directory from a
Daysim checkout if yours omits it.

Then, through the MCP server:

```
radiance_status()
```

Expect `{"available": true, "missing": [], "version": "RADIANCE 6.1a ..."}`. Note that `available`
keys only off `oconv` + `rtrace`, so **read `missing`, not `available`** — `available: true` with a
non-empty `missing` is a partial install.

> ⚠️ **Also read `source_cal.a1_honored` in that same result.** `false` means this Radiance build
> drops the `ies2rad` A1 candela-scale multiplier: **every IES luminaire under-emits** and glare
> collapses toward zero. The factor differs per luminaire, so results cannot be rescaled after the
> fact. Fix: set `HCL_RADIANCE_SHIM=1`, which puts a corrected `source.cal` on `RAYPATH` for every
> run, and re-run. Re-check this after **any** Radiance reinstall.

**Live check (optional, ~seconds):** run `daylight_factor` on a small scene and confirm the result
carries `"ran": true` rather than `"ran": false` plus a `commands` list.

---

## Step 2 — Daysim

Only needed for `generate_subhourly_wea` and the live `annual_nvrd` transport. Daysim is
**source-available under an NRC / Fraunhofer ISE licence and is never bundled**; there are no current
official prebuilt binaries.

### 2.1 Build

Preferred — let the server do it:

```
build_daysim(run=True)
```

It fetches ONE pinned commit of <https://github.com/MITSustainableDesignLab/Daysim>
(`27df1dfc98b6a75e209f787bef98374ce86ca077`, `master` as of 2025-01-19), checks that the checkout is that commit, builds headless
with CMake, and returns `bin_dir` plus a `source` block naming what was built. The default is
`run=False`: without `run=True`, or if `git`/`cmake` are missing, it returns the ordered command
plan and a reason instead. Where the client can ask, the user is asked before the download.

An existing `src_dir` is built only if it is a Daysim checkout at that commit. Local edits there
are allowed and reported (if `ds_shortterm.c` fails on its `time_step` extern, fix that one line
and call `build_daysim(run=True)` again). Any other folder is refused with a reason. To build
another commit or a branch, set `HCL_DAYSIM_REF` in the server's environment.

By hand (equivalent):

```bash
git init Daysim && git -C Daysim remote add origin https://github.com/MITSustainableDesignLab/Daysim.git
git -C Daysim fetch --depth 1 origin 27df1dfc98b6a75e209f787bef98374ce86ca077
git -C Daysim checkout --detach FETCH_HEAD
cmake -S Daysim -B build -DBUILD_HEADLESS=ON -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_POLICY_VERSION_MINIMUM=3.5
cmake --build build --target ds_shortterm epw2wea
```

### 2.2 Set the environment

```bash
export HCL_DAYSIM_BIN="<the bin_dir that build_daysim returned>"   # e.g. <src_dir>/build/bin
```

`build_daysim` returns `bin_dir` in its result — use that value verbatim. It is the DIRECTORY holding
`ds_shortterm` and `epw2wea`, not either binary.

### 2.3 Check

```bash
ls "$HCL_DAYSIM_BIN"/ds_shortterm "$HCL_DAYSIM_BIN"/epw2wea
```

Then, through the MCP server:

```
daysim_status()
```

Expect `{"available": true, "missing": []}`. `available` is true **only** when *both*
`ds_shortterm` and `epw2wea` resolve. `version` may be `null` — `ds_shortterm` has no `--version`,
so that alone is not a failure.

> ⚠️ **`epw2wea` also ships with Radiance.** So on a Radiance-only machine `daysim_status()` reports
> `found: ["epw2wea"], missing: ["ds_shortterm"], available: false`. A populated `found` list is not
> evidence Daysim is installed — **`ds_shortterm` is the one that proves it.**

```bash
uv run --extra dev pytest tests/test_daysim_discover.py tests/test_daysim_live.py -q
```

---

## Step 3 — SMARTS 2.9.5

Only needed when you pass `engine="smarts"`. The default `engine="spectrl2"` is pure Python and needs
nothing at all — **skip this whole step unless you specifically want the SMARTS oracle.**

### 3.1 Get it

Download the 2.9.5 distribution from NREL:
<https://www.nrel.gov/grid/solar-resource/smarts.html> (free, licence-gated; separate Mac and Linux
archives). Each carries the Fortran source `Source_code/smarts295.f` plus the data trees `Gases/`,
`Albedo/`, `Solar/`, `CIE_data/` that the engine opens by **relative** path at runtime.

**No SMARTS archive ships in this repository.**

### 3.2 Build (macOS / Linux)

The archive's prebuilt Mac binary is **PowerPC** — dead on Apple Silicon and modern Intel macOS, with
no Rosetta for PPC. Compile it yourself. Two source edits are mandatory:

```bash
# Use the archive filename NREL actually gave you; it unpacks to a SMARTS_295_* directory.
tar xzf /ABSOLUTE/PATH/TO/YOUR/DOWNLOAD/<the-archive-you-downloaded>.tar.gz
cd SMARTS_295_Mac/Source_code

# 1. strip CRLF   2. flip batch=.FALSE. -> .TRUE. (else it blocks on stdin and the 120 s timeout fires)
LC_ALL=C perl -pe 's/\r$//' smarts295.f > smarts295_lf.f
LC_ALL=C perl -i -pe 's/^       batch=\.FALSE\./       batch=.TRUE./; s/^c       batch=\.TRUE\./c       batch=.FALSE./' smarts295_lf.f

gfortran -std=legacy -ffixed-line-length-132 -w -o ../smarts295bat smarts295_lf.f
file ../smarts295bat        # expect: Mach-O 64-bit executable arm64
```

Keep the whole unpacked tree together — the binary **must stay beside its data dirs**:

```bash
cp -R SMARTS_295_Mac "$HOME/smarts"
```

Windows: use the distribution's `smarts295bat.exe`, unzipped with its data folders beside it.

### 3.3 Set the environment

```bash
export SMARTSPATH="$HOME/smarts/smarts295bat"        # the executable FILE
# Windows: SMARTSPATH=C:\smarts\smarts295bat.exe
```

> 🚨 **`SMARTSPATH` names the executable file, never a directory.** `smarts_available()` tests
> `isfile()` **and** `access(X_OK)`. A directory value, a trailing separator, or a non-executable file
> are all rejected. A **set-but-wrong** `SMARTSPATH` is worse than an unset one: unset means "SMARTS
> not installed" and is legitimate; set-but-wrong additionally blocks the fallback. `resolve_engine("smarts")`
> raises early and `smarts_misconfigured()` says which of the two states you are in.

### 3.4 Check

```bash
test -x "$SMARTSPATH" && echo "SMARTSPATH ok" || echo "SMARTSPATH BAD"

# The two tests that actually need the binary:
uv run --extra dev pytest tests/test_smarts.py -q -k "cross_check or um_units"
```

Expect **`2 passed, 6 deselected`**. `2 skipped` means SMARTS is **not** being found — an unset or
wrong `SMARTSPATH`.

> 🚨 **Do not run the plain `pytest tests/test_smarts.py -q` and call it a pass.** Six of its eight
> tests are pure-Python deck/parse tests that pass with **no SMARTS at all**. Without the binary the
> file reports `6 passed, 2 skipped`; with it, `7 passed, 1 skipped` (the one skip flips to
> `test_compute_raises_without_binary`, which only runs when `SMARTSPATH` is unset). Those two totals
> look alike at a glance — the `-k` selector above does not.

Add `-rs` to any of these to print the skip reasons, which name the exact cause.

---

## Step 4 — Final verification, all at once

```bash
cd hcl-mcp
uv run --extra dev pytest -q          # green, with fewer skips than in Step 0
```

Then, through the MCP server:

```
validate()
radiance_status()
daysim_status()
```

Confirm, in this order:

1. `radiance_status()`: `missing == []` and `version` says **6.1a**.
2. `which gensdaymtx rcomb rmtxop evalglare` resolves all four — `radiance_status()` does **not**
   probe these (Step 1.4).
3. `radiance_status().source_cal.a1_honored` is **not `false`** (see the Step 1.4 warning).
4. `daysim_status().available == true`, with `ds_shortterm` in `found` — only if you installed
   Daysim.
5. `pytest tests/test_smarts.py -k "cross_check or um_units"` says **`2 passed`**, not `2 skipped` —
   only if you installed SMARTS.
6. One real tool call returns `"ran": true`, not `"ran": false` with a `commands` list.

**Restart your MCP client after changing any of these environment variables.** The client passes them
to the server at launch; the running server does not re-read them.

---

## Environment variables, in one place

| Variable | Points at | Notes |
|---|---|---|
| `PATH` / `HCL_RADIANCE_BIN` | Radiance `bin` **directory** | `HCL_RADIANCE_BIN` is checked first |
| `RAYPATH` | `.` + Radiance `lib` **directory** | required; `gensdaymtx` aborts without `mie_ca.dat` |
| `HCL_RADIANCE_SHIM` | `1` | only when `a1_honored: false` |
| `HCL_DAYSIM_BIN` | Daysim `bin` **directory** | needs both `ds_shortterm` and `epw2wea` |
| `SMARTSPATH` | the `smarts295bat` **file** | a directory is rejected |

## If a check fails

| Symptom | Cause | Fix |
|---|---|---|
| `radiance_status()` shows `available: false` | binaries not on `PATH` | set `HCL_RADIANCE_BIN`, restart the client |
| `missing` lists a few binaries | partial build (spectral subset only) | re-run a full `make && make install` |
| `gensdaymtx` aborts at startup | `mie_ca.dat` not reachable | set `RAYPATH=.:<prefix>/lib` |
| annual tools emit instead of running | a Reinhart `.cal` is absent from `lib` | copy `reinsrc.cal` / `reinhartb.cal` / `reinhart.cal` in |
| electric results far too dim, glare ≈ 0 | `a1_honored: false` | `HCL_RADIANCE_SHIM=1`, re-run |
| `daysim_status().version` is `null` | `ds_shortterm` has no `--version` | not a fault — check `available` instead |
| `tests/test_smarts.py` says `6 passed, 2 skipped` | SMARTS not found — those 6 need no binary | point `SMARTSPATH` at the executable **file**; re-check with the `-k` selector |
| `daysim_status().found` lists `epw2wea` but `available: false` | that `epw2wea` is Radiance's | install Daysim; `ds_shortterm` is the proof |
| SMARTS run times out after 120 s | built with `batch=.FALSE.` | rebuild with the `batch=.TRUE.` edit |
| a tool returns `"ran": false` + `commands` | that engine is missing | expected, not an error — see the run/emit contract |

## Related docs

| Topic | Doc |
|---|---|
| Radiance 6.1a build detail, flags, runtime caveats | [radiance-6-build.md](radiance-6-build.md) |
| SMARTS build detail, deck structure, caveats | [smarts-build.md](smarts-build.md) |
| Which spectral engine does what, and which need building | [spectral-engines.md](spectral-engines.md) |
| Server install, client registration, five clients | [../INSTALL.md](../INSTALL.md) |
| Beginner walkthrough incl. engine appendix | [../hcl_validation/GUIDE.md](../hcl_validation/GUIDE.md) |
