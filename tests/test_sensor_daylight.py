import os, math
from hcl_radiance.sensor_daylight import (glazing_wall, daylight_zones, place_photosensors,
                                          _snap_into_footprint, _floor_centroid_xy)
from hcl_radiance.geometry_obj import parse_obj
from hcl_radiance.footprint import point_in_footprint

FIXDIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_daylight_zones_head_height_two_zones():
    zones = daylight_zones(2.48, 1.02)
    assert len(zones) == 2
    assert abs(zones[0]["sensor_depth"] - (2.0 / 3.0) * 2.48) < 1e-6
    assert abs(zones[1]["sensor_depth"] - (2.48 + (2.0 / 3.0) * 2.48)) < 1e-6


def test_daylight_zones_ies_mode_single_primary():
    zones = daylight_zones(2.48, 1.02, zone_rule="ies_2.5", task_height=0.8)
    assert len(zones) == 1
    assert abs(zones[0]["far"] - 2.5 * (2.48 - 0.8)) < 1e-6


OFFICE_MM = {"Rad_Floor_R020": {"type": "floor"}, "Rad_Glazing_T073": {"type": "glass"}}


def test_office_photosensors_reproduce_documented_coords():
    with open(os.path.join(FIXDIR, "office_room.obj")) as fh:
        parsed = parse_obj(fh.read())
    pts, meth = place_photosensors(parsed, OFFICE_MM, 1.0, "Z")
    assert len(pts) == 2
    assert meth["facade"]["group"] == "Rad_Glazing_T073"
    # sensor_1 ~ (0.00, 1.85, 0.80), sensor_2 ~ (0.00, -0.63, 0.80); tolerance for glazing-plane thickness
    assert abs(pts[0][0] - 0.0) < 0.1 and abs(pts[0][1] - 1.85) < 0.15 and abs(pts[0][2] - 0.80) < 1e-6
    assert abs(pts[1][0] - 0.0) < 0.1 and abs(pts[1][1] + 0.63) < 0.15 and abs(pts[1][2] - 0.80) < 1e-6
    assert pts[0][3:] == [0, 0, 1]


def test_glazing_wall_raises_without_glass():
    with open(os.path.join(FIXDIR, "office_room.obj")) as fh:
        parsed = parse_obj(fh.read())
    try:
        glazing_wall(parsed, {"Rad_Floor_R020": {"type": "floor"}}, 1.0, "Z")
        assert False, "expected ValueError"
    except ValueError:
        pass


# Shared-fix disclosure: _floor_centroid_xy backs both mean_aperture_normal (geometry_import)
# and glazing_wall/photosensors (this module). Fixing the untyped-floor origin fallback here
# therefore changes photosensors' zone placement too, on models with no group typed
# type:"floor" -- this is intentional (the same "inward" notion is wrong in both callers for
# the same reason) and is asserted directly here, not just in geometry_import's gaze tests.
_OFFSET_ROOM = """\
v 90 45 0
v 110 45 0
v 110 55 0
v 90 55 0
v 90 45 3
v 110 45 3
v 110 55 3
v 90 55 3
v 92 45 0.5
v 108 45 0.5
v 108 45 2.5
v 92 45 2.5
g floor
f 1 2 3 4
g ceiling
f 5 6 7 8
g walls
f 1 2 6 5
f 2 3 7 6
f 3 4 8 7
f 4 1 5 8
g glass
f 9 10 11 12
"""


def test_floor_centroid_xy_falls_back_to_non_context_centroid_not_the_origin():
    """No group typed floor -> must NOT silently return the world origin. This room is
    centred at (100, 50), so the origin fallback would be off by (100, 50)."""
    parsed = parse_obj(_OFFSET_ROOM)
    mm_untyped = {"ceiling": {"refl": 0.8}, "walls": {"refl": 0.7},
                  "glass": {"type": "glass"}, "floor": {"refl": 0.25}}
    cx, cy = _floor_centroid_xy(parsed, mm_untyped, 1.0, "Z")
    assert abs(cx - 100.0) < 1.0
    assert abs(cy - 50.0) < 1.0


def test_photosensors_inward_direction_unaffected_by_the_fix_when_floor_is_typed():
    """Sanity: with a typed floor, photosensors' inward direction is exactly the floor
    centroid as before -- the fix only changes behaviour in the untyped-floor fallback."""
    parsed = parse_obj(_OFFSET_ROOM)
    mm_typed = {"ceiling": {"refl": 0.8}, "walls": {"refl": 0.7},
                "glass": {"type": "glass"}, "floor": {"type": "floor", "refl": 0.25}}
    wall = glazing_wall(parsed, mm_typed, 1.0, "Z")
    assert wall["inward"] == (0.0, 1.0)


SQUARE_FOOTPRINT = [[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]]


def test_snap_into_footprint_pulls_outside_point_back_in():
    # facade point just inside the top edge, walking straight out (north, +y); the nominal
    # target d=3 lands at (2, 6.9), 2.9 m outside the 4x4 footprint -> must snap back inward
    # to just short of the boundary (interior, not on the exact edge -> no float-precision
    # knife-edge at the boundary itself).
    px0, py0 = 2.0, 3.9
    ix, iy = 0.0, 1.0
    d = 3.0
    sx, sy, snapped = _snap_into_footprint(px0, py0, ix, iy, d, SQUARE_FOOTPRINT)
    assert snapped is True
    assert point_in_footprint(sx, sy, SQUARE_FOOTPRINT)
    # snapped back near the facade point, well short of the unsnapped target (2, 6.9)
    assert abs(sx - 2.0) < 1e-9
    assert py0 <= sy < 4.0


def test_snap_into_footprint_noop_when_already_inside():
    # target already inside the footprint -> returned unchanged, snapped False
    px0, py0 = 0.0, 2.0
    ix, iy = 1.0, 0.0
    d = 1.0
    sx, sy, snapped = _snap_into_footprint(px0, py0, ix, iy, d, SQUARE_FOOTPRINT)
    assert snapped is False
    assert (sx, sy) == (px0 + ix * d, py0 + iy * d)
    assert point_in_footprint(sx, sy, SQUARE_FOOTPRINT)
