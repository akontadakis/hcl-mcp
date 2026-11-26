"""Geometry, grid and sensor defects found by the 2026-11-26 review, each pinned by the wrong
answer it gave. One section per finding (G1, G3-G9, G11-G13 of .scratch/review-2026-11-26)."""
import math
import os

import pytest

from hcl_radiance import footprint
from hcl_radiance.commands import ambient_convergence_note, pts_to_text
from hcl_radiance.geometry_health import check_coincident_surfaces
from hcl_radiance.geometry_import import (aperture_report, import_geometry, material_summary,
                                          mean_aperture_normal, obj_ungrouped_faces)
from hcl_radiance.geometry_obj import parse_obj
from hcl_radiance.grid import _select_non_sky
from hcl_radiance.sensor_daylight import glazing_wall
from hcl_radiance.sensor_layout import work_plane_grid
from hcl_radiance.sensor_methodology import _ceiling_z

# ---- G1: the two triangles of one rectangle are not coincident surfaces ----

_BOX_QUADS = """v 0 0 0
v 6 0 0
v 6 5 0
v 0 5 0
v 0 0 3
v 6 0 3
v 6 5 3
v 0 5 3
usemtl floor
f 1 2 3 4
usemtl ceiling
f 5 8 7 6
usemtl walls
f 1 5 6 2
f 2 6 7 3
f 3 7 8 4
f 4 8 5 1
"""


def _triangulated(obj_text):
    out = []
    for line in obj_text.splitlines():
        tok = line.split()
        if tok and tok[0] == "f" and len(tok) == 5:
            a, b, c, d = tok[1:]
            out += [f"f {a} {b} {c}", f"f {a} {c} {d}"]
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def test_a_triangulated_room_has_no_coincident_surfaces():
    """Blender, IFC and Revit all export triangles. Two triangles of a split rectangle share
    an edge and nothing else, but their bounding boxes are identical, and a box test called
    every such pair a z-fighting duplicate (six pairs in this room, health `ok: False`)."""
    assert check_coincident_surfaces(parse_obj(_BOX_QUADS)) == []
    assert check_coincident_surfaces(parse_obj(_triangulated(_BOX_QUADS))) == []


def test_a_real_duplicate_triangle_is_still_caught():
    duplicated = _triangulated(_BOX_QUADS) + "usemtl floor\nf 1 2 3\n"
    assert check_coincident_surfaces(parse_obj(duplicated)) != []


def test_two_triangles_that_really_overlap_are_still_caught():
    """Same plane, crossing each other: a genuine positive-area overlap."""
    crossing = _BOX_QUADS + "v 3 0 0\nv 6 5 0\nv 0 5 0\nusemtl rug\nf 9 10 11\nf 1 2 3\n"
    assert check_coincident_surfaces(parse_obj(crossing)) != []


# ---- G3 / G12: one glass group on two opposite walls ----

_ROOM_TWO_FACADES = """v 0 0 0
v 6 0 0
v 6 4 0
v 0 4 0
v 0 1 1
v 0 3 1
v 0 3 2
v 0 1 2
v 6 1 1
v 6 3 1
v 6 3 2
v 6 1 2
usemtl floor
f 1 2 3 4
usemtl glass
f 5 6 7 8
f 12 11 10 9
"""
_TWO_FACADE_MAP = {"floor": {"type": "floor", "refl": 0.2}, "glass": {"type": "glass", "tvis": 0.7}}


def test_a_glass_group_on_two_opposite_walls_still_gives_a_real_gaze_direction():
    """The inward direction was 'floor centroid minus the centroid of the group's vertices'.
    With the group on the east AND west walls those coincide: the direction came out (0, 0),
    every derived observer looked nowhere, and rtrace returned 0 for it without complaint."""
    wall = glazing_wall(parse_obj(_ROOM_TWO_FACADES), _TWO_FACADE_MAP, 1.0, "Z")
    assert math.hypot(*wall["inward"]) == pytest.approx(1.0)
    assert abs(wall["inward"][0]) == pytest.approx(1.0)            # along x: one of the two walls
    gaze = mean_aperture_normal(parse_obj(_ROOM_TWO_FACADES), _TWO_FACADE_MAP, "Z")
    assert math.hypot(*gaze) == pytest.approx(1.0)


