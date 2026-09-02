"""IES LM-83-12 policy: period, analysis areas, grouping, blind operation, rollups.

Pure Python. Consumes illuminance matrices from the three-phase engine and the
zero-bounce sun pass; produces the metrics and the conditions they were computed on.

Section references are to IES LM-83-12. The model-input clauses of 2.2.8-2.2.11 (dirt
depreciation, frame reduction, obstruction/reflectance defaults, furniture) are OUT OF
SCOPE for this implementation -- see MODEL_INPUTS_DEPARTURE. The flag this module emits
is therefore `lm83_method_conformant`, never `lm83_conformant`.
"""
import math

from hcl_core.daylight_metrics import (annual_sunlight_exposure, daylight_autonomy,
                                       spatial_da)

#: 2.2.1 -- 10 h/day from 8AM to 6PM local clock, EVERY day of the year.
LM83_PERIOD_HOURS = 3650.0

#: 2.2.5 -- analysis points no more than 24 inches on centre. 24in = 0.6096 m exactly.
LM83_MAX_GRID_M = 0.6096
#: 2.2.2 -- the horizontal workplane is 30 inches / 0.8 m above finished floor.
LM83_WORKPLANE_M = 0.8
#: 2.2.6 -- "direct sunlight" is 1000 lux or more of DIRECT BEAM at an interior
#: horizontal point, accounting for window transmittance, excluding operable blinds,
#: with no reflected and no diffuse-sky contribution. The zero-bounce sun pass.
DIRECT_SUN_LUX = 1000.0
#: 2.2.6 discussion -- analysis areas for deriving blind schedules "shall be considered
#: by facade orientation, and never exceed 10,000 sf".
MAX_ANALYSIS_AREA_SQFT = 10000.0
#: 3.1.3 discussion -- ASE bands from the supporting field research.
ASE_NEUTRAL = 0.07
ASE_CLEARLY_ACCEPTABLE = 0.03
#: 2.2.1 discussion -- the supporting research covered 37-48 degrees N.
_LAT_BAND = (37.0, 48.0)

#: An international foot is exactly 0.3048 m, so a square foot is exactly this.
_SQM_PER_SQFT = 0.09290304

#: 2.2.1 requires the window be local CLOCK time with daylight-savings and longitude
#: adjustment, and its discussion requires the solar position of the half hour (hour 9's
#: band uses 08:30). We apply a fixed mask on the weather file's own time base, so both
#: are unmet. 2.3.1 allows 5 deg of solar-position error; half an hour is ~7.5 deg of
#: hour angle, so this is a genuine conformance gap, not a rounding choice.
SCHEDULE_DEPARTURE = (
    "analysis hours are a fixed 8:00-18:00 mask on the weather file's own time base: "
    "no daylight savings or longitude adjustment (2.2.1), and solar position is taken "
    "at the hour rather than the half hour (2.2.1 discussion), which exceeds 2.3.1's "
    "5 degree solar-position tolerance by about 7.5 degrees of hour angle")

#: 2.2.8-2.2.11 impose model-input requirements this implementation does NOT apply:
#: dirt depreciation, frame/occlusion reduction, window reveals, exterior obstruction
#: and ground defaults, interior reflectance defaults and zoning, and furniture. They
#: are out of scope by decision, so this departure is unconditional -- a result from
#: this tool is computed BY LM-83's method but is not an LM-83-compliant study.
MODEL_INPUTS_DEPARTURE = (
    "model-input clauses 2.2.8-2.2.11 are not applied or verified: no dirt depreciation "
    "(2.2.9 requires 5% on vertical glazing), no frame/occlusion reduction (2.2.9 "
    "requires 20% when framing is unknown), no window reveals, no exterior-obstruction "
    "or ground-reflectance defaults (2.2.8), no interior-reflectance defaults (2.2.10) "
    "and no furniture (2.2.11). Glazing is used at its raw tvis, so transmitted flux is "
    "overstated -- about 32% for an unknown-frame vertical window -- which biases sDA "
    "upward.")


