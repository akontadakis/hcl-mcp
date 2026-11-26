import pytest

from hcl_radiance.spectral_native import (build_gensdaymtx_cmd, build_rcomb_melanopic_cmd,
                                          parse_smx_header, radiance_spectral_status,
                                          reconcile_to_native_bands, run_gensdaymtx,
                                          s026_melanopic_coefficients)


def test_gensdaymtx_cmd_basic():
    cmd = build_gensdaymtx_cmd("site.epw", mf=1)
    assert cmd == ["gensdaymtx", "-m", "1", "-oa", "site.epw"]


def test_gensdaymtx_cmd_sky_only_with_ground():
    # gensdaymtx.c:647-648 `case 'g': grefl = atof(argv[++i])` — -g takes ONE scalar gray reflectance.
    cmd = build_gensdaymtx_cmd("site.epw", mf=2, mode="sky", ground_refl=0.2)
    assert cmd[:3] == ["gensdaymtx", "-m", "2"]
    assert "-s" in cmd and "-g" in cmd
    gi = cmd.index("-g")
    assert cmd[gi + 1] == "0.2"
    assert cmd[gi + 2] == "-oa"  # only ONE value follows -g, then the output-format flag + EPW path
    assert cmd[-1] == "site.epw"


def test_gensdaymtx_cmd_rejects_tuple_ground_refl():
    with pytest.raises(TypeError):
        build_gensdaymtx_cmd("site.epw", mode="sky", ground_refl=(0.2, 0.2, 0.2))


def test_gensdaymtx_cmd_sun_only():
    assert "-d" in build_gensdaymtx_cmd("site.epw", mode="sun")


def test_gensdaymtx_cmd_never_uses_hallucinated_flags():
    cmd = build_gensdaymtx_cmd("site.epw", mf=4, mode="sky", ground_refl=0.1, outfmt="f")
    for bad in ("-c", "-O", "-A", "-D", "-M", "-x", "-y", "-t"):
        assert bad not in cmd


def test_rcomb_melanopic_cmd():
    cmd = build_rcomb_melanopic_cmd("sky.smx")
    # `-c M` is NOT CIE S 026 conformant (WHTMELANOPIC=179 is an equal-energy-white efficacy; on EE
    # white `-c M` == `-c Y` == 179.0). It must never be emitted -- this is the regression guard.
    assert "M" not in cmd
    assert cmd[0] == "rcomb" and cmd[1] == "-c" and cmd[-1] == "sky.smx"
    assert len(cmd) == 3 + 20                      # rcomb -c <20 coeffs> sky.smx
    assert [float(x) for x in cmd[2:-1]] == pytest.approx(s026_melanopic_coefficients(20))


def test_s026_melanopic_coefficients_reproduce_mel_edi():
    """The coefficients must return true CIE S 026 mel-EDI when dotted with Radiance components.

    Radiance's components carry E(lambda)*span (bright() is the MEAN of components), so a D65
    spectral irradiance enters as band_mean * span. Pins the generator against the independent
    alpha_opic path, and would have caught the shipped `-c M` defect (~23% off).
    """
    from hcl_core._recon_data import dseries_spd
    from hcl_core.alpha_opic import alpha_opic_from_spd

    d65 = dseries_spd(6504)
    truth = alpha_opic_from_spd([(380.0 + i, v) for i, v in enumerate(d65)], alpha=5)["EDI"]

    span, ncomp = 400.0, 20
    width = int(span / ncomp)
    # ascending band means * span -> Radiance component convention; reverse to the .smx body order
    comps = [sum(d65[i * width:(i + 1) * width]) / width * span for i in range(ncomp)][::-1]
    got = sum(k * c for k, c in zip(s026_melanopic_coefficients(ncomp), comps))

    # -0.20% live through rcomb; the residual is 20-band binning of a 1nm action spectrum.
    assert got == pytest.approx(truth, rel=3e-3)


