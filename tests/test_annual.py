import hcl_radiance.annual as annual

def test_run_annual_emits_when_unavailable(tmp_path):
    out = annual.run_annual(channel_scenes=[{"materials": "m.rad", "geometry": "g.rad",
                                             "sky_color": [0.3, 0.4, 0.5]}],
                            wea="w.wea", points="pts.pts", channel_type=0,
                            work_dir=str(tmp_path), run=False)
    assert out["ran"] is False
    blob = " ".join(out["commands"])
    assert "rfluxmtx" in blob and "gendaymtx -m 1 -s -c" in blob and "dctimestep" in blob and "rcontrib" in blob
    # GAP 1: the .cal staging copy commands are emitted so the run is reproducible.
    assert "reinhartb.cal" in blob and "reinsrc.cal" in blob and "reinhart.cal" in blob
    # ...and they appear BEFORE the first rfluxmtx/rcontrib that needs them.
    assert blob.index("reinhartb.cal") < blob.index("rfluxmtx")

def test_run_annual_9channel_requires_three_scenes(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        annual.run_annual(channel_scenes=[{"materials": "m.rad", "geometry": "g.rad", "sky_color": [1, 1, 1]}],
                          wea="w.wea", points="p.pts", channel_type=1, work_dir=str(tmp_path), run=False)

def test_run_annual_period_subsets_wea(tmp_path):
    # 6 header lines + 24 hourly data lines for Jan 1
    wea = tmp_path / "full.wea"
    header = "place\nlat 0\nlon 0\nmer 0\n1\n6\n"
    data = "".join(f"1 1 {h}.5 {h*10} {h*5}\n" for h in range(24))
    wea.write_text(header + data)
    out = annual.run_annual(channel_scenes=[{"materials": "m.rad", "geometry": "g.rad",
                                             "sky_color": [0.3, 0.4, 0.5]}],
                            wea=str(wea), points="pts.pts", channel_type=0,
                            work_dir=str(tmp_path), run=False, period=[[1, 1, 8], [1, 1, 10]])
    assert out["ran"] is False
    # the period-subset .wea was written and is what gendaymtx is told to read
    subset = (tmp_path / "period.wea").read_text().splitlines()
    assert subset[:6] == header.splitlines()           # header preserved
    assert len(subset) == 6 + 3                          # hours 8,9,10 only
    blob = " ".join(out["commands"])
    assert "gendaymtx -m 1 -s -c 0.3 0.4 0.5 period.wea" in blob

def test_build_annual_steps_shared_between_run_and_separated(tmp_path):
    # RAD-6: both entry points consume the same _build_annual_steps helper, so with no period
    # they MUST emit a byte-identical command list (the per-channel step loop is the single source).
    scenes = [{"materials": "m.rad", "geometry": "g.rad", "sky_color": [0.3, 0.4, 0.5]}]
    wd = str(tmp_path)  # same work_dir so the .cal-staging cp commands (which embed work_dir) match
    a = annual.run_annual(channel_scenes=scenes, wea="w.wea", points="pts.pts",
                          channel_type=0, work_dir=wd, run=False)
    b = annual.run_annual_separated(channel_scenes=scenes, wea="w.wea", points="pts.pts",
                                    channel_type=0, work_dir=wd, run=False)
    assert a["commands"] == b["commands"]

def test_run_annual_period_emits_subset_command_when_wea_missing(tmp_path):
    out = annual.run_annual(channel_scenes=[{"materials": "m.rad", "geometry": "g.rad",
                                             "sky_color": [0.3, 0.4, 0.5]}],
                            wea="missing.wea", points="pts.pts", channel_type=0,
                            work_dir=str(tmp_path), run=False, period=[[1, 1, 8], [1, 1, 10]])
    assert out["ran"] is False
    assert not (tmp_path / "period.wea").exists()
    blob = " ".join(out["commands"])
    assert "subset_wea missing.wea period.wea" in blob
    assert "gendaymtx -m 1 -s -c 0.3 0.4 0.5 period.wea" in blob

from hcl_radiance.annual import _build_annual_steps

def test_build_annual_steps_default_is_2tuple_byte_identical():
    scenes = [{"materials": ["m.rad"], "geometry": "g.rad", "sky_color": [1, 1, 1]}]
    steps, outs = _build_annual_steps(scenes, "in.wea", "pts.pts", "-ab 2", 1,
                                      work_dir="/tmp/hcl_reg", run_available=False)
    assert outs == [("annual_sky0.ill", "annual_sun0.ill")]   # 2-tuple, no ASE pass
    cmds = " ".join(" ".join(s["cmd"]) for s in steps)
    assert "annual_sun_ase0.ill" not in cmds                  # no ASE step when ase_rad_params=None


def test_run_annual_emit_has_no_ase_steps(tmp_path):
    # full run_annual emit unchanged by the ase_rad_params addition (Task 12): daylight_savings /
    # run_annual callers that never pass ase_rad_params must see byte-identical, ASE-free commands.
    scenes = [{"materials": ["m.rad"], "geometry": "g.rad", "sky_color": [1, 1, 1]}]
    out = annual.run_annual(channel_scenes=scenes, wea="in.wea", points="pts.pts",
                            channel_type=0, work_dir=str(tmp_path), run=False)
    flat = " ".join(out["commands"]).lower()   # commands are pre-rendered shell strings
    assert "ase" not in flat
