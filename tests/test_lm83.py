import math
import pytest
from hcl_core.lm83 import (LM83_MAX_GRID_M, LM83_PERIOD_HOURS, MAX_ANALYSIS_AREA_SQFT,
                           MODEL_INPUTS_DEPARTURE, SCHEDULE_DEPARTURE, closure_order,
                           direct_sun_point_limit, grid_geometry, group_windows,
                           lm83_metrics, lm83_schedule, points_in_direct_sun,
                           resolve_states, select_illuminance, validate_analysis_areas)


# ------------------------------------------------------------------------- schedule

def test_period_constant_is_3650_hours():
    assert LM83_PERIOD_HOURS == 3650.0


def test_schedule_has_exactly_3650_occupied_hours():
    """10 h/day x 365 days. Not 2610 -- 2.2.1 counts weekends."""
    assert sum(lm83_schedule()) == 3650


def test_schedule_covers_weekends():
    sched = lm83_schedule()
    for day in (5, 6):
        assert sum(sched[day * 24:(day + 1) * 24]) == 10


def test_occupied_hours_are_8_through_17_inclusive():
    day0 = lm83_schedule()[0:24]
    assert day0[7] == 0 and day0[8] == 1
    assert day0[17] == 1 and day0[18] == 0


def test_rejects_a_subhourly_timestep_count():
    """ASE's 250 h criterion is an hour count; a sub-hourly mask would rescale it."""
    with pytest.raises(ValueError, match="8760"):
        lm83_schedule(17520)


def test_the_dst_and_half_hour_gap_is_named_not_hidden():
    assert "daylight savings" in SCHEDULE_DEPARTURE
    assert "half hour" in SCHEDULE_DEPARTURE


# ------------------------------------------------------------------------- grouping

def _face(idx, az, area=1.0, offset=0.0):
    return {"group": "glazing", "index": idx, "verts": [], "area": area,
            "normal": (0, 0, 0), "azimuth_deg": az, "tilt_deg": 90.0,
            "centroid": (0, 0, 0), "plane_offset": offset}


def test_faces_within_tolerance_become_one_group():
    groups = group_windows([_face(0, 180.0), _face(1, 184.0)])
    assert len(groups) == 1
    assert groups[0]["n_faces"] == 2 and groups[0]["source"] == "auto"


def test_faces_beyond_tolerance_split():
    assert len(group_windows([_face(0, 180.0), _face(1, 0.0)])) == 2


def test_boundary_is_fifteen_degrees_total_spread():
    """2.2.6 discussion: within 15 degrees of the same orientation, i.e. +-7.5."""
    assert len(group_windows([_face(0, 0.0), _face(1, 14.9)])) == 1
    assert len(group_windows([_face(0, 0.0), _face(1, 15.1)])) == 2


def test_grouping_wraps_around_north():
    assert len(group_windows([_face(0, 359.0), _face(1, 1.0)])) == 1


def test_parallel_but_separate_facades_are_not_one_group():
    """2.2.6 glossary: a window group is COPLANAR windows. Same azimuth is not enough."""
    assert len(group_windows([_face(0, 180.0, offset=0.0),
                              _face(1, 180.0, offset=0.1)])) == 1
    assert len(group_windows([_face(0, 180.0, offset=0.0),
                              _face(1, 180.0, offset=12.0)])) == 2


def test_group_names_are_compass_labelled():
    """Faces at 90 and 92 of equal area average to 91, so the label carries 091."""
    groups = group_windows([_face(0, 180.0), _face(1, 90.0), _face(2, 92.0)])
    assert sorted(g["name"] for g in groups) == ["wg_e_091", "wg_s_180"]


def test_area_is_summed_and_azimuth_is_the_circular_mean():
    """The circular mean is deliberately not the arithmetic mean: it wraps correctly."""
    groups = group_windows([_face(0, 178.0, area=3.0), _face(1, 182.0, area=1.0)])
    assert groups[0]["area_m2"] == 4.0
    assert abs(groups[0]["azimuth_deg"] - 179.0) < 1e-3


def test_role_defaults_to_undeclared():
    """2.2.6 wants view groups closed before clerestory; geometry cannot tell them apart."""
    assert group_windows([_face(0, 180.0)])[0]["role"] == "undeclared"


def test_declared_groups_override_auto_and_carry_their_role():
    groups = group_windows([_face(0, 180.0), _face(1, 0.0)],
                           declared=[{"name": "all_glass", "face_indices": [0, 1],
                                      "role": "view"}])
    assert len(groups) == 1
    assert groups[0]["name"] == "all_glass" and groups[0]["source"] == "declared"
    assert groups[0]["role"] == "view" and groups[0]["n_faces"] == 2


