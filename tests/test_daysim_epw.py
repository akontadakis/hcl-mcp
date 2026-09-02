from hcl_daysim.epw import parse_epw_location

# Seattle-like LOCATION line: lat 47.6 N, lon 122.3 W (EPW east-positive => -122.3), UTC-8, 20 m.
_LOC = "LOCATION,Seattle,WA,USA,TMY,727930,47.6,-122.3,-8.0,20.0\n"

def test_parse_converts_to_daysim_convention(tmp_path):
    epw = tmp_path / "seattle.epw"
    epw.write_text(_LOC + "DESIGN CONDITIONS,0\n")
    site = parse_epw_location(str(epw))
    assert site["latitude"] == 47.6
    assert site["longitude"] == 122.3          # EPW east-positive -122.3 -> .wea west-positive +122.3
    assert site["time_zone"] == 120            # -15 * -8
    assert site["site_elevation"] == 20.0

def test_parse_truncates_half_hour_timezone(tmp_path):
    # epw2wea uses atoi (truncate toward zero): -9.5 -> -9 -> *-15 -> 135.
    epw = tmp_path / "half.epw"
    epw.write_text("LOCATION,X,,,,,10.0,5.0,-9.5,0\n")
    site = parse_epw_location(str(epw))
    assert site["time_zone"] == 135
    assert site["longitude"] == -5.0           # -1 * 5.0 (already west of Greenwich in EPW terms)

def test_parse_missing_file_returns_none():
    assert parse_epw_location("/no/such/file.epw") is None

def test_parse_non_location_first_line_returns_none(tmp_path):
    epw = tmp_path / "bad.epw"
    epw.write_text("NOTLOCATION,foo\n")
    assert parse_epw_location(str(epw)) is None

def test_parse_truncated_location_returns_none(tmp_path):
    epw = tmp_path / "short.epw"
    epw.write_text("LOCATION,Seattle,WA,USA\n")   # too few fields
    assert parse_epw_location(str(epw)) is None

def test_parse_flags_half_hour_timezone(tmp_path):
    import warnings
    epw = tmp_path / "half.epw"
    # lat@6=10.0, lon@7=5.0, tz@8=-9.5, elev@9=0
    epw.write_text("LOCATION,X,,,,,10.0,5.0,-9.5,0\n")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        site = parse_epw_location(str(epw))
    assert site["time_zone"] == 135            # int(-15 * int(-9.5)) = int(-15 * -9) = 135
    assert site["tz_truncated"] is True
    assert any("zone" in str(r.message).lower() for r in w)

def test_parse_whole_hour_timezone_not_flagged(tmp_path):
    import warnings
    epw = tmp_path / "whole.epw"
    # lat@6=10.0, lon@7=5.0, tz@8=-8.0, elev@9=0
    epw.write_text("LOCATION,X,,,,,10.0,5.0,-8.0,0\n")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        site = parse_epw_location(str(epw))
    assert site["tz_truncated"] is False
    assert not any("zone" in str(r.message).lower() for r in w)
