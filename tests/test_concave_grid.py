"""TDD tests: workplane_grid must support concave (L-shaped) rooms end-to-end.

detect_interior's innermost-wall-face rule collapses to an inner sub-rectangle (or a
degenerate zero-extent bbox) for concave rooms; workplane_grid must detect this and fall
back to the floor-polygon bounding box (clipped to the footprint) instead of crashing or
silently covering only one arm of the L.
"""
import os
import asyncio
import json

from hcl_mcp.server import workplane_grid

ROOT = os.path.join(os.path.dirname(__file__), "fixtures")
OFFICE_OBJ = os.path.join(ROOT, "office_room.obj")
OFFICE_SIDE = os.path.join(ROOT, "office_room_material_map.json")
L_OBJ = os.path.join(ROOT, "l_room.obj")
L_MAP = os.path.join(ROOT, "l_room_material_map.json")


def _call(**kw):
    return asyncio.run(workplane_grid(**kw))


def test_office_grid_still_byte_identical_regression(tmp_path):
    """Rectangular office room: DI is trustworthy (area ratio ~0.89 >= 0.6) -> DI path
    preserved, count stays 45 exactly as before this fix."""
    r = _call(obj_path=OFFICE_OBJ, sidecar=OFFICE_SIDE, work_dir=str(tmp_path))
    assert r["methodology"]["count"] == 45
    assert r["methodology"]["n_cells"] == {"x": 5, "y": 9}


def test_concave_opaque_l_covers_both_arms(tmp_path):
    """L-room with an all-opaque Window (material_map override to plastic): DI collapses
    to the inner 3x3 sub-square (area ratio 0.25 < 0.6) -> fallback to the floor bbox,
    clipped to the L footprint. The grid must cover BOTH arms of the L, not just one
    quadrant, and must drop the removed notch (x>3 and y>3)."""
    with open(L_MAP) as fh:
        mm = json.load(fh)
    mm = dict(mm)
    mm["Window"] = {"type": "plastic"}   # all-opaque concave variant, no new fixture needed

    r = _call(obj_path=L_OBJ, material_map=mm, units="m", up_axis="Z",
              work_dir=str(tmp_path))
    meth = r["methodology"]
    pts = r["points"]

    assert meth["count"] > 9
    assert any(p[0] > 3.0 for p in pts), "grid must cover the east arm (x>3)"
    assert any(p[1] > 3.0 for p in pts), "grid must cover the north arm (y>3)"
    assert not any(p[0] > 3.0 and p[1] > 3.0 for p in pts), "notch must be dropped"
    assert meth["clipped"]["dropped"] > 0
    assert meth["interior_extent_source"] == "footprint_bbox"
    assert any("concave" in w or "degenerate" in w for w in r["warnings"])


def test_concave_glazed_l_no_longer_raises(tmp_path):
    """As-shipped l_room.obj (south wall fully glazed -> DI degenerate, height 0):
    workplane_grid must no longer raise ValueError, and must return a non-empty grid
    covering both arms."""
    with open(L_MAP) as fh:
        mm = json.load(fh)

    r = _call(obj_path=L_OBJ, material_map=mm, units="m", up_axis="Z",
              work_dir=str(tmp_path))
    meth = r["methodology"]
    pts = r["points"]

    assert meth["count"] > 0
    assert any(p[0] > 3.0 for p in pts)
    assert any(p[1] > 3.0 for p in pts)
    assert not any(p[0] > 3.0 and p[1] > 3.0 for p in pts)
    assert meth["interior_extent_source"] == "footprint_bbox"