def test_declared_group_naming_an_unknown_face_is_an_error():
    with pytest.raises(ValueError, match="9"):
        group_windows([_face(0, 180.0)], declared=[{"name": "x", "face_indices": [0, 9]}])


def test_no_glass_faces_yields_no_groups():
    assert group_windows([]) == []


# -------------------------------------------------------------------------- trigger

def test_large_area_uses_the_two_percent_rule():
    assert direct_sun_point_limit(100, 111.5) == 2       # 1200 sf


def test_small_area_thresholds_from_2_2_6():
    """Under 1000 sf the 2% rule shows sampling error, so 2.2.6 fixes counts."""
    assert direct_sun_point_limit(100, 18.0) == 1        # 194 sf
    assert direct_sun_point_limit(100, 30.0) == 3        # 323 sf
    assert direct_sun_point_limit(100, 70.0) == 5        # 753 sf
    assert direct_sun_point_limit(100, 120.0) == 2       # 1292 sf


def test_two_percent_never_truncates_to_zero():
    """int(0.02*n) is 0 below 50 points, which would close blinds on ONE sunlit point."""
    for n in (1, 12, 30, 49):
        assert direct_sun_point_limit(n, 200.0) == 1


def test_band_boundaries_use_the_exact_foot():
    """A sqft conversion rounded to 10.7639 flips the limit at the band edges."""
    exactly_200_sf = 200 * 0.09290304
    assert direct_sun_point_limit(100, exactly_200_sf) == 3
    assert direct_sun_point_limit(100, exactly_200_sf - 1e-9) == 1


def test_counts_points_over_1000_lux_at_a_timestep():
    m = [[1200.0, 0.0], [800.0, 0.0], [5000.0, 0.0]]
    assert points_in_direct_sun(m, 0) == 2
    assert points_in_direct_sun(m, 1) == 0


def test_threshold_is_inclusive_at_1000_lux():
    """2.2.6: '1,000 lux or more of direct beam sunlight'."""
    assert points_in_direct_sun([[1000.0]], 0) == 1
    assert points_in_direct_sun([[999.9]], 0) == 0


def test_counting_can_be_restricted_to_one_areas_points():
    m = [[1200.0], [1200.0], [0.0]]
    assert points_in_direct_sun(m, 0, point_indices=[2]) == 0
    assert points_in_direct_sun(m, 0, point_indices=[0, 2]) == 1


def test_trigger_area_over_ten_thousand_sf_is_rejected():
    """2.2.6: areas used to derive blind schedules 'shall ... never exceed 10,000 sf'."""
    with pytest.raises(ValueError, match="10,000 sf"):
        validate_analysis_areas([{"name": "floor", "area_m2": 1000.0,
                                  "point_indices": [0]}])
    assert MAX_ANALYSIS_AREA_SQFT == 10000.0


def test_trigger_areas_under_the_cap_are_accepted():
    validate_analysis_areas([{"name": "ok", "area_m2": 900.0, "point_indices": [0]}])


def test_an_area_with_no_points_is_rejected():
    with pytest.raises(ValueError, match="no analysis points"):
        validate_analysis_areas([{"name": "empty", "area_m2": 10.0, "point_indices": []}])


# --------------------------------------------------------------------------- states

def _g(name, role="undeclared", area=100.0):
    return {"name": name, "azimuth_deg": 180.0, "area_m2": area, "n_faces": 1,
            "face_indices": [0], "role": role, "source": "auto"}


def _area(n_points, area_m2=200.0):
    return [{"name": "a", "area_m2": area_m2, "point_indices": list(range(n_points))}]


def test_view_groups_close_before_clerestory():
    """2.2.6: 'close the blinds for the view window groups first and clerestory last'."""
    groups = [_g("wg_high", "clerestory"), _g("wg_low", "view")]
    sun = {"wg_high": [[9000.0]], "wg_low": [[100.0]]}
    assert closure_order(groups, sun, 0) == ["wg_low", "wg_high"]


def test_contribution_breaks_ties_within_a_role():
    groups = [_g("wg_a", "view"), _g("wg_b", "view")]
    sun = {"wg_a": [[100.0]], "wg_b": [[5000.0]]}
    assert closure_order(groups, sun, 0) == ["wg_b", "wg_a"]


def test_closure_order_is_deterministic_on_a_full_tie():
    groups = [_g("wg_b"), _g("wg_a")]
    sun = {"wg_a": [[500.0]], "wg_b": [[500.0]]}
    assert closure_order(groups, sun, 0) == ["wg_a", "wg_b"]


