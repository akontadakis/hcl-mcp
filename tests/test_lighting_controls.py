import math
import pytest
from hcl_core.lighting_controls import light_fraction, power_fraction

# --- light_fraction ---------------------------------------------------------

def test_light_fraction_basic():
    # fL = max(0, (Iset - Itot) / Iset)
    assert light_fraction(122.543, 500) == pytest.approx(0.754914, abs=1e-6)
    assert light_fraction(24.427, 500) == pytest.approx(0.951146, abs=1e-6)
    assert light_fraction(489.474, 500) == pytest.approx(0.021052, abs=1e-6)

def test_light_fraction_clamps_at_zero_when_daylight_exceeds_setpoint():
    assert light_fraction(600, 500) == 0.0
    assert light_fraction(500, 500) == 0.0

def test_light_fraction_dark_default_is_full_electric():
    # EnergyPlus-faithful DEFAULT: genuine darkness -> full electric needed.
    assert light_fraction(0.0, 500) == 1.0

def test_light_fraction_dark_workbook_compat_gates_to_zero():
    # elec_lights.xlsx gate: Itot==0 -> fL=0 (the spreadsheet quirk, regression only).
    assert light_fraction(0.0, 500, workbook_compat=True) == 0.0
    # non-zero darkness-adjacent values are unaffected by the gate
    assert light_fraction(24.427, 500, workbook_compat=True) == pytest.approx(0.951146, abs=1e-6)

# --- power_fraction: Continuous ---------------------------------------------

def test_power_fraction_continuous_blend():
    # Row 14: both fL >= fL_min -> pure continuous blend.
    fL1 = light_fraction(122.543, 500)   # 0.754914
    fL2 = light_fraction(24.427, 500)    # 0.951146
    assert power_fraction(fL1, control_type="Continuous", fP_min=0.15, fL_min=0.05,
                          n_steps=3) == pytest.approx(0.78071253, abs=1e-6)
    assert power_fraction(fL2, control_type="Continuous", fP_min=0.15, fL_min=0.05,
                          n_steps=3) == pytest.approx(0.95628853, abs=1e-6)

def test_power_fraction_continuous_blend_equals_alternate_algebraic_form():
    # The EnergyPlus form (fL + (1-fL)*fP_min - fL_min)/(1 - fL_min) is algebraically identical to
    # fP_min + (fL - fL_min)*(1 - fP_min)/(1 - fL_min). Anchor both for a range of fL.
    fP_min, fL_min = 0.15, 0.05
    for fL in (0.05, 0.1, 0.3, 0.5, 0.754914, 0.951146, 1.0):
        ep = power_fraction(fL, control_type="Continuous", fP_min=fP_min, fL_min=fL_min, n_steps=3)
        alt = fP_min + (fL - fL_min) * (1 - fP_min) / (1 - fL_min)
        assert ep == pytest.approx(alt, abs=1e-12)

def test_power_fraction_continuous_below_fl_min_floors_to_fp_min():
    # Row 19: fL1 = 0.021052 < fL_min=0.05 -> Continuous returns the fP_min floor (0.15).
    fL = light_fraction(489.474, 500)
    assert fL < 0.05
    assert power_fraction(fL, control_type="Continuous", fP_min=0.15, fL_min=0.05, n_steps=3) == 0.15

def test_power_fraction_continuous_default_at_fl_zero_is_fp_min():
    # Row 16 divergence: default Continuous (no workbook_compat) at fL==0 gives the fP_min floor.
    assert power_fraction(0.0, control_type="Continuous", fP_min=0.15, fL_min=0.05, n_steps=3) == 0.15

def test_power_fraction_continuous_workbook_compat_gates_fl_zero_to_zero():
    # Row 16 with the sheet's extra gate: fL==0 -> fP=0 under Continuous+workbook_compat.
    assert power_fraction(0.0, control_type="Continuous", fP_min=0.15, fL_min=0.05, n_steps=3,
                          workbook_compat=True) == 0.0

# --- power_fraction: ContinuousOff (DEFAULT control type) --------------------

