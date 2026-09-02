import math
import pytest
from hcl_core.weather import import_wea, analysis_period, decompose, subset_wea, solar_zenith

WEA = ("place\nlat 0\nlon 0\nmer 0\n1\n6\n"  # 6 header lines
       "1 1 8.5 100 50\n1 1 9.5 300 80\n1 1 10.5 500 120\n")

def test_import_wea_skips_header(tmp_path):
    p = tmp_path / "x.wea"; p.write_text(WEA)
    d = import_wea(str(p))
    assert d["DNI"] == ["100", "300", "500"] and d["DHI"] == ["50", "80", "120"]
    assert d["hours"] == ["8.5", "9.5", "10.5"]

def test_decompose_hourly_wealines():
    period = analysis_period((1, 1, 8), (1, 1, 10))  # Jan 1, hours 8..10
    out = decompose(period, timestep_min=60)
    assert out["hours"] == [8, 9, 10]
    # wea data starts at line 7 -> HOY*1+7
    assert out["wea_lines"][0] == out["HOY"][0] * 1 + 7

def test_decompose_skips_invalid_days():
    period = analysis_period((2, 28, 12), (2, 31, 12))  # Feb 29/30/31 don't exist
    out = decompose(period, timestep_min=60)
    assert all(not (m == 2 and d in (29, 30, 31)) for m, d in zip(out["months"], out["days"]))

def test_subset_wea_keeps_header_and_selected(tmp_path):
    p = tmp_path / "x.wea"; p.write_text(WEA)
    out = subset_wea(str(p), [7, 9])  # 1-based data lines 7 and 9
    lines = out.strip().splitlines()
    assert lines[:6] == WEA.splitlines()[:6]
    assert lines[6:] == ["1 1 8.5 100 50", "1 1 10.5 500 120"]

def test_solar_zenith_noon_equinox_equator_is_about_zero():
    z = solar_zenith(month=3, day=21, hour=12.0, latitude=0.0, longitude=0.0, time_zone=0.0)
    # At clock-noon the sun sits ~2 deg off zenith: equinox declination is ~-0.4 deg and the
    # equation of time (~-7.8 min on Mar 21) shifts true solar noon ~2 deg in hour angle.
    assert z == pytest.approx(0.0, abs=2.5)

def test_solar_zenith_noon_equinox_at_latitude_equals_latitude():
    z = solar_zenith(month=3, day=21, hour=12.0, latitude=45.0, longitude=0.0, time_zone=0.0)
    assert z == pytest.approx(45.0, abs=1.5)

def test_solar_zenith_night_is_past_90():
    z = solar_zenith(month=3, day=21, hour=0.0, latitude=0.0, longitude=0.0, time_zone=0.0)
    assert z > 90.0

def test_solar_zenith_clamped_to_0_180():
    z = solar_zenith(month=6, day=21, hour=12.0, latitude=23.45, longitude=0.0, time_zone=0.0)
    assert 0.0 <= z <= 180.0


def test_decompose_handles_clock_hour_24():
    # Regression: hour 24 (Daysim/.wea 1-24 convention) used to raise ValueError in datetime().
    r = decompose([[6, 21, 24], [6, 21, 24]])
    assert r["hours"][-1] == 24
    assert r["HOY"][-1] == r["HOYround"][-1]  # minute 0 at hour 24 -> rolled to next-day 00:00


def test_subset_wea_raises_on_out_of_range_line(tmp_path):
    # Regression: line numbers overrunning the file (timestep/resolution mismatch) were silently
    # dropped, emitting a wrong-timestamp subset; now they fail loudly.
    p = tmp_path / "x.wea"
    p.write_text("h1\nh2\nh3\nh4\nh5\nh6\n" + "\n".join(f"d{i}" for i in range(3)) + "\n")
    with pytest.raises(ValueError):
        subset_wea(str(p), [7, 99])