def test_resolve_closes_only_as_many_groups_as_needed():
    """N+1 states, not 2^N: stop as soon as the criterion is met."""
    groups = [_g("wg_s"), _g("wg_n")]
    total = [[1200.0] for _ in range(5)] + [[0.0] for _ in range(95)]
    south = [[1200.0] for _ in range(5)] + [[0.0] for _ in range(95)]
    north = [[0.0] for _ in range(100)]
    assert resolve_states(groups, {"wg_s": south, "wg_n": north}, total, [1],
                          _area(100)) == [frozenset({"wg_s"})]


def test_resolve_leaves_blinds_open_when_no_sun():
    dark = [[0.0] for _ in range(100)]
    assert resolve_states([_g("wg_s")], {"wg_s": dark}, dark, [1],
                          _area(100)) == [frozenset()]


def test_resolve_never_closes_in_unoccupied_hours():
    bright = [[5000.0, 5000.0] for _ in range(100)]
    assert resolve_states([_g("wg_s")], {"wg_s": bright}, bright, [0, 1],
                          _area(100)) == [frozenset(), frozenset({"wg_s"})]


def test_criterion_must_hold_in_every_trigger_area():
    """Pooling all points would dilute the fraction and close blinds too late."""
    series = [[1200.0] if p < 10 else [0.0] for p in range(200)]
    areas = [{"name": "A", "area_m2": 200.0, "point_indices": list(range(20))},
             {"name": "B", "area_m2": 200.0, "point_indices": list(range(20, 200))}]
    assert resolve_states([_g("wg_s")], {"wg_s": series}, series, [1],
                          areas) == [frozenset({"wg_s"})]


def test_a_shade_with_openness_does_not_remove_the_whole_beam():
    """A fabric shade passing 30% of a 5000 lux beam still leaves 1500 lux -- above the
    1000 lux threshold, so closing it cannot satisfy the criterion."""
    series = [[5000.0] for _ in range(10)] + [[0.0] for _ in range(90)]
    assert resolve_states([_g("wg_s")], {"wg_s": series}, series, [1], _area(100),
                          beam_pass_fraction={"wg_s": 0.30}) == [frozenset({"wg_s"})]


def test_remaining_beam_never_goes_negative():
    """Two groups each credited with beam cannot subtract past zero and mark a lit point
    unlit -- the clamp matters when per-group series overlap."""
    series = [[1200.0] for _ in range(100)]
    groups = [_g("wg_a"), _g("wg_b")]
    states = resolve_states(groups, {"wg_a": series, "wg_b": series}, series, [1],
                            _area(100))
    assert states[0] == frozenset({"wg_a"})     # one closure already clears it


def test_select_picks_the_matrix_for_each_timesteps_state():
    matrices = {frozenset(): [[100.0, 100.0]], frozenset({"wg_s"}): [[10.0, 10.0]]}
    assert select_illuminance(matrices, [frozenset(),
                                         frozenset({"wg_s"})]) == [[100.0, 10.0]]


def test_select_errors_on_a_state_with_no_matrix():
    with pytest.raises(KeyError, match="wg_s"):
        select_illuminance({frozenset(): [[100.0]]}, [frozenset({"wg_s"})])


# -------------------------------------------------------------------------- metrics

def _points(n=10, spacing=0.6, z=0.8):
    return [[i * spacing, 0.0, z, 0.0, 0.0, 1.0] for i in range(n)]


def _areas(n=10):
    return [{"name": "a", "area_m2": 18.0, "point_indices": list(range(n))}]


def _flat(value, n_pts=10, n_ts=8760):
    return [[value] * n_ts for _ in range(n_pts)]


def _call(operated, sun, occ=None, **kw):
    kw.setdefault("groups", [_g("wg_s", "view")])
    kw.setdefault("points", _points())
    kw.setdefault("areas", _areas())
    kw.setdefault("blind_source", "lm83_2_2_7_unknown_shade")
    return lm83_metrics(operated, sun, occ or lm83_schedule(), **kw)


def test_grid_maximum_is_24_inches_not_0_61():
    assert abs(LM83_MAX_GRID_M - 0.6096) < 1e-9


def test_grid_geometry_is_measured_from_the_points():
    g = grid_geometry(_points(spacing=0.5, z=0.8))
    assert abs(g["spacing_m"] - 0.5) < 1e-9
    assert abs(g["workplane_z"] - 0.8) < 1e-9


def test_grid_geometry_handles_a_two_dimensional_grid():
    pts = [[x * 0.6, y * 0.6, 0.8, 0, 0, 1] for x in range(8) for y in range(8)]
    assert abs(grid_geometry(pts)["spacing_m"] - 0.6) < 1e-9


def test_reports_sda_and_ase():
    out = _call(_flat(500.0), _flat(0.0))
    assert out["sDA"] == 1.0 and out["ASE"] == 0.0


