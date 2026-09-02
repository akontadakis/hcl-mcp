import os
from hcl_radiance.geometry_obj import parse_obj

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "l_room.obj")


def test_l_room_parses_expected_groups():
    with open(FIX) as fh:
        parsed = parse_obj(fh.read())
    groups = set(parsed["groups"])
    assert {"Floor", "Ceiling", "Window", "Walls"} <= groups
    floor = [f for f in parsed["faces"] if f["group"] == "Floor"]
    assert len(floor) == 1 and len(floor[0]["verts"]) == 6
