from hcl_core.daylight_metrics import (rgb_to_photopic_lux, daylight_autonomy, continuous_da,
                                       daylight_metrics)

def test_rgb_to_photopic_lux_3channel_unit():
    # one point, two timesteps, RGB=[1,1,1] -> 179*(0.265+0.670+0.065)=179.0
    out = rgb_to_photopic_lux([[[1.0, 1.0, 1.0], [0.0, 0.0, 0.0]]], channel_type=0)
    assert len(out) == 1 and len(out[0]) == 2
    assert round(out[0][0], 6) == 179.0
    assert round(out[0][1], 6) == 0.0

def test_rgb_to_photopic_lux_9channel_unit():
    out = rgb_to_photopic_lux([[[1.0] * 9]], channel_type=1)
    # 179 * sum(W_PHOTOPIC_9)
    from hcl_core.data import W_PHOTOPIC_9
    assert round(out[0][0], 6) == round(179.0 * sum(W_PHOTOPIC_9), 6)

def test_rgb_to_photopic_lux_wrong_width_raises():
    import pytest
    with pytest.raises(ValueError):
        rgb_to_photopic_lux([[[1.0, 1.0]]], channel_type=0)

def test_daylight_autonomy_basic():
    lux = [500, 100, 400, 0]
    occ = [1, 1, 1, 0]                 # last hour unoccupied, excluded
    # occupied: 500>=300 yes, 100 no, 400 yes -> 2/3
    assert round(daylight_autonomy(lux, occ, 300.0), 6) == round(2 / 3, 6)

def test_daylight_autonomy_no_occupied_hours():
    assert daylight_autonomy([500, 500], [0, 0], 300.0) == 0.0

def test_continuous_da_partial_credit():
    lux = [150, 600]
    occ = [1, 1]
    # min(1,150/300)=0.5 ; min(1,600/300)=1.0 -> mean 0.75
    assert round(continuous_da(lux, occ, 300.0), 6) == 0.75

def test_udi_bins_boundaries():
    from hcl_core.daylight_metrics import udi_bins
    # values land exactly on bin edges: 100 -> supplementary, 300 -> autonomous, 3000 -> exceed
    lux = [50, 100, 300, 3000]
    occ = [1, 1, 1, 1]
    b = udi_bins(lux, occ)
    assert b == {"short": 0.25, "supplementary": 0.25, "autonomous": 0.25, "exceed": 0.25}

def test_udi_bins_no_occupied():
    from hcl_core.daylight_metrics import udi_bins
    assert udi_bins([500], [0]) == {"short": 0.0, "supplementary": 0.0, "autonomous": 0.0, "exceed": 0.0}

def test_spatial_da():
    from hcl_core.daylight_metrics import spatial_da
    assert spatial_da([0.6, 0.4, 0.5, 0.9], da_fraction=0.5) == 0.75  # 0.6,0.5,0.9 pass

def test_annual_sunlight_exposure():
    from hcl_core.daylight_metrics import annual_sunlight_exposure
    # point A: direct sun >=1000 for 3 occupied hours; point B: 1 hour
    sun = [[1200, 1100, 1500, 0], [1200, 0, 0, 0]]
    occ = [1, 1, 1, 1]
    out = annual_sunlight_exposure(sun, occ, threshold=1000.0, hour_limit=2.0, step_hours=1.0)
    assert out["per_point_hours"] == [3.0, 1.0]
    assert out["ase"] == 0.5  # only point A exceeds 2 h

def test_annual_sunlight_exposure_empty():
    from hcl_core.daylight_metrics import annual_sunlight_exposure
    assert annual_sunlight_exposure([], [1, 1]) == {"ase": 0.0, "per_point_hours": []}

def test_daylight_metrics_aggregate():
    from hcl_core.daylight_metrics import daylight_metrics
    lux = [[500, 500, 500, 500], [50, 50, 50, 50]]   # point 0 bright, point 1 dark
    occ = [1, 1, 1, 1]
    sun = [[0, 0, 0, 0], [0, 0, 0, 0]]
    out = daylight_metrics(lux, occ, da_threshold=300.0, sun_lux_matrix=sun)
    assert out["per_point"][0]["DA"] == 1.0
    assert out["per_point"][1]["DA"] == 0.0
    assert out["spatial"]["sDA"] == 0.5            # 1 of 2 points DA>=0.5
    assert out["spatial"]["DA_avg"] == 0.5
    assert out["spatial"]["ASE"] == 0.0
    assert "partial_year" not in out

def test_daylight_metrics_partial_year_flag():
    from hcl_core.daylight_metrics import daylight_metrics
    out = daylight_metrics([[500]], [1], partial_year=True)
    assert out["partial_year"] is True
    assert "ASE" not in out["spatial"]             # no sun matrix -> no ASE


def test_partial_year_flag_carries_its_caveat():
    """A partial-year run keeps the metric names but must say the window is not a year -- ASE's
    250 h criterion cannot be met by a shorter window, so a low ASE is not evidence of no glare."""
    lux = [[2000.0] * 100 for _ in range(3)]
    occ = [1] * 100
    out = daylight_metrics(lux, occ, sun_lux_matrix=lux, partial_year=True)
    assert out["partial_year"] is True
    assert "250" in out["partial_year_note"] and "full-year" in out["partial_year_note"].lower()
    # and the flag stays absent on a normal run
    assert "partial_year" not in daylight_metrics(lux, occ, sun_lux_matrix=lux)
