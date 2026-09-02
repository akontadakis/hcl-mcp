"""derive_sensors must measure heights from the floor's TOP face (the walkable surface).

Regression for the floor-slab defect: `_world_footprint` returned `min(z)` over the floor
faces, which is the UNDERSIDE of a slab. On a model with a 0.200 m floor slab that placed the
EN 12464-1 working plane at 0.600 m instead of 0.800 m and eye points at 1.0/1.4 m instead of
1.2/1.6 m -- silently, and in disagreement with `workplane_grid`/`observer_points`, which use
`floor_top_z` on the same geometry.

EN 12464-1 fixes the working-plane height above the floor the occupants stand on, so the top
face is the only correct datum.
"""
import os

from hcl_radiance.geometry_obj import parse_obj
from hcl_radiance.geometry_import import _world_footprint, derive_sensor_outputs
from hcl_radiance.sensor_methodology import floor_top_z

OBJ = os.path.join(os.path.dirname(__file__), "fixtures", "office_room.obj")
MAP = {"Rad_Floor_R020": {"type": "floor", "refl": 0.2},
       "Rad_Wall_R050": {"type": "plastic", "refl": 0.5},
       "Rad_Ceiling_R080": {"type": "plastic", "refl": 0.8},
       "Rad_Glazing_T073": {"type": "glass", "tvis": 0.73}}

SLAB_THICKNESS = 0.2   # office_room.obj floor spans z -0.200 .. 0.000


def _p():
    with open(OBJ) as fh:
        return parse_obj(fh.read())


def test_world_footprint_z_is_the_floor_top_not_the_slab_underside():
    """The third element must be the walkable surface, not min(z) over the slab."""
    parsed = _p()
    _fmin, _fmax, fz = _world_footprint(parsed, MAP, 1.0, "Z")
    assert abs(fz - 0.0) < 1e-6, (
        f"floor datum is {fz}, expected 0.0 (slab top). "
        f"{-SLAB_THICKNESS} would be the slab underside.")


def test_world_footprint_agrees_with_floor_top_z():
    """The two helpers must not disagree about what 'the floor' means."""
    parsed = _p()
    _fmin, _fmax, fz = _world_footprint(parsed, MAP, 1.0, "Z")
    assert abs(fz - floor_top_z(parsed, MAP, 1.0, "Z")) < 1e-9


def test_derived_workplane_is_08_above_the_walkable_floor():
    out = derive_sensor_outputs(_p(), MAP, 1.0, up_axis="Z", workplane_h=0.8)
    zs = {round(p[2], 4) for p in out["grid_points"]}
    assert zs == {0.8}, f"working plane at {zs}, expected {{0.8}}"


def test_derived_eye_heights_are_above_the_walkable_floor():
    out = derive_sensor_outputs(_p(), MAP, 1.0, up_axis="Z", eye_heights=(1.2, 1.6))
    for want, s in zip((1.2, 1.6), out["observer_sets"]):
        zs = {round(p[2], 4) for p in s["points"]}
        assert zs == {want}, f"eye set {s['eye_h']} at {zs}, expected {{{want}}}"


def test_derived_grid_matches_workplane_grid_on_the_same_model():
    """The two sensor paths must place the working plane at the same height."""
    from hcl_radiance.sensor_methodology import detect_interior, en12464_grid
    parsed = _p()
    out = derive_sensor_outputs(parsed, MAP, 1.0, up_axis="Z", workplane_h=0.8)
    xmin, xmax, ymin, ymax, _src = detect_interior(parsed, MAP, 1.0, "Z")
    pts, _meth = en12464_grid((xmin, xmax, ymin, ymax),
                              floor_top_z(parsed, MAP, 1.0, "Z"), workplane_h=0.8)
    assert {round(p[2], 4) for p in out["grid_points"]} == {round(p[2], 4) for p in pts}


def test_fallback_branch_without_floor_faces_does_not_return_the_ceiling():
    """With no floor-typed group the helper falls back to all non-context faces, which span the
    whole room. Taking their max(z) would return the CEILING; the lowest point is the only
    sane floor estimate there."""
    no_floor = {"Rad_Floor_R020": {"type": "plastic", "refl": 0.2},
                "Rad_Wall_R050": {"type": "plastic", "refl": 0.5},
                "Rad_Ceiling_R080": {"type": "plastic", "refl": 0.8},
                "Rad_Glazing_T073": {"type": "glass", "tvis": 0.73}}
    _fmin, _fmax, fz = _world_footprint(_p(), no_floor, 1.0, "Z")
    assert fz < 1.0, f"floor datum {fz} looks like a ceiling, not a floor"


def test_footprint_xy_is_unaffected():
    """Only the z datum changes; the x/y footprint must stay the slab's full extent."""
    fmin, fmax, _fz = _world_footprint(_p(), MAP, 1.0, "Z")
    assert abs(fmin[0] + 2.15) < 0.01 and abs(fmax[0] - 2.15) < 0.01
    assert abs(fmin[1] + 3.65) < 0.01 and abs(fmax[1] - 3.65) < 0.01
