"""Drive Radiance 6.1a native spectral sky (gensdaymtx) from an EPW — a parallel engine to the
Python SPECTRL2/SEDES1 stack. Capability-gated: degrades to emitting the command plan when the
Radiance 6.x binary is absent (the system Radiance has no gensdaymtx).

Only IMPLEMENTED gensdaymtx flags are used (the binary's usage string advertises non-existent
-c/-O/-A/-D/-M — using them aborts the run). Location/time come from the EPW header.
"""
import os
import subprocess

from hcl_core._spectra import ACTION_MEL

_MODE_FLAG = {"all": [], "sun": ["-d"], "sky": ["-s"]}


def build_gensdaymtx_cmd(epw_path, *, mf=1, mode="all", ground_refl=None, outfmt="a"):
    """gensdaymtx command (location read from the EPW header). mode: all|sun(-d)|sky(-s).

    `ground_refl` is a SINGLE scalar gray ground reflectance (gensdaymtx.c:647-648
    `case 'g': grefl = atof(argv[++i])` — one value, default .2), NOT an r/g/b tuple.
    """
    if mode not in _MODE_FLAG:
        raise ValueError("mode must be 'all', 'sun', or 'sky'")
    cmd = ["gensdaymtx", "-m", str(mf)]
    cmd += _MODE_FLAG[mode]
    if ground_refl is not None:
        if not isinstance(ground_refl, (int, float)):
            raise TypeError(f"ground_refl must be a scalar float, got {type(ground_refl).__name__}")
        cmd += ["-g", str(ground_refl)]
    cmd += [f"-o{outfmt}", epw_path]
    return cmd


def build_rcomb_melanopic_cmd(smx_path, *, ncomp=20):
    """rcomb collapse of a spectral matrix to a single CIE S 026 mel-EDI channel.

    Deliberately does NOT use Radiance's own `-c M`. That flag returns EQUAL-ENERGY-normalised
    "melanopic lux" (the EML-style quantity), NOT CIE S 026 mel-EDI: `util/rcomb.c:269-271` applies
    `scolor2melanopic * WHTMELANOPIC`, and `common/color.h:276` defines `WHTMELANOPIC 179.` —
    identical to `WHTEFFICACY`, matching Radiance's own photopic convention. The source comment says
    so: "melanopic EE white 380-780nm".

    This is Radiance behaving as documented (`rcomb.1:150` states the 179 lm/W factor and calls the
    output melanopic lux), NOT a Radiance defect — `-c M`/`-c Y` = 1.098 is essentially the Lucas
    EML/mel-EDI ratio, and Greg Ward states the conversion publicly ("divide melanopic illuminance
    by 1.1 to get mEDI, which is based on D65"). The defect was OURS: consuming EML as if it were
    mel-EDI. S 026 requires mel-DER(D65) = 1 exactly.

    Verified live (2026-07-17) on a D65 spectrum in DESCENDING band order: `-c M` reads 1.081x true
    mel-EDI (8.1% high) and `-c M`/`-c Y` = 1.098. (Feeding ASCENDING components instead reads 0.774
    — Radiance's symbolic path indexes `scol[ncs-1-n]`, `spec_rgb.c:280`, i.e. it assumes descending.
    Getting that backwards fabricates a spurious ~23% error; do not repeat it.)

    So we pass explicit numeric coefficients instead (s026_melanopic_coefficients), which `rcomb`
    applies as a plain dot product over the components, in file order.
    """
    coeffs = s026_melanopic_coefficients(ncomp)
    return ["rcomb", "-c", *[f"{k:.10e}" for k in coeffs], smx_path]


