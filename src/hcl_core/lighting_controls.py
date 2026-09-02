"""Daylight-responsive electric-lighting controls & energy savings.

A faithful pure-Python port of the EnergyPlus Engineering Reference §7.3.5 lighting-control model
(Continuous / Continuous-Off / Stepped + Lighting Power Reduction), verified against the user's
`elec_lights.xlsx`. PURE PYTHON, NO DEPENDENCIES; imports nothing from hcl_radiance/hcl_mcp.

Two semantics:
  * DEFAULT  (EnergyPlus-faithful): Itot=0 -> fL=1 (full electric at genuine darkness). "No sensor
    reading" is a DISTINCT state (None / occupancy-off hour), never Itot==0.
  * workbook_compat=True reproduces elec_lights.xlsx's TWO off-gates so the §5.4 spreadsheet
    regression goldens reproduce: (i) Itot==0 -> fL=0, and (ii) within Continuous, fL==0 -> fP=0
    (instead of the EnergyPlus fP=fP_min floor). The default model does NEITHER.
"""
import math

# Defaults (all overridable). See spec §5.2.
DEFAULT_CONTROL_TYPE = "ContinuousOff"
DEFAULT_ISET = 500.0      # lx setpoint (EN 12464-1 office writing/reading; matches workbook)
DEFAULT_FP_MIN = 0.15     # minimum power fraction (elec_lights.xlsx)
DEFAULT_FL_MIN = 0.05     # minimum light fraction (elec_lights.xlsx)
DEFAULT_N_STEPS = 3       # stepped control only

_CONTROL_TYPES = ("Continuous", "ContinuousOff", "Stepped")


def light_fraction(itot, iset, *, workbook_compat=False):
    """Light-output fraction the electric system must supply at one reference point.

    fL = max(0, (iset - itot) / iset). DEFAULT is EnergyPlus-faithful: itot=0 -> fL=1 (full electric
    at darkness). workbook_compat=True adds the elec_lights.xlsx gate itot==0 -> fL=0.
    """
    if workbook_compat and itot == 0:
        return 0.0
    return max(0.0, (iset - itot) / iset)


def power_fraction(fL, *, control_type, fP_min, fL_min, n_steps, workbook_compat=False):
    """Power-input fraction for one reference point given its light fraction fL.

    Continuous:    fP_min                                  if fL < fL_min
                   (fL + (1-fL)*fP_min - fL_min)/(1-fL_min) if fL_min <= fL <= 1
                   (with workbook_compat=True ALSO: fL==0 -> fP=0, the sheet's extra gate)
    ContinuousOff: as Continuous, but fP=0 when fL < fL_min (lamp switched off) -- the DEFAULT.
    Stepped:       0 if fL==0; 1 if fL==1; else (floor(n_steps*fL)+1)/n_steps  (EnergyPlus form).
    """
    if control_type not in _CONTROL_TYPES:
        raise ValueError(f"control_type must be one of {_CONTROL_TYPES}, got {control_type!r}")

    if control_type == "Stepped":
        if fL == 0:
            return 0.0
        if fL == 1:
            return 1.0
        return (math.floor(n_steps * fL) + 1) / n_steps

    # Continuous / ContinuousOff share the blend; they differ only below fL_min.
    if fL < fL_min:
        if control_type == "ContinuousOff":
            return 0.0
        # Continuous: the sheet's extra gate fL==0 -> fP=0 only under workbook_compat.
        if workbook_compat and fL == 0:
            return 0.0
        return fP_min
    return (fL + (1.0 - fL) * fP_min - fL_min) / (1.0 - fL_min)


_WEIGHT_EPS = 1e-6  # tolerance for sum(weights) <= 1


def zone_power_fraction(fps, weights):
    """Zone power fraction FP = Σ fP_i·W_i + (1 − Σ W_i) (EnergyPlus Lighting Power Reduction).

    `weights` are floor-AREA FRACTIONS of each daylight-controlled zone (perimeter, mid, …), NOT
    one-per-zone full-power flags: they must sum to ≤ 1 (so e.g. two zones cannot both be 1.0).
    The remainder term (1 − Σ W) is the uncontrolled core area running at full power. Validates
    Σ W ≤ 1 (within a small epsilon); a Σ W slightly over 1 clamps the remainder to 0. Use
    area_weights_from_geometry(...) to derive the fractions from room dimensions.
    """
    if len(fps) != len(weights):
        raise ValueError(f"need one control fraction per weight: got {len(fps)} point value(s) "
                         f"for {len(weights)} weight(s)")
    # Check EACH weight, not only their sum. Weights are floor-AREA fractions, so a negative one is
    # not physical - and it hides inside a valid-looking total: (-0.075, 1.075) sums to exactly 1.0,
    # passed the sum check, and produced FP = -0.075, i.e. a 250 W installation reporting -18.7 W
    # consumed and 107.5 % saved.
    neg = [(i, w) for i, w in enumerate(weights) if w < -_WEIGHT_EPS]
    if neg:
        detail = ", ".join(f"weights[{i}]={w}" for i, w in neg)
        raise ValueError(
            f"negative zone weight ({detail}). Weights are floor-area fractions and cannot be "
            f"negative; a negative one yields negative power and >100% savings. Check the "
            f"geometry that produced them (window_head below task_height gives a negative "
            f"primary depth).")
    total_w = sum(weights)
    if total_w > 1.0 + _WEIGHT_EPS:
        raise ValueError(f"sum(weights)={total_w} exceeds 1.0")
    remainder = max(0.0, 1.0 - total_w)
    return sum(fp * w for fp, w in zip(fps, weights)) + remainder


