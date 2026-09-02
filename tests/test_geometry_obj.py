"""Tests for geometry_obj.py — rich OBJ/MTL parser (v2 foundation).

All tests run binary-free (no Radiance). Numeric expectations are computed from
the actual fixture geometry; see the comments for derivation.

Fixture: tests/fixtures/sample_room.obj
  Room: 4 m (x) × 3 m (z) × 2.7 m high (y), Y-up.
  Groups: oak_floor (floor), painted_gypsum (3 walls), clear_glass (glazing),
          lum1 (luminaire marker group only — no face, only a p-line).
  Vertex 9 (2.0, 2.69, 1.5) is under g lum1 / usemtl painted_gypsum.
"""

import math
import os
import pytest

from hcl_radiance.geometry_obj import (
    parse_obj,
    bbox,
    mesh_quality,
    _vert,
    face_normal,
    face_area,
    horizontal_floor_faces,
    marker_positions,
    parse_mtl,
    mtl_suggestions,
)

# ---------------------------------------------------------------------------
# Fixture loading helpers
# ---------------------------------------------------------------------------

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name: str) -> str:
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


@pytest.fixture(scope="module")
def obj_text():
    return _load("sample_room.obj")


@pytest.fixture(scope="module")
def mtl_text():
    return _load("sample_room.mtl")


@pytest.fixture(scope="module")
def parsed(obj_text):
    return parse_obj(obj_text)


@pytest.fixture(scope="module")
def mtl_map(mtl_text):
    return parse_mtl(mtl_text)


# ---------------------------------------------------------------------------
# parse_obj — groups and qualifiers
# ---------------------------------------------------------------------------

class TestParseObjGroups:
    def test_groups_sorted(self, parsed):
        assert parsed["groups"] == ["clear_glass", "oak_floor", "painted_gypsum"]

    def test_qualifier_all_material(self, parsed):
        for g in parsed["groups"]:
            assert parsed["qualifier"][g] == "Material", (
                f"Expected 'Material' for group {g!r}, got {parsed['qualifier'][g]!r}"
            )

    def test_lum1_not_in_groups(self, parsed):
        # lum1 has a usemtl but no face, so it must NOT appear as a face group.
        assert "lum1" not in parsed["groups"]


# ---------------------------------------------------------------------------
# parse_obj — face and point counts
# ---------------------------------------------------------------------------

class TestParseObjFaces:
    def test_n_faces(self, parsed):
        assert parsed["n_faces"] == 5

    def test_faces_length_matches_n_faces(self, parsed):
        assert len(parsed["faces"]) == parsed["n_faces"]

    def test_face_groups(self, parsed):
        face_groups = [f["group"] for f in parsed["faces"]]
        assert face_groups.count("oak_floor") == 1
        assert face_groups.count("painted_gypsum") == 3
        assert face_groups.count("clear_glass") == 1

    def test_n_missing_normals(self, parsed):
        # Only the floor face (1//1 2//1 3//1 4//1) references normals.
        # The remaining 4 faces have no normal references → n_missing_normals == 4.
        assert parsed["n_missing_normals"] == 4


# ---------------------------------------------------------------------------
# parse_obj — point markers
# ---------------------------------------------------------------------------

class TestParseObjPoints:
    def test_points(self, parsed):
        # p 9 under g lum1
        assert parsed["points"] == [9]

    def test_point_markers_vertex(self, parsed):
        assert len(parsed["point_markers"]) == 1
        assert parsed["point_markers"][0]["vertex"] == 9

    def test_point_markers_group_is_lum1(self, parsed):
        # The active *g* group (not usemtl) at the p-line is 'lum1'.
        assert parsed["point_markers"][0]["group"] == "lum1"


# ---------------------------------------------------------------------------
# parse_obj — vertices
# ---------------------------------------------------------------------------

class TestParseObjVertices:
    def test_vertex_count(self, parsed):
        # 8 room corners + 1 luminaire marker = 9 vertices
        assert len(parsed["vertices"]) == 9

    def test_vertex_9_luminaire_position(self, parsed):
        assert _vert(parsed, 9) == pytest.approx((2.0, 2.69, 1.5))


