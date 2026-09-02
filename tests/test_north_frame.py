"""Nonzero-north frame contract: _rotate_north must be applied exactly once, consistently,
by the sensor-placement tools (workplane_grid here). Covers the highest-value gap found in
the final whole-branch review — no prior test exercised a nonzero rotation.
"""
import os
import asyncio

from hcl_radiance.geometry_import import _rotate_north
from hcl_mcp.server import workplane_grid

FIXDIR = os.path.join(os.path.dirname(__file__), "fixtures")
OBJ = os.path.join(FIXDIR, "office_room.obj")
MATERIAL_MAP = {"Rad_Floor_R020": {"type": "floor"}, "Rad_Glazing_T073": {"type": "glass"}}


def test_rotate_north_known_rows():
    # north_angle_deg=90 -> th = -90 deg -> (x, y) -> (y, -x); gaze (dx, dy) rotates the same way.
    rows = [[1.0, 0.0, 0.5, 0.0, 1.0, 0.0], [0.0, 2.0, 0.8, 1.0, 0.0, 0.0]]
    out = _rotate_north(rows, 90)
    assert out[0][:2] == [0.0, -1.0]
    assert out[0][3:5] == [1.0, 0.0]
    assert out[1][:2] == [2.0, 0.0]
    assert out[1][3:5] == [0.0, -1.0]
    # z / dz pass through untouched
    assert out[0][2] == 0.5 and out[0][5] == 0.0
    assert out[1][2] == 0.8 and out[1][5] == 0.0


def test_rotate_north_noop_at_zero():
    rows = [[1.0, 2.0, 0.5, 0.0, 1.0, 0.0]]
    assert _rotate_north(rows, 0) == rows
    assert _rotate_north(rows, None) == rows


def _rotate_xy(x, y, north_angle_deg):
    row = _rotate_north([[x, y, 0.0, 0.0, 0.0, 1.0]], north_angle_deg)[0]
    return row[0], row[1]


def test_workplane_grid_north_90_matches_single_rotation_of_north_0(tmp_path):
    r0 = asyncio.run(workplane_grid(obj_path=OBJ, material_map=MATERIAL_MAP, up_axis="Z",
                                    north_angle_deg=0, write_pts=None,
                                    work_dir=str(tmp_path / "n0")))
    r90 = asyncio.run(workplane_grid(obj_path=OBJ, material_map=MATERIAL_MAP, up_axis="Z",
                                     north_angle_deg=90, write_pts=None,
                                     work_dir=str(tmp_path / "n90")))
    pts0 = r0["points"]
    pts90 = r90["points"]
    assert len(pts0) == len(pts90) and len(pts0) > 0

    # Applying _rotate_north once more to the north=0 point set must reproduce the north=90
    # set exactly (within rounding) -> _rotate_north is applied exactly once by the tool.
    expected = _rotate_north(pts0, 90)
    assert len(expected) == len(pts90)
    for e, a in zip(expected, pts90):
        assert abs(e[0] - a[0]) < 1e-3
        assert abs(e[1] - a[1]) < 1e-3
        assert abs(e[2] - a[2]) < 1e-6
        assert abs(e[3] - a[3]) < 1e-6
        assert abs(e[4] - a[4]) < 1e-6
        assert abs(e[5] - a[5]) < 1e-6

    # Sanity: the two point sets are not identical (rotation actually happened, not a no-op).
    assert any(abs(p0[0] - p90[0]) > 1e-3 or abs(p0[1] - p90[1]) > 1e-3
              for p0, p90 in zip(pts0, pts90))

    # Direct spot-check on a couple of known rows using the (x, y) -> (y, -x) rule for north=90.
    for p0 in pts0[:2]:
        ex, ey = _rotate_xy(p0[0], p0[1], 90)
        match = next(p for p in pts90 if abs(p[0] - ex) < 1e-3 and abs(p[1] - ey) < 1e-3)
        assert abs(match[2] - p0[2]) < 1e-6