def lm83_schedule(n_timesteps=8760, start_hour=8, end_hour=18):
    """LM-83's fixed analysis period as a per-timestep 0/1 mask.

    Deliberately NOT lighting_controls.default_schedule, which is weekdays-only (2610 h)
    and right for occupancy-driven work. LM-83 fixes an "asset value" period that counts
    weekends so designs on different operating schedules stay comparable (2.2.1).
    """
    if n_timesteps > 8760:
        raise ValueError(
            f"LM-83's period is defined in whole HOURS; got {n_timesteps} timesteps, more "
            f"than the 8760 in a year. A sub-hourly series (e.g. 17520 half-hours) would "
            f"silently rescale ASE's 250 h criterion, so it is rejected rather than "
            f"resampled.")
    if n_timesteps % 24 != 0:
        # A partial series carries no hour-of-day anchor, so every step is treated as
        # occupied. `_conditions` reports the period shortfall as a departure, which is
        # the honest answer: the metrics then describe the window simulated, not a year.
        return [1] * n_timesteps
    return [1 if start_hour <= (i % 24) < end_hour else 0 for i in range(n_timesteps)]


# --------------------------------------------------------------------------- grouping

_COMPASS = (("n", 0), ("ne", 45), ("e", 90), ("se", 135),
            ("s", 180), ("sw", 225), ("w", 270), ("nw", 315))


def _angular_gap(a, b):
    """Smallest angle between two bearings, wrapping across north."""
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _compass_label(azimuth):
    return min(_COMPASS, key=lambda c: _angular_gap(azimuth, c[1]))[0]


def _summarise(name, faces, source, role="undeclared"):
    """Area-weighted circular mean bearing plus the group's totals."""
    area = sum(f["area"] for f in faces)
    if area > 0:
        x = sum(f["area"] * math.sin(math.radians(f["azimuth_deg"])) for f in faces)
        y = sum(f["area"] * math.cos(math.radians(f["azimuth_deg"])) for f in faces)
        az = math.degrees(math.atan2(x, y)) % 360.0
    else:
        az = 0.0
    return {"name": name, "azimuth_deg": az, "area_m2": area, "n_faces": len(faces),
            "face_indices": sorted(f["index"] for f in faces),
            "role": role, "source": source}


def group_windows(faces, *, tolerance_deg=7.5, plane_tolerance_m=0.5, declared=None):
    """LM-83 window groups (2.2.6).

    The glossary defines a window group as "coplanar windows, with similar shadow
    patterns from exterior shading and obstructions, and with similar shading device type
    and operation, that are associated with the same analysis area". The +-7.5 degree
    azimuth rule appears only in a discussion box, as a PERMISSION ("may be considered in
    the same window group") -- not as the definition. So clustering keys on azimuth AND
    plane offset; azimuth alone merges parallel facades at opposite ends of a building.

    `role` ("view" | "clerestory") cannot be inferred from geometry -- 2.2.6's own example
    is the glazing above versus below a light shelf, which share an azimuth and a plane --
    so it defaults to "undeclared" and is reported as a departure.

    `declared` overrides auto entirely: [{"name", "face_indices", "role"?}].
    """
    if declared is not None:
        by_index = {f["index"]: f for f in faces}
        out = []
        for spec in declared:
            picked = []
            for idx in spec["face_indices"]:
                if idx not in by_index:
                    raise ValueError(
                        f"declared window group {spec['name']!r} names face index {idx}, "
                        f"which is not a glass face in this model")
                picked.append(by_index[idx])
            out.append(_summarise(spec["name"], picked, "declared",
                                  spec.get("role", "undeclared")))
        return out

    if not faces:
        return []
    clusters = []
    for face in sorted(faces, key=lambda f: (f["azimuth_deg"], f["plane_offset"])):
        for cluster in clusters:
            seed = cluster[0]
            if (_angular_gap(face["azimuth_deg"], seed["azimuth_deg"]) < tolerance_deg * 2
                    and abs(face["plane_offset"] - seed["plane_offset"]) <= plane_tolerance_m):
                cluster.append(face)
                break
        else:
            clusters.append([face])
    out = []
    for cluster in clusters:
        s = _summarise("", cluster, "auto")
        s["name"] = f"wg_{_compass_label(s['azimuth_deg'])}_{round(s['azimuth_deg']):03d}"
        out.append(s)
    return out


# ---------------------------------------------------------------------------- trigger

def direct_sun_point_limit(n_points, area_m2):
    """How many points may be in direct sun before blinds must close (2.2.6).

    The headline rule is 2% of analysis points, but 2.2.6's discussion fixes absolute
    counts below 1000 sf, where a 2 ft grid gives too few points for 2% to mean anything.

    The 2% branch is floored at 1: int(0.02 * n) is zero for any grid under 50 points,
    which would make a single sunlit point close the blinds -- a silent, unreported
    departure from the rule the standard actually states.
    """
    sqft = float(area_m2) / _SQM_PER_SQFT
    if sqft < 200:
        return 1
    if sqft < 500:
        return 3
    if sqft < 1000:
        return 5
    return max(1, int(0.02 * n_points))