def test_the_facade_point_lies_on_the_chosen_wall_not_in_the_middle_of_the_room():
    wall = glazing_wall(parse_obj(_ROOM_TWO_FACADES), _TWO_FACADE_MAP, 1.0, "Z")
    assert wall["point"][0] in (pytest.approx(0.0), pytest.approx(6.0))
    # and "inward" points from that wall into the room
    assert (3.0 - wall["point"][0]) * wall["inward"][0] > 0


def test_an_aperture_group_whose_panes_face_apart_reports_no_single_orientation():
    """An area-weighted mean of opposite normals is zero; normalising it produced azimuth 0,
    tilt 90 -- "a north-facing window" -- for glazing that faces east and west."""
    (report,) = aperture_report(parse_obj(_ROOM_TWO_FACADES), _TWO_FACADE_MAP, 1.0, up_axis="Z")
    assert report["orientation_ambiguous"] is True
    assert report["azimuth_deg"] is None and report["tilt_deg"] is None
    assert report["area_m2"] == pytest.approx(4.0)


def test_an_ordinary_window_keeps_its_orientation():
    one_wall = _ROOM_TWO_FACADES.replace("f 12 11 10 9\n", "")
    (report,) = aperture_report(parse_obj(one_wall), _TWO_FACADE_MAP, 1.0, up_axis="Z")
    assert report["orientation_ambiguous"] is False
    assert report["azimuth_deg"] is not None


# ---- G4: sensor rows are six numbers, or the call is refused ----

@pytest.mark.parametrize("rows", [
    [[1, 2, 0.8]],                                   # a position with no direction
    [[1, 2, 0.8, 0, 0, 1], [1, 2, 0.8, 0, 0]],       # one short row among good ones
    [[1, 2, 0.8, 0, 0, 1, 9]],                       # one value too many
    [[1, 2, "a", 0, 0, 1]],
])
def test_a_sensor_row_that_is_not_six_numbers_is_refused(rows):
    """rtrace reads its input as a free stream of numbers. Four 3-column rows are two rays to
    it: half the points, at the wrong places, with no error."""
    with pytest.raises(ValueError, match="x y z dx dy dz"):
        pts_to_text(rows)


def test_good_sensor_rows_are_written_one_per_line():
    assert pts_to_text([[1, 2, 0.8, 0, 0, 1], [3.5, 2, 0.8, 0, 0, 1]]) == \
        "1 2 0.8 0 0 1\n3.5 2 0.8 0 0 1\n"


# ---- G5: faces before the first group ----

_UNGROUPED = "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nv 0 0 1\nv 1 0 1\nv 1 1 1\nf 1 2 3 4\ng roof\nf 5 6 7\n"


def test_faces_before_the_first_group_are_counted():
    """In a group-only OBJ these belong to no group; obj2rad drops them and the room is
    silently missing a surface."""
    assert obj_ungrouped_faces(_UNGROUPED) == 1
    assert obj_ungrouped_faces("g a\nf 1 2 3\ng b\nf 1 2 3\n") == 0
    assert obj_ungrouped_faces("usemtl m\nf 1 2 3\n") == 0        # usemtl mode: other rule applies


def test_importing_such_a_file_is_refused_with_the_count(tmp_path):
    obj = tmp_path / "ungrouped.obj"
    obj.write_text(_UNGROUPED)
    with pytest.raises(ValueError, match="1 face"):
        import_geometry(str(obj), material_map={"roof": {"type": "plastic", "refl": 0.5}},
                        units="m", up_axis="Z", work_dir=str(tmp_path), run=False)


def test_a_summary_skips_a_group_the_map_does_not_know():
    parsed = {"groups": ["known", "white"], "faces": [], "vertices": []}
    rows = material_summary(parsed, {"known": {"type": "plastic", "refl": 0.5}}, [])
    assert [row["group"] for row in rows] == ["known"]


# ---- G6: run=False runs nothing, and says why ----

