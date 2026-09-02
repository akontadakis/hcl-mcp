"""Climate-based (photopic) daylight metrics: DA / cDA / UDI / sDA / ASE.

Pure Python, no Radiance dependency. Consumes a points x timesteps illuminance
matrix produced by hcl_radiance.annual_daylight.
"""
from hcl_core.data import LUMINOUS_EFFICACY, W_PHOTOPIC_3, W_PHOTOPIC_9


def rgb_to_photopic_lux(rgb_matrix, channel_type):
    """[n_points][n_timesteps][n_channels] RGB -> [n_points][n_timesteps] photopic lux.

    Uses the verified Radiance luminous-efficacy weighting (data.py). n_channels must be
    3 (channel_type=0) or 9 (channel_type=1), matching W_PHOTOPIC_3 / W_PHOTOPIC_9.
    """
    weights = W_PHOTOPIC_3 if channel_type == 0 else W_PHOTOPIC_9
    n = len(weights)
    out = []
    for series in rgb_matrix:
        row = []
        for ch in series:
            if len(ch) != n:
                raise ValueError(f"expected {n} channels for channel_type={channel_type}, got {len(ch)}")
            row.append(LUMINOUS_EFFICACY * sum(w * float(c) for w, c in zip(weights, ch)))
        out.append(row)
    return out


def _occupied_indices(occupancy):
    return [i for i, o in enumerate(occupancy) if o > 0]


def daylight_autonomy(lux_series, occupancy, threshold=300.0):
    """Fraction of OCCUPIED timesteps with illuminance >= threshold (0..1)."""
    occ = _occupied_indices(occupancy)
    if not occ:
        return 0.0
    met = sum(1 for i in occ if lux_series[i] >= threshold)
    return met / len(occ)


def continuous_da(lux_series, occupancy, threshold=300.0):
    """Continuous DA: partial credit min(1, E/threshold) averaged over occupied timesteps."""
    occ = _occupied_indices(occupancy)
    if not occ:
        return 0.0
    if threshold <= 0:
        return 1.0
    return sum(min(1.0, lux_series[i] / threshold) for i in occ) / len(occ)


def udi_bins(lux_series, occupancy, lower=100.0, upper_sup=300.0, upper_aut=3000.0):
    """Useful Daylight Illuminance fractions over occupied hours.

    short:        E < lower
    supplementary: lower <= E < upper_sup
    autonomous:   upper_sup <= E < upper_aut
    exceed:       E >= upper_aut
    """
    occ = [lux_series[i] for i in _occupied_indices(occupancy)]
    n = len(occ)
    if n == 0:
        return {"short": 0.0, "supplementary": 0.0, "autonomous": 0.0, "exceed": 0.0}
    short = sum(1 for e in occ if e < lower)
    sup = sum(1 for e in occ if lower <= e < upper_sup)
    aut = sum(1 for e in occ if upper_sup <= e < upper_aut)
    exc = sum(1 for e in occ if e >= upper_aut)
    return {"short": short / n, "supplementary": sup / n, "autonomous": aut / n, "exceed": exc / n}


def spatial_da(per_point_da, da_fraction=0.5):
    """Fraction of points whose Daylight Autonomy >= da_fraction (LM-83/LEED sDA spatial rollup).

    This is the ARITHMETIC of sDA, not a conformance verdict: LM-83 additionally fixes the shading
    model, the analysis period and the grid spacing, none of which this function can see. Callers
    reach it through `daylight_metrics`, which returns the basis alongside in `sDA_basis`.
    """
    if not per_point_da:
        return 0.0
    return sum(1 for d in per_point_da if d >= da_fraction) / len(per_point_da)


def annual_sunlight_exposure(sun_lux_matrix, occupancy, threshold=1000.0, hour_limit=250.0,
                             step_hours=1.0):
    """LEED ASE: fraction of points seeing DIRECT sun >= threshold for more than hour_limit
    occupied hours. sun_lux_matrix is the direct-only (-ab 0) per-point lux series.
    """
    n_pts = len(sun_lux_matrix)
    if n_pts == 0:
        return {"ase": 0.0, "per_point_hours": []}
    occ = _occupied_indices(occupancy)
    per_point_hours, over = [], 0
    for series in sun_lux_matrix:
        h = sum(step_hours for i in occ if series[i] >= threshold)
        per_point_hours.append(h)
        if h > hour_limit:
            over += 1
    return {"ase": over / n_pts, "per_point_hours": per_point_hours}


