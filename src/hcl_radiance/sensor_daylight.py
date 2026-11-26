"""Daylight-dimming photosensor placement (methodology.md §3). Pure stdlib, pre-north frame."""
import math

from hcl_radiance.geometry_obj import face_area, face_normal
from hcl_radiance.geometry_import import _to_world, _glass_groups, _floor_groups, _context_groups
from hcl_radiance.sensor_methodology import floor_top_z, _ceiling_z, detect_interior
from hcl_radiance.footprint import floor_polygons, point_in_footprint


def _floor_centroid_xy(parsed, material_map, scale, up_axis):
    """Interior-reference (x, y) used to derive "inward" from the glazing plane.

    Prefers the centroid of vertices belonging to a group typed `type:"floor"`. When no
    group resolves to floor (a plausible, unflagged-elsewhere OBJ shape — see
    NO_FLOOR_GROUP in geometry_health.py), falls back to the centroid of every vertex on
    NON-CONTEXT geometry (the same interior-reference notion the health module uses),
    rather than the world origin: the world origin is only correct by coincidence, and for
    a room not centred on it, "inward" silently points outdoors instead of into the room.
    Only returns (0.0, 0.0) when the model has no vertices at all.
    """
    fg = _floor_groups(material_map, None)
    pts = []
    for f in parsed["faces"]:
        if f["group"] in fg:
            for vi in f["verts"]:
                wx, wy, _ = _to_world(parsed["vertices"][vi - 1], up_axis, None, scale)
                pts.append((wx, wy))
    if not pts:
        ctx = _context_groups(material_map)
        for f in parsed["faces"]:
            if f["group"] in ctx:
                continue
            for vi in f["verts"]:
                wx, wy, _ = _to_world(parsed["vertices"][vi - 1], up_axis, None, scale)
                pts.append((wx, wy))
    if not pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def glazing_wall(parsed, material_map, scale, up_axis):
    """Dominant glazed facade (largest total glass area). Inward direction is derived from
    the room centroid (NOT the face normal — winding is unreliable in this codebase)."""
    glass = _glass_groups(material_map)
    faces = [f for f in parsed["faces"] if f["group"] in glass]
    if not faces:
        raise ValueError("photosensors needs a glazing group (material type 'glass') to locate "
                         "the daylit facade")
    area_by_g = {}
    for f in faces:
        area_by_g[f["group"]] = area_by_g.get(f["group"], 0.0) + face_area(parsed, f)
    dom = max(area_by_g, key=area_by_g.get)
    fcx, fcy = _floor_centroid_xy(parsed, material_map, scale, up_axis)
    # One material often glazes several walls. The facade is ONE of them: taking the centroid
    # of every pane of the group puts it in the middle of the room when the panes are on
    # opposite walls, the "inward" direction comes out (0, 0), and every sensor or observer
    # built from it sits on one spot looking nowhere (rtrace answers 0 without complaint).
    # So the group's panes are sorted by which way they face, and the largest set is the facade.
    facades = []                          # [direction (ux, uy) into the room, area, points]
    for f in faces:
        if f["group"] != dom:
            continue
        pts = [_to_world(parsed["vertices"][vi - 1], up_axis, None, scale) for vi in f["verts"]]
        nx, ny, _nz = _to_world(face_normal(parsed, f), up_axis, None, 1.0)
        horizontal = math.hypot(nx, ny)
        if horizontal < 1e-6:
            direction = None              # a skylight: no horizontal facing at all
        else:
            ux, uy = nx / horizontal, ny / horizontal
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            if ux * (fcx - cx) + uy * (fcy - cy) < 0:     # winding is unreliable: face the room
                ux, uy = -ux, -uy
            direction = (ux, uy)
        for facade in facades:
            same = (facade[0] is None and direction is None) or (
                facade[0] is not None and direction is not None
                and facade[0][0] * direction[0] + facade[0][1] * direction[1] > 0.866)
            if same:
                facade[1] += face_area(parsed, f)
                facade[2].extend(pts)
                break
        else:
            facades.append([direction, face_area(parsed, f), list(pts)])
    dpts = max(facades, key=lambda facade: facade[1])[2]
    gx = sum(p[0] for p in dpts) / len(dpts)
    gy = sum(p[1] for p in dpts) / len(dpts)
    zmax = max(p[2] for p in dpts)
    zmin = min(p[2] for p in dpts)
    ix, iy = fcx - gx, fcy - gy
    mag = math.hypot(ix, iy)
    if mag < 1e-6:
        raise ValueError(
            f"cannot tell which way the glazing of group {dom!r} faces: its centre is the "
            "room's centre (a skylight, or panes all round). Give the facade explicitly.")
    inward = (ix / mag, iy / mag)
    return {"point": (gx, gy), "inward": inward, "transverse": (-inward[1], inward[0]),
            "H_win": zmax, "sill_z": zmin, "group": dom}


