from hcl_radiance.sensor_methodology import en12464_grid


def test_en12464_d_is_the_calculation_area_not_the_interior():
    """EN 12464-1 defines d on the calculation area; grading it on the larger
    interior extent yields a more permissive p_max than the standard allows."""
    # 4 x 7 m interior, default 0.25 m border -> 3.5 x 6.5 m calc area.
    points, meth = en12464_grid((0.0, 4.0, 0.0, 7.0), 0.0)
    assert meth["d_source"] == "calculation_area"
    assert abs(meth["d"] - 6.5) < 1e-9, meth["d"]
    # p = 0.2 * 5**log10(6.5); methodology["p_max"] is stored rounded to 4dp.
    assert abs(meth["p_max"] - 0.2 * (5 ** __import__("math").log10(6.5))) < 1e-4


def test_en12464_max_spacing_override_still_wins():
    _, meth = en12464_grid((0.0, 4.0, 0.0, 7.0), 0.0, max_spacing=1.0)
    assert meth["p_source"] == "override"
    assert abs(meth["p_max"] - 1.0) < 1e-9
