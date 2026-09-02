import os, asyncio
from hcl_mcp.server import photosensors

ROOT = os.path.join(os.path.dirname(__file__), "fixtures")
OBJ = os.path.join(ROOT, "office_room.obj")
SIDE = os.path.join(ROOT, "office_room_material_map.json")


def test_photosensors_tool_office(tmp_path):
    res = asyncio.run(photosensors(obj_path=OBJ, sidecar=SIDE,
                                   write_pts="photosensors.pts", work_dir=str(tmp_path)))
    assert len(res["points"]) == 2
    assert res["pts_path"] and os.path.exists(res["pts_path"])
    assert res["methodology"]["zone_rule"] == "head_height"
    assert res["methodology"]["facade"]["group"] == "Rad_Glazing_T073"