def test_power_fraction_continuousoff_below_fl_min_switches_off():
    # Row 19 under ContinuousOff: fL < fL_min -> lamp OFF (fP=0), not the fP_min floor.
    fL = light_fraction(489.474, 500)
    assert power_fraction(fL, control_type="ContinuousOff", fP_min=0.15, fL_min=0.05, n_steps=3) == 0.0

def test_power_fraction_continuousoff_above_fl_min_matches_continuous_blend():
    fL = light_fraction(122.543, 500)
    assert power_fraction(fL, control_type="ContinuousOff", fP_min=0.15, fL_min=0.05,
                          n_steps=3) == pytest.approx(0.78071253, abs=1e-6)

def test_power_fraction_continuousoff_at_fl_zero_is_off():
    # Row 16: ContinuousOff at fL==0 (fL < fL_min) -> fP=0, matching the workbook gate WITHOUT compat.
    assert power_fraction(0.0, control_type="ContinuousOff", fP_min=0.15, fL_min=0.05, n_steps=3) == 0.0

# --- power_fraction: Stepped ------------------------------------------------

def test_power_fraction_stepped_endpoints():
    assert power_fraction(0.0, control_type="Stepped", fP_min=0.15, fL_min=0.05, n_steps=3) == 0.0
    assert power_fraction(1.0, control_type="Stepped", fP_min=0.15, fL_min=0.05, n_steps=3) == 1.0

def test_power_fraction_stepped_uses_floor_plus_one_not_ceil():
    # EnergyPlus form: (floor(N*fL)+1)/N. For N=3:
    #   fL=0.10 -> (floor(0.3)+1)/3 = 1/3 ; fL=0.40 -> (floor(1.2)+1)/3 = 2/3 ;
    #   fL=0.70 -> (floor(2.1)+1)/3 = 3/3 = 1.0
    assert power_fraction(0.10, control_type="Stepped", fP_min=0.15, fL_min=0.05,
                          n_steps=3) == pytest.approx(1 / 3, abs=1e-12)
    assert power_fraction(0.40, control_type="Stepped", fP_min=0.15, fL_min=0.05,
                          n_steps=3) == pytest.approx(2 / 3, abs=1e-12)
    assert power_fraction(0.70, control_type="Stepped", fP_min=0.15, fL_min=0.05,
                          n_steps=3) == pytest.approx(1.0, abs=1e-12)

def test_power_fraction_stepped_step_boundary_is_floor_not_ceil():
    # At an exact boundary fL=1/3: floor(3*1/3)=floor(1.0)=1 -> (1+1)/3 = 2/3 (NOT ceil -> 1/3).
    assert power_fraction(1 / 3, control_type="Stepped", fP_min=0.15, fL_min=0.05,
                          n_steps=3) == pytest.approx(2 / 3, abs=1e-12)

def test_power_fraction_unknown_control_type_raises():
    with pytest.raises(ValueError):
        power_fraction(0.5, control_type="bogus", fP_min=0.15, fL_min=0.05, n_steps=3)


from hcl_core.lighting_controls import zone_power_fraction, controls_point

# --- zone_power_fraction ----------------------------------------------------

def test_zone_power_fraction_full_coverage():
    # Row 14: FP = 0.78071253*0.6071428571 + 0.95628853*0.3928571429 (weights sum to 1 -> no remainder)
    fps = [0.78071253, 0.95628853]
    weights = [0.6071428571, 0.3928571429]
    assert zone_power_fraction(fps, weights) == pytest.approx(0.84968881, abs=1e-6)

def test_zone_power_fraction_adds_uncontrolled_remainder():
    # weights sum to 0.8 -> 0.2 of the lights are uncontrolled (full power): FP = 0.5*0.8 + 0.2 = 0.6
    assert zone_power_fraction([0.5], [0.8]) == pytest.approx(0.6, abs=1e-12)

def test_zone_power_fraction_weights_over_one_raises():
    with pytest.raises(ValueError):
        zone_power_fraction([0.5, 0.5], [0.7, 0.7])