def test_asking_for_an_annotated_dry_run_executes_nothing(tmp_path):
    from test_lm83_tool import _MAP, _OBJ
    obj = tmp_path / "room.obj"
    obj.write_text(_OBJ)
    out = import_geometry(str(obj), material_map=_MAP, units="m", up_axis="Z",
                          work_dir=str(tmp_path), run=False, annotate=True)
    assert out["annotate_commands"]
    assert not os.path.exists(tmp_path / "annot.oct"), "oconv ran although run=False"


def test_a_dry_run_is_not_blamed_on_a_missing_radiance(monkeypatch):
    """`run=False` with Radiance installed used to answer "Radiance not available; set
    HCL_RADIANCE_BIN" -- sending the user to fix an install that was fine."""
    from hcl_radiance import runner
    monkeypatch.setattr(runner, "_radiance_present", lambda: True)
    out = runner.run_sequence([{"cmd": ["oconv", "a.rad"], "stdout": "a.oct"}], "/tmp/x", False)
    assert out["ran"] is False and "run=False" in out["reason"]
    monkeypatch.setattr(runner, "_radiance_present", lambda: False)
    out = runner.run_sequence([{"cmd": ["oconv", "a.rad"], "stdout": "a.oct"}], "/tmp/x", False)
    assert "not available" in out["reason"]


# ---- G7: a border is measured to the room's edge, not to a seam inside the floor ----

def test_points_next_to_an_internal_seam_are_kept():
    """A floor exported as two triangles has a diagonal seam. Measuring the border to every
    ring's edges dropped valid points all along it."""
    whole = [[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]]
    split = [[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0)], [(0.0, 0.0), (4.0, 4.0), (0.0, 4.0)]]
    points = [[1.0, 1.1, 0.8], [2.0, 2.1, 0.8], [3.0, 3.1, 0.8], [1.0, 3.0, 0.8], [0.1, 2.0, 0.8]]
    kept_whole, _ = footprint.clip_points(points, whole, border=0.3)
    kept_split, _ = footprint.clip_points(points, split, border=0.3)
    assert kept_split == kept_whole
    assert [0.1, 2.0, 0.8] not in kept_split               # still inside the real border


# ---- G8: naming the sky file must exclude it, however its path is written ----

def test_a_sky_named_by_a_relative_path_is_still_excluded():
    """sky_files was matched as an exact string. `sky.rad` against `/w/sky.rad` matched
    nothing, the sky stayed in the electric-only octree, and daylight was reported as
    electric light (the ADR-0007 failure)."""
    files = ["/w/room.rad", "/w/sky.rad"]
    assert _select_non_sky(files, ["sky.rad"]) == ["/w/room.rad"]
    assert _select_non_sky(files, ["/w/./sky.rad"]) == ["/w/room.rad"]
    assert _select_non_sky(files, ["/w/sky.rad"]) == ["/w/room.rad"]


def test_a_sky_file_that_names_nothing_in_the_scene_is_an_error():
    with pytest.raises(ValueError, match="clear_sky.rad"):
        _select_non_sky(["/w/room.rad", "/w/sky.rad"], ["clear_sky.rad"])


def test_a_partial_file_name_does_not_match():
    with pytest.raises(ValueError, match="ky.rad"):
        _select_non_sky(["/w/room.rad", "/w/sky.rad"], ["ky.rad"])


# ---- G9: a ceiling is a ceiling whichever way it is wound ----

@pytest.mark.parametrize("ceiling_face", ["f 5 8 7 6", "f 5 6 7 8"], ids=["outward", "inward"])
def test_the_ceiling_is_found_whichever_way_it_is_wound(ceiling_face):
    obj = _BOX_QUADS.replace("f 5 8 7 6", ceiling_face)
    material_map = {"floor": {"type": "floor", "refl": 0.2}, "ceiling": {"type": "plastic", "refl": 0.8},
                    "walls": {"type": "plastic", "refl": 0.5}}
    assert _ceiling_z(parse_obj(obj), material_map, 1.0, "Z", 0.0) == pytest.approx(3.0)