def test_s026_melanopic_coefficients_are_descending():
    """k[0] pairs with .smx component 0 = 770nm (red); the melanopic peak (~490nm) sits near k[14]."""
    k = s026_melanopic_coefficients(20)
    assert len(k) == 20
    assert k.index(max(k)) == 14                   # band 14 descending == 480-500nm, the mel peak
    assert k[0] < k[-1]                            # red end damped, blue end alive
    with pytest.raises(ValueError):
        s026_melanopic_coefficients(30)            # 400/30 is not a whole-nm band width


def test_parse_smx_header():
    # The real gensdaymtx header (gensdaymtx.c:917 fputwlsplit(WLPART,...) → color.h:321) prints
    # WAVELENGTH_SPLITS as exactly FOUR values: the legacy RGB+UV/IR partition WLPART[4]={780,588,480,380}
    # (color.c:94, DESCENDING). It is NOT a 21-edge band list. The 20 spectral bins (NCOMP=NSSAMP=20)
    # are a separate uniform 380–780nm grid.
    header = (
        "#?RADIANCE\n"
        "gensdaymtx ...\n"
        "NROWS=146\n"
        "NCOLS=8760\n"
        "NCOMP=20\n"
        "WAVELENGTH_SPLITS= 780 588 480 380\n"
        "FORMAT=ascii\n"
        "\n"
    )
    h = parse_smx_header(header)
    assert h["ncomp"] == 20
    assert h["nrows"] == 146 and h["ncols"] == 8760
    # Stored under the honest key; it is the 4-value RGB partition, not band edges.
    assert h["rgb_partition"] == [780.0, 588.0, 480.0, 380.0]
    assert "wlpart" not in h


def test_radiance_spectral_status_shape():
    st = radiance_spectral_status()
    # aerosol_data / data_note appear only when gensdaymtx itself was found (review N1).
    assert {"available", "gensdaymtx", "rcomb"} <= set(st.keys()) <= {
        "available", "gensdaymtx", "rcomb", "aerosol_data", "data_note"}
    assert isinstance(st["available"], bool)


def test_reconcile_to_native_bands_rebins_onto_uniform_ncomp_grid():
    # gensdaymtx's 20 spectral bins are a UNIFORM 380–780nm grid (atmos.h:17 NSSAMP=20; atmos.c:164
    # WVLSPAN=400 "380nm to 780nm"; atmos.c:169 "380nm to 780nm at 20nm intervals"). The grid is
    # derived from ncomp, NOT from the header's RGB partition. A flat spectrum re-bins to ncomp equal
    # per-band means.
    flat = [2.0] * 401
    bands = reconcile_to_native_bands(flat, 20)
    assert len(bands) == 20 and all(abs(b - 2.0) < 1e-9 for b in bands)
    # Arbitrary ncomp still yields one mean per band over the uniform span.
    coarse = reconcile_to_native_bands(flat, 4)
    assert len(coarse) == 4 and all(abs(b - 2.0) < 1e-9 for b in coarse)


def test_reconcile_native_grid_equals_nominal_hcl_grid_when_ncomp_20():
    # When ncomp==20 the native uniform grid IS the Phase-5 nominal BAND_EDGES_20 (380–780 @20nm),
    # so reconciliation reproduces band_average exactly — a confirmation, not a correction.
    from hcl_core.spectral_emit import band_average
    spectrum = [float(i) for i in range(401)]
    assert reconcile_to_native_bands(spectrum, 20) == pytest.approx(band_average(spectrum))


def test_run_gensdaymtx_emits_when_unavailable(tmp_path, monkeypatch):
    import hcl_radiance.spectral_native as sn
    monkeypatch.setattr(sn, "radiance_spectral_status",
                        lambda: {"available": False, "gensdaymtx": None, "rcomb": None})
    out = run_gensdaymtx("site.epw", str(tmp_path), mf=1)
    assert out["ran"] is False
    assert any("gensdaymtx" in c for c in out["commands"])
    assert "RAYPATH" in out["reason"] or "mie_ca.dat" in out["reason"]