def test_zone_power_fraction_allows_tiny_epsilon_over_one():
    # sum(W) = 1 + 5e-10 is within tolerance (no raise); remainder clamps to >= 0.
    fp = zone_power_fraction([0.5, 0.5], [0.6071428571, 0.3928571429 + 5e-10])
    assert fp == pytest.approx(0.5, abs=1e-6)

# --- controls_point: the §5.4 golden rows -----------------------------------

W1, W2 = 0.6071428571, 0.3928571429

def test_controls_point_row14_mode_independent():
    # Row 14: both fL >= fL_min, pure continuous blend. Holds for Continuous AND ContinuousOff.
    for ct in ("Continuous", "ContinuousOff"):
        r = controls_point([122.543, 24.427], [W1, W2], iset=500, control_type=ct,
                           fP_min=0.15, fL_min=0.05, n_steps=3, p_rated=448)
        assert r["fL"][0] == pytest.approx(0.754914, abs=1e-6)
        assert r["fL"][1] == pytest.approx(0.951146, abs=1e-6)
        assert r["fP"][0] == pytest.approx(0.78071253, abs=1e-6)
        assert r["fP"][1] == pytest.approx(0.95628853, abs=1e-6)
        assert r["FP"] == pytest.approx(0.84968881, abs=1e-6)
        assert r["reduction"] == pytest.approx(0.15031119, abs=1e-6)
        assert r["P_elec"] == pytest.approx(448 * 0.84968881, abs=1e-4)
        assert r["P_saved"] == pytest.approx(448 * 0.15031119, abs=1e-4)

def test_controls_point_row19_continuous_floors_first_point():
    # Row 19: Itot1=489.474 -> fL1=0.021052 < fL_min -> Continuous fP1 = fP_min = 0.15.
    r = controls_point([489.474, 24.427], [W1, W2], iset=500, control_type="Continuous",
                       fP_min=0.15, fL_min=0.05, n_steps=3, p_rated=448)
    assert r["fL"][0] == pytest.approx(0.021052, abs=1e-6)
    assert r["fP"][0] == 0.15

def test_controls_point_row19_continuousoff_switches_first_point_off():
    # Row 19 under ContinuousOff: fL1 < fL_min -> fP1 = 0.
    r = controls_point([489.474, 24.427], [W1, W2], iset=500, control_type="ContinuousOff",
                       fP_min=0.15, fL_min=0.05, n_steps=3, p_rated=448)
    assert r["fP"][0] == 0.0

def test_controls_point_row16_divergence_continuous_vs_continuousoff():
    # Row 16: Itot1 >= Iset -> fL1 = 0.
    #   default Continuous -> fP1 = fP_min = 0.15 (the divergence)
    #   ContinuousOff      -> fP1 = 0
    #   Continuous + workbook_compat -> fP1 = 0 (sheet gate)
    cont = controls_point([500.0, 24.427], [W1, W2], iset=500, control_type="Continuous",
                          fP_min=0.15, fL_min=0.05, n_steps=3, p_rated=448)
    off = controls_point([500.0, 24.427], [W1, W2], iset=500, control_type="ContinuousOff",
                         fP_min=0.15, fL_min=0.05, n_steps=3, p_rated=448)
    compat = controls_point([500.0, 24.427], [W1, W2], iset=500, control_type="Continuous",
                            fP_min=0.15, fL_min=0.05, n_steps=3, p_rated=448, workbook_compat=True)
    assert cont["fL"][0] == 0.0 and cont["fP"][0] == 0.15
    assert off["fP"][0] == 0.0
    assert compat["fP"][0] == 0.0

