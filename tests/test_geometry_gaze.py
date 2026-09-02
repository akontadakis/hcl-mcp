"""Derived-observer gaze must not depend on OBJ winding.

mean_aperture_normal fed `toward` into eye_observer_points and dgp_views, so a
reversed-wound window pointed every observer at the back wall -- a first-order
error on vertical eye illuminance (mel-EDI, nvRD, WELL L03).
"""
import hcl_radiance.geometry_import as gi
from hcl_radiance.geometry_obj import parse_obj

# 4x4 m room, floor at z=0, a south wall (y=0) that is entirely glazing.
# The room interior is at +y, so gaze from the glazing must point +y.
_FLOOR = """\
v 0 0 0
v 4 0 0
v 4 4 0
v 0 4 0
"""
_GLASS_CCW = """\
v 0 0 0
v 4 0 0
v 4 0 3
v 0 0 3
"""

def _obj(glass_face):
    return (_FLOOR + _GLASS_CCW
            + "g floor\nf 1 2 3 4\n"
            + "g glass\n" + glass_face)

MAP = {"floor": {"type": "floor", "refl": 0.2}, "glass": {"type": "glass", "tvis": 0.7}}


def test_gaze_points_into_the_room():
    parsed = parse_obj(_obj("f 5 6 7 8\n"))
    gx, gy = gi.mean_aperture_normal(parsed, MAP, "Z")
    assert gy > 0.9, f"gaze must point into the room (+y), got {(gx, gy)}"


def test_gaze_is_winding_independent():
    """The regression: reversing the glazing winding must not flip the gaze."""
    ccw = gi.mean_aperture_normal(parse_obj(_obj("f 5 6 7 8\n")), MAP, "Z")
    cw = gi.mean_aperture_normal(parse_obj(_obj("f 8 7 6 5\n")), MAP, "Z")
    assert ccw[1] > 0.9 and cw[1] > 0.9
    assert abs(ccw[0] - cw[0]) < 1e-6
    assert abs(ccw[1] - cw[1]) < 1e-6


def test_gaze_falls_back_without_glazing():
    """No glass group -> the documented (0,-1) fallback, not an exception."""
    parsed = parse_obj(_FLOOR + "g floor\nf 1 2 3 4\n")
    assert gi.mean_aperture_normal(parsed, {"floor": {"refl": 0.2}}, "Z") == (0.0, -1.0)


# Room centred at (100, 50) -- far from the world origin -- 20x10 m, glazing on its -Y
# (south) wall. The correct inward gaze is (0, 1) regardless of whether the floor group
# is typed: `_floor_centroid_xy` must not silently fall back to the world origin (0, 0)
# when no group resolves to type:"floor", or "inward" becomes "toward the origin", which
# for a room not centred there points outdoors.
def _offset_room(floor_typed):
    lines = [
        "v 90 45 0", "v 110 45 0", "v 110 55 0", "v 90 55 0",
        "v 90 45 3", "v 110 45 3", "v 110 55 3", "v 90 55 3",
        "v 92 45 0.5", "v 108 45 0.5", "v 108 45 2.5", "v 92 45 2.5",
    ]
    lines += [
        "g floor", "f 1 2 3 4",
        "g ceiling", "f 5 6 7 8",
        "g walls",
        "f 1 2 6 5", "f 2 3 7 6", "f 3 4 8 7", "f 4 1 5 8",
        "g glass", "f 9 10 11 12",
    ]
    obj = "\n".join(lines) + "\n"
    mm = {"ceiling": {"refl": 0.8}, "walls": {"refl": 0.7}, "glass": {"type": "glass", "tvis": 0.7}}
    mm["floor"] = {"type": "floor", "refl": 0.25} if floor_typed else {"refl": 0.25}
    return parse_obj(obj), mm


def test_gaze_with_typed_floor_on_an_offset_room():
    parsed, mm = _offset_room(floor_typed=True)
    gaze = gi.mean_aperture_normal(parsed, mm, "Z")
    assert gaze == (0.0, 1.0)


def test_gaze_with_untyped_floor_on_an_offset_room_still_points_inward():
    """The defect: with no group typed floor, _floor_centroid_xy used to fall back to the
    world origin (0, 0), so 'inward' became 'toward the origin' -- 116 degrees wrong for
    this room, pointing outdoors. It must now match the typed-floor case exactly, since
    the fallback (centroid of all non-context geometry) coincides with the floor centroid
    for this simple box room."""
    parsed, mm = _offset_room(floor_typed=False)
    gaze = gi.mean_aperture_normal(parsed, mm, "Z")
    assert gaze[1] > 0.9, f"gaze must point into the room (+y), got {gaze}"
    assert gaze == (0.0, 1.0)