def _native_band_vector_for_hour(smx_path, hour):
    """Reduce a gensdaymtx sky `.smx` (NROWS=146 patches x NCOLS=timesteps, NCOMP=20 bands) to a
    20-band sky-diffuse spectrum for one hour, on the ascending 380->780nm hcl grid.

    Layout verified live against the bundled Radiance 6.1a build (2026-06-20):
      * The ASCII body is PATCH-MAJOR: element index = patch*NCOLS + col; each non-empty body line is
        one matrix element = NCOMP component values. (A sun-only `-d` run peaks at the solar-noon
        column, confirming col == EPW-row index; a timestep-major reading gives a non-physical
        night-energy profile.)
      * For a single-day EPW the column index is `hour-1` (rows are hours 1..24).
      * The 20 components are stored in DESCENDING wavelength order (red->blue), matching the header's
        `WAVELENGTH_SPLITS= 780 588 480 380`. We REVERSE them to ascending (380->780) so the grid
        lines up with hcl_core.spectral_emit band centers (390..770). Evidence: as-stored the native
        shape correlates -0.70 with the SPECTRL2 diffuse spectrum (inverted); reversed it correlates
        +0.99. This is a band-ordering convention, not a tolerance fudge.
    """
    txt = open(smx_path).read()
    header_text, body = txt.split("\n\n", 1)
    hdr = parse_smx_header(header_text)
    nrows, ncols, ncomp = hdr["nrows"], hdr["ncols"], hdr["ncomp"]
    elems = [[float(x) for x in ln.split()] for ln in body.split("\n") if ln.strip()]
    assert len(elems) == nrows * ncols, (len(elems), nrows, ncols)
    col = hour - 1
    bands = [0.0] * ncomp
    for p in range(nrows):
        e = elems[p * ncols + col]
        for b in range(ncomp):
            bands[b] += e[b]
    return bands[::-1], hdr  # reverse red->blue to ascending 380->780


@pytest.mark.skipif(not radiance_spectral_status()["available"],
                    reason="Radiance 6.x gensdaymtx not on PATH")