def points_in_direct_sun(sun_lux_matrix, t, point_indices=None, threshold=DIRECT_SUN_LUX):
    """Analysis points seeing >= threshold of direct beam at timestep t.

    `point_indices` restricts the count to one analysis area's points; None counts all.
    """
    idx = range(len(sun_lux_matrix)) if point_indices is None else point_indices
    return sum(1 for p in idx if sun_lux_matrix[p][t] >= threshold)


def validate_analysis_areas(areas):
    """Enforce 2.2.6's constraints on analysis areas used to derive blind schedules.

    The 10,000 sf cap is scoped by the standard to "the purpose of deriving the blinds
    operation schedules" -- it constrains the TRIGGER domain, not the area over which sDA
    and ASE are reported. 2.2.4 explicitly allows reporting to accumulate across a whole
    building, so this must never be applied to a reporting area.
    """
    for area in areas:
        sqft = float(area["area_m2"]) / _SQM_PER_SQFT
        if sqft > MAX_ANALYSIS_AREA_SQFT:
            raise ValueError(
                f"trigger area {area['name']!r} is {sqft:,.0f} sf; LM-83 2.2.6 requires "
                f"areas used to derive blind schedules never exceed 10,000 sf. Split it "
                f"by facade orientation.")
        if not area.get("point_indices"):
            raise ValueError(
                f"trigger area {area['name']!r} has no analysis points; 2.2.6 requires "
                "grids that extend across the entire space")


# ----------------------------------------------------------------------------- states

#: 2.2.6 discussion asks that view window groups close before clerestory ones.
_ROLE_RANK = {"view": 0, "undeclared": 1, "clerestory": 2}


def closure_order(groups, sun_by_group, t):
    """Which window group to close first at timestep t (2.2.6).

    2.2.6's discussion says "it is advisable to close the blinds for the 'view' window
    groups first and 'clerestory' window groups last" -- advisable, in a discussion box,
    so guidance rather than a "shall". Role leads anyway, because ordering purely by
    direct-sun contribution inverts the guidance whenever a clerestory admits more beam
    than the view window below it, which at high sun is the common case.

    Contribution breaks ties within a role; name breaks full ties so runs reproduce.
    """
    def contribution(name):
        series = sun_by_group.get(name)
        return sum(row[t] for row in series) if series else 0.0
    return [g["name"] for g in sorted(
        groups,
        key=lambda g: (_ROLE_RANK.get(g.get("role", "undeclared"), 1),
                       -contribution(g["name"]), g["name"]))]


def resolve_states(groups, sun_by_group, sun_lux_matrix, occupancy, areas,
                   *, beam_pass_fraction=None, threshold=DIRECT_SUN_LUX):
    """Per timestep, the set of window groups whose blinds are closed (2.2.6).

    Closes groups one at a time in `closure_order` and stops the moment the criterion
    holds in EVERY trigger area, so N groups yield at most N+1 distinct states rather
    than the 2^N of every combination. 2.2.6 permits closing "in any combination", so
    searching only a fixed nested order is a simplification -- recorded as a departure
    by `_conditions` rather than left implicit.

    `beam_pass_fraction` maps a group to the share of its direct beam that still passes
    when closed -- a fabric shade's openness factor (2.2.7). Default 0: the shade is
    opaque to the beam, which is 2.2.7's no-specular default.

    `sun_by_group[name]` must be that group's OWN direct-sun contribution. Passing the
    whole-model series for every group lets closing one group cancel beam another group
    admitted, which satisfies the criterion with the wrong blind down.
    """
    passes = beam_pass_fraction or {}
    limits = [(a, direct_sun_point_limit(len(a["point_indices"]), a["area_m2"]))
              for a in areas]
    out = []
    for t, occ in enumerate(occupancy):
        if not occ or not sun_lux_matrix:
            out.append(frozenset())
            continue
        closed = set()
        order = closure_order(groups, sun_by_group, t)
        while True:
            satisfied = True
            for area, limit in limits:
                lit = 0
                for p in area["point_indices"]:
                    remaining = sun_lux_matrix[p][t]
                    for name in closed:
                        series = sun_by_group.get(name)
                        if series:
                            remaining -= series[p][t] * (1.0 - passes.get(name, 0.0))
                    if max(0.0, remaining) >= threshold:
                        lit += 1
                if lit > limit:
                    satisfied = False
                    break
            if satisfied:
                break
            nxt = next((n for n in order if n not in closed), None)
            if nxt is None:
                break                 # every group closed; nothing further can be done
            closed.add(nxt)
        out.append(frozenset(closed))
    return out


