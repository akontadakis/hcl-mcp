import os
import pytest
from hcl_radiance.sensor_methodology import en12464_grid
from hcl_radiance.footprint import floor_polygons
from hcl_radiance.geometry_obj import parse_obj

L = [(0.0, 0.0), (6.0, 0.0), (6.0, 3.0), (3.0, 3.0), (3.0, 6.0), (0.0, 6.0)]
FIXDIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_grid_no_footprint_is_unchanged():
    pts0, meth0 = en12464_grid((0.0, 4.0, 0.0, 6.0), 0.0)
    pts1, meth1 = en12464_grid((0.0, 4.0, 0.0, 6.0), 0.0, footprint=None)
    assert pts0 == pts1
    assert "clipped" not in meth1


def test_grid_L_footprint_drops_notch_cells():
    # interior bbox is the full 6x6 that bounds the L; clip to the L slab
    pts, meth = en12464_grid((0.0, 6.0, 0.0, 6.0), 0.0, footprint=[L])
    # every kept point must be inside the L (no point with x>3 and y>3)
    assert all(not (p[0] > 3.0 and p[1] > 3.0) for p in pts)
    assert meth["clipped"]["dropped"] > 0
    assert meth["clipped"]["kept"] == len(pts) == meth["count"]


def test_office_grid_byte_identical_with_footprint_border_zero():
    obj = os.path.join(FIXDIR, "office_room.obj")
    with open(obj) as fh:
        parsed = parse_obj(fh.read())
    mm = {"Rad_Floor_R020": {"type": "floor"}}
    # baseline (no clip) vs clip with border 0 against the floor slab
    base, _ = en12464_grid((-2.0, 2.0, -3.5, 3.5), 0.0)
    polys = floor_polygons(parsed, mm, 1.0, "Z")
    clipped, meth = en12464_grid((-2.0, 2.0, -3.5, 3.5), 0.0, footprint=polys, footprint_border=0.0)
    assert clipped == base
    assert meth["clipped"]["dropped"] == 0
