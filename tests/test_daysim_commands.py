import pytest

from hcl_daysim.commands import build_epw2wea, write_hea, build_ds_shortterm

def test_build_epw2wea_argv():
    cmd = build_epw2wea("/w/in.epw", "/w/in.wea")
    assert cmd == ["epw2wea", "/w/in.epw", "/w/in.wea"]

def test_build_ds_shortterm_argv():
    assert build_ds_shortterm("daysim_header.hea") == ["ds_shortterm", "daysim_header.hea"]

def test_write_hea_contains_required_keywords():
    txt = write_hea(input_wea="in.wea", output_wea="in_6_short.wea", timestep_min=6,
                    latitude=47.6, longitude=-122.3, time_zone=120, site_elevation=20)
    # Lark's verbatim non-standard keyword names (Lark Generate Sub-Hourly wea File.py:130-138)
    assert "wea_data_file in.wea" in txt
    assert "time_step 6" in txt
    assert "wea_data_short_file in_6_short.wea" in txt
    assert "wea_data_short_file_units 1" in txt
    assert "first_weekday 1" in txt
    # site information block carries the location numbers
    assert "47.6" in txt and "-122.3" in txt and "120" in txt and "20" in txt

def test_write_hea_emits_recognized_input_units_keyword():
    # ds_shortterm's read_in_header matches `wea_data_file_units` (NOT epw2wea's
    # `weather_data_file_units`); emit the recognized spelling so input units aren't
    # left to ds_shortterm's internal default.
    txt = write_hea(input_wea="in.wea", output_wea="o.wea", timestep_min=6,
                    latitude=0, longitude=0, time_zone=0, site_elevation=0)
    assert "wea_data_file_units 1" in txt
    assert "weather_data_file_units" not in txt   # the unrecognized epw2wea spelling must NOT appear
    assert "wea_data_short_file_units 1" in txt    # distinct keyword: OUTPUT units

def test_write_hea_input_units_override():
    txt = write_hea(input_wea="i.wea", output_wea="o.wea", timestep_min=6, latitude=0,
                    longitude=0, time_zone=0, site_elevation=0, input_units=2)
    assert "wea_data_file_units 2" in txt

def test_write_hea_units_override():
    txt = write_hea(input_wea="i.wea", output_wea="o.wea", timestep_min=6,
                    latitude=0, longitude=0, time_zone=0, site_elevation=0, units=2)
    assert "wea_data_short_file_units 2" in txt

def test_write_hea_timestep_appears_for_each_value():
    # 60 is text-valid but runtime-rejected by ds_shortterm; test only runtime-valid steps
    for ts in (1, 6, 30):
        txt = write_hea(input_wea="i.wea", output_wea="o.wea", timestep_min=ts,
                        latitude=0, longitude=0, time_zone=0, site_elevation=0)
        assert f"time_step {ts}" in txt

def test_write_hea_rejects_runtime_invalid_timestep():
    # Values outside the ds_shortterm genshortterm allow-set must raise at the Python
    # boundary, not produce a textually-valid .hea that only fails at ds_shortterm runtime.
    for bad in (0, 7, 8, 60, -6, 45):
        with pytest.raises(ValueError):
            write_hea(input_wea="i.wea", output_wea="o.wea", timestep_min=bad,
                      latitude=0, longitude=0, time_zone=0, site_elevation=0)

def test_write_hea_accepts_every_allowed_timestep():
    for ts in (1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30):
        txt = write_hea(input_wea="i.wea", output_wea="o.wea", timestep_min=ts,
                        latitude=0, longitude=0, time_zone=0, site_elevation=0)
        assert f"time_step {ts}" in txt
