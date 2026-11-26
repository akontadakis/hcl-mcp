"""EN 12464-1 working-plane grid + workstation observer methodology (pure stdlib).

All math runs in the PRE-north footprint frame; callers apply _rotate_north once at the end.
"""
import math
import re
from hcl_radiance.geometry_obj import face_area, face_normal, object_centroid
from hcl_radiance.geometry_import import (
    _to_world, _glass_groups, _context_groups, _floor_groups, _world_footprint,
)


def floor_top_z(parsed, material_map, scale, up_axis):
    """Max world-z of floor faces (the walkable surface). 0.0 if no floor faces."""
    fg = _floor_groups(material_map, None)
    zs = []
    for f in parsed["faces"]:
        if f["group"] in fg:
            for vi in f["verts"]:
                _, _, wz = _to_world(parsed["vertices"][vi - 1], up_axis, None, scale)
                zs.append(wz)
    return max(zs) if zs else 0.0


def _xy(parsed, vi, scale, up_axis):
    wx, wy, _ = _to_world(parsed["vertices"][vi - 1], up_axis, None, scale)
    return wx, wy


def _face_xy_centroid(parsed, face, scale, up_axis):
    pts = [_xy(parsed, vi, scale, up_axis) for vi in face["verts"]]
    n = len(pts)
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)


def _ceiling_z(parsed, material_map, scale, up_axis, floor_z):
    """Detect ceiling height as the z-centroid of the largest upward-facing horizontal face
    that is above the floor and not in a floor or glass group. Returns None if undetected."""
    fg = _floor_groups(material_map, None)
    glass = _glass_groups(material_map)
    best_area, best_z = 0.0, None
    for f in parsed["faces"]:
        if f["group"] in fg or f["group"] in glass:
            continue
        _, _, nz = _to_world(face_normal(parsed, f), up_axis, None, 1.0)
        if abs(nz) <= 0.8:                  # either winding: a ceiling wound to face the room
                                            # has its normal pointing DOWN, and surfaces are
                                            # two-sided here. Require fairly horizontal (<~37 deg tilt) for a ceiling;
                                            # accepts typical sloped ceilings, rejects steep wall-ish
                                            # faces. Normal alone can't separate a 45 deg ceiling from
                                            # a 45 deg wall — if undetected, room height degrades to None.
            continue
        pts = [_to_world(parsed["vertices"][vi - 1], up_axis, None, scale) for vi in f["verts"]]
        z_mid = sum(p[2] for p in pts) / len(pts)
        if z_mid <= floor_z:
            continue
        # 2D shoelace area in x-y plane
        n = len(pts)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
        area = abs(area) / 2.0
        if area > best_area:
            best_area, best_z = area, z_mid
    return best_z


#: A wall plane counts as a side of the room only if it carries at least this share of the
#: largest plane's area on that side. A window reveal is 1-3 % of its wall; a partition that
#: really bounds the room is far above a quarter.
_WALL_PLANE_SHARE = 0.25


