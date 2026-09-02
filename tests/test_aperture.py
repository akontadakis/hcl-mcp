import math
import os
from hcl_radiance.aperture import (glass_faces, window_sender_rad, write_window_sender,
                                   faces_need_flip)
from hcl_radiance.geometry_obj import parse_obj

# 1x1 m square in the XZ plane at y=0, wound so the normal faces -Y (south, +Y north).
_SOUTH = """v 0 0 0
v 1 0 0
v 1 0 1
v 0 0 1
usemtl glazing
f 1 2 3 4
"""

# A second square at y=5 wound the other way, normal facing +Y (north).
_BOTH = _SOUTH + """v 0 5 0
v 0 5 1
v 1 5 1
v 1 5 0
usemtl glazing
f 5 6 7 8
"""

_MAP = {"glazing": {"type": "glass", "tvis": 0.7}}


def test_dereferences_vertex_indices_into_coordinates():
    """parse_obj returns 1-based INDICES in `verts`; they must be looked up."""
    faces = glass_faces(parse_obj(_SOUTH), _MAP)
    assert len(faces) == 1
    assert faces[0]["verts"] == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                                 (1.0, 0.0, 1.0), (0.0, 0.0, 1.0)]
    assert math.isclose(faces[0]["area"], 1.0, rel_tol=1e-9)


def test_azimuth_is_per_face_not_per_group():
    """One OBJ group, two opposite normals: a per-group mean would collapse these."""
    faces = glass_faces(parse_obj(_BOTH), _MAP)
    assert sorted(round(f["azimuth_deg"]) for f in faces) == [0, 180]


def test_tilt_of_a_vertical_window_is_90_degrees():
    faces = glass_faces(parse_obj(_SOUTH), _MAP)
    assert math.isclose(faces[0]["tilt_deg"], 90.0, abs_tol=1e-6)


def test_plane_offset_distinguishes_parallel_but_separate_windows():
    """2.2.6 groups COPLANAR windows; two parallel facades are not one group."""
    faces = glass_faces(parse_obj(_BOTH), _MAP)
    offsets = sorted(round(f["plane_offset"], 6) for f in faces)
    assert offsets == [0.0, 5.0]


def test_ignores_non_glass_groups():
    parsed = parse_obj(_SOUTH.replace("glazing", "walls"))
    assert glass_faces(parsed, {"walls": {"type": "plastic", "refl": 0.5}}) == []


_FACE = {"group": "glazing", "index": 0,
         "verts": [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
         "area": 1.0, "normal": (0, -1, 0), "azimuth_deg": 180.0,
         "tilt_deg": 90.0, "centroid": (0.5, 0.0, 0.5), "plane_offset": 0.0}


def test_sender_declares_the_klems_basis_and_up_vector():
    text = window_sender_rad([_FACE], "wg_south")
    assert "#@rfluxmtx" in text
    assert "h=kf" in text
    assert "u=+Z" in text


def test_glow_fourth_real_is_zero():
    """A non-zero fourth real makes the glow self-illuminating and corrupts the matrix."""
    assert "4 1 1 1 0" in window_sender_rad([_FACE], "wg_south")


def test_emits_one_polygon_per_face_with_all_vertices():
    text = window_sender_rad([_FACE], "wg_south")
    assert "wg_south polygon" in text
    assert text.count("polygon") == 1
    assert " 12 " in text or text.count("\n12 ") == 1   # 4 verts x 3 coords


def test_default_reverses_the_objs_outward_winding():
    """Live-measured: the V receiver must face INTO the room. An OBJ exterior wall is
    wound outward, so the default flips it. Getting this backwards yields a correctly
    shaped V matrix of exactly 0.0 -- silently, with no error or warning."""
    text = window_sender_rad([_FACE], "wg_south")
    assert "12 0 0 1 1 0 1 1 0 0 0 0 0" in text


def test_flip_off_keeps_the_objs_own_winding():
    text = window_sender_rad([_FACE], "wg_south", flip=False)
    assert "12 0 0 0 1 0 0 1 0 1 0 0 1" in text


def test_flip_is_measured_against_an_interior_point_when_given():
    """Nothing enforces OBJ winding convention, so the direction is measured, not assumed."""
    # _FACE sits at y=0 with normal (0,-1,0). A room at y>0 means it points away.
    assert faces_need_flip([_FACE], (0.5, 2.0, 0.5)) is True
    # A room on the other side means the same face already points inward.
    assert faces_need_flip([_FACE], (0.5, -2.0, 0.5)) is False


def test_write_emits_one_sender_serving_both_roles(tmp_path):
    """D is winding-insensitive, so one file serves V's receiver and D's sender."""
    path = write_window_sender([_FACE], "wg_south", str(tmp_path))
    assert os.path.isfile(path)
    assert path.endswith("wg_south_sender.rad")
    assert open(path).read() == window_sender_rad([_FACE], "wg_south", flip=True)


def test_write_honours_a_measured_interior_point(tmp_path):
    a = write_window_sender([_FACE], "wg_a", str(tmp_path), interior_point=(0.5, 2.0, 0.5))
    b = write_window_sender([_FACE], "wg_b", str(tmp_path), interior_point=(0.5, -2.0, 0.5))
    assert open(a).read() != open(b).read()


def test_group_name_is_used_as_the_modifier():
    text = window_sender_rad([_FACE], "wg_north")
    assert "void glow wg_north" in text
    assert "wg_south" not in text
