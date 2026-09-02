"""Daylight-zone coverage must be explicit at both ends of the control calculation.

Regression: two shipped helpers zone a room by different rules. `photosensors` builds zones one
window-head depth each; `lighting_controls.area_weights_from_geometry` uses 2.5x(head-task) for
the primary zone. On a 7 m room the first covers 70.7% of the floor and the second 100%, and the
same annual simulation then returns 54% or 79% savings. Neither is wrong, but nothing made the
assumption visible, so the number a caller got depended on which helper they happened to reach.

The fix surfaces coverage where it is decided (photosensors emits its own weights) and where it
is consumed (daylight_savings echoes the sum and the uncontrolled remainder).
"""
import os

from hcl_radiance.geometry_obj import parse_obj
from hcl_radiance.sensor_daylight import place_photosensors

OBJ = os.path.join(os.path.dirname(__file__), "fixtures", "office_room.obj")
MAP = {"Rad_Floor_R020": {"type": "floor", "refl": 0.2},
       "Rad_Wall_R050": {"type": "plastic", "refl": 0.5},
       "Rad_Ceiling_R080": {"type": "plastic", "refl": 0.8},
       "Rad_Glazing_T073": {"type": "glass", "tvis": 0.73}}


def _meth():
    with open(OBJ) as fh:
        _pts, m = place_photosensors(parse_obj(fh.read()), MAP, 1.0, "Z")
    return m


def test_photosensors_emits_per_zone_floor_area_weights():
    m = _meth()
    assert "weights" in m, f"no weights in methodology: {sorted(m)}"
    assert len(m["weights"]) == len(m["zones"])
    assert all(0.0 < w <= 1.0 for w in m["weights"]), m["weights"]


def test_photosensors_reports_the_uncontrolled_remainder():
    m = _meth()
    assert "uncontrolled_fraction" in m
    total = sum(m["weights"])
    assert abs(m["uncontrolled_fraction"] - (1.0 - total)) < 1e-9
    # office_room is 7 m deep with a 2.475 m head: two zones of 2.475 m leave a real remainder.
    assert m["uncontrolled_fraction"] > 0.2, m["uncontrolled_fraction"]


def test_weights_are_directly_usable_by_daylight_savings():
    """They must be floor-area FRACTIONS summing to <= 1, the contract lighting_controls states."""
    m = _meth()
    assert sum(m["weights"]) <= 1.0 + 1e-9


def test_lighting_controls_reports_coverage_in_its_result():
    from hcl_core.lighting_controls import controls_series
    r = controls_series(itot_series=[[600.0, 200.0]] * 4, weights=[0.354, 0.354],
                        area=28.0, p_rated=392.0, schedule=[1, 1, 1, 1],
                        iset=500.0, control_type='ContinuousOff', fP_min=0.15,
                        fL_min=0.05, n_steps=3)
    assert abs(r["sum_weights"] - 0.708) < 1e-9, r.get("sum_weights")
    assert abs(r["uncontrolled_fraction"] - 0.292) < 1e-9
    assert "coverage_note" in r


def test_full_coverage_reports_a_zero_remainder_not_a_missing_key():
    from hcl_core.lighting_controls import controls_series
    r = controls_series(itot_series=[[600.0, 200.0]] * 4, weights=[0.6, 0.4],
                        area=28.0, p_rated=392.0, schedule=[1, 1, 1, 1],
                        iset=500.0, control_type='ContinuousOff', fP_min=0.15,
                        fL_min=0.05, n_steps=3)
    assert abs(r["sum_weights"] - 1.0) < 1e-9
    assert abs(r["uncontrolled_fraction"]) < 1e-9


def test_uncontrolled_floor_caps_the_achievable_saving():
    """With 29.2% uncontrolled, mean reduction can never exceed 70.8% however bright it is."""
    from hcl_core.lighting_controls import controls_series
    r = controls_series(itot_series=[[100000.0, 100000.0]] * 4, weights=[0.354, 0.354],
                        area=28.0, p_rated=392.0, schedule=[1, 1, 1, 1],
                        iset=500.0, control_type='ContinuousOff', fP_min=0.15,
                        fL_min=0.05, n_steps=3)
    assert r["mean_reduction"] <= 0.708 + 1e-9, r["mean_reduction"]