def detect_interior(parsed, material_map, scale, up_axis, *, wall_thickness=None, override=None):
    """Interior (xmin,xmax,ymin,ymax,source).

    Inner-surface rule: identifies wall-scale groups (those containing at least one vertical
    face spanning ≥50% of the room height from floor to ceiling). Each vertical face of those
    groups is filed under the side it FACES (the dominant horizontal axis of its normal; east
    or west by which side of the room centre it lies on), faces are gathered into planes, and
    each side takes its innermost plane that carries a real share of the wall area, at that
    plane's room-facing (inner) edge. A side with no wall is mirrored about the room centre. This reliably
    excludes floor/ceiling slab edges, furniture, and frames while capturing the actual wall
    inner surfaces. Fallback: floor footprint inset by wall_thickness.
    """
    if override is not None:
        x0, x1, y0, y1 = override
        return (min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), "override")

    glass = _glass_groups(material_map)
    ctx = _context_groups(material_map)
    fg = _floor_groups(material_map, None)

    # Determine floor z and ceiling z to compute room height
    fz = floor_top_z(parsed, material_map, scale, up_axis)
    cz = _ceiling_z(parsed, material_map, scale, up_axis, fz)
    room_h = (cz - fz) if cz is not None else None

    # Identify wall-scale groups: groups with any vertical face spanning ≥50% of room height.
    # If room height unknown, use any group not in floor/glass/context.
    wall_groups: set = set()
    if room_h and room_h > 0:
        min_span = room_h * 0.5
        for f in parsed["faces"]:
            g = f["group"]
            if g in glass or g in ctx or g in fg:
                continue
            _, _, nz = _to_world(face_normal(parsed, f), up_axis, None, 1.0)
            if abs(nz) >= 0.5:        # horizontal face — skip
                continue
            pts = [_to_world(parsed["vertices"][vi - 1], up_axis, None, scale) for vi in f["verts"]]
            zs = [p[2] for p in pts]
            if (max(zs) - min(zs)) >= min_span:
                wall_groups.add(g)
    else:
        wall_groups = {f["group"] for f in parsed["faces"]
                       if f["group"] not in glass and f["group"] not in ctx and f["group"] not in fg}

    # room centre = xy centroid of floor vertices (model bbox centre if no floor)
    fpts = [_xy(parsed, vi, scale, up_axis)
            for f in parsed["faces"] if f["group"] in fg for vi in f["verts"]]
    if fpts:
        cx = sum(p[0] for p in fpts) / len(fpts)
        cy = sum(p[1] for p in fpts) / len(fpts)
    else:
        cx = cy = 0.0

    # File every vertical wall face under the side it FACES, then take the innermost wall
    # plane on each side.
    #
    # The side comes from the face's normal, not from where its centre lies. A wall cut into
    # pieces round a window has strips whose centres sit diagonally from the room's centre; by
    # the centre's bearing such a strip of the south wall is a "west wall", and it used to drag
    # the west edge of the interior in to the strip's end. The normal's SIGN is not used: a
    # surface is two-sided, so which side of the room centre the face lies on decides
    # east from west.
    #
    # A plane counts only if it carries a real share of the side's wall area. That keeps out
    # window reveals and door jambs, which face along a wall and sit well inside the room's
    # outline, yet are a few tenths of a square metre each.
    planes: dict = {"xmin": {}, "xmax": {}, "ymin": {}, "ymax": {}}
    for f in parsed["faces"]:
        if f["group"] not in wall_groups:
            continue
        nx, ny, nz = _to_world(face_normal(parsed, f), up_axis, None, 1.0)
        if abs(nz) >= 0.5:                      # not vertical
            continue
        axis = 0 if abs(nx) >= abs(ny) else 1
        coords = [_xy(parsed, vi, scale, up_axis)[axis] for vi in f["verts"]]
        offset = sum(coords) / len(coords) - (cx, cy)[axis]
        # The ROOM-FACING edge on that axis: the smaller coordinate on the east/north sides,
        # the larger on the west/south. For an upright wall min == max; for a leaning one this
        # keeps the interior inside the wall's inner surface.
        if offset > 0:
            side, inner = ("xmax", "ymax")[axis], min(coords)
        else:
            side, inner = ("xmin", "ymin")[axis], max(coords)
        key = round(inner, 3)
        planes[side][key] = planes[side].get(key, 0.0) + face_area(parsed, f)

    def innermost(side):
        found = planes[side]
        if not found:
            return None
        enough = _WALL_PLANE_SHARE * max(found.values())
        real = [coord for coord, area in found.items() if area >= enough]
        return min(real) if side in ("xmax", "ymax") else max(real)

    xmin_v, xmax_v = innermost("xmin"), innermost("xmax")
    ymin_v, ymax_v = innermost("ymin"), innermost("ymax")

    # Mirror a single missing side about the room centre (NOT the origin).
    if xmin_v is None and xmax_v is not None: xmin_v = 2 * cx - xmax_v
    if xmax_v is None and xmin_v is not None: xmax_v = 2 * cx - xmin_v
    if ymin_v is None and ymax_v is not None: ymin_v = 2 * cy - ymax_v
    if ymax_v is None and ymin_v is not None: ymax_v = 2 * cy - ymin_v
    if all(v is not None for v in (xmin_v, xmax_v, ymin_v, ymax_v)):
        return (xmin_v, xmax_v, ymin_v, ymax_v, "inner_surface")

    # fallback: floor footprint, optionally inset by wall_thickness
    (fmin, fmax, _ftz) = _world_footprint(parsed, material_map, scale, up_axis)
    t = wall_thickness or 0.0
    return (fmin[0] + t, fmax[0] - t, fmin[1] + t, fmax[1] - t,
            "fallback_floor_inset" if t else "fallback_floor")