# ---------------------------------------------------------------------------
# bbox
# ---------------------------------------------------------------------------

class TestBbox:
    def test_bbox_values(self, parsed):
        lo, hi = bbox(parsed)
        assert lo == pytest.approx((0.0, 0.0, 0.0))
        # Vertex 9 at y=2.69 is below y=2.7; the eight corners reach 2.7.
        assert hi == pytest.approx((4.0, 2.7, 3.0))

    def test_bbox_empty(self):
        lo, hi = bbox({"vertices": []})
        assert lo == (0, 0, 0)
        assert hi == (0, 0, 0)


# ---------------------------------------------------------------------------
# mesh_quality
# ---------------------------------------------------------------------------

class TestMeshQuality:
    def test_degenerate_faces(self, parsed):
        mq = mesh_quality(parsed)
        assert mq["degenerate_faces"] == 0

    def test_missing_normals(self, parsed):
        mq = mesh_quality(parsed)
        assert mq["missing_normals"] == 4

    def test_non_manifold_edges_non_negative(self, parsed):
        mq = mesh_quality(parsed)
        assert mq["non_manifold_edges"] >= 0

    def test_worst_group_none_when_no_degenerates(self, parsed):
        mq = mesh_quality(parsed)
        assert mq["worst_group"] is None


# ---------------------------------------------------------------------------
# parse_mtl
# ---------------------------------------------------------------------------

class TestParseMtl:
    def test_painted_gypsum_kd(self, mtl_map):
        assert mtl_map["painted_gypsum"]["kd"] == pytest.approx([0.7, 0.7, 0.68])

    def test_painted_gypsum_map_kd(self, mtl_map):
        assert mtl_map["painted_gypsum"]["map_kd"] == "textures/gypsum.png"

    def test_clear_glass_map_kd_none(self, mtl_map):
        assert mtl_map["clear_glass"]["map_kd"] is None

    def test_clear_glass_kd(self, mtl_map):
        assert mtl_map["clear_glass"]["kd"] == pytest.approx([0.1, 0.1, 0.12])

    def test_oak_floor_kd(self, mtl_map):
        assert mtl_map["oak_floor"]["kd"] == pytest.approx([0.3, 0.2, 0.1])

    def test_keys_present(self, mtl_map):
        assert set(mtl_map.keys()) == {"painted_gypsum", "clear_glass", "oak_floor"}


# ---------------------------------------------------------------------------
# mtl_suggestions
# ---------------------------------------------------------------------------

class TestMtlSuggestions:
    def test_painted_gypsum_refl(self, mtl_map):
        # mean([0.7, 0.7, 0.68]) = 2.08 / 3 = 0.6933…
        s = mtl_suggestions(mtl_map, ["painted_gypsum", "oak_floor"])
        assert s["painted_gypsum"]["suggested_refl"] == pytest.approx(0.6933, abs=0.01)

    def test_oak_floor_refl(self, mtl_map):
        # mean([0.3, 0.2, 0.1]) = 0.2
        s = mtl_suggestions(mtl_map, ["painted_gypsum", "oak_floor"])
        assert s["oak_floor"]["suggested_refl"] == pytest.approx(0.2, abs=0.001)

    def test_oak_floor_map_kd_none(self, mtl_map):
        s = mtl_suggestions(mtl_map, ["painted_gypsum", "oak_floor"])
        assert s["oak_floor"]["map_kd"] is None

    def test_painted_gypsum_map_kd(self, mtl_map):
        s = mtl_suggestions(mtl_map, ["painted_gypsum", "oak_floor"])
        assert s["painted_gypsum"]["map_kd"] == "textures/gypsum.png"

    def test_missing_group_skipped(self, mtl_map):
        s = mtl_suggestions(mtl_map, ["painted_gypsum", "no_such_group"])
        assert "no_such_group" not in s

    def test_clear_glass_included_when_requested(self, mtl_map):
        s = mtl_suggestions(mtl_map, ["clear_glass"])
        assert "clear_glass" in s