def controls_point(itot_per_point, weights, *, iset, control_type, fP_min, fL_min, n_steps,
                   p_rated, schedule=1.0, workbook_compat=False):
    """One time step. Returns {fL[], fP[], FP, P_elec, P_saved, reduction}.

    P_elec = p_rated·schedule·FP ; P_saved = p_rated·schedule·(1 − FP) ; reduction = 1 − FP.
    """
    fLs = [light_fraction(itot, iset, workbook_compat=workbook_compat) for itot in itot_per_point]
    fPs = [power_fraction(fL, control_type=control_type, fP_min=fP_min, fL_min=fL_min,
                          n_steps=n_steps, workbook_compat=workbook_compat) for fL in fLs]
    FP = zone_power_fraction(fPs, weights)
    return {"fL": fLs, "fP": fPs, "FP": FP,
            "P_elec": p_rated * schedule * FP,
            "P_saved": p_rated * schedule * (1.0 - FP),
            "reduction": 1.0 - FP}


def area_weights_from_geometry(width, length, window_head, task_height):
    """(W_primary, W_secondary) from room geometry (the elec_lights.xlsx geometry helper).

    primary_depth = 2.5·(window_head − task_height); area_primary = primary_depth·width, capped at
    the total floor area; W = area/area_total. The secondary zone is the remainder.
    """
    area_tot = width * length
    # Clamp at 0 as well as capping at the floor area. A window head BELOW the working plane makes
    # (window_head - task_height) negative, and an unclamped negative depth becomes a negative area
    # fraction -> negative power. There is no negative daylit area; the physical reading is simply
    # "no primary zone".
    primary_depth = max(0.0, 2.5 * (window_head - task_height))
    area_pr = min(primary_depth * width, area_tot)
    w_primary = area_pr / area_tot
    return (w_primary, 1.0 - w_primary)


def default_schedule(year_hours=8760, occupied_start=8, occupied_end=18):
    """Occupancy schedule: 1.0 on weekday hours in [occupied_start, occupied_end), else 0.0.

    Convention: HOY 0 = Monday 00:00 (day-of-week = (hour // 24) % 7, 0..4 = Mon..Fri).
    Returns a list of length year_hours (default 8760).
    """
    sched = []
    for h in range(year_hours):
        dow = (h // 24) % 7
        hour_of_day = h % 24
        on = dow < 5 and occupied_start <= hour_of_day < occupied_end
        sched.append(1.0 if on else 0.0)
    return sched


def controls_series(itot_series, weights, *, schedule, area, workbook_compat=False, **params):
    """Run a time series of per-point daylight illuminances through controls_point.

    itot_series : list of per-hour [itot_point_1, itot_point_2, ...] (e.g. 8760 rows).
    schedule    : per-hour occupancy multiplier (list), or None for default_schedule(). Only hours
                  with schedule > 0 are "occupied" — savings/energy are summed over occupied hours.
    area        : floor area (m²) for the per-m² normalization.
    params      : iset, control_type, fP_min, fL_min, n_steps, p_rated (passed to controls_point).

    Returns {per_hour[...], annual_kwh, annual_kwh_per_m2, mean_FP, mean_reduction, occupied_hours}.
    annual_kwh_per_m2 = Σ consumed_Wh / 1000 / area (consumed over occupied hours only).
    """
    if schedule is None:
        schedule = default_schedule(len(itot_series))
    if len(schedule) != len(itot_series):
        # zip() would silently truncate to the shorter, dropping tail hours from the annual energy
        # sum and reporting an under-count as a valid result. Fail loudly on the mismatch instead.
        raise ValueError(
            f"schedule length ({len(schedule)}) must match itot_series length ({len(itot_series)})")
    per_hour = []
    for itot, sch in zip(itot_series, schedule):
        if sch <= 0:
            continue  # unoccupied: lights off, no consumption, excluded from occupied hours
        per_hour.append(controls_point(itot, weights, schedule=sch, workbook_compat=workbook_compat,
                                       **params))
    consumed_wh = sum(h["P_elec"] for h in per_hour)  # each P_elec is Wh over a 1-hour step
    occupied = len(per_hour)
    mean_fp = (sum(h["FP"] for h in per_hour) / occupied) if occupied else 0.0
    total_w = sum(weights)
    uncontrolled = max(0.0, 1.0 - total_w)
    return {"per_hour": per_hour,
            "annual_kwh": consumed_wh / 1000.0,
            "annual_kwh_per_m2": (consumed_wh / 1000.0 / area) if area else 0.0,
            "mean_FP": mean_fp,
            "mean_reduction": 1.0 - mean_fp,
            "occupied_hours": occupied,
            # Coverage is echoed because it CAPS the result: whatever the daylight, the saving
            # can never exceed sum(weights). Two shipped zoning helpers disagree about what the
            # weights should be for the same room (photosensors zones vs
            # area_weights_from_geometry), so the assumption must be visible in the result that
            # depends on it rather than inferable only from the caller's choice of helper.
            "sum_weights": total_w,
            "uncontrolled_fraction": uncontrolled,
            "coverage_note": (
                f"{uncontrolled * 100:.1f}% of the floor lies outside every daylight-controlled "
                f"zone and is billed at full power, capping the achievable saving at "
                f"{total_w * 100:.1f}%." if uncontrolled > 1e-9 else
                "Weights sum to 1.0: the whole floor is treated as daylight-controlled. Confirm "
                "that is physically true — an uncontrolled core would lower the saving.")}
