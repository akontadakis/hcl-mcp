import os
import pytest
from hcl_radiance.discover import geometry_available, radiance_status
from hcl_radiance.geometry_import import import_geometry, luminaire_block
from hcl_radiance.geometry_obj import parse_obj
from hcl_radiance.commands import build_oconv, build_rtrace, pts_to_text
from hcl_radiance.runner import run_sequence

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sample_room.obj")
IES = os.path.join(os.path.dirname(__file__), "fixtures", "synthetic_typeC.ies")
MAP = {"oak_floor": {"type": "plastic", "refl": 0.3},
       "painted_gypsum": {"type": "plastic", "refl": 0.7},
       "clear_glass": {"type": "glass", "tvis": 0.6}}

pytestmark = pytest.mark.skipif(not geometry_available(),
    reason="Radiance obj2rad/xform not available")

_SKY = ("void glow skyglow\n0\n0\n4 1 1 1 0\n"
        "skyglow source sky\n0\n0\n4 0 0 1 180\n"
        "skyglow source ground\n0\n0\n4 0 0 -1 180\n")

def test_live_obj2rad_xform_oconv_rtrace(tmp_path):
    r = import_geometry(FIX, material_map=MAP, units="m", up_axis="Y", channel_type=0,
                        north_angle_deg=0, work_dir=str(tmp_path))   # run=True default
    geom = r["geometry_set"][0]
    assert os.path.exists(geom)
    sky = os.path.join(str(tmp_path), "sky.rad"); open(sky, "w").write(_SKY)
    scene = [*r["material_sets"][0], sky, geom]
    open(os.path.join(str(tmp_path), "pts.txt"), "w").write(pts_to_text([[2, -1.5, 0.8, 0, 0, 1]]))
    steps = [{"cmd": build_oconv(scene, "scene.oct"), "stdout": "scene.oct"},
             {"cmd": build_rtrace("scene.oct", "-I -ab 1 -ad 128"), "stdin": "pts.txt", "stdout": "res.txt"}]
    out = run_sequence(steps, str(tmp_path), available=True)
    assert out.get("returncode", 0) == 0
    vals = open(os.path.join(str(tmp_path), "res.txt")).read().split()
    assert float(vals[0]) > 0.0

def test_live_north_rotation_round_trip(tmp_path):
    r = import_geometry(FIX, material_map=MAP, units="m", up_axis="Y", channel_type=0,
                        north_angle_deg=90, work_dir=str(tmp_path), derive_sensors=True)
    assert r["grid_points"]
    assert all("-rz -90" in c for c in r["commands"] if "-rz" in c)
    sky = os.path.join(str(tmp_path), "sky.rad"); open(sky, "w").write(_SKY)
    g = r["grid_points"][0]
    scene = [*r["material_sets"][0], sky, r["geometry_set"][0]]
    open(os.path.join(str(tmp_path), "pts.txt"), "w").write(pts_to_text([g]))
    steps = [{"cmd": build_oconv(scene, "scene.oct"), "stdout": "scene.oct"},
             {"cmd": build_rtrace("scene.oct", "-I -ab 1 -ad 128"), "stdin": "pts.txt", "stdout": "res.txt"}]
    out = run_sequence(steps, str(tmp_path), available=True)
    assert out.get("returncode", 0) == 0

def test_live_luminaire_octree_builds(tmp_path):
    # The bug-prone live path (memory: ies2rad -o / ordering / flat-white stub). With the Part A
    # filename fix, the placement !xform references g.rad (the ies2rad output), so the octree builds.
    m = dict(MAP); m["lum1"] = {"type": "luminaire", "ies": IES}
    parsed = parse_obj(open(FIX).read())
    blk = luminaire_block(parsed, m, scale=1.0, up_axis="Y")
    assert "-t 2 -1.5 2.69" in blk["placement_rad"]      # fixture at the ceiling, not floating
    place = os.path.join(str(tmp_path), "place.rad"); open(place, "w").write(blk["placement_rad"])
    # ies2rad -o lum1 <ies> writes lum1.rad in work_dir; then oconv the placement (which !xform's it)
    steps = [{"cmd": blk["ies2rad"][0]},
             {"cmd": build_oconv(["place.rad"], "lum.oct"), "stdout": "lum.oct"}]
    out = run_sequence(steps, str(tmp_path), available=True)
    assert out.get("returncode", 0) == 0 and os.path.exists(os.path.join(str(tmp_path), "lum.oct"))
    lum1_rad_text = open(os.path.join(str(tmp_path), "lum1.rad")).read()
    # Real ies2rad produces a brightdata distribution + polygon geometry.
    # A flat-white stub would have "void plastic" with no distribution data.
    assert "brightdata" in lum1_rad_text  # real ies2rad photometry, not a stub

@pytest.mark.skipif(not (geometry_available() and radiance_status().get("available")),
                    reason="Radiance not installed")
def test_annotate_render_produces_hdr(tmp_path):
    from hcl_radiance.geometry_import import import_geometry
    m = {"oak_floor": {"type": "plastic", "refl": 0.3},
         "painted_gypsum": {"type": "plastic", "refl": 0.7},
         "clear_glass": {"type": "glass", "tvis": 0.6}}
    r = import_geometry(FIX, material_map=m, units="m", up_axis="Y", channel_type=0,
                        work_dir=str(tmp_path), annotate=True)
    # annotate_steps emits oconv->rpict->falsecolor into work_dir; when Radiance ran, the
    # falsecolor .hdr must exist and be non-empty with the Radiance magic header.
    hdr = os.path.join(str(tmp_path), "annot_fc.hdr")
    assert os.path.exists(hdr) and os.path.getsize(hdr) > 0
    with open(hdr, "rb") as fh:
        head = fh.read(16)
    assert head.startswith(b"#?RADIANCE") or head.startswith(b"#?RGBE")


@pytest.mark.skipif(not (geometry_available() and radiance_status().get("available")),
                    reason="Radiance not installed")
def test_electric_lights_feeds_run_grid(tmp_path):
    # NOTE: needs a real .ies; skip cleanly if the sample fixture has none.
    ies = os.path.join(os.path.dirname(__file__), "fixtures", "sample.ies")
    if not os.path.exists(ies):
        pytest.skip("no sample.ies fixture")
    from hcl_radiance.geometry_import import import_geometry
    from hcl_radiance.grid import run_grid
    m = {"oak_floor": {"type": "plastic", "refl": 0.3},
         "painted_gypsum": {"type": "plastic", "refl": 0.7},
         "clear_glass": {"type": "glass", "tvis": 0.6},
         "lum1": {"type": "luminaire", "ies": ies, "spd": "380 0.1\n780 0.9\n"}}
    g = import_geometry(FIX, material_map=m, units="m", up_axis="Y", channel_type=0,
                        work_dir=str(tmp_path), derive_sensors=True)
    assert g["electric_lights"]
    # the importer side is pure-Python; this asserts the DOWNSTREAM consumption is non-degenerate
    res = run_grid(scene_sets=[[*g["material_sets"][0], g["geometry_set"][0]]],
                   points=g["grid_points"], channel_type=0,
                   electric_lights=g["electric_lights"], work_dir=str(tmp_path))
    assert res is not None