def parse_smx_header(text):
    """Parse a gensdaymtx matrix header: NCOMP/NROWS/NCOLS + the WAVELENGTH_SPLITS record.

    WAVELENGTH_SPLITS is the legacy 4-value RGB+UV/IR partition WLPART[4]={780,588,480,380}
    (common/color.c:94, printed by gensdaymtx.c:917 via fputwlsplit, common/color.h:321) — NOT a
    band-edge list. It is stored under `rgb_partition`. The 20 spectral bins (NCOMP=NSSAMP=20,
    gen/atmos.h:17) are a separate uniform 380–780nm grid (see reconcile_to_native_bands).

    BAND ORDER NOTE (confirmed by first live validation, 2026-06-20):
    The native .smx matrix BODY stores the 20 spectral components in DESCENDING wavelength order
    (red→blue), consistent with WAVELENGTH_SPLITS = 780 588 480 380 (high-to-low). Any future code
    that reads the matrix body into a per-wavelength band vector MUST reverse it ([::-1]) to
    ascending 380→780 order to align with the nominal grid (NATIVE_LO_NM=380 → NATIVE_HI_NM=780).
    See the reference implementation in the test helper `_native_band_vector_for_hour` in
    tests/test_spectral_native.py. No production code currently reads the .smx body; this note is
    insurance for any future reader.
    """
    out: dict[str, int | list[float] | None] = {
        "ncomp": None, "nrows": None, "ncols": None, "rgb_partition": None}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#?"):
            continue            # blank lines / the #?RADIANCE magic are not key=value header records
        if "=" not in line:
            continue            # matrix body rows (no '=') — skip; header records are all key=value
        key, _, val = line.partition("=")
        key = key.strip().upper()
        if key == "NCOMP":
            out["ncomp"] = int(val.split()[0])
        elif key == "NROWS":
            out["nrows"] = int(val.split()[0])
        elif key == "NCOLS":
            out["ncols"] = int(val.split()[0])
        elif key in ("WAVELENGTH_SPLITS", "WLSPLIT", "WLPART"):
            nums = []
            for tok in val.replace(",", " ").split():
                try:
                    nums.append(float(tok))
                except ValueError:
                    pass
            out["rgb_partition"] = nums or None
    return out


def radiance_spectral_status():
    """Detect the Radiance 6.x spectral tools via HCL_RADIANCE_BIN or PATH."""
    from hcl_radiance.discover import resolve_bin
    gens = resolve_bin("gensdaymtx")
    rc = resolve_bin("rcomb")
    return {"available": gens is not None, "gensdaymtx": gens, "rcomb": rc}


def run_gensdaymtx(epw_path, work_dir, *, mf=1, mode="all", ground_refl=None, run=True, timeout=None):
    """Run gensdaymtx (EPW → 20-band spectral sky matrix) if Radiance 6.x is present, else emit the plan.

    `timeout` caps the gensdaymtx subprocess in SECONDS. Default `None` = NO cap: gensdaymtx ALWAYS
    processes every EPW hour. A full 8760-hour year at mf=1 (NROWS=146, NCOMP=20) is fast — ~12 s wall /
    ~10 s CPU on Radiance 6.1a (measured 2026-06-29) — but cost grows steeply with the Reinhart
    subdivision mf (minutes at mf>=4), which is why the cap is caller-supplied. On expiry we return a
    discriminable {ok: False, timed_out: True} instead of raising. Pass a number to cap it, or trim the EPW.
    """
    os.makedirs(work_dir, exist_ok=True)
    cmd = build_gensdaymtx_cmd(epw_path, mf=mf, mode=mode, ground_refl=ground_refl)
    smx = os.path.join(work_dir, "sky_spectral.smx")
    status = radiance_spectral_status()
    if not (run and status["available"]):
        rcomb = build_rcomb_melanopic_cmd(smx)
        return {"ran": False,
                "commands": [" ".join(cmd) + " > " + smx, " ".join(rcomb) + " > sky_melanopic.mtx"],
                "reason": "gensdaymtx (Radiance 6.x) not on PATH. Ensure mie_ca.dat is on RAYPATH, "
                          "then run the commands; re-call with run=True once available."}
    try:
        with open(smx, "w") as fh:
            proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ran": True, "ok": False, "timed_out": True, "smx": smx,
                "error": f"gensdaymtx exceeded the {timeout}s timeout. A full-year EPW matrix is many "
                         "minutes of CPU (gensdaymtx runs every hour); pass a larger `timeout` (or None "
                         "for no cap) or trim the EPW to the hours you need."}
    if proc.returncode != 0:
        return {"ran": True, "ok": False, "error": proc.stderr.decode(errors="replace"),
                "returncode": proc.returncode, "smx": smx}
    # Read the whole file: parse_smx_header skips body rows (lines without '='), so a full read is
    # safe and avoids the fixed-4096-byte read truncating before NCOMP on a long argv echo (I2).
    with open(smx) as fh:
        header = parse_smx_header(fh.read())
    return {"ran": True, "ok": True, "smx": smx, "header": header}


# gensdaymtx's native spectral grid: NSSAMP=20 bins UNIFORM over 380–780nm. Verified in the bundled
# Radiance source — gen/atmos.h:17 (`#define NSSAMP 20`), gen/atmos.c:164 (`WVLSPAN = 400; /* 380nm to
# 780nm */`) and gen/atmos.c:169 (`/** 380nm to 780nm at 20nm intervals **/` over the NSSAMP arrays).
# (START_WVL=390 / END_WVL=770 are the bin CENTERS, i.e. edges 380..780.) The header's
# WAVELENGTH_SPLITS is the unrelated 4-value RGB partition (see parse_smx_header) — it is NOT used here.
NATIVE_LO_NM = 380.0
NATIVE_HI_NM = 780.0