# ---------------------------------------------------------------------------
# face_area and face_normal
# ---------------------------------------------------------------------------

class TestFaceGeometry:
    def _get_face(self, parsed, group):
        for f in parsed["faces"]:
            if f["group"] == group:
                return f
        return None

    def test_clear_glass_face_area(self, parsed):
        # clear_glass: verts 3,7,8,4
        # v3=(4,0,3), v7=(4,2.7,3), v8=(0,2.7,3), v4=(0,0,3)
        # This is the back wall: 4 m wide × 2.7 m high = 10.8 m²
        face = self._get_face(parsed, "clear_glass")
        assert face is not None
        assert face_area(parsed, face) == pytest.approx(10.8, abs=1e-9)

    def test_clear_glass_face_verts(self, parsed):
        face = self._get_face(parsed, "clear_glass")
        assert face["verts"] == [3, 7, 8, 4]

    def test_floor_face_normal_is_unit(self, parsed):
        face = self._get_face(parsed, "oak_floor")
        assert face is not None
        nx, ny, nz = face_normal(parsed, face)
        length = math.sqrt(nx * nx + ny * ny + nz * nz)
        assert length == pytest.approx(1.0, abs=1e-9)

    def test_floor_face_normal_direction(self, parsed):
        # Floor: verts 1,2,3,4 at y=0 → Newell's method gives (0, -1, 0)
        face = self._get_face(parsed, "oak_floor")
        nx, ny, nz = face_normal(parsed, face)
        # The floor faces downward by Newell convention with this winding.
        assert abs(abs(ny) - 1.0) < 1e-9
        assert abs(nx) < 1e-9
        assert abs(nz) < 1e-9


# ---------------------------------------------------------------------------
# horizontal_floor_faces
# ---------------------------------------------------------------------------

class TestHorizontalFloorFaces:
    def test_returns_floor_face(self, parsed):
        floors = horizontal_floor_faces(parsed, ["oak_floor"])
        assert len(floors) == 1
        assert floors[0]["group"] == "oak_floor"

    def test_empty_when_name_not_present(self, parsed):
        floors = horizontal_floor_faces(parsed, ["no_such_material"])
        assert floors == []

    def test_multiple_floor_names(self, parsed):
        # painted_gypsum has 3 faces; oak_floor has 1.
        floors = horizontal_floor_faces(parsed, ["oak_floor", "painted_gypsum"])
        assert len(floors) == 4


# ---------------------------------------------------------------------------
# marker_positions
# ---------------------------------------------------------------------------

class TestMarkerPositions:
    def test_all_markers(self, parsed):
        # Vertex 9 is the only point marker, at (2.0, 2.69, 1.5).
        positions = marker_positions(parsed)
        assert len(positions) == 1
        assert positions[0] == pytest.approx((2.0, 2.69, 1.5))

    def test_marker_positions_by_group_lum1(self, parsed):
        positions = marker_positions(parsed, group="lum1")
        assert len(positions) == 1
        assert positions[0] == pytest.approx((2.0, 2.69, 1.5))

    def test_marker_positions_no_such_group(self, parsed):
        # 'no_such' group has no markers AND no faces → empty list.
        positions = marker_positions(parsed, group="no_such")
        assert positions == []

    def test_marker_positions_group_none_returns_all(self, parsed):
        # group=None returns all markers.
        assert marker_positions(parsed, group=None) == marker_positions(parsed)


# ---------------------------------------------------------------------------
# _vert helper
# ---------------------------------------------------------------------------

class TestVertHelper:
    def test_vert_1_based(self, parsed):
        # Vertex 1 is (0,0,0)
        assert _vert(parsed, 1) == (0.0, 0.0, 0.0)

    def test_vert_6(self, parsed):
        # Vertex 6 is (4, 2.7, 0)
        assert _vert(parsed, 6) == pytest.approx((4.0, 2.7, 0.0))


