import math
from hcl_radiance.footprint import (
    point_in_polygon, point_in_footprint, min_edge_distance, clip_points, floor_polygons,
)

RECT = [(0.0, 0.0), (4.0, 0.0), (4.0, 6.0), (0.0, 6.0)]
# L-shape: full 6x6 minus the top-right 3x3 corner
L = [(0.0, 0.0), (6.0, 0.0), (6.0, 3.0), (3.0, 3.0), (3.0, 6.0), (0.0, 6.0)]


def test_point_in_polygon_inside_and_outside():
    assert point_in_polygon(2.0, 3.0, RECT) is True
    assert point_in_polygon(5.0, 3.0, RECT) is False


def test_point_in_footprint_L_notch_excluded():
    assert point_in_footprint(1.0, 1.0, [L]) is True     # in the stem
    assert point_in_footprint(4.5, 4.5, [L]) is False    # in the removed corner


def test_min_edge_distance_center_of_rect():
    # nearest wall of the 4x6 rect from (2,3) is 2.0 (the x=0/x=4 walls)
    assert abs(min_edge_distance(2.0, 3.0, [RECT]) - 2.0) < 1e-9


def test_clip_points_drops_notch_and_far_points():
    pts = [[1.0, 1.0, 0.8, 0, 0, 1], [4.5, 4.5, 0.8, 0, 0, 1]]
    kept, dropped = clip_points(pts, [L], border=0.0)
    assert kept == [[1.0, 1.0, 0.8, 0, 0, 1]]
    assert dropped == [[4.5, 4.5, 0.8, 0, 0, 1]]


def test_clip_points_no_polygons_is_passthrough():
    pts = [[1.0, 1.0, 0.8, 0, 0, 1]]
    kept, dropped = clip_points(pts, [], border=0.5)
    assert kept == pts and dropped == []


def test_point_in_polygon_boundary_all_edges_inclusive():
    """Test that boundary points on all edge orientations (horizontal, vertical, diagonal) return True."""
    # Rectangle: horizontal top/bottom edges, vertical left/right edges
    assert point_in_polygon(2.0, 6.0, RECT) is True   # top horizontal edge (previously False)
    assert point_in_polygon(2.0, 0.0, RECT) is True   # bottom horizontal edge
    assert point_in_polygon(0.0, 3.0, RECT) is True    # left vertical edge
    assert point_in_polygon(4.0, 3.0, RECT) is True    # right vertical edge
    assert point_in_polygon(4.0, 6.0, RECT) is True    # corner vertex
    # Triangle: diagonal hypotenuse
    TRI = [(0.0, 0.0), (4.0, 0.0), (0.0, 4.0)]
    assert point_in_polygon(2.0, 2.0, TRI) is True     # on the hypotenuse


def test_floor_polygons_from_parsed():
    # one horizontal floor face (a triangle) in a minimal parsed dict, up_axis Z
    parsed = {
        "vertices": [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 2.0, 0.0)],
        "faces": [{"group": "Floor", "object": None, "verts": [1, 2, 3]}],
    }
    polys = floor_polygons(parsed, {"Floor": {"type": "floor"}}, 1.0, "Z")
    assert len(polys) == 1
    assert polys[0] == [(0.0, 0.0), (2.0, 0.0), (0.0, 2.0)]