def en12464_grid(interior, floor_top_z_val, *, workplane_h=0.8, border_offset=0.25,
                 max_spacing=None, footprint=None, footprint_border=0.0):
    """EN 12464-1 working-plane grid. Returns (points, methodology). Pre-north frame."""
    xmin, xmax, ymin, ymax = interior
    wx, wy = xmax - xmin, ymax - ymin
    if wx <= 0 or wy <= 0:
        raise ValueError(
            f"interior extent must have positive width and height; got width={wx}, height={wy} "
            f"(interior={tuple(round(float(v), 4) for v in interior)}). Check interior_extent / "
            "the detected room bounds.")
    cx0, cx1 = xmin + border_offset, xmax - border_offset
    cy0, cy1 = ymin + border_offset, ymax - border_offset
    Lx, Ly = cx1 - cx0, cy1 - cy0
    if Lx <= 0 or Ly <= 0:
        raise ValueError(
            f"calc area is non-positive after border_offset={border_offset} m "
            f"(Lx={round(Lx, 4)}, Ly={round(Ly, 4)}); the interior "
            f"({round(wx, 4)}x{round(wy, 4)} m) is too small for this border_offset.")
    # EN 12464-1 grades d on the CALCULATION AREA, not the interior extent. Taking it from
    # the larger interior yields a more permissive p_max than the standard sanctions --
    # under-sampling, in the non-conservative direction.
    d = max(Lx, Ly)
    if max_spacing is not None:
        p, p_source = float(max_spacing), "override"
    else:
        p, p_source = 0.2 * (5 ** math.log10(d)), "en_formula"

    nx = max(1, math.ceil(Lx / p))
    ny = max(1, math.ceil(Ly / p))
    sx, sy = Lx / nx, Ly / ny
    z = round(floor_top_z_val + workplane_h, 4)

    x_positions = [round(cx0 + (i + 0.5) * sx, 4) for i in range(nx)]
    y_positions = [round(cy0 + (j + 0.5) * sy, 4) for j in range(ny)]
    points = [[x, y, z, 0, 0, 1] for y in y_positions for x in x_positions]

    clipped_meta = None
    if footprint:
        from hcl_radiance.footprint import clip_points
        kept, dropped = clip_points(points, footprint, border=footprint_border)
        clipped_meta = {"kept": len(kept), "dropped": len(dropped),
                        "footprint_source": "floor_polygons",
                        "footprint_border": footprint_border}
        points = kept

    methodology = {
        "interior_extent": [round(v, 4) for v in (xmin, xmax, ymin, ymax)],
        "floor_top_z": round(floor_top_z_val, 4),
        "workplane_z": z,
        "d": round(d, 4),
        "d_source": "calculation_area",
        "p_max": round(p, 4),
        "p_source": p_source,
        "border_offset": border_offset,
        "calc_area": [round(Lx, 4), round(Ly, 4)],
        "n_cells": {"x": nx, "y": ny},
        "spacing": {"x": round(sx, 4), "y": round(sy, 4)},
        "x_positions": x_positions,
        "y_positions": y_positions,
        "count": len(points),
        **({"clipped": clipped_meta} if clipped_meta else {}),
    }
    return points, methodology


def _trailing_int(name):
    m = re.search(r"(\d+)\s*$", name or "")
    return m.group(1) if m else None


def detect_workstations(parsed, seat_pattern, screen_pattern):
    """Return (pairings, seats, screens). Pair seat<->screen by trailing integer suffix."""
    seat_re, screen_re = re.compile(seat_pattern), re.compile(screen_pattern)
    objs = sorted({f.get("object") for f in parsed["faces"] if f.get("object")})
    seats, screens = {}, {}
    for o in objs:
        if seat_re.search(o):
            seats[o] = _trailing_int(o)
        elif screen_re.search(o):
            screens[o] = _trailing_int(o)
    by_suffix = {}
    for s, k in screens.items():
        if k is not None:
            by_suffix.setdefault(k, []).append(s)
    pairings = []
    for seat, k in seats.items():
        match = by_suffix.get(k, [None])[0] if k is not None else None
        pairings.append({"seat": seat, "screen": match, "suffix": k})
    return pairings, seats, screens


def glazing_centroid(parsed, material_map, scale, up_axis):
    """XY centroid of all glass-group faces' vertices, or None if no glazing."""
    glass = _glass_groups(material_map)
    pts = [_xy(parsed, vi, scale, up_axis)
           for f in parsed["faces"] if f["group"] in glass for vi in f["verts"]]
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _normalize_xy(dx, dy):
    mag = math.hypot(dx, dy)
    if mag == 0:
        # Degenerate gaze (eye coincident with its target/glazing): direction is undefined.
        # Fall back to +Y — a valid unit vector matching the no-glazing window default — so a
        # zero-direction [0,0,0] (which rtrace treats as undefined) never reaches the .pts.
        return [0, 1, 0]
    return [round(dx / mag, 6), round(dy / mag, 6), 0]


