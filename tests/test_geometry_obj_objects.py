# tests/test_geometry_obj_objects.py
import os
from hcl_radiance.geometry_obj import parse_obj, object_centroid

OBJ = os.path.join(os.path.dirname(__file__), "fixtures", "office_room.obj")


def _parsed():
    with open(OBJ) as fh:
        return parse_obj(fh.read())


def test_faces_carry_distinct_object_names():
    p = _parsed()
    objs = {f["object"] for f in p["faces"] if f.get("object")}
    assert "Chair_Seat_1" in objs and "Chair_Seat_2" in objs   # not collapsed to one material


def test_group_key_unchanged_is_usemtl():
    p = _parsed()
    groups = {f["group"] for f in p["faces"]}
    assert "Rad_Furniture_R050" in groups   # usemtl semantics preserved


def test_object_precedence_over_group():
    # 'o Obj' then 'g Grp' then a face -> object is the 'o' name
    p = parse_obj("v 0 0 0\nv 1 0 0\nv 0 1 0\no Obj\ng Grp\nusemtl M\nf 1 2 3\n")
    assert p["faces"][0]["object"] == "Obj"
    assert p["faces"][0]["group"] == "M"


def test_object_centroid_matches_seat():
    p = _parsed()
    cx, cy, _ = object_centroid(p, "Chair_Seat_1", scale=1.0, up_axis="Z")
    assert abs(cx - 1.75) < 0.05 and abs(cy + 1.20) < 0.05


def test_object_centroid_y_up_remap():
    # up_axis="Y" must apply the _to_world remap (x, y, z) -> (x, -z, y)
    p = parse_obj("v 1 2 3\nv 1 2 3\nv 1 2 3\no Tri\nf 1 2 3\n")
    assert object_centroid(p, "Tri", scale=1.0, up_axis="Y") == (1.0, -3.0, 2.0)


def test_object_centroid_empty_returns_origin():
    p = parse_obj("v 0 0 0\nv 1 0 0\nv 0 1 0\no Tri\nf 1 2 3\n")
    assert object_centroid(p, "NoSuchObject") == (0.0, 0.0, 0.0)


def test_object_centroid_applies_scale():
    p = parse_obj("v 1 2 3\nv 1 2 3\nv 1 2 3\no T\nf 1 2 3\n")
    assert object_centroid(p, "T", scale=2.0, up_axis="Z") == (2.0, 4.0, 6.0)
