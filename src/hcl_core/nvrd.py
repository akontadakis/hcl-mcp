"""Non-visual Direct Response (nvRD) alerting model — faithful port of Lark (Amundadottir 2016).

Pure-Python: the source's custom convolution + lfilter truncation are reproduced exactly so output
matches Lark. Consumes a user-provided sub-hourly spectral irradiance series (no Daysim; spec §9.4).
"""
import math
from typing import Any

from hcl_core.data import IPRGC_SENS_WEIGHTING, NVRD

# ---- math primitives (verbatim) ----
def cumtrapz(y, x: Any = False, delta=1, initial=0.0):
    n = len(y)
    dx = [delta] * n if not x else [j - i for i, j in zip(x[:-1], x[1:])]
    area = []
    for i in range(n):
        area.append(initial if i == 0 else (((y[i] + y[i - 1]) / 2) * dx[i - 1]) + area[i - 1])
    return area

def trapz(y, x=False, delta=1, initial=0.0):
    return cumtrapz(y, x, delta, initial)[len(y) - 1]

def naive_convolve(g, f):
    vmax = len(f); smax = len(g); smid = smax // 2; xmax = vmax + 2 * smid
    h = [0] * xmax
    for xi in range(xmax):
        s_from = max(smid - xi, -smid); s_to = min((xmax - xi) - smid, smid + 1); value = 0
        for s in range(s_from, s_to):
            value += g[smid - s] * f[xi - smid + s]
        h[xi] = value
    return h

def lfilter_base(b, a, x):
    b = [i / a for i in b]
    y = naive_convolve(b, x)
    return y[:len(y) - len(b) + 1]

def filter_sma(filter_length, input_signal):
    filter_length = int(filter_length)
    sma = [1.0 / filter_length] * filter_length
    return lfilter_base(sma, sum(sma), input_signal)

def filter_ema(filter_length, input_signal):
    filter_length = int(filter_length)
    alpha = 2.0 / (filter_length + 1.0)
    a_vec = [1.0 - alpha] * filter_length
    c_vec = [a ** b for a, b in zip(a_vec, range(1, filter_length + 1))]
    return lfilter_base(c_vec, sum(c_vec), input_signal)

# ---- response model (verbatim) ----
def relative_response(light_stimuli, sigma, rate_growth):
    return [1.0 / (1.0 + (s / ls) ** rate_growth) if ls != 0 else 0.0
            for s, ls in zip(sigma, light_stimuli)]

def adaptive_response(I, Ieff, sigma, n, d, FLOOR):
    H = filter_sma(d, [math.log10(i * 118.5 * 2.2) if i != 0 else 0.0 for i in I])
    H = [0 if h < 0.0 else h for h in H]
    if FLOOR == 1:
        H = [math.floor(h) if h > 0.0 else h for h in H]
    sigma = [sigma * 2.0 ** (h - 1) for h in H]
    return relative_response(Ieff, sigma, n)

def direct_response(eff_irradiance, delta):
    if delta > 0.3:
        return "Error: Step size must be smaller or equal to 0.3"
    zeff = NVRD["zeff"]            # 310.0/683.0/118.5/1.42*0.91
    EI50 = NVRD["EI50"]           # 106 lx
    slope = NVRD["slope"]         # 3.55
    fL1_h, fLH_h, fL2_h = NVRD["filters_h"]   # (0.3, 1.7, 2.3) h -> L1, LH, L2
    dFL1 = round(fL1_h / delta); dFLH = round(fLH_h / delta); dFL2 = round(fL2_h / delta)
    # lfilter_base preserves the input length only when the filter length is ODD; an even
    # length yields len+1, which misaligns the final `eff_irradiance[i]` gate and raises an
    # opaque IndexError. The source only ever ran at delta=0.1 (lengths 3/17/23, all odd),
    # so this never surfaced upstream; exposing `delta` as a parameter does. Reject even-
    # length timesteps with a clear error rather than crash or return a misaligned series.
    if any(L % 2 == 0 for L in (dFL1, dFLH, dFL2)):
        return ("Error: timestep yields an even filter length (the nvRD filters are "
                "validated at 0.1 h); choose a timestep whose 0.3/1.7/2.3 h filter "
                "lengths are all odd (e.g. 0.1)")
    u = filter_sma(dFL1, eff_irradiance)
    v = adaptive_response(eff_irradiance, u, EI50 * zeff, slope, dFLH, 0)
    RD = filter_ema(dFL2, v)
    return [RD[i] if eff_irradiance[i] > 0.0 else 0 for i in range(len(RD))]