def select_illuminance(state_matrices, states):
    """Assemble the operated illuminance: at each timestep take that state's matrix.

    `state_matrices` maps a frozenset of closed group names to a points x timesteps lux
    matrix. A state with no matrix is a KeyError rather than a fallback: silently
    substituting the open state would report an unoperated blind as an operated one.
    """
    if not states:
        return []
    for state in states:
        if state not in state_matrices:
            raise KeyError(f"no illuminance matrix simulated for state "
                           f"{sorted(state) or ['<all open>']}")
    n_pts = len(state_matrices[states[0]])
    return [[state_matrices[state][p][t] for t, state in enumerate(states)]
            for p in range(n_pts)]


# ---------------------------------------------------------------------------- metrics

def grid_geometry(points):
    """Measure 2.2.5/2.2.2 grid facts from the sensor points themselves.

    A caller-supplied grid spacing is an assertion; the grid is a fact. Spacing is the
    smallest positive centre-to-centre distance, which is what "no greater than 24 inches
    on center" constrains. Uses a coordinate sort so a large grid does not cost O(n^2):
    for each point only the neighbours within the current best distance in x are probed.
    """
    pts = [(float(p[0]), float(p[1])) for p in points]
    zs = [float(p[2]) for p in points]
    spacing = None
    order = sorted(range(len(pts)), key=lambda i: pts[i][0])
    for a in range(len(order)):
        xa, ya = pts[order[a]]
        for b in range(a + 1, len(order)):
            xb, yb = pts[order[b]]
            if spacing is not None and (xb - xa) >= spacing:
                break                     # sorted by x: no later point can be closer
            d = math.hypot(xa - xb, ya - yb)
            if d > 1e-9 and (spacing is None or d < spacing):
                spacing = d
    return {"n_points": len(points), "spacing_m": spacing,
            "workplane_z": (sum(zs) / len(zs)) if zs else None,
            "workplane_z_spread": (max(zs) - min(zs)) if zs else 0.0}


def _conditions(occupancy, groups, points, areas, blind_source, latitude):
    """Every LM-83 condition this layer can see, and whether each is met."""
    occupied_hours = float(sum(1 for o in occupancy if o > 0))
    grid = grid_geometry(points)
    departures = [MODEL_INPUTS_DEPARTURE, SCHEDULE_DEPARTURE]

    if abs(occupied_hours - LM83_PERIOD_HOURS) > 1.0:
        departures.append(
            f"analysis period is {occupied_hours:g} occupied hours against LM-83's "
            f"{LM83_PERIOD_HOURS:g} h (2.2.1: 10 h/day, every day of the year)")
    if grid["spacing_m"] is None:
        departures.append("grid spacing could not be measured from the supplied points "
                          "(2.2.5 requires a continuous grid)")
    elif grid["spacing_m"] > LM83_MAX_GRID_M:
        departures.append(
            f"grid spacing is {grid['spacing_m']:.4g} m against LM-83's maximum "
            f"{LM83_MAX_GRID_M:.4g} m / 24 in on centre (2.2.5)")
    if grid["workplane_z"] is not None and abs(grid["workplane_z"] - LM83_WORKPLANE_M) > 0.05:
        departures.append(
            f"workplane height is {grid['workplane_z']:.3g} m against LM-83's "
            f"{LM83_WORKPLANE_M:g} m / 30 in above finished floor (2.2.2)")
    departures.append(
        "wall offset was not verified: 2.2.5 requires analysis points sit 12-24 in from "
        "the walls, which needs the room boundary this layer is not given")
    if not groups:
        departures.append("no window group was identified, so no blind could be operated "
                          "(2.2.6 requires every exterior window to carry one)")
    if any(g.get("role", "undeclared") == "undeclared" for g in groups):
        departures.append(
            "window-group role (view / clerestory) was not declared, so 2.2.6's guidance "
            "that view groups close before clerestory ones could not be applied; closure "
            "fell back to direct-sun contribution")
    if len(groups) > 1:
        departures.append(
            "blind closure searched a fixed nested order rather than every combination; "
            "2.2.6 permits groups to close 'in any combination', so a smaller closed set "
            "may exist for some hours")
    if blind_source is None:
        departures.append("no blind was modelled or substituted (2.2.6)")
    if latitude is not None and not (_LAT_BAND[0] <= abs(float(latitude)) <= _LAT_BAND[1]):
        departures.append(
            f"site latitude {latitude:g} deg is outside the 37-48 deg band the supporting "
            f"research covered; 2.2.1 asks that this uncertainty be noted")
    return {"occupied_hours": occupied_hours, "lm83_period_hours": LM83_PERIOD_HOURS,
            "grid": grid, "max_grid_spacing_m": LM83_MAX_GRID_M,
            "blind_source": blind_source or "none",
            "window_groups": [dict(g) for g in groups],
            "trigger_areas": [{k: v for k, v in a.items() if k != "point_indices"}
                              for a in areas],
            "lm83_method_conformant": not departures,
            "scope": "method_only",
            "departures": departures,
            "model_inputs_note": MODEL_INPUTS_DEPARTURE}