def test_controls_point_all_dark_default_is_full_power():
    # DEFAULT model divergence test: Itot=[0,0] -> fL=1 -> full electric. Proves the two semantics
    # cannot be silently conflated. ContinuousOff with fL=1 (>= fL_min) -> blend at fL=1 == 1.0.
    r = controls_point([0.0, 0.0], [W1, W2], iset=500, control_type="ContinuousOff",
                       fP_min=0.15, fL_min=0.05, n_steps=3, p_rated=448)
    assert r["fL"] == [1.0, 1.0]
    assert r["fP"] == pytest.approx([1.0, 1.0], abs=1e-12)
    assert r["FP"] == pytest.approx(1.0, abs=1e-12)
    assert r["P_elec"] == pytest.approx(448.0, abs=1e-9)
    assert r["P_saved"] == pytest.approx(0.0, abs=1e-9)

def test_controls_point_all_dark_workbook_compat_is_all_zero():
    # Same input under workbook_compat -> all gates fire -> zero power (the spreadsheet semantics).
    r = controls_point([0.0, 0.0], [W1, W2], iset=500, control_type="Continuous",
                       fP_min=0.15, fL_min=0.05, n_steps=3, p_rated=448, workbook_compat=True)
    assert r["fL"] == [0.0, 0.0]
    assert r["fP"] == [0.0, 0.0]
    assert r["FP"] == pytest.approx(0.0, abs=1e-12)
    assert r["P_elec"] == 0.0 and r["P_saved"] == pytest.approx(448.0, abs=1e-9)

def test_controls_point_schedule_scales_power():
    r = controls_point([122.543, 24.427], [W1, W2], iset=500, control_type="ContinuousOff",
                       fP_min=0.15, fL_min=0.05, n_steps=3, p_rated=448, schedule=0.5)
    assert r["P_elec"] == pytest.approx(448 * 0.5 * 0.84968881, abs=1e-4)


from hcl_core.lighting_controls import (area_weights_from_geometry, default_schedule,
                                        controls_series)

# --- area_weights_from_geometry --------------------------------------------

def test_area_weights_from_geometry_workbook():
    # primary_depth = 2.5*(window_head - task_height) = 2.5*(2.5-0.8) = 4.25
    # area_pr = 4.25*4 = 17 ; area_tot = 4*7 = 28 ; W1 = 17/28, W2 = 11/28
    w1, w2 = area_weights_from_geometry(4, 7, 2.5, 0.8)
    assert w1 == pytest.approx(0.6071428571, abs=1e-9)
    assert w2 == pytest.approx(0.3928571429, abs=1e-9)
    assert (w1 + w2) == pytest.approx(1.0, abs=1e-12)

def test_area_weights_primary_depth_capped_at_room_length():
    # If 2.5*(head-task) exceeds the room length, the primary zone is the whole room (W1=1, W2=0).
    w1, w2 = area_weights_from_geometry(4, 3, 2.5, 0.8)  # primary_depth 4.25 > length 3
    assert w1 == pytest.approx(1.0, abs=1e-12)
    assert w2 == pytest.approx(0.0, abs=1e-12)

# --- default_schedule -------------------------------------------------------

def test_default_schedule_length_and_occupied_count():
    sched = default_schedule()
    assert len(sched) == 8760
    # weekdays 08:00-18:00 inclusive-exclusive -> 10 occupied hours/day.
    # Jan 1 of the modeling year is a Monday convention (HOY 0 = Mon 00:00); 52*5 + leading weekdays.
    assert sum(1 for s in sched if s > 0) == 2610  # 261 weekdays * 10 h

def test_default_schedule_marks_occupied_hours_on():
    sched = default_schedule()
    assert sched[8] == 1.0 and sched[17] == 1.0      # Mon 08:00 and 17:00 occupied
    assert sched[7] == 0.0 and sched[18] == 0.0      # Mon 07:00 and 18:00 unoccupied
    assert sched[24 * 5 + 8] == 0.0                  # Sat 08:00 unoccupied

# --- controls_series --------------------------------------------------------