def _fallback_dirs(eye_xy, *, direction_fallback, fallback_azimuth, sweep_n, glaze):
    """Return list of (direction, source) for one eye under the chosen fallback."""
    if direction_fallback == "sweep":
        out = []
        for k in range(sweep_n):
            th = 2 * math.pi * k / sweep_n
            out.append(([round(math.cos(th), 6), round(math.sin(th), 6), 0],
                        f"fallback:sweep[{k}]"))
        return out
    if direction_fallback == "azimuth" and fallback_azimuth is not None:
        th = math.radians(fallback_azimuth)        # compass: 0=N(+Y),90=E(+X); pre-north frame
        return [([round(math.sin(th), 6), round(math.cos(th), 6), 0], "fallback:azimuth")]
    # default: window
    if glaze is not None:
        return [(_normalize_xy(glaze[0] - eye_xy[0], glaze[1] - eye_xy[1]), "fallback:window")]
    return [([0, 1, 0], "fallback:window")]        # no glazing -> +Y default


def build_observers(parsed, material_map, scale, up_axis, *, eye_height=1.2,
                    seat_pattern=r"(?i)chair.*seat|seat",
                    screen_pattern=r"(?i)disp.*panel|screen|monitor|display",
                    direction_fallback="window", fallback_azimuth=None, sweep_n=8,
                    workstations=None, position_fallback="room_center", interior=None):
    """Build observer dicts (pre-north frame). See module/spec for the fallback ladder."""
    heights = list(eye_height) if isinstance(eye_height, (list, tuple)) else [eye_height]
    ftz = floor_top_z(parsed, material_map, scale, up_axis)
    glaze = glazing_centroid(parsed, material_map, scale, up_axis)
    out, idx = [], 0

    def _emit(eye_xy, direction, source, seat_obj, screen_obj):
        nonlocal idx
        for h in heights:
            out.append({"id": idx, "eye": [round(eye_xy[0], 4), round(eye_xy[1], 4),
                                           round(ftz + h, 4)],
                        "direction": direction, "source": source,
                        "seat_object": seat_obj, "screen_object": screen_obj, "eye_height": h})
            idx += 1

    if workstations:
        for ws in workstations:
            eye_xy = (ws["eye"][0], ws["eye"][1])
            tgt = ws.get("target")
            if tgt is not None:
                _emit(eye_xy, _normalize_xy(tgt[0] - eye_xy[0], tgt[1] - eye_xy[1]),
                      "explicit", None, None)
            else:
                for d, src in _fallback_dirs(eye_xy, direction_fallback="azimuth",
                                             fallback_azimuth=ws.get("azimuth"),
                                             sweep_n=sweep_n, glaze=glaze):
                    _emit(eye_xy, d, src, None, None)
        return out

    pairings, seats, screens = detect_workstations(parsed, seat_pattern, screen_pattern)

    if not pairings:                                   # no seats -> position fallback
        if position_fallback == "room_center":
            if interior is None:
                interior = detect_interior(parsed, material_map, scale, up_axis)[:4]
            eye_xy = ((interior[0] + interior[1]) / 2.0, (interior[2] + interior[3]) / 2.0)
        else:
            eye_xy = (position_fallback[0], position_fallback[1])
        for d, src in _fallback_dirs(eye_xy, direction_fallback=direction_fallback,
                                     fallback_azimuth=fallback_azimuth, sweep_n=sweep_n,
                                     glaze=glaze):
            _emit(eye_xy, d, src, None, None)
        return out

    for pr in pairings:
        eye_xy = object_centroid(parsed, pr["seat"], scale, up_axis)[:2]
        if pr["screen"]:
            tgt = object_centroid(parsed, pr["screen"], scale, up_axis)[:2]
            _emit(eye_xy, _normalize_xy(tgt[0] - eye_xy[0], tgt[1] - eye_xy[1]),
                  "workstation", pr["seat"], pr["screen"])
        else:
            for d, src in _fallback_dirs(eye_xy, direction_fallback=direction_fallback,
                                         fallback_azimuth=fallback_azimuth, sweep_n=sweep_n,
                                         glaze=glaze):
                _emit(eye_xy, d, src, pr["seat"], None)
    return out