def test_native_vs_python_engine_envelope(tmp_path, monkeypatch):
    """LIVE cross-validation: native gensdaymtx (Radiance 6.1a) vs the Python SPECTRL2 engine.

    First live 6.1a run (2026-06-20) — this is VALIDATION, not a known-good baseline. The two engines
    use different atmospheres (gensdaymtx: broadband AOD + fixed continental aerosol/H2O/O3 shape;
    SPECTRL2: EPW-derived AOD/PWV/O3), and emit different quantities (native = summed sky-patch
    radiance W/sr/m^2; Python = horizontal diffuse irradiance W/m^2/nm). So we cross-validate the
    SPECTRAL SHAPE (normalized per-band) within a loose, evidence-based envelope, NOT a byte-match and
    NOT absolute broadband energy across incommensurable units.
    """
    import os
    import math

    from hcl_core.spectral_engine.base import ClearSkySpectra
    from hcl_core.spectral_validate import compare_engines
    from hcl_core.spectral_pipeline import record_from_epw
    from hcl_core.spectral_emit import band_average, _band_centers

    monkeypatch.setenv("RAYPATH", ".:/usr/local/radiance/lib")  # gensdaymtx needs mie_ca.dat on RAYPATH

    # Repo-relative: the same Athens IWEC EPW ships in the validation kit. This used to point at an
    # absolute path on the dev machine, so the cross-check silently skipped everywhere else — and on
    # the dev machine too, once that file moved.
    src_epw = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "hcl_validation", "inputs", "weather", "GRC_Athens.167160_IWEC.epw")
    if not os.path.exists(src_epw):
        pytest.skip("EPW fixture unavailable")

    # Trim the annual EPW to one clear summer day (Athens, 7/15 — DNI peaks 886 W/m^2 at hour 13,
    # diffuse fraction ~0.12). Single day => gensdaymtx runs sub-second on 24 timesteps, not 8760.
    lines = open(src_epw).readlines()
    header, rows = lines[:8], lines[8:]
    day_rows = [r for r in rows
                if len(r.split(",")) > 4
                and r.split(",")[1].strip() == "7" and r.split(",")[2].strip() == "15"]
    assert len(day_rows) == 24
    trim_epw = str(tmp_path / "athens_1day.epw")
    with open(trim_epw, "w") as fh:
        fh.writelines(header)
        fh.writelines(day_rows)

    CLEAR_HOUR = 13

    # --- 1. Run native gensdaymtx (sky-diffuse only) and assert it executed & emitted NCOMP=20 ---
    out = run_gensdaymtx(trim_epw, str(tmp_path / "native"), mf=1, mode="sky", run=True)
    assert out["ran"] is True, out
    assert out["ok"] is True, out.get("error")
    hdr = out["header"]
    assert hdr["ncomp"] == 20, hdr           # the 20-band convention the parser assumes
    assert hdr["nrows"] == 146, hdr          # Reinhart MF=1 sky patches
    assert hdr["ncols"] == 24, hdr           # one column per EPW timestep

    native, hdr2 = _native_band_vector_for_hour(out["smx"], CLEAR_HOUR)
    assert len(native) == 20 and all(v > 0.0 for v in native), native
    assert hdr2["ncomp"] == 20
    # NCOMP==20 => native uniform grid == nominal hcl grid; reconcile would be a no-op (confirmation,
    # not correction). reconcile_to_native_bands is only needed if a non-20 NCOMP ever appears.

    # --- 2. Python SPECTRL2 sky-diffuse, matched location/time, on the same 20-band grid ---
    rec = record_from_epw(trim_epw, 7, 15, CLEAR_HOUR)
    py = band_average(rec.sky_diffuse_horizontal)
    assert len(py) == 20 and sum(py) > 0.0

    centers = _band_centers()                # 390..770nm, ascending — both vectors share this grid

    # --- 3. Shape comparison: normalize each to unit broadband area, then compare per band ---
    def _norm(v):
        s = sum(v)
        return [x / s for x in v]
    nn, pn = _norm(native), _norm(py)

    # 3a. Ordering / no-inversion: clear-sky diffuse is blue-rich -> red-poor. Use action-weighted
    #     mel/photopic ratio (shape indicator, unit-independent) on a 1nm interpolation of each.
    def _spd(vals):
        def interp(x):
            if x <= centers[0]:
                return vals[0]
            if x >= centers[-1]:
                return vals[-1]
            lo = 0
            while centers[lo + 1] < x:
                lo += 1
            t = (x - centers[lo]) / (centers[lo + 1] - centers[lo])
            return vals[lo] + t * (vals[lo + 1] - vals[lo])
        return "\n".join(f"{w} {interp(w)}" for w in range(380, 781))

    from hcl_core.spectral_metrics import mel_photopic_ratio
    mp_native = mel_photopic_ratio(_spd(nn))
    mp_python = mel_photopic_ratio(_spd(pn))
    # Both must be blue-rich daylight diffuse (mel/phot > 0.85; a red-rich/inverted spectrum would be
    # well below). Measured 2026-06-20: native 0.9868, python 1.0145.
    assert mp_native > 0.85, mp_native
    assert mp_python > 0.85, mp_python
    assert abs(mp_native - mp_python) <= 0.10, (mp_native, mp_python)  # within a loose band (meas ~0.03)

    # Blue-half vs red-half ordering preserved in BOTH (no inverted spectrum).
    blue, red = slice(0, 7), slice(13, 20)
    assert sum(nn[blue]) > sum(nn[red]), nn   # native blue/red ~1.17 after band-order alignment
    assert sum(pn[blue]) > sum(pn[red]), pn   # python blue/red ~1.34

    # 3b. Per-band envelope via Phase-6 compare_engines. Build ClearSkySpectra shims on a grid that
    #     spans [380,780] (compare_engines refuses to extrapolate): pad band centers with the 380/780
    #     endpoints (flat-held). Same vector in both channels (we only have one diffuse spectrum each).
    def _shim(vals):
        wl = [380.0] + list(centers) + [780.0]
        v = [vals[0]] + list(vals) + [vals[-1]]
        return ClearSkySpectra(wavelength_nm=wl, direct_normal=v, sky_diffuse_horizontal=v)

    cmp = compare_engines(_shim(pn), _shim(nn))   # b=native relative to a=python
    # Measured 2026-06-20: diffuse_mean_pct +2.45, diffuse_max_pct +20.75 (per-band max |rel| ~21%).
    # Envelope: brief suggests +-25-40% per band. The measured max sits at ~21%, comfortably inside,
    # so we assert the tighter, evidence-based +-30% band (still loose, still failable if a future
    # build inverts/rescales the spectrum).
    assert abs(cmp["diffuse_mean_pct"]) <= 12.0, cmp   # mean drift small; meas ~2.5%
    assert abs(cmp["diffuse_max_pct"]) <= 30.0, cmp    # worst band; meas ~20.8%

    # 3c. Direct shape sanity (same vectors duplicated into the direct channel) tracks diffuse.
    assert abs(cmp["direct_max_pct"]) <= 30.0, cmp

    # Per-band normalized correlation must be strongly positive (catches an inverted/scrambled grid).
    mnn, mpn = sum(nn) / 20, sum(pn) / 20
    num = sum((a - mnn) * (b - mpn) for a, b in zip(nn, pn))
    den = math.sqrt(sum((a - mnn) ** 2 for a in nn) * sum((b - mpn) ** 2 for b in pn))
    corr = num / den
    assert corr > 0.9, corr   # measured 0.987; as-stored (un-reversed) would be -0.70 and FAIL here