def test_controls_series_annual_kwh_per_m2_definition():
    # Tiny synthetic 3-hour series, all occupied (schedule of 1.0), area=10 m^2.
    # Per hour P_elec = 448*ContinuousOff(FP). Assert annual_kwh_per_m2 = Σ P_elec / 1000 / area.
    series = [[122.543, 24.427], [489.474, 24.427], [0.0, 0.0]]
    out = controls_series(series, [W1, W2], schedule=[1.0, 1.0, 1.0], area=10.0,
                          iset=500, control_type="ContinuousOff", fP_min=0.15, fL_min=0.05,
                          n_steps=3, p_rated=448)
    consumed = sum(h["P_elec"] for h in out["per_hour"])
    assert out["annual_kwh"] == pytest.approx(consumed / 1000.0, abs=1e-9)
    assert out["annual_kwh_per_m2"] == pytest.approx(consumed / 1000.0 / 10.0, abs=1e-9)
    assert out["occupied_hours"] == 3
    assert out["mean_FP"] == pytest.approx(sum(h["FP"] for h in out["per_hour"]) / 3, abs=1e-9)
    assert out["mean_reduction"] == pytest.approx(1.0 - out["mean_FP"], abs=1e-9)

def test_controls_series_skips_unoccupied_hours():
    # Unoccupied hours (schedule==0) consume nothing and are excluded from occupied_hours.
    series = [[122.543, 24.427], [122.543, 24.427]]
    out = controls_series(series, [W1, W2], schedule=[1.0, 0.0], area=10.0,
                          iset=500, control_type="ContinuousOff", fP_min=0.15, fL_min=0.05,
                          n_steps=3, p_rated=448)
    assert out["occupied_hours"] == 1
    assert len(out["per_hour"]) == 1
    assert out["per_hour"][0]["P_elec"] == pytest.approx(448 * 0.84968881, abs=1e-4)

def test_controls_series_default_schedule_used_when_none():
    # schedule=None -> default weekdays 08:00-18:00 mask, applied to an 8760-h flat series.
    series = [[300.0, 200.0]] * 8760
    out = controls_series(series, [W1, W2], schedule=None, area=28.0,
                          iset=500, control_type="ContinuousOff", fP_min=0.15, fL_min=0.05,
                          n_steps=3, p_rated=448)
    assert out["occupied_hours"] == 2610
    assert out["annual_kwh_per_m2"] > 0


def test_controls_series_rejects_schedule_length_mismatch():
    # Regression: zip() silently truncated to the shorter, under-counting annual energy.
    import pytest
    from hcl_core.lighting_controls import controls_series
    with pytest.raises(ValueError):
        controls_series([[100.0], [100.0]], [1.0], schedule=[1.0], area=10.0)


def test_zone_power_fraction_rejects_a_negative_weight():
    """A negative area fraction must be rejected, not turned into negative wattage.

    Found by audit 2026-08-06. The validation checked only sum(weights) <= 1, so (-0.075, 1.075)
    -- which sums to exactly 1.0 -- sailed through and produced FP = -0.075: a 250 W installation
    reporting -18.7 W consumed and 107.5 % saved. A floor area cannot be negative, so the check
    belongs on each weight, not only on their sum.
    """
    import pytest
    with pytest.raises(ValueError, match="negative"):
        zone_power_fraction([1.0, 0.0], [-0.075, 1.075])


def test_area_weights_from_geometry_clamps_an_inverted_window():
    """window_head below task_height gives a negative primary depth; clamp it at zero.

    2.5*(window_head - task_height) goes negative when the window head sits below the working
    plane. There is no negative daylit area -- the correct reading is 'no primary zone'.
    """
    w = area_weights_from_geometry(width=4.0, length=5.0, window_head=1.0, task_height=1.15)
    assert w[0] == 0.0, f"primary weight must clamp to 0, got {w[0]}"
    assert w[1] == 1.0
    assert abs(sum(w) - 1.0) < 1e-12


def test_area_weights_from_geometry_unchanged_for_a_normal_room():
    """The clamp must not disturb an ordinary geometry."""
    w = area_weights_from_geometry(width=4.0, length=5.0, window_head=2.5, task_height=0.8)
    assert w[0] > 0.0 and w[1] > 0.0
    assert abs(sum(w) - 1.0) < 1e-12
