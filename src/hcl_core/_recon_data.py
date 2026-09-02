"""Embedded standard tabulated data for the enhanced spectral reconstruction (spec §5.2).

Two standards, both interpolated to 401 points (380..780 nm @1 nm) in pure Python:

1) SOLAR_AM_SPD: air-mass-indexed DIRECT-NORMAL solar spectral irradiance shape templates.
   These are REPRESENTATIVE direct-normal solar slope templates capturing the air-mass reddening
   trend (inspired by ASTM G173 / SMARTS direct-normal) — NOT literal ASTM G173 values, and they omit
   the 760nm O2 dip. Stored as coarse 20-nm anchor points per air mass and linearly interpolated. Used
   only for the RELATIVE shape within each Radiance bin (renormalized per bin in spectral_reconstruct),
   so absolute calibration is irrelevant — only the spectral slope (reddening with air mass) matters.
   For production rigor, replace with the literal ASTM G173-03 direct-normal column from NREL's
   ASTMG173.xls (https://www.nrel.gov/grid/solar-resource/spectra-am1.5).

2) DSERIES_S0/S1/S2: the CIE daylight reconstruction eigenvectors. Source: CIE 15 /
   Judd-MacAdam-Wyszecki (tabulated 300-830 nm @10 nm). Stored as the 380..780 @10 nm slice and
   interpolated to 1 nm. dseries_spd(cct) reconstructs a relative daylight SPD from a CCT via the
   daylight locus (xy from CCT) and the standard M1/M2 mixing coefficients.

NOTE: these are standard tabulated values, NOT measurements. Every consumer renormalizes the
shape, so coarse anchors are sufficient and faithful for shaping purposes.
"""

# ---------- helpers ----------
_NM0, _NM1, _STEP1 = 380, 780, 1

def _interp_anchors(anchor_nm, anchor_vals, start=_NM0, stop=_NM1):
    """Linearly interpolate (anchor_nm -> anchor_vals) onto a 1-nm grid start..stop inclusive (401 pts)."""
    out = []
    n = len(anchor_nm)
    for w in range(start, stop + 1):
        if w <= anchor_nm[0]:
            out.append(float(anchor_vals[0])); continue
        if w >= anchor_nm[-1]:
            out.append(float(anchor_vals[-1])); continue
        # find bracketing anchors
        for i in range(n - 1):
            a0, a1 = anchor_nm[i], anchor_nm[i + 1]
            if a0 <= w <= a1:
                t = (w - a0) / (a1 - a0)
                out.append(float(anchor_vals[i] + t * (anchor_vals[i + 1] - anchor_vals[i])))
                break
    return out

# ---------- 1) Representative direct-normal solar slope templates, coarse 20-nm anchors per air mass --
# Anchor wavelengths (nm). Values are RELATIVE direct-normal irradiance (arbitrary scale; shape only).
# These are representative direct-normal solar slope templates capturing the air-mass reddening trend
# (inspired by ASTM G173 / SMARTS direct-normal); used shape-only after per-bin renormalization, so
# only the relative slope (AM1.0 bluest, AM3.0 reddest) reaches the output. They are NOT literal ASTM
# G173 values and omit the 760nm O2 dip. For production rigor, replace with the literal ASTM G173-03
# direct-normal column from NREL's ASTMG173.xls (https://www.nrel.gov/grid/solar-resource/spectra-am1.5).
_SOLAR_NM = [380, 400, 420, 440, 460, 480, 500, 520, 540, 560, 580, 600,
             620, 640, 660, 680, 700, 720, 740, 760, 780]
_SOLAR_ANCHORS = {
    # air_mass: relative direct-normal irradiance at _SOLAR_NM
    1.0: [0.62, 0.78, 0.95, 1.05, 1.12, 1.16, 1.18, 1.17, 1.15, 1.13, 1.11, 1.08,
          1.05, 1.02, 0.99, 0.96, 0.93, 0.90, 0.87, 0.84, 0.81],
    1.5: [0.45, 0.60, 0.78, 0.92, 1.02, 1.08, 1.12, 1.13, 1.13, 1.12, 1.11, 1.09,
          1.07, 1.05, 1.02, 1.00, 0.97, 0.95, 0.92, 0.90, 0.87],
    2.0: [0.33, 0.47, 0.65, 0.80, 0.92, 1.00, 1.06, 1.09, 1.10, 1.11, 1.11, 1.10,
          1.09, 1.07, 1.05, 1.03, 1.01, 0.99, 0.97, 0.94, 0.92],
    3.0: [0.18, 0.30, 0.46, 0.62, 0.76, 0.87, 0.95, 1.01, 1.05, 1.07, 1.09, 1.09,
          1.10, 1.09, 1.08, 1.07, 1.06, 1.04, 1.02, 1.01, 0.99],
}
SOLAR_AM_SPD = {am: _interp_anchors(_SOLAR_NM, vals) for am, vals in _SOLAR_ANCHORS.items()}

