import os, asyncio
from hcl_mcp.prompts import place_sensors
from hcl_mcp.server import workplane_grid

ROOT = os.path.join(os.path.dirname(__file__), "fixtures")


def test_prompt_mentions_both_tools_and_steps():
    t = place_sensors("a 4x7 m office")
    assert "workplane_grid" in t and "observer_points" in t
    assert "EN 12464" in t and "glare" in t.lower()
    assert "a 4x7 m office" in t


def test_grid_pts_is_run_grid_consumable(tmp_path):
    r = asyncio.run(
        workplane_grid(obj_path=os.path.join(ROOT, "office_room.obj"),
                       sidecar=os.path.join(ROOT, "office_room_material_map.json"),
                       work_dir=str(tmp_path)))
    from hcl_radiance.annual import _count_points
    assert _count_points(r["pts_path"], str(tmp_path)) == 45
