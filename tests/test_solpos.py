from hcl_core import solpos, weather


def test_zenith_matches_weather_solar_zenith():
    # solpos must reproduce the existing Cooper-1969 zenith exactly (single source of truth).
    kw = dict(month=6, day=21, hour=12.0, latitude=37.9, longitude=-23.7, time_zone=-30)
    geo = solpos.compute(**kw)
    expected = weather.solar_zenith(**kw)
    assert abs(geo.zenith_deg - expected) < 1e-9


def test_zenith_small_at_summer_noon_athens():
    geo = solpos.compute(month=6, day=21, hour=12.0, latitude=37.9, longitude=-23.7, time_zone=-30)
    assert 10.0 < geo.zenith_deg < 25.0  # high midsummer sun


def test_azimuth_sweeps_east_to_west_through_south():
    # Northern hemisphere: morning sun east-of-south (<180), noon ~south, afternoon west-of-south (>180).
    site = dict(latitude=40.0, longitude=0.0, time_zone=0, month=4, day=15)
    az9 = solpos.compute(hour=9.0, **site).azimuth_deg
    az12 = solpos.compute(hour=12.0, **site).azimuth_deg
    az15 = solpos.compute(hour=15.0, **site).azimuth_deg
    assert 90.0 < az9 < 180.0
    assert 135.0 < az12 < 225.0
    assert 180.0 < az15 < 270.0
    assert az9 < az12 < az15


def test_air_mass_overhead_is_one():
    assert abs(solpos.air_mass(0.0) - 1.0) < 0.01


def test_air_mass_at_60deg_is_about_two():
    assert abs(solpos.air_mass(60.0) - 2.0) < 0.05


def test_air_mass_infinite_below_horizon():
    assert solpos.air_mass(95.0) == float("inf")


def test_earth_radius_vector_perihelion_and_aphelion():
    # Perihelion (~Jan 3, doy 3) → correction max (>1.03); aphelion (~Jul 4, doy 185) → min (<0.97).
    assert solpos.earth_radius_vector(3) > 1.03
    assert solpos.earth_radius_vector(185) < 0.97


def test_compute_populates_all_fields():
    geo = solpos.compute(month=6, day=21, hour=12.0, latitude=37.9, longitude=-23.7, time_zone=-30)
    assert geo.day_of_year == 172
    assert geo.air_mass > 0
    assert 0.96 < geo.earth_radius_vector < 1.04
    assert 0.0 <= geo.azimuth_deg < 360.0