# ---- G11: a span that is an exact multiple of the spacing ----

@pytest.mark.parametrize("span, spacing, count", [(6.6, 0.6, 11), (1.0, 0.1, 10), (10.2, 0.6, 17),
                                                  (3.0, 0.5, 6), (2.9, 0.5, 5)])
def test_the_grid_has_as_many_columns_as_fit(span, spacing, count):
    """6.6 // 0.6 is 10.0 in floating point, not 11: a row and a column went missing."""
    rows = work_plane_grid((0.0, 0.0), (span, spacing), spacing=spacing)
    assert len(rows) == count


# ---- G13: no ambient flags at all is the direct-only case, and it is the one to warn about ----

@pytest.mark.parametrize("params", ["", "-I+", None, "-dj 0.5"])
def test_parameters_with_no_ambient_flag_get_the_direct_only_warning(params):
    note = ambient_convergence_note(params)
    assert note and "NO interreflected light" in note


def test_a_deliberately_direct_only_pass_is_still_quiet():
    assert ambient_convergence_note("", direct_only_ok=True) is None
    assert ambient_convergence_note("-ab 0", direct_only_ok=True) is None


# ---- G2: a piece of wall belongs to the wall it lies in, wherever its centre happens to be ----

def _room_obj(length, depth, south_strips=None, east_split=None):
    """A box of `length` x `depth` x 3 m. Optionally the south wall cut into four pieces round
    an opening (x from..to), or the east wall split in two at a given y."""
    L, D = length, depth
    v = [(0, 0, 0), (L, 0, 0), (L, D, 0), (0, D, 0), (0, 0, 3), (L, 0, 3), (L, D, 3), (0, D, 3)]
    faces = {"floor": [[1, 2, 3, 4]], "ceiling": [[5, 8, 7, 6]], "walls": [[3, 7, 8, 4], [4, 8, 5, 1]]}

    def add(*points):
        ids = []
        for p in points:
            v.append(p)
            ids.append(len(v))
        return ids

    if south_strips:
        a, b = south_strips
        faces["walls"] += [add((0, 0, 0), (L, 0, 0), (L, 0, 0.8), (0, 0, 0.8)),
                           add((0, 0, 2.3), (L, 0, 2.3), (L, 0, 3), (0, 0, 3)),
                           add((0, 0, 0.8), (a, 0, 0.8), (a, 0, 2.3), (0, 0, 2.3)),
                           add((b, 0, 0.8), (L, 0, 0.8), (L, 0, 2.3), (b, 0, 2.3))]
    else:
        faces["walls"].append([1, 5, 6, 2])
    if east_split:
        faces["walls"] += [add((L, 0, 0), (L, east_split, 0), (L, east_split, 3), (L, 0, 3)),
                           add((L, east_split, 0), (L, D, 0), (L, D, 3), (L, east_split, 3))]
    else:
        faces["walls"].append([2, 6, 7, 3])
    lines = [f"v {x} {y} {z}" for x, y, z in v]
    for group, quads in faces.items():
        lines.append(f"usemtl {group}")
        lines += ["f " + " ".join(str(i) for i in quad) for quad in quads]
    return "\n".join(lines) + "\n"


_ROOM_MAP = {"floor": {"type": "floor", "refl": 0.2}, "ceiling": {"type": "plastic", "refl": 0.8},
             "walls": {"type": "plastic", "refl": 0.5}}


@pytest.mark.parametrize("obj, expected", [
    (_room_obj(6, 4), (0, 6, 0, 4)),
    (_room_obj(6, 4, south_strips=(2, 4)), (0, 6, 0, 4)),     # was (2, 4, 0, 4)
    (_room_obj(6, 20, east_split=8), (0, 6, 0, 20)),          # was (0, 6, 8, 8): zero depth
], ids=["plain", "south_wall_cut_round_a_window", "east_wall_in_two_pieces"])
def test_the_interior_reaches_every_wall_however_the_walls_are_cut_up(obj, expected):
    """A wall piece used to be filed under the side its CENTRE lay towards. The strip beside a
    window sits diagonally from the room's centre, was taken for a west wall, and pulled the
    west edge of the interior in to the strip's end."""
    from hcl_radiance.sensor_methodology import detect_interior
    found = detect_interior(parse_obj(obj), _ROOM_MAP, 1.0, "Z")
    assert tuple(round(c, 6) for c in found[:4]) == expected


