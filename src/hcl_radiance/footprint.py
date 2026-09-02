"""Room footprint polygons + point clipping (pure stdlib).

Works in the PRE-north footprint frame by default; callers apply _rotate_north at the
end. The footprint is the FLOOR SLAB (floor-group horizontal faces), which lies
wall-thickness OUTSIDE the interior wall surface — reliable for "is this point over the
floor?" (shape clipping), NOT for "is it >= border from the room wall?".
"""
import math

from hcl_radiance.geometry_obj import face_normal
from hcl_radiance.geometry_import import _to_world, _floor_groups


def floor_polygons(parsed, material_map, scale, up_axis, north_angle_deg=None):
    """XY rings (one per horizontal floor-group face) in the post-remap frame.

    Pass north_angle_deg to project into the post-north final frame (used by the SVG
    renderer); omit it (default) for the pre-north frame used by grid clipping.
    """
    fg = _floor_groups(material_map, None)
    polys = []
    for f in parsed["faces"]:
        if f["group"] not in fg:
            continue
        _, _, nz = _to_world(face_normal(parsed, f), up_axis, None, 1.0)
        if abs(nz) < 0.5:                      # skip vertical floor-tagged trims
            continue
        ring = []
        for vi in f["verts"]:
            wx, wy, _ = _to_world(parsed["vertices"][vi - 1], up_axis, north_angle_deg, scale)
            ring.append((wx, wy))
        if len(ring) >= 3:
            polys.append(ring)
    return polys


def point_in_polygon(x, y, ring):
    """Ray-cast PIP for a single ring; a point on the boundary counts as inside.

    Tests all edges (horizontal, vertical, diagonal) for exact boundary membership
    using collinearity + segment-bounds checks, then falls back to ray-cast interior test.
    """
    n = len(ring)

    # Explicit boundary test: iterate all edges and check if (x,y) lies on any edge.
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]

        # Collinearity test: cross-product == 0 means point is on the line containing the edge.
        # We use (x-x1)*(y2-y1) - (y-y1)*(x2-x1) == 0 for exact arithmetic.
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if cross == 0:
            # Point is collinear with the edge. Check if it falls within the segment bounds.
            # Use both x and y bounds in case the segment is vertical, horizontal, or diagonal.
            if (min(x1, x2) <= x <= max(x1, x2) and
                min(y1, y2) <= y <= max(y1, y2)):
                return True

    # Ray-cast for interior points.
    inside = False
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xint = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xint:
                inside = not inside

    return inside


def point_in_footprint(x, y, polygons):
    return any(point_in_polygon(x, y, ring) for ring in polygons)


def _point_seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def min_edge_distance(x, y, polygons):
    best = math.inf
    for ring in polygons:
        n = len(ring)
        for i in range(n):
            ax, ay = ring[i]
            bx, by = ring[(i + 1) % n]
            d = _point_seg_dist(x, y, ax, ay, bx, by)
            if d < best:
                best = d
    return best


def clip_points(points, polygons, border=0.0):
    """Return (kept, dropped). Keep a row iff it is over the footprint AND >= border from
    any boundary edge. Empty polygons -> pass-through (kept=all, dropped=[])."""
    if not polygons:
        return list(points), []
    kept, dropped = [], []
    for p in points:
        x, y = p[0], p[1]
        if point_in_footprint(x, y, polygons) and min_edge_distance(x, y, polygons) >= border:
            kept.append(p)
        else:
            dropped.append(p)
    return kept, dropped
