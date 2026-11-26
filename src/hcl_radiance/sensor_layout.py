"""Sensor layout utilities for geometry-derived analysis points.

Pure geometry, stdlib only (math used in eye_observer_points).
Produces work-plane grids, eye observers, and Radiance fisheye view strings.
"""


def _centred_axis(lo, hi, spacing):
    span = hi - lo
    # Not `span // spacing`: 6.6 // 0.6 is 10.0 in floating point although eleven fit, and a
    # whole row and column went missing whenever the span was an exact multiple.
    n = int(span / spacing + 1e-9)
    if n <= 0:
        return [(lo + hi) / 2.0]
    offset = (span - n * spacing) / 2.0
    return [lo + offset + (i + 0.5) * spacing for i in range(n)]


def work_plane_grid(footprint_min, footprint_max, *, workplane_h=0.8, spacing=0.5):
    """Up-facing rows [x,y,z,0,0,1] at workplane_h, centred & clipped to the footprint."""
    xs = _centred_axis(footprint_min[0], footprint_max[0], spacing)
    ys = _centred_axis(footprint_min[1], footprint_max[1], spacing)
    return [[round(x, 4), round(y, 4), workplane_h, 0, 0, 1] for y in ys for x in xs]


def eye_observer_points(footprint_min, footprint_max, *, eye_h=1.2, toward=(0.0, -1.0), spacing=2.0):
    """Vertical-gaze rows [x,y,z,dx,dy,0] at eye_h; horizontal dir = normalized `toward`."""
    import math
    mag = math.hypot(toward[0], toward[1]) or 1.0
    dx, dy = toward[0] / mag, toward[1] / mag
    xs = _centred_axis(footprint_min[0], footprint_max[0], spacing)
    ys = _centred_axis(footprint_min[1], footprint_max[1], spacing)
    return [[round(x, 4), round(y, 4), eye_h, round(dx, 6), round(dy, 6), 0] for y in ys for x in xs]


def dgp_views(observers):
    """One Radiance fisheye view per observer: -vp .. -vd .. -vta -vh 180 -vv 180."""
    return [
        f"-vp {o[0]} {o[1]} {o[2]} -vd {o[3]} {o[4]} {o[5]} -vta -vh 180 -vv 180"
        for o in observers
    ]
