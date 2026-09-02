import os
from hcl_radiance.geometry_obj import parse_obj
from hcl_radiance.scene_preview import (
    build_scene, render_plan, render_3d, object_xy_bbox, _box_aspect,
)

FIXDIR = os.path.join(os.path.dirname(__file__), "fixtures")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MM = {"Rad_Floor_R020": {"type": "floor"}, "Rad_Glazing_T073": {"type": "glass"}}
LUMS = ["Luminaire_L09_1", "Luminaire_L09_2", "Luminaire_L09_3", "Luminaire_L09_4"]


def _office():
    with open(os.path.join(FIXDIR, "office_room.obj")) as fh:
        return parse_obj(fh.read())


def _is_png(path):
    assert os.path.getsize(path) > 0
    with open(path, "rb") as fh:
        assert fh.read(8) == PNG_MAGIC


def test_plan_png_is_written(tmp_path):
    scene = build_scene(_office(), MM, 1.0, "Z", None, luminaire_groups=LUMS)
    grid = [[x, y, 0.8, 0, 0, 1] for x in (-1.4, 0.0, 1.4) for y in (-2.0, 0.0, 2.0)]
    out = str(tmp_path / "plan.png")
    render_plan(scene, {"grid": grid}, out)
    _is_png(out)


def test_3d_png_is_written_with_luminaires(tmp_path):
    scene = build_scene(_office(), MM, 1.0, "Z", None, luminaire_groups=LUMS)
    out = str(tmp_path / "iso.png")
    render_3d(scene, {"observers": [[1.75, -1.2, 1.2, -1, 0, 0]]}, out)
    _is_png(out)


def test_window_carries_z_extent():
    scene = build_scene(_office(), MM, 1.0, "Z", None)
    assert scene["windows"], "expected a glazing face"
    assert len(scene["windows"][0]) == 6                # (x0,y0,x1,y1,z0,z1)
    x0, y0, x1, y1, z0, z1 = scene["windows"][0]
    assert z1 > z0                                      # non-degenerate height


def test_object_xy_bbox_luminaire():
    bb = object_xy_bbox(_office(), "Luminaire_L09_1", 1.0, "Z")
    assert bb is not None
    (x0, y0), (x1, y1) = bb
    assert x1 > x0 and y1 > y0


def test_L_room_footprint_is_hexagon():
    with open(os.path.join(FIXDIR, "l_room.obj")) as fh:
        parsed = parse_obj(fh.read())
    mm = {"Floor": {"type": "floor"}, "Window": {"type": "glass"}}
    scene = build_scene(parsed, mm, 1.0, "Z", None)
    assert len(scene["footprint"][0]) == 6


def _l_room_scene():
    with open(os.path.join(FIXDIR, "l_room.obj")) as fh:
        parsed = parse_obj(fh.read())
    return build_scene(parsed, {"Floor": {"type": "floor"}, "Window": {"type": "glass"}},
                       1.0, "Z", None)


def test_box_aspect_derives_from_scene_not_hardcoded():
    # Aspect must track the room's real footprint + height, not a fixed office proportion.
    s = build_scene(_office(), MM, 1.0, "Z", None)
    dx, dy, dz = _box_aspect(s)
    assert abs(dx - 4.0) < 0.3 and abs(dy - 7.0) < 0.3            # office footprint ~4 x 7
    assert abs(dz - (s["z_ceiling"] - s["z_floor"])) < 1e-9      # height derived, not fixed 3.4
    # a taller ceiling changes only the z proportion
    taller = dict(s, z_ceiling=s["z_floor"] + 10.0)
    assert _box_aspect(taller)[2] > dz
    # a differently-shaped room yields a different aspect than the office
    assert _box_aspect(_l_room_scene()) != (dx, dy, dz)


def test_box_aspect_handles_empty_footprint():
    dx, dy, dz = _box_aspect({"footprint": [], "z_floor": 0.0, "z_ceiling": 0.0})
    assert dx > 0 and dy > 0 and dz > 0                          # never zero -> no matplotlib error


def test_3d_png_renders_nonrectangular_room(tmp_path):
    out = str(tmp_path / "lroom_3d.png")
    render_3d(_l_room_scene(), {}, out)                          # general shape, no layers
    _is_png(out)