def _sda_criterion(sda):
    """2.1.3: 75% or more is 'preferred', 55% or more 'nominally accepted'."""
    if sda >= 0.75:
        return "preferred"
    if sda >= 0.55:
        return "nominally_accepted"
    return "below_criteria"


def _ase_criterion(ase):
    """3.1.3 discussion: under 3% clearly acceptable, under 7% neutral."""
    if ase < ASE_CLEARLY_ACCEPTABLE:
        return "clearly_acceptable"
    if ase < ASE_NEUTRAL:
        return "neutral"
    return "unsatisfactory"


def lm83_metrics(operated_lux, sun_lux_open, occupancy, *, groups, points, areas,
                 blind_source, latitude=None, no_blind_lux=None,
                 declared_no_blinds=False):
    """LM-83 sDA300/50% and ASE1000,250h with the conditions they were computed on.

    `operated_lux` is the blind-operated illuminance (points x timesteps); `sun_lux_open`
    is the zero-bounce direct-sun series with every operable blind OPEN, which is what
    3.2.6 requires for ASE. `no_blind_lux`, when supplied, is the illuminance with blinds
    never deployed -- reported as 2.2.6's alternative case, never substituted.

    The ASE hour test is strictly greater than 250 h, matching the existing
    `annual_sunlight_exposure`. 3.1.2 says "more than 250 hours" and 3.2.3 says "250
    hours or more"; the standard differs from itself by one hour, and `ase_hour_rule`
    records which reading was taken.
    """
    da = [daylight_autonomy(series, occupancy, 300.0) for series in operated_lux]
    sda = spatial_da(da, 0.5)
    ase = annual_sunlight_exposure(sun_lux_open, occupancy, 1000.0, 250.0, 1.0)
    out = {
        "sDA": sda, "sda_criterion": _sda_criterion(sda),
        "ASE": ase["ase"], "ase_criterion": _ase_criterion(ase["ase"]),
        "ASE_per_point_hours": ase["per_point_hours"],
        "ase_hour_rule": ("strictly more than 250 h, for continuity with annual_daylight; "
                          "3.1.2 says 'more than 250 hours' while 3.2.3 says '250 hours "
                          "or more', so the standard differs from itself by one hour"),
        "per_point_DA": da,
        "conditions": _conditions(occupancy, groups, points, areas, blind_source, latitude),
    }
    if no_blind_lux is not None:
        ase_ok = ase["ase"] <= ASE_NEUTRAL
        nb_da = [daylight_autonomy(s, occupancy, 300.0) for s in no_blind_lux]
        out["no_blind_case"] = {
            "ase_condition_met": ase_ok,
            "design_documents_declare_no_blinds": bool(declared_no_blinds),
            "applies": bool(ase_ok and declared_no_blinds),
            "sDA": spatial_da(nb_da, 0.5),
            "note": ("2.2.6 permits omitting blinds only when BOTH hold: design documents "
                     "state none will be installed, AND the window group's ASE meets the "
                     f"'nominally acceptable' criterion (<= {ASE_NEUTRAL:.0%}). This block "
                     "reports that alternative case; it is not substituted for the "
                     "headline sDA, which is always computed with blinds operated. The "
                     "ASE condition here is evaluated for the whole model, not per window "
                     "group as 2.2.6 scopes it."),
        }
    return out
