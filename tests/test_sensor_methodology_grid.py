# hcl-mcp/tests/test_sensor_methodology_grid.py
from hcl_radiance.sensor_methodology import en12464_grid

INTERIOR = (-2.0, 2.0, -3.5, 3.5)   # office_room: 4.0 x 7.0

def test_p_formula_and_counts():
    pts, m = en12464_grid(INTERIOR, 0.0)
    # d is graded on the border-inset CALCULATION AREA (3.5 x 6.5), not the 4.0 x 7.0
    # interior: d = 6.5 -> p_max = 0.2 * 5**log10(6.5) = 0.7400.
    assert m["d_source"] == "calculation_area"
    assert abs(m["d"] - 6.5) < 1e-9
    assert abs(m["p_max"] - 0.7400) < 1e-3
    assert m["n_cells"] == {"x": 5, "y": 9}
    assert m["count"] == 45 and len(pts) == 45

def test_actual_spacing_under_p():
    _, m = en12464_grid(INTERIOR, 0.0)
    assert abs(m["spacing"]["x"] - 0.700) < 1e-3
    assert abs(m["spacing"]["y"] - 0.722) < 1e-3
    assert m["spacing"]["x"] <= m["p_max"] and m["spacing"]["y"] <= m["p_max"]

def test_cell_centre_positions_and_z():
    pts, m = en12464_grid(INTERIOR, 0.0, workplane_h=0.8)
    assert m["x_positions"] == [-1.4, -0.7, 0.0, 0.7, 1.4]
    assert m["x_positions"][0] == -1.4 and m["y_positions"][0] == round(-2.8889, 4)
    assert all(abs(row[2] - 0.8) < 1e-9 and row[3:] == [0, 0, 1] for row in pts)

def test_max_spacing_override():
    _, m = en12464_grid(INTERIOR, 0.0, max_spacing=0.5)
    assert m["p_source"] == "override" and m["p_max"] == 0.5


def test_degenerate_interior_raises_clear_error():
    """A2: a zero-width/height interior (d=0) must raise a clear ValueError, not the opaque
    'math domain error' from math.log10(0)."""
    import pytest
    with pytest.raises(ValueError):
        en12464_grid((1.0, 1.0, 2.0, 2.0), 0.0)   # width=0, height=0 -> d=0 -> log10(0)


def test_degenerate_interior_with_override_spacing_still_guarded():
    """A2: even with max_spacing set (which skips the log10), a degenerate interior is invalid."""
    import pytest
    with pytest.raises(ValueError):
        en12464_grid((1.0, 1.0, 2.0, 2.0), 0.0, max_spacing=0.5)


def test_calc_area_nonpositive_after_border_raises():
    """A2b: a room smaller than 2*border_offset has a non-positive inset calc area; that must
    raise a clear ValueError rather than silently emit a point outside the inset region."""
    import pytest
    with pytest.raises(ValueError):
        en12464_grid((0.0, 0.3, 0.0, 0.3), 0.0)   # 0.3 m wide, border 0.25 -> Lx = -0.2