def _air_mass(zenith_deg):
    """Simple plane-parallel air mass AM = 1/cos(z), clamped (z in degrees)."""
    import math
    z = max(0.0, min(zenith_deg, 89.0))
    return 1.0 / math.cos(math.radians(z))

def solar_spd_for_zenith(zenith_deg):
    """401-value direct-normal solar SPD shape for a solar zenith angle, by air-mass interpolation."""
    am = _air_mass(zenith_deg)
    keys = sorted(SOLAR_AM_SPD)
    if am <= keys[0]:
        return list(SOLAR_AM_SPD[keys[0]])
    if am >= keys[-1]:
        return list(SOLAR_AM_SPD[keys[-1]])
    for i in range(len(keys) - 1):
        k0, k1 = keys[i], keys[i + 1]
        if k0 <= am <= k1:
            t = (am - k0) / (k1 - k0)
            s0, s1 = SOLAR_AM_SPD[k0], SOLAR_AM_SPD[k1]
            return [s0[j] + t * (s1[j] - s0[j]) for j in range(401)]
    return list(SOLAR_AM_SPD[keys[-1]])

# ---------- 2) CIE D-series eigenvectors S0/S1/S2 (380..780 @10 nm anchors) ----------
# CIE 15 / Wyszecki & Stiles daylight S0,S1,S2 (380-780nm @10nm), 41 values each.
# Authoritative values; interpolated to 1 nm below. By CIE construction the eigenvectors are
# anchored at 560nm (index 18): S0=100.0, S1=0.0, S2=0.0 — the daylight-reconstruction normalization
# point. (test_dseries_table_structural_anchor locks this so a future re-fabrication can't pass.)
_DS_NM = list(range(380, 790, 10))  # 380,390,...,780 (41 anchors)
_S0 = [63.4, 65.8, 94.8, 104.8, 105.9, 96.8, 113.9, 125.6, 125.5, 121.3, 121.3, 113.5, 113.1, 110.8, 106.5,
       108.8, 105.3, 104.4, 100.0, 96.0, 95.1, 89.1, 90.5, 90.3, 88.4, 84.0, 85.1, 81.9, 82.6, 84.9,
       81.3, 71.9, 74.3, 76.4, 63.3, 71.7, 77.0, 65.2, 47.7, 68.6, 65.0]
_S1 = [38.5, 35.0, 43.4, 46.3, 43.9, 37.1, 36.7, 35.9, 32.6, 27.9, 24.3, 20.1, 16.2, 13.2, 8.6,
       6.1, 4.2, 1.9, 0.0, -1.6, -3.5, -3.5, -5.8, -7.2, -8.6, -9.5, -10.9, -10.7, -12.0, -14.0,
       -13.6, -12.0, -13.3, -12.9, -10.6, -11.6, -12.2, -10.2, -7.8, -11.2, -10.4]
_S2 = [3.0, 1.2, -1.1, -0.5, -0.7, -1.2, -2.6, -2.9, -2.8, -2.6, -2.6, -1.8, -1.5, -1.3, -1.2,
       -1.0, -0.5, -0.3, 0.0, 0.2, 0.5, 2.1, 3.2, 4.1, 4.7, 5.1, 6.7, 7.3, 8.6, 9.8,
       10.2, 8.3, 9.6, 8.5, 7.0, 7.6, 8.0, 6.7, 5.2, 7.4, 6.8]
DSERIES_S0 = _interp_anchors(_DS_NM, _S0)
DSERIES_S1 = _interp_anchors(_DS_NM, _S1)
DSERIES_S2 = _interp_anchors(_DS_NM, _S2)

def dseries_xy_from_cct(cct):
    """CIE daylight-locus chromaticity (x,y) from a correlated color temperature (4000-25000 K)."""
    T = float(cct)
    if not (4000.0 <= T <= 25000.0):
        raise ValueError(
            f"CCT {T} K out of CIE daylight-locus range 4000-25000 K; "
            "dseries reconstruction is only valid for daylight CCTs in this domain")
    if T <= 7000.0:
        x = (-4.6070e9 / T**3) + (2.9678e6 / T**2) + (0.09911e3 / T) + 0.244063
    else:
        x = (-2.0064e9 / T**3) + (1.9018e6 / T**2) + (0.24748e3 / T) + 0.237040
    y = -3.000 * x * x + 2.870 * x - 0.275
    return x, y

def dseries_spd(cct):
    """Reconstruct a RELATIVE daylight SPD (401 pts) from a CCT via the CIE D-series S0/S1/S2 method."""
    x, y = dseries_xy_from_cct(cct)
    denom = 0.0241 + 0.2562 * x - 0.7341 * y
    m1 = (-1.3515 - 1.7703 * x + 5.9114 * y) / denom
    m2 = (0.0300 - 31.4424 * x + 30.0717 * y) / denom
    return [DSERIES_S0[i] + m1 * DSERIES_S1[i] + m2 * DSERIES_S2[i] for i in range(401)]