def test_run_gensdaymtx_emit_has_no_ok_field(tmp_path, monkeypatch):
    # I1: the emit path is discriminable by ran=False (no `ok`); success/failure carry `ok`.
    import hcl_radiance.spectral_native as sn
    monkeypatch.setattr(sn, "radiance_spectral_status",
                        lambda: {"available": False, "gensdaymtx": None, "rcomb": None})
    out = run_gensdaymtx("site.epw", str(tmp_path), mf=1)
    assert out["ran"] is False
    assert "ok" not in out


def test_run_gensdaymtx_failure_is_discriminable(tmp_path, monkeypatch):
    # I1: a non-zero returncode must read as ok=False (not the old ran=True-looks-like-success).
    import hcl_radiance.spectral_native as sn

    class _Proc:
        returncode = 1
        stderr = b"gensdaymtx: boom"

    monkeypatch.setattr(sn, "radiance_spectral_status",
                        lambda: {"available": True, "gensdaymtx": "/x/gensdaymtx", "rcomb": "/x/rcomb"})
    monkeypatch.setattr(sn.subprocess, "run", lambda *a, **k: _Proc())
    out = run_gensdaymtx("site.epw", str(tmp_path), mf=1)
    assert out["ran"] is True and out["ok"] is False
    assert out["returncode"] == 1 and "boom" in out["error"]