def test_the_model_inputs_departure_is_always_present():
    """2.2.8-2.2.11 are out of scope, so the flag can never claim full conformance."""
    out = _call(_flat(500.0), _flat(0.0))
    assert any("2.2.8" in d for d in out["conditions"]["departures"])
    assert out["conditions"]["lm83_method_conformant"] is False
    assert out["conditions"]["scope"] == "method_only"
    assert "dirt" in MODEL_INPUTS_DEPARTURE


def test_the_flag_is_not_named_lm83_conformant():
    """The name must not read as full LM-83 conformance on a LEED form."""
    assert "lm83_conformant" not in _call(_flat(500.0), _flat(0.0))["conditions"]


def test_a_short_period_is_a_departure():
    out = _call(_flat(500.0, n_ts=24), _flat(0.0, n_ts=24), occ=[1] * 24)
    assert any("3650" in d for d in out["conditions"]["departures"])


def test_a_coarse_grid_is_a_departure():
    out = _call(_flat(500.0), _flat(0.0), points=_points(spacing=1.0))
    assert any("spacing" in d for d in out["conditions"]["departures"])


def test_a_wrong_workplane_height_is_a_departure():
    """2.2.2: the workplane is 30 in / 0.8 m above finished floor."""
    out = _call(_flat(500.0), _flat(0.0), points=_points(z=1.4))
    assert any("workplane" in d for d in out["conditions"]["departures"])


def test_the_unverified_wall_offset_is_declared():
    """2.2.5's 12-24 in offset needs the room boundary, which this layer never sees."""
    assert any("wall offset" in d
               for d in _call(_flat(500.0), _flat(0.0))["conditions"]["departures"])


def test_an_undeclared_window_role_is_a_departure():
    out = _call(_flat(500.0), _flat(0.0), groups=[_g("wg_s", "undeclared")])
    assert any("role" in d for d in out["conditions"]["departures"])


def test_multiple_groups_declare_the_nested_closure_simplification():
    """2.2.6 permits closing 'in any combination'; we search a fixed order."""
    out = _call(_flat(500.0), _flat(0.0),
                groups=[_g("wg_a", "view"), _g("wg_b", "view")])
    assert any("any combination" in d for d in out["conditions"]["departures"])


def test_latitude_outside_the_research_band_is_a_departure():
    """2.2.1 discussion: the supporting research covered 37-48 deg N."""
    assert any("latitude" in d for d in
               _call(_flat(500.0), _flat(0.0), latitude=64.0)["conditions"]["departures"])
    assert not any("latitude" in d for d in
                   _call(_flat(500.0), _flat(0.0), latitude=38.0)["conditions"]["departures"])


def test_performance_criteria_from_2_1_3():
    lux = _flat(500.0)
    for p in range(8, 10):
        lux[p] = [0.0] * 8760
    out = _call(lux, _flat(0.0))
    assert out["sDA"] == 0.8 and out["sda_criterion"] == "preferred"


def test_nominally_accepted_band():
    lux = _flat(500.0)
    for p in range(6, 10):
        lux[p] = [0.0] * 8760
    out = _call(lux, _flat(0.0))
    assert out["sDA"] == 0.6 and out["sda_criterion"] == "nominally_accepted"


def test_ase_bands_from_3_1_3():
    n_ts = 8760
    # Direct sun on every point for 300 occupied hours -> ASE 1.0.
    hot = [[1200.0 if (t % 24 == 9 and t // 24 < 300) else 0.0 for t in range(n_ts)]
           for _ in range(10)]
    out = _call(_flat(500.0), hot)
    assert out["ASE"] == 1.0 and out["ase_criterion"] == "unsatisfactory"


def test_escape_clause_needs_both_conjuncts():
    """2.2.6: design documents say no blinds AND ASE is nominally acceptable."""
    out = _call(_flat(500.0), _flat(0.0), no_blind_lux=_flat(900.0))
    assert out["no_blind_case"]["ase_condition_met"] is True
    assert out["no_blind_case"]["applies"] is False        # no design-document declaration
    both = _call(_flat(500.0), _flat(0.0), no_blind_lux=_flat(900.0),
                 declared_no_blinds=True)
    assert both["no_blind_case"]["applies"] is True


def test_escape_clause_never_replaces_the_headline():
    out = _call(_flat(400.0), _flat(0.0), no_blind_lux=_flat(100.0),
                declared_no_blinds=True)
    assert out["sDA"] == 1.0                       # headline: blinds operated
    assert out["no_blind_case"]["sDA"] == 0.0      # alternative: reported only
    assert "not substituted" in out["no_blind_case"]["note"]