#: LM-83 fixes the analysis period at 10 h/day for EVERY day of the year.
_LM83_PERIOD_HOURS = 3650.0


def _sda_basis(occupancy, step_hours, shading_model):
    """What basis the `sDA` key was computed on, so a caller cannot read it as LM-83 by default.

    `sDA` is the name of a compliance metric with conditions attached, and this function returns
    every condition this layer can actually see. Shading it cannot see -- the scene is upstream --
    so `shading_model` is a caller declaration, and an undeclared one is reported as undeclared
    rather than assumed conformant. A result that omits the condition is not interpretable, and
    the whole point of emitting this block is that the bare number is not self-describing.
    """
    occupied_hours = len(_occupied_indices(occupancy)) * float(step_hours)
    reasons = []
    if shading_model is None:
        reasons.append("shading model not declared by the caller")
    elif shading_model == "none":
        reasons.append("no operable shading device modelled, and LM-83's default blind "
                       "was not substituted")
    if abs(occupied_hours - _LM83_PERIOD_HOURS) > 1.0:
        reasons.append(f"analysis period is {occupied_hours:g} occupied hours against LM-83's "
                       f"{_LM83_PERIOD_HOURS:g} h (10 h/day, every day of the year)")
    return {
        "shading_model": shading_model or "undeclared",
        "occupied_hours": round(occupied_hours, 4),
        "lm83_period_hours": _LM83_PERIOD_HOURS,
        "lm83_conformant": not reasons,
        "departures": reasons,
        "note": ("`sDA` is the LM-83 spatial rollup computed on the basis recorded here. It is an "
                 "LM-83 sDA only when `lm83_conformant` is true; otherwise it is the underlying "
                 "DA-based spatial fraction and must not be entered into an LM-83 or LEED "
                 "submission. ASE is defined with operable shading left open, so it is unaffected "
                 "by the shading departure, but its 250 h criterion is an absolute hour count and "
                 "a period shorter than LM-83's understates it."),
    }


def daylight_metrics(lux_matrix, occupancy, *, da_threshold=300.0, udi=(100.0, 300.0, 3000.0),
                     sda_da_fraction=0.5, ase_threshold=1000.0, ase_hours=250.0,
                     sun_lux_matrix=None, step_hours=1.0, partial_year=False,
                     shading_model=None):
    """Per-point DA/cDA/UDI + spatial sDA/ASE/DA_avg from a points x timesteps lux matrix."""
    per_point, da_list = [], []
    for series in lux_matrix:
        da = daylight_autonomy(series, occupancy, da_threshold)
        cda = continuous_da(series, occupancy, da_threshold)
        bins = udi_bins(series, occupancy, *udi)
        da_list.append(da)
        per_point.append({"DA": da, "cDA": cda,
                          "UDI_short": bins["short"], "UDI_supplementary": bins["supplementary"],
                          "UDI_autonomous": bins["autonomous"], "UDI_exceed": bins["exceed"]})
    spatial = {
        "sDA": spatial_da(da_list, sda_da_fraction),
        "DA_avg": (sum(da_list) / len(da_list)) if da_list else 0.0,
        "UDI_autonomous_avg": (sum(p["UDI_autonomous"] for p in per_point) / len(per_point))
                              if per_point else 0.0,
    }
    if sun_lux_matrix is not None:
        a = annual_sunlight_exposure(sun_lux_matrix, occupancy, ase_threshold, ase_hours, step_hours)
        spatial["ASE"] = a["ase"]
        spatial["ASE_per_point_hours"] = a["per_point_hours"]
    out = {"per_point": per_point, "spatial": spatial,
           "sDA_basis": _sda_basis(occupancy, step_hours, shading_model)}
    if partial_year:
        # sDA/ASE/DA are defined over a full occupied YEAR. On a subset the names still apply to
        # the window actually simulated, so flag it AND say what the caveat is -- ASE's 250 h
        # criterion in particular can never be met by a window shorter than 250 occupied hours, so
        # a partial-year ASE of 0 means "not enough hours", not "no direct sun problem".
        out["partial_year"] = True
        out["partial_year_note"] = (
            "Metrics cover only the simulated window, not a full year. sDA/DA/UDI are fractions of "
            "the supplied occupied hours; ASE's 250 h threshold is a FULL-YEAR criterion and cannot "
            "be reached by a shorter window, so a low ASE here is not evidence of no glare risk.")
    return out