# ---------------------------------------------------------------------------
# Regression: C1 — usemtl must NOT be reset on a g line
# ---------------------------------------------------------------------------

class TestUsemtlPersistsAcrossGLines:
    """Fixture: usemtl shell followed by g block1 / g block2 (two faces).

    Before the fix, parse_obj resets cur_usemtl on every g line, so block1
    and block2 become their own effective groups instead of inheriting 'shell'.
    After the fix, both faces must be in group 'shell'.
    """

    @pytest.fixture(scope="class")
    def text(self):
        return _load("usemtl_then_groups.obj")

    @pytest.fixture(scope="class")
    def result(self, text):
        return parse_obj(text)

    def test_groups_equals_shell_only(self, result):
        # Both faces inherit the active usemtl 'shell'; neither g name should
        # surface as an effective group.
        assert result["groups"] == ["shell"]

    def test_both_faces_in_shell(self, result):
        assert result["n_faces"] == 2
        for face in result["faces"]:
            assert face["group"] == "shell", (
                f"Expected group 'shell', got {face['group']!r}"
            )


# ---------------------------------------------------------------------------
# C3 — negative (relative) OBJ indices
# ---------------------------------------------------------------------------

class TestNegativeIndices:
    def test_face_negative_indices_resolve_relative(self):
        """OBJ permits negative (relative) indices: -1 is the last vertex defined so far.
        parse_obj must resolve them to positive 1-based indices."""
        obj = "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf -4 -3 -2 -1\n"
        p = parse_obj(obj)
        assert p["faces"][0]["verts"] == [1, 2, 3, 4]
        # downstream helpers must then read the correct vertices
        assert _vert(p, p["faces"][0]["verts"][0]) == (0.0, 0.0, 0.0)
        assert _vert(p, p["faces"][0]["verts"][3]) == (0.0, 1.0, 0.0)

    def test_point_negative_index_resolves_relative(self):
        obj = "v 0 0 0\nv 5 5 5\np -1\n"
        p = parse_obj(obj)
        assert p["points"] == [2]
        assert p["point_markers"][0]["vertex"] == 2

    def test_out_of_range_index_raises_clear_error(self):
        """A face referencing a vertex that does not exist must raise a clear ValueError, not an
        opaque IndexError later when the vertex is dereferenced."""
        with pytest.raises(ValueError):
            parse_obj("v 0 0 0\nv 1 0 0\nf 1 2 5\n")    # only 2 verts, ref 5

    def test_zero_index_raises_clear_error(self):
        with pytest.raises(ValueError):
            parse_obj("v 0 0 0\nf 1 0\n")               # 0 is not a valid OBJ index

    def test_out_of_range_negative_index_raises_clear_error(self):
        with pytest.raises(ValueError):
            parse_obj("v 0 0 0\nf -5\n")                # only 1 vert, relative -5


# ---------------------------------------------------------------------------
# B2 — marker_positions centroid fallback weights each vertex once
# ---------------------------------------------------------------------------

def test_marker_centroid_uses_unique_vertices():
    """B2: the centroid fallback must average each UNIQUE vertex once (matching object_centroid),
    not weight by how many faces reference it."""
    # Vertex 1 is referenced by all 3 faces; vertices 2..7 once each. A multiplicity-weighted
    # mean would over-weight vertex 1 (at the origin) and pull the centroid toward it.
    obj = ("v 0 0 0\nv 10 0 0\nv 10 2 0\nv 10 4 0\nv 10 6 0\nv 10 8 0\nv 10 10 0\n"
           "usemtl M\nf 1 2 3\nf 1 4 5\nf 1 6 7\n")
    p = parse_obj(obj)
    pos = marker_positions(p, group="M")
    assert len(pos) == 1
    # unique verts {1..7}: x = 60/7, y = 30/7  (NOT the multiplicity-weighted 60/9, 30/9)
    assert pos[0][0] == pytest.approx(60 / 7)
    assert pos[0][1] == pytest.approx(30 / 7)
