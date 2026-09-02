import math
import pytest
from hcl_core.nvrd import (trapz, cumtrapz, naive_convolve, filter_sma, filter_ema,
                            direct_response, nvrd)
from hcl_core.data import IPRGC_SENS_WEIGHTING

# --- reference copies of the SOURCE functions (must match the port bit-for-bit) ---
def _ref_naive_convolve(g, f):
    vmax = len(f); smax = len(g); smid = smax // 2; xmax = vmax + 2 * smid
    h = [0] * xmax
    for x in range(xmax):
        s_from = max(smid - x, -smid); s_to = min((xmax - x) - smid, smid + 1); value = 0
        for s in range(s_from, s_to):
            v = x - smid + s; value += g[smid - s] * f[v]
        h[x] = value
    return h
def _ref_lfilter(b, a, x):
    b = [i / a for i in b]; y = _ref_naive_convolve(b, x); return y[:len(y) - len(b) + 1]
def _ref_sma(L, x):
    L = int(L); sma = [1.0 / L] * L; return _ref_lfilter(sma, sum(sma), x)
def _ref_ema(L, x):
    L = int(L); alpha = 2.0 / (L + 1.0); a = [1.0 - alpha] * L; b = range(1, L + 1)
    c = [aa ** bb for aa, bb in zip(a, b)]; return _ref_lfilter(c, sum(c), x)

def test_convolve_matches_source():
    f = [1.0, 2.0, 3.0, 4.0, 5.0]; g = [0.25, 0.5, 0.25]
    assert naive_convolve(g, f) == _ref_naive_convolve(g, f)

def test_sma_ema_match_source():
    x = [0.1 * i for i in range(20)]
    assert filter_sma(3, x) == _ref_sma(3, x)
    assert filter_ema(5, x) == _ref_ema(5, x)

def test_trapz_and_cumtrapz():
    assert cumtrapz([0, 1, 2], delta=1) == [0.0, 0.5, 2.0]
    assert trapz([0, 1, 2], delta=1) == 2.0

def test_direct_response_step_guard():
    assert isinstance(direct_response([1.0] * 10, 0.5), str)  # error string when delta > 0.3

def test_nvrd_output_shape_and_ranges():
    # 30 timesteps of a flat positive spectral irradiance (311 pts, 390-700 nm)
    series = [[0.01] * 311 for _ in range(30)]
    out = nvrd(series, timestep_h=0.1)
    assert len(out["relative_response"]) == 30
    assert all(0.0 <= r <= 1.0 for r in out["relative_response"])
    # cumulative is non-decreasing
    cum = out["cumulative_response"]
    assert all(cum[i + 1] >= cum[i] - 1e-9 for i in range(len(cum) - 1))

def test_nvrd_accepts_401_and_slices():
    series = [[0.01] * 401 for _ in range(15)]   # 380-780 carrier -> sliced to 311
    out = nvrd(series, timestep_h=0.1)
    assert len(out["relative_response"]) == 15

def test_nvrd_rejects_bad_spectral_length():
    with pytest.raises(ValueError):
        nvrd([[0.01] * 200], timestep_h=0.1)

def test_nvrd_accepts_file_path_series(tmp_path):
    # DEF-4: a full-resolution series passed as a FILE PATH (one 401-pt row per line) must parse and
    # produce identical output to the equivalent inline list — sidesteps MCP wire truncation.
    series = [[0.01] * 401 for _ in range(15)]
    p = tmp_path / "series.csv"
    p.write_text("\n".join(",".join(str(v) for v in row) for row in series) + "\n")
    out_path = nvrd(str(p), timestep_h=0.1)
    out_inline = nvrd(series, timestep_h=0.1)
    assert out_path["relative_response"] == out_inline["relative_response"]

def test_nvrd_file_path_supports_comments_and_whitespace(tmp_path):
    p = tmp_path / "series.txt"
    lines = ["# header comment"] + [" ".join(["0.01"] * 311) for _ in range(15)] + [""]
    p.write_text("\n".join(lines))
    out = nvrd(str(p), timestep_h=0.1)
    assert len(out["relative_response"]) == 15

def test_nvrd_file_path_missing_raises(tmp_path):
    with pytest.raises(ValueError):
        nvrd(str(tmp_path / "nope.csv"), timestep_h=0.1)

def test_nvrd_directory_path_raises_valueerror(tmp_path):
    """C1: passing a directory (not a file) must raise a clear ValueError, not an opaque
    IsADirectoryError from open()."""
    with pytest.raises(ValueError):
        nvrd(str(tmp_path), timestep_h=0.1)

def test_nvrd_rejects_big_timestep():
    with pytest.raises(ValueError):
        nvrd([[0.01] * 311] * 5, timestep_h=0.5)

def test_nvrd_rejects_non_monotonic_hours():
    # input contract (b): explicit hours must be chronological (non-decreasing).
    series = [[0.01] * 311 for _ in range(4)]
    with pytest.raises(ValueError):
        nvrd(series, timestep_h=0.1, hours=[0.0, 0.2, 0.1, 0.3])

def test_nvrd_accepts_monotonic_nonuniform_hours():
    # explicit non-uniform but chronological hours are accepted.
    series = [[0.01] * 311 for _ in range(4)]
    out = nvrd(series, timestep_h=0.1, hours=[0.0, 0.1, 0.3, 0.6])
    assert len(out["cumulative_response"]) == 4

def test_nvrd_rejects_even_filter_timestep():
    # Within the <=0.3 bound but yielding an even filter length: must raise ValueError
    # cleanly (previously an opaque IndexError). 0.2/0.15/0.3 each produce an even length.
    series = [[0.01] * 311 for _ in range(30)]
    for bad in (0.2, 0.15, 0.3):
        with pytest.raises(ValueError):
            nvrd(series, timestep_h=bad)

def test_nvrd_accepts_odd_filter_timestep_0p25():
    # 0.25 -> filter lengths 1/7/9 (all odd) -> valid, no crash.
    series = [[0.01] * 311 for _ in range(30)]
    out = nvrd(series, timestep_h=0.25)
    assert len(out["relative_response"]) == 30

def test_direct_response_even_filter_guard():
    # even filter length returns an error string (same convention as the delta>0.3 guard)
    assert isinstance(direct_response([1.0] * 10, 0.2), str)