def effective_irradiance(spectral_irradiance_311):
    """Effective ipRGC irradiance from a 311-point (390-700 nm @1 nm) spectral irradiance."""
    if len(spectral_irradiance_311) != 311:
        raise ValueError("spectral irradiance must be 311 points (390-700 nm @1 nm)")
    weighted = [spectral_irradiance_311[i] * IPRGC_SENS_WEIGHTING[i] for i in range(311)]
    return trapz(weighted) * 311

def _slice_311(row):
    if len(row) == 311:
        return list(row)
    if len(row) == 401:           # 380-780 carrier -> 390-700 window (source: wl[10:-80])
        return list(row[10:-80])
    raise ValueError("spectral row must be 311 (390-700) or 401 (380-780) points")

def _coerce_series(spectral_series):
    """Accept the spectral series as inline rows OR as a path to a text/CSV file of rows.

    DEF-4: a full-resolution series (many rows x 401 pts) can be truncated or garbled when sent
    inline over the MCP stdio wire (the tester saw 401-pt rows arrive as 367), which then trips the
    311/401 row-length check. Passing a FILE PATH sidesteps the transport entirely — consistent with
    the file-path-input contract used elsewhere on the tool surface. Each non-empty, non-comment line
    is one timestep row of whitespace- or comma-separated floats.
    """
    import os
    if isinstance(spectral_series, str):
        if not os.path.isfile(spectral_series):
            raise ValueError(f"spectral_series path not found (or is not a file): {spectral_series}")
        rows = []
        with open(spectral_series) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                sep = "," if "," in line else None
                rows.append([float(x) for x in (line.split(sep) if sep else line.split())])
        if not rows:
            raise ValueError(f"spectral_series file has no data rows: {spectral_series}")
        return rows
    return spectral_series


def nvrd(spectral_series, timestep_h=NVRD["timestep_h"], hours=None):
    """Alerting response over time from a sub-hourly spectral irradiance series.

    spectral_series: per-timestep spectral irradiance rows (311 pts 390-700, or 401 pts 380-780) as an
      inline list, OR a path to a text/CSV file with one row per line (recommended for large series —
      avoids MCP wire truncation; see `_coerce_series`).
    timestep_h: hours per step. Must be <= 0.3 AND yield odd nvRD filter lengths (the model is
      validated at 0.1 h, the default/recommended step); other values raise ValueError. Returns
      relative + cumulative response per timestep.

    INPUT CONTRACT (caller's responsibility — see "Behavioral details / input contract" below):
      The rows MUST be a SINGLE point+view orientation, in CHRONOLOGICAL order, ideally
      uniformly spaced at `timestep_h`. For non-uniform spacing, pass an explicit `hours`
      vector. Multi-orientation or multi-day CSVs must be pre-grouped by the caller (one
      nvrd() call per orientation): the Lark source's automatic per-orientation grouping
      (its `pts_vecs_date` key + per-group sort) is intentionally NOT reproduced in v1 (§9.4).
    """
    if timestep_h > 0.3:
        raise ValueError("timestep_h must be <= 0.3 h")
    spectral_series = _coerce_series(spectral_series)
    eff = [effective_irradiance(_slice_311(row)) for row in spectral_series]
    rD = direct_response(eff, timestep_h)
    if isinstance(rD, str):
        raise ValueError(rD)
    if hours is None:
        # NOTE (documented divergence): when hours is None we synthesize a UNIFORM grid
        # (i * timestep_h). The Lark source instead integrates over the CSV's actual `hour`
        # column. For non-uniform real timestamps, pass an explicit `hours` vector.
        hours = [i * timestep_h for i in range(len(rD))]
    else:
        # Lightweight guard: cumulative trapezoidal integration is only meaningful for
        # chronologically ordered input. Out-of-order hours yield meaningless cumulatives.
        if any(hours[i + 1] < hours[i] for i in range(len(hours) - 1)):
            raise ValueError("hours must be monotonically non-decreasing (chronological order)")
    cum = cumtrapz(rD, hours, initial=0.0)
    return {"effective_irradiance": eff, "relative_response": rD, "cumulative_response": cum}
