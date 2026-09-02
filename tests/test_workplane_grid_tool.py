"""TDD tests for workplane_grid MCP tool (Task 4)."""
import os
import asyncio
from hcl_mcp.server import workplane_grid

ROOT = os.path.join(os.path.dirname(__file__), "fixtures")
OBJ = os.path.join(ROOT, "office_room.obj")
SIDE = os.path.join(ROOT, "office_room_material_map.json")


def _call(**kw):
    return asyncio.run(workplane_grid(**kw))


def test_reproduces_reference_grid(tmp_path):
    r = _call(obj_path=OBJ, sidecar=SIDE, work_dir=str(tmp_path))
    assert r["methodology"]["count"] == 45
    assert r["methodology"]["n_cells"] == {"x": 5, "y": 9}
    assert os.path.isfile(r["pts_path"])
    assert len(open(r["pts_path"]).read().strip().splitlines()) == 45


def test_requires_material_map_or_sidecar(tmp_path):
    try:
        _call(obj_path=OBJ, work_dir=str(tmp_path))
        assert False, "expected ValueError"
    except ValueError as e:
        assert "material_map" in str(e)
