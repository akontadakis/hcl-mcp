import os
import pytest
import hcl_daysim.subhourly as sub

# Minimal EPW first line: Seattle-like (lat 47.6 N, lon 122.3 W -> EPW -122.3, UTC-8, 20 m).
_EPW_LOC = "LOCATION,Seattle,WA,USA,TMY,727930,47.6,-122.3,-8.0,20.0\n"

def test_emit_path_when_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(sub, "_available", lambda: False)
    out = sub.generate_subhourly_wea("/w/in.epw", timestep_min=6, latitude=47.6, longitude=-122.3,
                                     time_zone=120, site_elevation=20, work_dir=str(tmp_path), run=True)
    assert out["ran"] is False
    joined = "\n".join(out["commands"])
    assert "epw2wea" in joined and "ds_shortterm" in joined
    # the .hea is written even on the emit path so the user can run the commands themselves
    assert (tmp_path / "daysim_header.hea").exists()
    hea = (tmp_path / "daysim_header.hea").read_text()
    assert "time_step 6" in hea
    assert "build_daysim" in out["reason"].lower() or "hcl_daysim_bin" in out["reason"].lower()

def test_default_timestep_is_six(monkeypatch, tmp_path):
    monkeypatch.setattr(sub, "_available", lambda: False)
    out = sub.generate_subhourly_wea("/w/in.epw", latitude=0, longitude=0, time_zone=0,
                                     site_elevation=0, work_dir=str(tmp_path), run=True)
    assert "time_step 6" in (tmp_path / "daysim_header.hea").read_text()

def test_output_wea_name_encodes_timestep(monkeypatch, tmp_path):
    monkeypatch.setattr(sub, "_available", lambda: False)
    out = sub.generate_subhourly_wea("/data/seattle.epw", timestep_min=6, latitude=0, longitude=0,
                                     time_zone=0, site_elevation=0, work_dir=str(tmp_path), run=True)
    assert out["wea"].endswith("seattle_6_short.wea")

def test_dry_run_reason_distinguishes_from_absent(monkeypatch, tmp_path):
    # run=False with Daysim AVAILABLE -> emit, but reason must NOT claim Daysim is missing.
    monkeypatch.setattr(sub, "_available", lambda: True)
    out = sub.generate_subhourly_wea("/w/in.epw", latitude=0, longitude=0, time_zone=0,
                                     site_elevation=0, work_dir=str(tmp_path), run=False)
    assert out["ran"] is False
    assert "dry run" in out["reason"].lower()
    assert (tmp_path / "daysim_header.hea").exists()

def test_site_values_derived_from_epw_when_not_supplied(monkeypatch, tmp_path):
    # No explicit coords: the .hea must carry the EPW LOCATION line converted to DAYSIM convention
    # (longitude negated to west-positive; time_zone = -15 x UTC offset; elevation verbatim).
    monkeypatch.setattr(sub, "_available", lambda: False)
    epw = tmp_path / "seattle.epw"; epw.write_text(_EPW_LOC + "DESIGN CONDITIONS,0\n")
    out = sub.generate_subhourly_wea(str(epw), work_dir=str(tmp_path), run=True)
    hea = (tmp_path / "daysim_header.hea").read_text()
    assert "latitude 47.6" in hea
    assert "longitude 122.3" in hea     # NOT the raw EPW -122.3
    assert "time_zone 120" in hea       # -15 * -8
    assert "site_elevation 20.0" in hea

def test_explicit_site_values_override_epw(monkeypatch, tmp_path):
    monkeypatch.setattr(sub, "_available", lambda: False)
    epw = tmp_path / "seattle.epw"; epw.write_text(_EPW_LOC)
    out = sub.generate_subhourly_wea(str(epw), latitude=10, longitude=20, time_zone=30,
                                     work_dir=str(tmp_path), run=True)
    hea = (tmp_path / "daysim_header.hea").read_text()
    assert "latitude 10" in hea and "longitude 20" in hea and "time_zone 30" in hea

def test_missing_location_and_no_coords_raises(monkeypatch, tmp_path):
    # Unreadable EPW + no explicit coords must raise, not silently run at lat 0 / long 0.
    monkeypatch.setattr(sub, "_available", lambda: False)
    with pytest.raises(ValueError, match="could not be determined"):
        sub.generate_subhourly_wea("/no/such.epw", work_dir=str(tmp_path), run=True)

def test_generate_subhourly_rejects_bad_timestep_before_io(tmp_path):
    # An out-of-set timestep must raise at the Python boundary BEFORE any file I/O —
    # in particular before the .hea is written — so the emit path never produces a plan
    # that only fails at ds_shortterm runtime.
    from hcl_daysim.subhourly import generate_subhourly_wea
    with pytest.raises(ValueError):
        generate_subhourly_wea("/nonexistent.epw", timestep_min=60, latitude=47.6,
                               longitude=-122.3, time_zone=120, site_elevation=20,
                               work_dir=str(tmp_path), run=False)
    assert not (tmp_path / "daysim_header.hea").exists()

def test_run_path_invokes_runner(monkeypatch, tmp_path):
    monkeypatch.setattr(sub, "_available", lambda: True)
    seen = {}
    def fake_run(steps, work_dir, available):
        seen["steps"] = steps; seen["available"] = available
        return {"ran": True, "returncode": 0, "commands": [], "outputs": ["seattle_6_short.wea"]}
    monkeypatch.setattr(sub, "run_sequence", fake_run)
    out = sub.generate_subhourly_wea("/data/seattle.epw", timestep_min=6, latitude=1.0, longitude=2.0,
                                     time_zone=0, site_elevation=0, work_dir=str(tmp_path), run=True)
    assert out["ran"] is True
    assert seen["available"] is True
    cmds = [s["cmd"][0] for s in seen["steps"]]
    assert cmds == ["epw2wea", "ds_shortterm"]

def test_run_path_returns_timestamps_and_solar_zeniths(monkeypatch, tmp_path):
    monkeypatch.setattr(sub, "_available", lambda: True)
    short_wea = tmp_path / "seattle_6_short.wea"
    short_wea.write_text(
        "place Seattle\nlatitude 47.6\nlongitude 122.3\ntime_zone 120\n1\n6\n"
        "1 1 8.0 100 50\n1 1 12.0 800 120\n1 1 18.0 50 30\n")
    monkeypatch.setattr(sub, "run_sequence",
                        lambda steps, work_dir, available: {"ran": True, "returncode": 0,
                                                            "commands": [], "outputs": []})
    out = sub.generate_subhourly_wea(str(tmp_path / "seattle.epw"), timestep_min=6,
                                     latitude=47.6, longitude=122.3, time_zone=120,
                                     site_elevation=20, work_dir=str(tmp_path), run=True)
    assert out["ran"] is True
    assert out["timestamps"] == [(1, 1, 8.0), (1, 1, 12.0), (1, 1, 18.0)]
    zen = out["solar_zeniths"]
    assert len(zen) == 3 and all(0.0 <= z <= 180.0 for z in zen)
    assert zen[1] < zen[0] and zen[1] < zen[2]