def test_run_gensdaymtx_success_is_discriminable(tmp_path, monkeypatch):
    # I1: success carries ok=True + header; I2: header read tolerates a long argv echo (>4096 bytes).
    import hcl_radiance.spectral_native as sn

    class _Proc:
        returncode = 0
        stderr = b""

    def _fake_run(cmd, stdout=None, **k):
        long_argv = "gensdaymtx " + "x" * 5000 + "\n"
        stdout.write(long_argv + "NROWS=146\nNCOLS=8760\nNCOMP=20\n"
                     "WAVELENGTH_SPLITS= 780 588 480 380\nFORMAT=ascii\n\n"
                     "0.1 0.2 0.3\n")
        return _Proc()

    monkeypatch.setattr(sn, "radiance_spectral_status",
                        lambda: {"available": True, "gensdaymtx": "/x/gensdaymtx", "rcomb": "/x/rcomb"})
    monkeypatch.setattr(sn.subprocess, "run", _fake_run)
    out = run_gensdaymtx("site.epw", str(tmp_path), mf=1)
    assert out["ran"] is True and out["ok"] is True
    assert out["header"]["ncomp"] == 20  # parsed despite the >4096-byte argv echo (I2)
    assert out["header"]["rgb_partition"] == [780.0, 588.0, 480.0, 380.0]


def test_run_gensdaymtx_default_timeout_is_unbounded(tmp_path, monkeypatch):
    # The old hardcoded 600s cap made the tool RAISE TimeoutExpired on a full-year EPW (gensdaymtx
    # always processes every hour). The default must impose no cap so a real annual EPW completes.
    import hcl_radiance.spectral_native as sn
    seen = {}

    class _Proc:
        returncode = 0
        stderr = b""

    def _fake_run(cmd, stdout=None, timeout=None, **k):
        seen["timeout"] = timeout
        stdout.write("NROWS=146\nNCOLS=24\nNCOMP=20\n\n0.1\n")
        return _Proc()

    monkeypatch.setattr(sn, "radiance_spectral_status",
                        lambda: {"available": True, "gensdaymtx": "/x/gensdaymtx", "rcomb": "/x/rcomb"})
    monkeypatch.setattr(sn.subprocess, "run", _fake_run)
    run_gensdaymtx("site.epw", str(tmp_path), mf=1)
    assert seen["timeout"] is None


def test_run_gensdaymtx_forwards_timeout(tmp_path, monkeypatch):
    # An explicit timeout must reach subprocess.run unchanged.
    import hcl_radiance.spectral_native as sn
    seen = {}

    class _Proc:
        returncode = 0
        stderr = b""

    def _fake_run(cmd, stdout=None, timeout=None, **k):
        seen["timeout"] = timeout
        stdout.write("NROWS=146\nNCOLS=24\nNCOMP=20\n\n0.1\n")
        return _Proc()

    monkeypatch.setattr(sn, "radiance_spectral_status",
                        lambda: {"available": True, "gensdaymtx": "/x/gensdaymtx", "rcomb": "/x/rcomb"})
    monkeypatch.setattr(sn.subprocess, "run", _fake_run)
    run_gensdaymtx("site.epw", str(tmp_path), mf=1, timeout=1234)
    assert seen["timeout"] == 1234


def test_run_gensdaymtx_timeout_is_graceful(tmp_path, monkeypatch):
    # On expiry the tool must return a discriminable ok=False/timed_out=True dict, NOT raise — an
    # unhandled TimeoutExpired crashes the MCP call (the bug found on the full-year Athens EPW).
    import hcl_radiance.spectral_native as sn

    def _raise(cmd, stdout=None, timeout=None, **k):
        raise sn.subprocess.TimeoutExpired(cmd, timeout)

    monkeypatch.setattr(sn, "radiance_spectral_status",
                        lambda: {"available": True, "gensdaymtx": "/x/gensdaymtx", "rcomb": "/x/rcomb"})
    monkeypatch.setattr(sn.subprocess, "run", _raise)
    out = run_gensdaymtx("site.epw", str(tmp_path), mf=1, timeout=5)
    assert out["ran"] is True and out["ok"] is False
    assert out["timed_out"] is True
    assert "timeout" in out["error"].lower() or "timed out" in out["error"].lower()


def test_native_capability_gate_is_bool():
    assert isinstance(radiance_spectral_status()["available"], bool)
