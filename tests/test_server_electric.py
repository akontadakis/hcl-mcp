import asyncio
import hcl_mcp.server as srv
import hcl_mcp.resources as res

def test_ies_analyze_tool():
    import os
    fix = os.path.join(os.path.dirname(__file__), "fixtures", "synthetic_typeC.ies")
    rep = srv.ies_analyze(open(fix).read())
    assert rep["rated_lumens"] == 1000.0 and rep["efficacy"] == 100.0

def test_ies_to_radiance_emit(tmp_path):
    out = asyncio.run(srv.ies_to_radiance(
        ies="lamp.ies", units=2, multiplier=1.0, maintenance_factor=0.8,
        placement={"positions": [{"xyz": [0, 0, 3]}]}, work_dir=str(tmp_path), run=False))
    blob = " ".join(out["commands"])
    assert "ies2rad" in blob and "-m 0.8" in blob and "xform" in blob

def test_glare_ugr_emit(tmp_path):
    out = asyncio.run(srv.glare_ugr(
        scene_sets=[["m.rad", "sky.rad", "g.rad"]], channel_type=0,
        view="-vta -vh 180 -vv 180", work_dir=str(tmp_path), run=False))
    assert out["ran"] is False
    assert any("evalglare" in c for c in out["commands"])

def test_new_tools_and_params_registered():
    names = {t.name for t in asyncio.run(srv.mcp.list_tools())}
    assert {"ies_analyze", "ies_to_radiance", "glare_ugr"} <= names

def test_run_grid_tool_accepts_electric_lights(tmp_path):
    out = asyncio.run(srv.run_grid(
        scene_sets=[["m.rad", "sky.rad", "g.rad"]], points=[[0, 0, 1.2, 0, 0, 1]],
        channel_type=0, work_dir=str(tmp_path), run=False,
        electric_lights=[{"ies": "lamp.ies", "placement": {"positions": [{"xyz": [0, 0, 3]}]},
                          "wattage": 40}]))
    assert out["ran"] is False and any("ies2rad" in c for c in out["commands"])

def test_reference_ies_resource_text():
    txt = res.reference_ies()
    assert "LM-63" in txt
    assert "candela_multiplier" in txt and "pfactor" in txt
    assert "TILT" in txt

def test_reference_ies_resource_registered():
    uris = {str(r.uri) for r in asyncio.run(srv.mcp.list_resources())}
    assert "hcl://reference/ies" in uris