def test_a_window_reveal_is_not_taken_for_a_wall():
    """The sides of a window opening face along the wall and sit inside the room's outline.
    They are a sliver of wall area, and the interior must not stop at them."""
    from hcl_radiance.sensor_methodology import detect_interior
    reveals = ("v 2 -0.2 0.8\nv 2 0 0.8\nv 2 0 2.3\nv 2 -0.2 2.3\n"
               "v 4 -0.2 0.8\nv 4 0 0.8\nv 4 0 2.3\nv 4 -0.2 2.3\n"
               "usemtl walls\nf -8 -7 -6 -5\nf -4 -3 -2 -1\n")
    found = detect_interior(parse_obj(_room_obj(6, 4, south_strips=(2, 4)) + reveals),
                            _ROOM_MAP, 1.0, "Z")
    assert tuple(round(c, 6) for c in found[:4]) == (0, 6, 0, 4)


# ---- G15: a model with nothing in it is not a healthy model ----

@pytest.mark.parametrize("obj", ["", "# exported 2026\n", "v 0 0 0\nv 1 0 0\nv 1 1 0\n"],
                         ids=["empty_file", "comment_only", "vertices_no_faces"])
def test_a_model_with_no_faces_fails_the_health_check(obj):
    """An export that wrote no faces passed as healthy: every check loops over the faces, so
    with none there was nothing to object to."""
    from hcl_radiance.geometry_health import check_geometry_health
    report = check_geometry_health(parse_obj(obj), {})
    assert report["ok"] is False
    codes = {f["code"]: f["severity"] for f in report["findings"]}
    assert codes.get("NO_FACES") == "error"


# ---- second review, 2026-11-26: finding the footprint's boundary must not take minutes ----

def _triangulated_square(n):
    rings = []
    for i in range(n):
        for j in range(n):
            a, b, c, d = (i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)
            rings += [[a, b, c], [a, c, d]]
    return [[(float(x), float(y)) for x, y in ring] for ring in rings]


def test_the_boundary_of_a_finely_triangulated_floor_is_found_quickly():
    """Probing both sides of every edge against every ring was quadratic: 1800 triangles took
    20 s, a 5000-triangle export minutes. A seam shared by two rings needs no probe at all."""
    import time
    rings = _triangulated_square(40)                       # 3200 triangles
    start = time.perf_counter()
    edges = footprint.boundary_edges(rings)
    assert time.perf_counter() - start < 3.0
    assert len(edges) == 160                               # 40 unit edges on each of 4 sides
    for (ax, ay), (bx, by) in edges:
        assert (ax == bx and ax in (0.0, 40.0)) or (ay == by and ay in (0.0, 40.0))


def test_a_seam_where_one_long_edge_meets_two_short_ones_is_still_a_seam():
    """A T-junction: the tiles share the line y = 1 but not an edge, so counting shared edges
    cannot see it. Only the outline of the 2 x 2 square is boundary."""
    rings = [[(0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0)],
             [(0.0, 1.0), (1.0, 1.0), (1.0, 2.0), (0.0, 2.0)],
             [(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0)]]
    edges = footprint.boundary_edges(rings)
    for (ax, ay), (bx, by) in edges:
        assert not (ay == by == 1.0), "the seam at y = 1 was taken for a boundary"
        assert not (ax == bx == 1.0), "the seam at x = 1 was taken for a boundary"
    assert footprint.min_edge_distance(1.0, 1.0, rings, edges) == pytest.approx(1.0)


def test_a_slab_given_as_top_and_bottom_faces_keeps_its_outline_whatever_their_winding():
    top = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]
    edges = footprint.boundary_edges([top, list(reversed(top))])
    assert len(edges) == 4
    assert footprint.min_edge_distance(2.0, 1.5, [top, list(reversed(top))], edges) == pytest.approx(1.5)
