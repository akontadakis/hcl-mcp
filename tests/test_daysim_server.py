import os
import asyncio
import hcl_mcp.server as srv
import hcl_mcp.resources as res

def test_daysim_status_tool_shape():
    st = srv.daysim_status()
    assert set(["available", "bin_dir", "version", "found", "missing"]) <= set(st.keys())

def test_build_daysim_tool_emits_plan():
    out = srv.build_daysim(src_dir="/tmp/Daysim", run=False)
    assert out["ran"] is False
    assert any("MITSustainableDesignLab/Daysim" in c for c in out["commands"])
    assert any("-DBUILD_HEADLESS=ON" in c for c in out["commands"])

def test_generate_subhourly_wea_emit_path(tmp_path, monkeypatch):
    import hcl_daysim.subhourly as sub
    monkeypatch.setattr(sub, "_available", lambda: False)
    out = asyncio.run(srv.generate_subhourly_wea(
        epw="/w/in.epw", timestep_min=6, latitude=47.6, longitude=-122.3, time_zone=120,
        site_elevation=20, work_dir=str(tmp_path), run=False))
    assert out["ran"] is False and any("ds_shortterm" in c for c in out["commands"])

def test_trim_subhourly_result_offloads_large_arrays(tmp_path):
    # DEF-6: a large timestamps/solar_zeniths pair must be written to a sidecar CSV and dropped from
    # the inline response, replaced by a path + count + preview.
    n = srv._MAX_INLINE_TIMESTEPS + 50
    res = {"wea": "/w/x.wea", "ran": True, "commands": [],
           "timestamps": [f"t{i}" for i in range(n)], "solar_zeniths": [float(i) for i in range(n)]}
    out = srv._trim_subhourly_result(res, str(tmp_path))
    assert "timestamps" not in out and "solar_zeniths" not in out
    assert out["n_timesteps"] == n
    assert out["timesteps_csv"].endswith("subhourly_timesteps.csv")
    assert os.path.exists(out["timesteps_csv"])
    assert len(out["timesteps_preview"]) == 6
    # CSV has a header + one row per timestep
    lines = open(out["timesteps_csv"]).read().strip().splitlines()
    assert lines[0] == "index,timestamp,solar_zenith_deg" and len(lines) == n + 1

def test_trim_subhourly_result_keeps_small_arrays_inline(tmp_path):
    res = {"wea": "/w/x.wea", "ran": True, "timestamps": ["t0", "t1"], "solar_zeniths": [1.0, 2.0]}
    out = srv._trim_subhourly_result(res, str(tmp_path))
    assert out["timestamps"] == ["t0", "t1"] and "timesteps_csv" not in out

def test_daysim_reference_resource_text():
    txt = res.reference_daysim()
    assert "ds_shortterm" in txt and "epw2wea" in txt
    assert "NRC" in txt or "Fraunhofer" in txt