# CIE S 026 melanopic action-spectrum -> EDI constant: K_mel,D65 = 1.3262 mW/lm, expressed in W/lm.
# This is what makes mel-DER(D65) == 1 by definition. Cross-check: hcl_core.alpha_opic recomputes the
# same constant from the D65 spectrum every call and gets 1.3263 mW/lm (4 s.f. agreement).
K_MEL_D65 = 1.3262e-3


def s026_melanopic_coefficients(ncomp=20, *, lo_nm=NATIVE_LO_NM, hi_nm=NATIVE_HI_NM):
    """Explicit CIE S 026 mel-EDI coefficients for `rcomb -c`, in the .smx body's DESCENDING order.

        k_i = (integral of s_mel over band i) / (span_nm * K_MEL_D65)

    The `span_nm` divisor is Radiance's component convention, not a fudge factor: `bright()` is the
    MEAN of the components (common/color.h), so each spectral component carries `E(lambda) * span`
    rather than the per-nm density. Dividing by the span converts back.

    Band order is DESCENDING (k[0] <-> 770nm, k[19] <-> 390nm) to match the .smx body documented in
    parse_smx_header. `rcomb -c` is a plain dot product with NO reordering — verified live: given
    components 0..19, `-c 0 .. 0 1` returns 19.0 and `-c 1 0 .. 0` returns 0.0. So the coefficient
    order MUST match the body order or the melanopic answer silently inverts.

    Verified live end-to-end through rcomb against a D65 spectrum (2026-07-17): reproduces
    hcl_core.alpha_opic.alpha_opic_from_spd's mel-EDI to -0.20% (7205186 vs 7219808). The residual is
    the 20-band binning of a 1nm action spectrum -- input resolution, not method error.
    """
    if not ncomp or ncomp < 1:
        raise ValueError("ncomp must be a positive integer band count (e.g. NCOMP from the header)")
    span = hi_nm - lo_nm
    width = span / ncomp
    if width != int(width):
        raise ValueError(f"ncomp={ncomp} does not divide {span:.0f}nm into whole-nm bands")
    width = int(width)
    lo_i = int(lo_nm - 380.0)  # ACTION_MEL is 401 values on the 1nm 380..780 grid
    asc = [sum(ACTION_MEL[lo_i + i * width: lo_i + (i + 1) * width]) / (span * K_MEL_D65)
           for i in range(ncomp)]
    return asc[::-1]  # -> descending, matching the .smx body


def reconcile_to_native_bands(values_401, ncomp, *, lo_nm=NATIVE_LO_NM, hi_nm=NATIVE_HI_NM):
    """Re-bin a Phase-5 401-pt 1nm spectrum (380..780) onto gensdaymtx's NATIVE uniform spectral grid.

    The native grid is `ncomp` equal-width bins over [lo_nm, hi_nm] — derived from NCOMP (=NSSAMP=20),
    NOT from the header's RGB partition. Returns one mean per band over [edge_k, edge_{k+1}); the last
    band includes its upper edge. Edges are clamped to the 1nm grid.

    Note: for the default ncomp=20 over 380–780nm this uniform grid IS the Phase-5 nominal
    BAND_EDGES_20 (380–780 @20nm), so reconciliation reproduces hcl_core.spectral_emit.band_average
    exactly — confirming, not correcting, the nominal grid. The "byte-compat gap" the spec §8 feared
    does not exist for matching ncomp/span. (Standalone hcl artifacts keep the nominal grid; this is
    only for Track-C-interoperable emission, and lets a future non-20 ncomp re-bin cleanly.)
    """
    if not ncomp or ncomp < 1:
        raise ValueError("ncomp must be a positive integer band count (e.g. NCOMP from the header)")
    n = len(values_401)
    out = []
    for k in range(ncomp):
        edge_lo = lo_nm + (hi_nm - lo_nm) * k / ncomp
        edge_hi = lo_nm + (hi_nm - lo_nm) * (k + 1) / ncomp
        lo = max(0, min(n - 1, int(round(edge_lo - lo_nm))))
        hi = int(round(edge_hi - lo_nm)) + (1 if k == ncomp - 1 else 0)
        hi = max(lo + 1, min(n, hi))
        seg = values_401[lo:hi]
        out.append(sum(seg) / len(seg) if seg else 0.0)
    return out
