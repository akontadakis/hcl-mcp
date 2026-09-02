# tests/test_sensor_methodology_interior.py
import os
from hcl_radiance.geometry_obj import parse_obj
from hcl_radiance.sensor_methodology import floor_top_z, detect_interior

OBJ = os.path.join(os.path.dirname(__file__), "fixtures", "office_room.obj")
MAP = {"Rad_Floor_R020": {"type": "floor", "refl": 0.2},
       "Rad_Wall_R050": {"type": "plastic", "refl": 0.5},
       "Rad_Ceiling_R080": {"type": "plastic", "refl": 0.8},
       "Rad_Glazing_T073": {"type": "glass", "tvis": 0.73}}


def _p():
    with open(OBJ) as fh:
        return parse_obj(fh.read())


def test_floor_top_z_is_zero():
    assert abs(floor_top_z(_p(), MAP, 1.0, "Z") - 0.0) < 1e-6


def test_inner_surface_interior_is_4x7():
    xmin, xmax, ymin, ymax, src = detect_interior(_p(), MAP, 1.0, "Z")
    assert src == "inner_surface"
    assert abs(xmin + 2.0) < 0.05 and abs(xmax - 2.0) < 0.05   # +/-2.0 -> 4.0 wide
    assert abs(ymin + 3.5) < 0.05 and abs(ymax - 3.5) < 0.05   # +/-3.5 -> 7.0 long


def test_override_wins():
    out = detect_interior(_p(), MAP, 1.0, "Z", override=[-1, 1, -2, 2])
    assert out == (-1, 1, -2, 2, "override")


FLOOR_ONLY = "v -1 -1 0\nv 1 -1 0\nv 1 1 0\nv -1 1 0\nusemtl F\nf 1 2 3 4\n"

def test_fallback_floor_when_no_walls():
    from hcl_radiance.geometry_obj import parse_obj
    out = detect_interior(parse_obj(FLOOR_ONLY), {"F": {"type": "floor", "refl": 0.2}}, 1.0, "Z")
    assert out[4] == "fallback_floor"

def test_fallback_floor_inset_with_thickness():
    from hcl_radiance.geometry_obj import parse_obj
    out = detect_interior(parse_obj(FLOOR_ONLY), {"F": {"type": "floor", "refl": 0.2}}, 1.0, "Z",
                          wall_thickness=0.1)
    assert out[4] == "fallback_floor_inset"
    assert abs(out[0] - (-0.9)) < 1e-9 and abs(out[1] - 0.9) < 1e-9

def test_ceiling_z_detected():
    from hcl_radiance.sensor_methodology import _ceiling_z
    p = _p()
    cz = _ceiling_z(p, MAP, 1.0, "Z", floor_top_z(p, MAP, 1.0, "Z"))
    assert cz is not None and abs(cz - 3.0) < 0.1


# A3 — non-axis-aligned (leaning) east wall: top edge at x=3.8, bottom edge at x=4.0.
SKEWED_ROOM = (
    "v 0 0 0\nv 4 0 0\nv 4 6 0\nv 0 6 0\n"          # 1-4 floor corners (z=0)
    "v 0 0 3\nv 4 0 3\nv 4 6 3\nv 0 6 3\n"          # 5-8 ceiling corners (z=3)
    "v 3.8 0 3\nv 3.8 6 3\n"                         # 9-10 east-wall top (leans inward)
    "usemtl FLOOR\nf 1 2 3 4\n"
    "usemtl CEIL\nf 5 6 7 8\n"
    "usemtl WALL\n"
    "f 1 2 6 5\n"                                    # south wall (y=0)
    "f 4 3 7 8\n"                                    # north wall (y=6)
    "f 1 4 8 5\n"                                    # west wall  (x=0)
    "f 2 3 10 9\n"                                   # east wall  (slanted: x 4.0 -> 3.8)
)
SKEW_MAP = {"FLOOR": {"type": "floor", "refl": 0.2},
            "WALL": {"type": "plastic", "refl": 0.5},
            "CEIL": {"type": "plastic", "refl": 0.8}}


def test_skewed_wall_uses_inner_surface_not_outer_edge():
    """A3: for a leaning (non-axis-aligned) wall the interior boundary must be the room-facing
    (inner) edge of the chosen wall face, not its outer edge."""
    xmin, xmax, ymin, ymax, src = detect_interior(parse_obj(SKEWED_ROOM), SKEW_MAP, 1.0, "Z")
    assert src == "inner_surface"
    # East wall leans from x=4.0 (bottom/outer) to x=3.8 (top/inner): interior must stop at the
    # inner edge (~3.8), not extend out to 4.0.
    assert xmax < 3.9, f"interior xmax {xmax} reached the OUTER wall edge instead of the inner surface"
    assert abs(xmax - 3.8) < 0.05


# A4 — a face tilted ~45 deg (nz ~ 0.707) rising in +y; not a ceiling.
TILTED = (
    "v 0 0 0\nv 4 0 0\nv 4 6 0\nv 0 6 0\n"          # floor (z=0)
    "v 0 0 0\nv 4 0 0\nv 4 6 6\nv 0 6 6\n"          # 45-degree tilted face
    "usemtl F\nf 1 2 3 4\n"
    "usemtl W\nf 5 6 7 8\n"
)
TILT_MAP = {"F": {"type": "floor", "refl": 0.2}, "W": {"type": "plastic", "refl": 0.5}}


def test_ceiling_ignores_steeply_tilted_face():
    """A4: a face tilted ~45 deg (nz ~ 0.707) is not a ceiling; _ceiling_z must reject it instead
    of reporting its mid-height as the ceiling."""
    from hcl_radiance.sensor_methodology import _ceiling_z
    p = parse_obj(TILTED)
    fz = floor_top_z(p, TILT_MAP, 1.0, "Z")
    assert _ceiling_z(p, TILT_MAP, 1.0, "Z", fz) is None


# A4 — a genuine shallow sloped ceiling (~30 deg, nz ~ 0.866) must STILL be detected; the
# threshold must reject steep wall-ish faces without discarding typical sloped ceilings.
SLOPED_CEILING = (
    "v 0 0 0\nv 4 0 0\nv 4 6 0\nv 0 6 0\n"          # floor (z=0)
    "v 0 0 0\nv 4 0 0\nv 4 6 3.4641\nv 0 6 3.4641\n"  # ~30 deg pitch (tan30*6=3.4641)
    "usemtl F\nf 1 2 3 4\n"
    "usemtl W\nf 5 6 7 8\n"
)


def test_ceiling_detects_shallow_sloped_ceiling():
    """A4: a ~30 deg sloped ceiling (nz ~ 0.866) is a legitimate ceiling and must be detected."""
    from hcl_radiance.sensor_methodology import _ceiling_z
    p = parse_obj(SLOPED_CEILING)
    fz = floor_top_z(p, TILT_MAP, 1.0, "Z")
    cz = _ceiling_z(p, TILT_MAP, 1.0, "Z", fz)
    assert cz is not None and abs(cz - 1.7320) < 0.01   # mid-height of the 0..3.4641 slope
