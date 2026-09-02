import asyncio
import os
import pytest
from hcl_radiance.discover import radiance_status

pytestmark = pytest.mark.skipif(not radiance_status()["available"],
                                reason="Radiance not installed")

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "synthetic_typeC.ies")

_FLOOR = ("void plastic floor_mat\n0\n0\n5 0.5 0.5 0.5 0 0\n\n"
          "floor_mat polygon floor\n0\n0\n12  -5 -5 0   5 -5 0   5 5 0   -5 5 0\n")
_SKY = ("void glow skyglow\n0\n0\n4 1 1 1 0\n\n"
        "skyglow source sky\n0\n0\n4 0 0 1 180\n")


def _write_scene(tmp_path):
    """Minimal lit room: a grey floor + a uniform glow sky. Returns (floor_path, sky_path)."""
    floor = tmp_path / "floor.rad"
    floor.write_text(_FLOOR)
    sky = tmp_path / "sky.rad"
    sky.write_text(_SKY)
    return str(floor), str(sky)


def test_ies2rad_runs_and_writes_rad(tmp_path):
    import hcl_mcp.server as srv
    out = asyncio.run(srv.ies_to_radiance(ies=FIX, units=2, work_dir=str(tmp_path), run=True))
    assert out["ran"] is True and out.get("returncode", 0) == 0
    assert any(f.endswith(".rad") for f in os.listdir(tmp_path))


def test_grid_electric_contributes_real_illuminance(tmp_path):
    """Full live electric grid path: ies2rad -o -> colorize (real luminaire) -> !xform place ->
    oconv(combined/electric) -> rtrace. Guards the colorize-before-ies2rad / bare-xform regressions:
    the luminaire must actually emit, so electric illuminance is strictly positive and combined ~=
    daylight + electric (Radiance superposition, within ambient sampling variance)."""
    import hcl_radiance.grid as grid
    floor, sky = _write_scene(tmp_path)
    out = grid.run_grid(
        scene_sets=[[floor, sky]],
        points=[[0, 0, 0.1, 0, 0, 1]], channel_type=0,
        electric_lights=[{"ies": FIX, "placement": {"positions": [{"xyz": [0, 0, 2.5]}]},
                          "wattage": 40}],
        work_dir=str(tmp_path), run=True)
    assert out["ran"] is True and out.get("error") is None
    d = out["daylight"]["metrics"][0]["photopic_lux"]
    e = out["electric"]["metrics"][0]["photopic_lux"]
    c = out["combined"]["metrics"][0]["photopic_lux"]
    assert e > 1.0                              # the placed luminaire really emits light
    assert abs(c - (d + e)) / (d + e) < 0.05    # combined ~= daylight + electric
    assert out["total_wattage"] == 40


def test_image_glare_electric_produces_numeric_ugr(tmp_path):
    """Full live electric glare path: ies2rad -> colorize -> !xform -> oconv(combined) -> rpict
    fisheye -> evalglare -> parse. Asserts a numeric UGR/DGP comes back (guards the oconv
    `undefined modifier xform` regression)."""
    import hcl_radiance.image as image
    floor, sky = _write_scene(tmp_path)
    out = image.run_image(
        scene_sets=[[floor, sky]], channel_type=0,
        view="-vta -vh 180 -vv 180 -vp 0 0 1.2 -vd 0 0 1 -vu 0 1 0", x=200, y=200,
        electric_lights=[{"ies": FIX, "placement": {"positions": [{"xyz": [0, 0, 2.5]}]},
                          "wattage": 40}],
        glare=True, work_dir=str(tmp_path), run=True)
    assert out["ran"] is True and out.get("error") is None
    assert "glare" in out
    assert out["glare"]["UGR"] is not None and out["glare"]["DGP"] is not None
    assert out["total_wattage"] == 40