def daylight_zones(H_win, sill_z, *, zone_rule="head_height", depth_factors=(1, 2),
                   sensor_fraction=2 / 3, task_height=0.0):
    """Sidelighting zones from the window head height. Depths measured from the facade."""
    names = ["primary", "secondary", "tertiary"]
    if zone_rule == "ies_2.5":
        depth = 2.5 * (H_win - task_height)
        return [{"index": 1, "name": "primary", "near": 0.0, "far": depth,
                 "sensor_depth": sensor_fraction * depth}]
    zones, prev = [], 0.0
    for k, factor in enumerate(depth_factors):
        near, far = prev, factor * H_win
        zones.append({"index": k + 1, "name": names[k] if k < len(names) else f"zone{k + 1}",
                      "near": near, "far": far,
                      "sensor_depth": near + sensor_fraction * (far - near)})
        prev = far
    return zones


def _snap_into_footprint(px0, py0, ix, iy, d, polys, step=0.05):
    t = d
    while t > 0:
        sx, sy = px0 + ix * t, py0 + iy * t
        if point_in_footprint(sx, sy, polys):
            return sx, sy, (t < d)
        t -= step
    return px0 + ix * step, py0 + iy * step, True


def place_photosensors(parsed, material_map, scale, up_axis, *, zone_rule="head_height",
                       depth_factors=(1, 2), sensor_fraction=2 / 3, task_height=0.0,
                       mount="workplane", workplane_h=0.8):
    wall = glazing_wall(parsed, material_map, scale, up_axis)
    ftz = floor_top_z(parsed, material_map, scale, up_axis)
    zones = daylight_zones(wall["H_win"] - ftz, wall["sill_z"], zone_rule=zone_rule,
                           depth_factors=depth_factors, sensor_fraction=sensor_fraction,
                           task_height=task_height)
    polys = floor_polygons(parsed, material_map, scale, up_axis)
    if mount == "ceiling":
        cz = _ceiling_z(parsed, material_map, scale, up_axis, ftz)
        z = round((cz if cz is not None else ftz + 3.0) - 0.001, 4)
        direction = [0, 0, -1]
    else:
        z = round(ftz + workplane_h, 4)
        direction = [0, 0, 1]
    px0, py0 = wall["point"]
    ix, iy = wall["inward"]
    points, zone_meta = [], []
    for zone in zones:
        d = zone["sensor_depth"]
        sx, sy = px0 + ix * d, py0 + iy * d
        snapped = False
        if polys and not point_in_footprint(sx, sy, polys):
            sx, sy, snapped = _snap_into_footprint(px0, py0, ix, iy, d, polys)
        points.append([round(sx, 4), round(sy, 4), z] + direction)
        zone_meta.append({**zone, "position": [round(sx, 4), round(sy, 4), z], "snapped": snapped})
    weights, uncontrolled = _zone_area_weights(
        zones, wall, detect_interior(parsed, material_map, scale, up_axis))
    methodology = {
        "facade": {"group": wall["group"], "point": [round(wall["point"][0], 4), round(wall["point"][1], 4)],
                   "inward": [round(ix, 4), round(iy, 4)], "H_win": round(wall["H_win"] - ftz, 4),
                   "sill_z": round(wall["sill_z"], 4)},
        "zone_rule": zone_rule, "sensor_fraction": sensor_fraction, "mount": mount,
        "zones": zone_meta, "count": len(points),
        # Emitted so a caller feeding daylight_savings uses the zoning that matches THESE sensors
        # by construction. Without them the natural next step is area_weights_from_geometry, which
        # encodes a different zone rule and can cover the whole floor where these zones do not —
        # a difference worth tens of percent in the resulting savings figure.
        "weights": weights,
        "uncontrolled_fraction": uncontrolled,
        "weights_note": (
            "Floor-area fractions of each sensed zone, for daylight_savings(weights=...). They sum "
            f"to {sum(weights):.4f}; the remaining {uncontrolled * 100:.1f}% of the floor is not "
            "sensed by any of these photosensors and is billed at full power."),
    }
    return points, methodology


def _zone_area_weights(zones, wall, interior):
    """Floor-area fraction of each sidelighting zone: a band parallel to the facade.

    Each zone spans [near, far] inward from the glazing plane, so its share is the depth of that
    band clipped to the room, over the room's total depth — exact arithmetic, so two zones of
    equal depth get byte-identical weights.

    The denominator is the OCCUPIED INTERIOR, not the floor slab. A modelled slab runs under the
    walls, and that strip is neither occupied nor lit by the installation; measuring against it
    would understate every zone's share and overstate the uncontrolled remainder that the savings
    calculation bills at full power.
    """
    if not zones or not interior:
        return [], 0.0
    ixmin, ixmax, iymin, iymax, _src = interior
    px0, py0 = wall["point"]
    ix, iy = wall["inward"]
    ds = [(cx - px0) * ix + (cy - py0) * iy
          for cx, cy in ((ixmin, iymin), (ixmax, iymin), (ixmax, iymax), (ixmin, iymax))]
    d_lo, d_hi = min(ds), max(ds)
    total = d_hi - d_lo
    if total <= 0:
        return [], 0.0
    # Zone depths are measured from the GLAZING PLANE, while d_lo is the interior wall face, which
    # sits a wall-thickness inside it. Rebasing the room onto the same origin keeps zone 1 from
    # losing that strip (which lies inside the wall, not in the room) and makes equal-depth zones
    # come out equal.
    weights = [round(max(0.0, min(z["far"], total) - max(z["near"], 0.0)) / total, 6)
               for z in zones]
    return weights, round(max(0.0, 1.0 - sum(weights)), 6)
