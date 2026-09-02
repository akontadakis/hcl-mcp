import os, asyncio
from hcl_mcp.server import observer_points

ROOT = os.path.join(os.path.dirname(__file__), "fixtures")
OBJ = os.path.join(ROOT, "office_room.obj")
SIDE = os.path.join(ROOT, "office_room_material_map.json")


def test_office_observers_are_inside_footprint(tmp_path):
    res = asyncio.run(observer_points(obj_path=OBJ, sidecar=SIDE,
                                      write_pts=None, work_dir=str(tmp_path)))
    assert res["observers"]
    assert res["methodology"]["footprint_checked"] is True
    # no warning about out-of-footprint observers on this rectangular room
    assert not any("outside the floor" in w for w in res["warnings"])
