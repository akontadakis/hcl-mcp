"""Import a Wavefront .obj into a per-channel Radiance scene (obj2rad + xform).

Pure command-builders (string-tested, no Radiance) plus an import_geometry()
orchestrator that follows the run-or-emit pattern. obj2rad runs once per
channel-set with a generated -m mapfile so modifier names match write_material's
_a/_b/_c suffixes (see spec D8).
"""

import hashlib
import json as _json
import math
import os
import time

from hcl_core.materials import write_material, require_safe_name
from hcl_core.spd import parse_spd, bin_average, to_grid_list
from hcl_core.surface_library import surface_lookup, surface_meta
from hcl_platform import rad_path as _rad_path  # aliased: `rad_path` is a local var name below
from hcl_radiance.commands import build_oconv
from hcl_radiance.discover import resolve_bin
from hcl_radiance.geometry_obj import (
    parse_obj,
    bbox as _obj_bbox,
    mesh_quality,
    parse_mtl,
    mtl_suggestions,
    face_area,
    face_normal,
    horizontal_floor_faces,
    marker_positions,
)
from hcl_radiance.ies_radiance import place_luminaires, build_ies2rad
from hcl_radiance.image_commands import build_rpict
from hcl_radiance.runner import run_sequence
from hcl_radiance.sensor_layout import work_plane_grid, eye_observer_points, dgp_views

_SCALE = {"mm": 0.001, "cm": 0.01, "m": 1.0, "ft": 0.3048}


# ---------------------------------------------------------------------------
# Frame transform helpers — model → final-world (mirrors build_xform chain)
# ---------------------------------------------------------------------------

_UP_AXES = ("Y", "Z")


def _normalize_up_axis(up_axis):
    """Canonicalise up_axis to "Y"/"Z". None -> "Z" (build_xform's historical default).

    Three call sites compared this string directly and one compared it uppercased, so
    up_axis="y" rotated the traced geometry while leaving every derived point in the
    unrotated frame. Normalising once at every entry removes the seam.
    """
    if up_axis is None:
        return "Z"
    norm = str(up_axis).strip().upper()
    if norm not in _UP_AXES:
        raise ValueError(f"up_axis must be one of {list(_UP_AXES)}, got {up_axis!r}")
    return norm


def _to_world(p, up_axis, north_angle_deg=None, scale=1.0):
    """model -> final-world. Pass scale=1.0 for a direction vector."""
    x, y, z = p[0] * scale, p[1] * scale, p[2] * scale
    if _normalize_up_axis(up_axis) == "Y":
        x, y, z = x, -z, y                       # -rx 90
    if north_angle_deg:
        th = math.radians(-north_angle_deg)      # -rz(−north): CCW about +Z by −north
        c, s = math.cos(th), math.sin(th)
        x, y = x * c - y * s, x * s + y * c
    return (x, y, z)


def parsed_in_world(parsed, *, units="m", up_axis="Z", north_angle_deg=None):
    """A parsed OBJ with its vertices in the SCENE's frame: metres, Z up, turned to north.

    `import_geometry` scales and turns the geometry it hands to Radiance (build_xform). Anything
    else read from the same file and then placed in that scene (window senders, blockers, a
    point compared with the sensor grid) has to make the same move, or it sits in the raw
    file's units and orientation while the room does not. The moves are a uniform scale and
    rotations, so face winding is kept.
    """
    scale = scale_factor(units)
    return {**parsed, "vertices": [_to_world(v, up_axis, north_angle_deg, scale)
                                   for v in parsed.get("vertices", [])]}


def _rotate_north(rows, north_angle_deg):
    """Rotate each [x,y,z,dx,dy,dz] row's (x,y) position and (dx,dy) gaze by the geometry's north."""
    if not north_angle_deg:
        return rows
    th = math.radians(-north_angle_deg)
    c, s = math.cos(th), math.sin(th)
    return [[round(x * c - y * s, 4), round(x * s + y * c, 4), z,
             round(dx * c - dy * s, 6), round(dx * s + dy * c, 6), dz]
            for x, y, z, dx, dy, dz in rows]


def _glass_groups(material_map):
    out = set()
    for g, spec in (material_map or {}).items():
        s, _ = resolve_spec(spec)
        if isinstance(s, dict) and s.get("type") == "glass":
            out.add(g)
    return out


def _floor_groups(material_map, floor_groups):
    named = set(floor_groups or [])
    typed = set()
    for g, spec in (material_map or {}).items():
        s, _ = resolve_spec(spec)
        if isinstance(s, dict) and s.get("type") == "floor":
            typed.add(g)
    return named | typed


def _context_groups(material_map):
    """Groups whose RESOLVED spec is type:"context" (exterior shading)."""
    out = set()
    for g, spec in (material_map or {}).items():
        s, _ = resolve_spec(spec)
        if isinstance(s, dict) and s.get("type") == "context":
            out.add(g)
    return out


def _world_footprint(parsed, material_map, scale, up_axis, floor_groups=None):
    """Axis-aligned footprint + floor height in the POST-remap, PRE-north frame.

    Floor faces = horizontal_floor_faces for type:floor/named groups, else all faces except type:context.

    The returned floor height is the floor's TOP face — the surface occupants stand on — so it
    matches `sensor_methodology.floor_top_z`, which `workplane_grid` and `observer_points` use.
    A modelled floor is usually a slab of non-zero thickness, and anchoring to its underside
    (`min(z)`) placed every derived height one slab-thickness low: on a 0.2 m slab, the EN 12464-1
    working plane at 0.6 m and eyes at 1.0/1.4 m. EN 12464-1 fixes the working plane relative to
    the walkable floor, so the top face is the only correct datum.

    The x/y footprint deliberately stays the full extent of the floor faces.
    """
    faces = horizontal_floor_faces(parsed, _floor_groups(material_map, floor_groups))
    have_floor = bool(faces)
    if not have_floor:
        ctx = _context_groups(material_map)
        faces = [f for f in parsed["faces"] if f["group"] not in ctx]
    idxs = {i for f in faces for i in f["verts"]} or set(range(1, len(parsed["vertices"]) + 1))
    pts = [_to_world(parsed["vertices"][i - 1], up_axis, None, scale) for i in idxs]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    # With real floor faces, their top is the walkable surface. Without them we are looking at
    # the whole room, where max(z) would be the CEILING -- there the lowest point is the best
    # available floor estimate.
    floor_z = max(zs) if have_floor else min(zs)
    return (min(xs), min(ys)), (max(xs), max(ys)), floor_z


def mean_aperture_normal(parsed, material_map, up_axis):
    """Horizontal gaze direction from the dominant glazing INTO the room, normalized.

    Winding-independent. This feeds `toward` in derive_sensor_outputs, which becomes the
    gaze direction of every derived eye observer and the -vd of every DGP fisheye view, so
    deriving it from the OBJ's face normal made vertical eye illuminance (mel-EDI, nvRD,
    WELL L03) depend on export winding: a reversed window pointed every observer at the
    back wall, silently. sensor_daylight.glazing_wall already resolves inward direction
    from the room centroid; this reuses it. Falls back to (0,-1) with no glazing.
    """
    from hcl_radiance.sensor_daylight import glazing_wall
    try:
        return tuple(glazing_wall(parsed, material_map, 1.0, up_axis)["inward"])
    except (ValueError, ZeroDivisionError):
        return (0.0, -1.0)


def aperture_report(parsed, material_map, scale, *, up_axis="Y", north_angle_deg=None):
    """Per resolved type:"glass" group: total area + TRUE-north azimuth/tilt. The face normal
    goes through the SAME _to_world chain as the geometry (incl. north), so azimuth is the real
    compass orientation (0=N, 90=E) — not a model-frame angle (spec C4/3.1)."""
    glass = _glass_groups(material_map)
    by_group = {}
    for f in parsed["faces"]:
        if f["group"] in glass:
            by_group.setdefault(f["group"], []).append(f)
    out = []
    for g, faces in by_group.items():
        area = sum(face_area(parsed, f) for f in faces) * scale * scale
        # Area-weighted mean normal (model frame), then transform to world
        wx = wy = wz = 0.0
        for f in faces:
            af = face_area(parsed, f)
            fnx, fny, fnz = face_normal(parsed, f)
            wx += af * fnx; wy += af * fny; wz += af * fnz
        wmag = math.sqrt(wx * wx + wy * wy + wz * wz)
        total = sum(face_area(parsed, f) for f in faces)
        # The mean normal only means something when the panes face the same way. For panes on
        # opposite walls, or wound opposite ways, it cancels: normalising what is left gave
        # "azimuth 0, tilt 90" -- a north-facing window -- for glazing that faces east and west.
        ambiguous = total <= 0.0 or wmag < 0.5 * total
        if ambiguous:
            out.append({"group": g, "area_m2": round(area, 4), "azimuth_deg": None,
                        "tilt_deg": None, "orientation_ambiguous": True})
            continue
        nx, ny, nz = _to_world((wx / wmag, wy / wmag, wz / wmag), up_axis, north_angle_deg, 1.0)
        azimuth = math.degrees(math.atan2(nx, ny)) % 360.0
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, nz))))
        out.append({"group": g, "area_m2": round(area, 4),
                    "azimuth_deg": round(azimuth, 1), "tilt_deg": round(tilt, 1),
                    "orientation_ambiguous": False})
    return out


def _ground_groups(material_map):
    """Groups whose RESOLVED spec is type:"ground" -> {group: resolved_spec}."""
    out = {}
    for g, spec in (material_map or {}).items():
        s, _ = resolve_spec(spec)
        if isinstance(s, dict) and s.get("type") == "ground":
            out[g] = s
    return out


def _albedo_from_spec(spec):
    """(albedo_list[401], has_spd) for one ground spec. Values clamped to [0,1]."""
    if spec.get("spd") is not None:
        vals = [min(1.0, max(0.0, float(v))) for v in to_grid_list(parse_spd(spec["spd"]))]
        return vals, True
    refl = min(1.0, max(0.0, float(spec.get("refl", 0.0))))
    return [refl] * 401, False


def derive_ground_albedo(parsed, material_map):
    """1 nm spectral albedo (len 401) from every type:"ground" group, area-weighted.

    Returns (albedo, kind) where kind is "spd" if any ground group carried a real SPD, else
    "flat"; (None, None) when no ground group is mapped. Consumed by spectral_sky_from_epw's
    spectral_albedo override so the scene ground reflectance drives the sky ground-glow term.
    """
    grounds = _ground_groups(material_map)
    if not grounds:
        return None, None
    weighted = [0.0] * 401
    total_area = 0.0
    any_spd = False
    for g, spec in grounds.items():
        area = sum(face_area(parsed, f) for f in parsed["faces"] if f["group"] == g) or 1.0
        vals, has_spd = _albedo_from_spec(spec)
        any_spd = any_spd or has_spd
        for i in range(401):
            weighted[i] += vals[i] * area
        total_area += area
    albedo = [w / total_area for w in weighted]
    return albedo, ("spd" if any_spd else "flat")


def derive_sensor_outputs(parsed, material_map, scale, *, up_axis="Y", north_angle_deg=None,
                          floor_groups=None, workplane_h=0.8, eye_heights=(1.2, 1.6), spacing=0.6,
                          clip_to_footprint=True, footprint_border=0.0):
    """Work-plane grid + eye observers (one set per eye height) + DGP views, all in the SAME
    final frame as the scene. observer_points/glare_views are flat concatenations (back-compat).

    `_world_footprint` returns the floor's full axis-aligned EXTENT, so on a concave (L/T/U) plan
    the lattice covers the bounding box and lands points in the notch -- outside the room, in open
    air. Those points are not merely useless: the notch has no floor, ceiling or walls, so they
    read HIGH and inflate every unweighted spatial aggregate (sDA, DA_avg, UDI, ASE, and `df_min`,
    which sets DF uniformity from a single point). On `l_room.obj` at spacing 1.0 that was 9 of 36
    grid points and 2 of 8 observers, silently.

    So points are clipped to the real floor polygons, exactly as `workplane_grid` /
    `observer_points` / `photosensors` already do -- this was the one sensor producer wired to
    `footprint` nowhere. Clipping happens in the PRE-north frame, matching `floor_polygons`'
    default, i.e. before `_rotate_north`. Each dropped observer takes its paired DGP view with it,
    so `observer_points` and `glare_views` stay index-aligned. `clipped` reports the counts.

    `clip_to_footprint=False` restores the raw bounding-box lattice; `footprint_border` insets the
    polygon (use it to keep points out of a wall solid when the floor slab runs under the walls).
    """
    (fmin, fmax, floor_z) = _world_footprint(parsed, material_map, scale, up_axis, floor_groups)
    toward = mean_aperture_normal(parsed, material_map, up_axis)

    polys = None
    if clip_to_footprint:
        from hcl_radiance.footprint import floor_polygons
        polys = floor_polygons(parsed, material_map, scale, up_axis) or None

    def _clip(rows):
        """(kept, n_dropped) for [x,y,z,dx,dy,dz] rows, in the pre-north frame."""
        if not polys:
            return rows, 0
        from hcl_radiance.footprint import clip_points
        kept, dropped = clip_points(rows, polys, border=footprint_border)
        return kept, len(dropped)

    grid_raw, grid_dropped = _clip(
        work_plane_grid(fmin, fmax, workplane_h=floor_z + workplane_h, spacing=spacing))
    grid = _rotate_north(grid_raw, north_angle_deg)

    observer_sets, flat_points, flat_views = [], [], []
    obs_dropped = 0
    for eh in eye_heights:
        obs, n_dropped = _clip(eye_observer_points(fmin, fmax, eye_h=floor_z + eh, toward=toward,
                                                   spacing=max(spacing * 3, 1.5)))
        obs_dropped += n_dropped
        obs = _rotate_north(obs, north_angle_deg)
        views = dgp_views(obs)           # derived AFTER clipping, so views track the kept points
        observer_sets.append({"eye_h": eh, "points": obs, "glare_views": views})
        flat_points.extend(obs)
        flat_views.extend(views)

    out = {"grid_points": grid, "observer_sets": observer_sets,
           "observer_points": flat_points, "glare_views": flat_views}
    if polys:
        out["clipped"] = {"grid_kept": len(grid), "grid_dropped": grid_dropped,
                          "observers_kept": len(flat_points), "observers_dropped": obs_dropped,
                          "footprint_source": "floor_polygons",
                          "footprint_border": footprint_border}
    return out


def _fmt(x):
    """Format a number without trailing-zero noise (0.001 not 0.001000...)."""
    return f"{float(x):.10g}"


def scale_factor(units):
    """Length-unit -> meters multiplier. Raises ValueError on an unknown unit."""
    try:
        return _SCALE[units]
    except KeyError:
        raise ValueError(f"units must be one of {sorted(_SCALE)}, got {units!r}")


def build_obj2rad(obj_path, mapfile):
    """obj2rad -m <mapfile> <obj_path>  -> Radiance polygons on stdout."""
    return ["obj2rad", "-m", mapfile, _rad_path(obj_path)]


def build_xform(path, *, scale=None, up_axis="Z", north_angle_deg=None):
    """xform a converted .rad: -s <scale> to meters, -rx 90 for Y-up -> Z-up.

    A meters + Z-up scene needs neither flag.
    north_angle_deg: clockwise azimuth (degrees) that post-remap +Y points toward.
    Applied as -rz (-north_angle_deg) after the up-axis correction.
    """
    argv = ["xform"]
    if scale is not None and float(scale) != 1.0:
        argv += ["-s", _fmt(scale)]
    if _normalize_up_axis(up_axis) == "Y":
        argv += ["-rx", "90"]
    if north_angle_deg:
        argv += ["-rz", _fmt(-north_angle_deg)]
    argv.append(path)
    return argv


def build_material_mapfile(groups, suffix, qualifier="Material"):
    """obj2rad mapping file: assign each source material its suffixed modifier.

    e.g. groups=['walls'], suffix='_a' -> 'walls_a (Material "walls") ;\\n'.
    qualifier: 'Material' matches usemtl names; 'Group' matches g group names.
    Use 'Group' when the OBJ has no usemtl at all (group-only files).
    """
    return "".join(f'{g}{suffix} ({qualifier} "{g}") ;\n' for g in groups)


def obj_group_qualifier(obj_text):
    """Return 'Material' if any usemtl line exists in obj_text, else 'Group'.

    Mirrors parse_obj_groups' usemtl-vs-g detection logic.
    obj2rad matches 'Material' to usemtl names and 'Group' to g group names.
    """
    for line in obj_text.splitlines():
        tok = line.split()
        if tok and tok[0] == "usemtl" and len(tok) > 1:
            return "Material"
    return "Group"


def obj_ungrouped_faces(obj_text):
    """Count face lines before the first `g` line, in a file that names its surfaces by group.

    The counterpart of `obj_unmaterialized_faces` for group-only files (no usemtl anywhere).
    Such faces belong to no group, obj2rad writes nothing for them, and the room comes out
    with a surface missing and no word said. A file with no `g` line at all is a different
    case -- everything is one implicit group -- and returns 0, as does a usemtl file.
    """
    seen_group = False
    ungrouped = 0
    has_group = False
    for line in obj_text.splitlines():
        tok = line.split()
        if not tok:
            continue
        if tok[0] == "usemtl" and len(tok) > 1:
            return 0
        if tok[0] == "g":
            seen_group = has_group = True
        elif tok[0] == "f" and not seen_group:
            ungrouped += 1
    return ungrouped if has_group else 0


def obj_unmaterialized_faces(obj_text):
    """Count face lines that occur without an active usemtl, but only when usemtl is used.

    Scans obj_text tracking whether a usemtl has been declared before each 'f' line.
    If the file has NO usemtl at all (group-only), returns 0 (valid via Group qualifier).
    If the file HAS usemtl somewhere, returns the count of 'f' lines that appear
    before the first (or with no active) usemtl — these faces obj2rad would silently drop.
    """
    has_usemtl = False
    active_usemtl = False
    dropped = 0
    for line in obj_text.splitlines():
        tok = line.split()
        if not tok:
            continue
        if tok[0] == "usemtl" and len(tok) > 1:
            has_usemtl = True
            active_usemtl = True
        elif tok[0] == "f":
            if not active_usemtl:
                dropped += 1
    return dropped if has_usemtl else 0


def parse_obj_groups(obj_text):
    """Discovered material names: usemtl in order; if none, the g group names. Deduped.

    A multi-name `g grp1 grp2` line contributes EVERY name, because obj2rad registers all of them
    and the mapfile must therefore define a modifier for each -- an unmapped one would emit an
    undefined modifier. Note this is deliberately broader than `geometry_obj.parse_obj`, which
    tracks only the name obj2rad actually PAINTS the face with (the last). Both are correct for
    their purpose; the pair must stay consistent about which name wins, or the aperture report
    describes a different surface than Radiance shades.
    """
    usemtl, groups = [], []
    for line in obj_text.splitlines():
        tok = line.split()
        if not tok:
            continue
        if tok[0] == "usemtl" and len(tok) > 1:
            usemtl.append(tok[1])
        elif tok[0] == "g" and len(tok) > 1:
            groups.extend(tok[1:])
    names = usemtl or groups
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def parse_obj_bbox(obj_text):
    """Axis-aligned bounds over the 'v' vertices, or None when there are none."""
    lo = [None, None, None]
    hi = [None, None, None]
    for line in obj_text.splitlines():
        tok = line.split()
        if len(tok) >= 4 and tok[0] == "v":
            try:
                xyz = [float(tok[1]), float(tok[2]), float(tok[3])]
            except ValueError:
                continue
            for i, c in enumerate(xyz):
                lo[i] = c if lo[i] is None else min(lo[i], c)
                hi[i] = c if hi[i] is None else max(hi[i], c)
    if lo[0] is None:
        return None
    return (tuple(lo), tuple(hi))


def _noncontext_model_bbox(parsed, ctx_groups):
    """Axis-aligned model-coord bbox over faces NOT in ctx_groups, or None when empty."""
    idxs = {i for f in parsed["faces"] if f["group"] not in ctx_groups for i in f["verts"]}
    if not idxs:
        return None
    pts = [parsed["vertices"][i - 1] for i in idxs]
    lo = [min(p[k] for p in pts) for k in range(3)]
    hi = [max(p[k] for p in pts) for k in range(3)]
    return (tuple(lo), tuple(hi))


def obj_has_normals(obj_text):
    """True if the OBJ declares any vertex normals (vn)."""
    return any(line.split()[:1] == ["vn"] for line in obj_text.splitlines())


class UnmappedGroupsError(ValueError):
    """Raised when discovered OBJ groups are not all present in material_map (spec D6).

    Subclasses ``ValueError`` (back-compat: callers catching ``ValueError`` still work).
    ``.payload`` is the SAME structured discovery report ``dry_run`` returns, plus an
    ``unmapped`` list — so the failure body doubles as the discovery path (spec §4 / D6).
    """

    def __init__(self, message, payload):
        super().__init__(message)
        self.payload = payload


def _discovery_payload(obj_path, parsed, units, scale, *, unmapped=None):
    """Structured discovery report shared by ``dry_run`` and the unmapped hard-fail."""
    (mn, mx) = _obj_bbox(parsed)
    size = [round((mx[i] - mn[i]) * scale, 6) for i in range(3)]
    payload = {
        "groups": parsed["groups"],
        "units": units,
        "bbox_m": {"size": size},
        "missing_normals": parsed["n_missing_normals"],
        "mesh_quality": mesh_quality(parsed),
        "suggestions": _adjacent_mtl_suggestions(obj_path, parsed["groups"]),
    }
    if unmapped is not None:
        payload["unmapped"] = unmapped
    return payload


def validate_material_map(groups, material_map, *, bbox, units, missing_normals,
                          parsed=None, scale=None, obj_path=None):
    """Raise UnmappedGroupsError naming every unmapped group, plus discovery context.

    When ``parsed``/``scale`` are supplied (the import_geometry call path) the error's
    ``.payload`` is the full structured discovery report (mirrors ``dry_run``: groups,
    bbox_m, missing_normals, mesh_quality, suggestions, unmapped). Without them
    (direct/back-compat calls) the payload carries the basic group/bbox/units/normals echo.
    """
    unmapped = [g for g in groups if g not in (material_map or {})]
    if not unmapped:
        return
    msg = (
        "unmapped groups (add them to material_map): " + ", ".join(unmapped)
        + f"\ndiscovered groups: {', '.join(groups)}"
        + f"\nunits={units} bbox={bbox} missing_normals={missing_normals}")
    if parsed is not None and scale is not None:
        payload = _discovery_payload(obj_path, parsed, units, scale, unmapped=unmapped)
    else:
        payload = {"groups": list(groups), "unmapped": unmapped, "units": units,
                   "bbox": bbox, "missing_normals": missing_normals}
    raise UnmappedGroupsError(msg, payload)


def group_channels(spec, channel_type):
    """Per-channel reflectance/transmittance for one material spec (spec D7).

    'spd' (2-column SPD) -> binned channels; otherwise a scalar 'refl' (plastic)
    or 'tvis' (glass) is broadcast flat to the 3- or 9-channel width.
    """
    n = 3 if channel_type == 0 else 9
    if spec.get("spd") is not None:
        return bin_average(parse_spd(spec["spd"]), channel_type)
    key = "tvis" if spec.get("type") == "glass" else "refl"
    if key not in spec:
        raise ValueError(
            f"material spec missing required key {key!r} (type={spec.get('type')!r}); "
            "provide a scalar value or an 'spd' entry")
    scalar = spec[key]
    return [scalar] * n


def build_material_sets(material_map, channel_type, work_dir):
    """Write per-group materials; return per-channel-set lists of .rad paths.

    write_material emits name.rad (3ch) or name_a/_b/_c.rad (9ch); index i of its
    returned files is channel-set i, so we transpose group-major -> set-major.
    """
    n_sets = 1 if channel_type == 0 else 3
    sets = [[] for _ in range(n_sets)]
    for group, spec in material_map.items():
        channels = group_channels(spec, channel_type)
        material_type = 0 if spec.get("type") == "glass" else 1
        res = write_material(
            channels, material_type=material_type, channel_type=channel_type,
            name=group, roughness=spec.get("roughness", 0.0),
            specularity=spec.get("specularity", 0.0), work_dir=work_dir)
        for i, path in enumerate(res["files"]):
            sets[i].append(path)
    return sets


_SUFFIXES = {0: [""], 1: ["_a", "_b", "_c"]}


# ---------------------------------------------------------------------------
# v2 helpers — material ergonomics, sidecar, north plumbing
# ---------------------------------------------------------------------------

def resolve_spec(spec):
    """Resolve a material spec.

    A string -> surface_library lookup. If the entry carries an `spd` FILE PATH, its text is loaded
    into the returned spec so group_channels binds a real spectrum (measured entries). The illustrative
    flag follows surface_meta (False for measured, True for illustrative).
    A dict -> pass through unchanged (not illustrative).

    Returns (resolved_dict, is_illustrative).
    """
    if isinstance(spec, str):
        entry = surface_lookup(spec)
        spd_val = entry.get("spd")
        if isinstance(spd_val, str) and os.path.isfile(spd_val):
            with open(spd_val) as fh:
                entry["spd"] = fh.read()
        return entry, bool(surface_meta(spec)["illustrative"])
    return spec, False


_SIDECAR_KEYS = ("material_map", "units", "up_axis", "north_angle_deg", "channel_type")
_SIDECAR_SCALAR_KEYS = ("units", "up_axis", "north_angle_deg", "channel_type")


def split_map_metadata(data):
    """Split a map-shaped dict into (material_map, scalars), applying one shared convention.

    Accepts BOTH shapes a caller is likely to have:
      1. Wrapped:  {"material_map": {group: spec, ...}, "units": ..., "up_axis": ...}
      2. Bare map: {group: spec, ..., "units": ..., "up_axis": ...} — the group specs
         live at the top level (this is what an exported material_map.json looks like).
    When no explicit "material_map" key is present, every top-level key that is neither a
    recognised scalar (units/up_axis/north_angle_deg/channel_type) nor underscore-prefixed
    (e.g. "_README") is treated as a group spec.

    DEF-INLINE-MAP: this used to live inside `load_sidecar`, so it applied only when the map
    arrived as a FILE. A caller who parsed that same JSON and passed it as `material_map=`
    got no stripping, and `resolve_spec` then read every non-group key as a surface-library
    name — surfacing a documentation comment as `KeyError: unknown surface "Pinned material
    map for office_room.obj. Keys are the OBJ's ..."`. Since the two arguments describe the
    same artifact, they now share this one function; only the source differs.

    Anything left after the split is still treated as a group spec, so a typo'd material name
    raises as before rather than being silently dropped.
    """
    scalars = {k: data[k] for k in _SIDECAR_SCALAR_KEYS if k in data}
    if "material_map" in data:
        return data["material_map"], scalars
    bare = {k: v for k, v in data.items()
            if k not in _SIDECAR_SCALAR_KEYS and not k.startswith("_")}
    return (bare or None), scalars


def load_sidecar(path):
    """Load a JSON sidecar file and return only the recognised import_geometry keys.

    Shape handling is `split_map_metadata`'s; this only supplies the file.
    """
    with open(path) as fh:
        data = _json.load(fh)
    mm, out = split_map_metadata(data)
    if mm:
        out["material_map"] = mm
    return out


def _adjacent_mtl_suggestions(obj_path, groups):
    """Return mtl_suggestions for the .mtl adjacent to *obj_path*, or {} if absent."""
    if not obj_path:
        return {}
    mtl_path = os.path.splitext(obj_path)[0] + ".mtl"
    if not os.path.exists(mtl_path):
        return {}
    with open(mtl_path) as fh:
        return mtl_suggestions(parse_mtl(fh.read()), groups)


def _available():
    """True when both Radiance binaries this importer needs are resolvable."""
    return bool(resolve_bin("obj2rad") and resolve_bin("xform"))


def _bbox_warnings(bbox, scale, missing_normals, sanity_bbox=None):
    """Human-readable warnings: scaled full-scene bbox, an implausibility flag (computed over
    sanity_bbox when given — e.g. non-context room geometry), missing normals."""
    warnings = []
    if bbox is not None:
        dims = [(hi - lo) * scale for lo, hi in zip(bbox[0], bbox[1])]
        warnings.append("bbox %.2f x %.2f x %.2f m" % tuple(dims))
        sb = sanity_bbox if sanity_bbox is not None else bbox
        sdims = [(hi - lo) * scale for lo, hi in zip(sb[0], sb[1])]
        biggest = max(sdims)
        if biggest > 200.0 or (biggest > 0 and biggest < 0.5):
            warnings.append(
                "implausible bbox for a room (check units/up_axis): %.3f m" % biggest)
    if missing_normals:
        warnings.append("OBJ declares no vertex normals (vn); surface orientation relies on winding")
    return warnings


# ---------------------------------------------------------------------------
# D5 additions — P8: luminaires (D1) + provenance manifest (D2) + annotate (D3)
# ---------------------------------------------------------------------------

def _position(marker, spec, up_axis, north_angle_deg, scale):
    """One placement entry: world-frame xyz, plus the group's `rot` when it declares one.

    `rot` is the Y-up Euler triple place_luminaires expects (rot[1], the spin about the up
    axis, remaps to -rz). It matters for any luminaire that is not azimuthally symmetric:
    ies2rad lays a luminaire's long axis along +Y, so a fitting modelled along +X needs
    rot=[0, 90, 0] or its distribution sits 90 degrees across its own housing — silently,
    since the run still completes. Omitted entirely when unset, so payloads are unchanged.
    """
    entry = {"xyz": list(_to_world(marker, up_axis, north_angle_deg, scale))}
    rot = spec.get("rot") if isinstance(spec, dict) else None
    if rot:
        entry["rot"] = list(rot)
    return entry


def luminaire_block(parsed, material_map, *, scale, up_axis="Y", north_angle_deg=None):
    """Place EVERY type:"luminaire" group at its markers, in the final world frame.

    Each marker goes through _to_world (scale, -rx 90, -rz(-north)) so it shares
    the geometry's coordinate system. ies2rad is a list of argv-lists (one per group).
    Groups with no marker or no ies are surfaced in `warnings` rather than dropped silently.
    """
    lum_groups = {g: s for g, s in (material_map or {}).items()
                  if isinstance(s, dict) and s.get("type") == "luminaire"}
    if not lum_groups:
        return {"placement_rad": "", "ies2rad": None, "warnings": []}
    blocks, ies_cmds, warnings = [], [], []
    for g, spec in lum_groups.items():
        markers = marker_positions(parsed, group=g)
        if not markers:
            warnings.append(f"luminaire group {g!r}: no marker (p primitive or group faces) — skipped")
            continue
        positions = [_position(p, spec, up_axis, north_angle_deg, scale) for p in markers]
        blocks.append(place_luminaires(f"{g}.rad", {"positions": positions}))
        if spec.get("ies"):
            ies_cmds.append(build_ies2rad(spec["ies"], out_prefix=g))
        else:
            warnings.append(f"luminaire group {g!r}: no 'ies' path — placed without photometry")
    return {"placement_rad": "".join(blocks), "ies2rad": ies_cmds or None, "warnings": warnings}


def luminaire_electric_lights(parsed, material_map, *, scale, up_axis="Y", north_angle_deg=None):
    """Build the drop-in electric_lights payload run_grid/run_image consume directly.

    Each type:"luminaire" group -> one input spec with world-frame marker positions and the
    source ies/spd forwarded. run_grid runs ies2rad + colorize + _luminaire_channels itself —
    this function deliberately does NEITHER (spec v3a §5.2). Groups without a marker or ies are
    surfaced as warnings, not silently dropped.
    """
    lum_groups = {g: s for g, s in (material_map or {}).items()
                  if isinstance(s, dict) and s.get("type") == "luminaire"}
    out, warnings = [], []
    for g, spec in lum_groups.items():
        markers = marker_positions(parsed, group=g)
        if not markers:
            warnings.append(f"luminaire group {g!r}: no marker (p primitive or group faces) — skipped")
            continue
        if not spec.get("ies"):
            warnings.append(f"luminaire group {g!r}: no 'ies' path — skipped from electric_lights")
            continue
        positions = [_position(p, spec, up_axis, north_angle_deg, scale) for p in markers]
        if len(positions) > 1:
            warnings.append(
                f"luminaire group {g!r}: {len(positions)} emitters from {len(positions)} "
                f"disconnected mesh islands (one per fitting); total load scales with this count")
        out.append({
            "ies": spec["ies"],
            "placement": {"positions": positions},
            "spd": spec.get("spd"),
            "preset": spec.get("preset"),
            "multiplier": spec.get("multiplier", 1.0),
            "maintenance_factor": spec.get("maintenance_factor", 1.0),
            "units": spec.get("units", 2),
        })
    return out, warnings


_MANIFEST_HEADER_MARK = "# --- hcl-mcp geometry provenance ---"


def manifest_header(manifest):
    """The provenance block as text: one `# key: value` line per entry.

    A value is flattened to a single line first. A line break inside one (a sidecar path can
    hold one) would end the comment, and the rest would be a line of its own in a file Radiance
    reads, where `!command` is run.
    """
    lines = [_MANIFEST_HEADER_MARK]
    for k in sorted(manifest):
        lines.append(f"# {k}: {' '.join(str(manifest[k]).split())}")
    lines.append("# --- end provenance ---")
    return "\n".join(lines) + "\n"


def _embed_manifest_header(rad_path, manifest):
    """Prepend a #-comment provenance block to a geometry .rad. Idempotent; Radiance ignores #."""
    with open(rad_path) as fh:
        body = fh.read()
    if _MANIFEST_HEADER_MARK in body:
        return
    lines = manifest_header(manifest).splitlines()
    with open(rad_path, "w") as fh:
        fh.write("\n".join(lines) + "\n" + body)


def build_manifest(obj_path, *, units, up_axis, north_angle_deg, channel_type, parsed, scale,
                   map_source, tool_version, timestamp):
    """Stamp a provenance manifest for the geometry import.

    Records the SHA-256 of the source OBJ, the import parameters, the bounding-box
    in meters, and the timestamp (passed in so the function stays pure / testable).
    """
    with open(obj_path, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    (mn, mx) = _obj_bbox(parsed)
    return {"source_sha256": sha, "units": units, "up_axis": up_axis,
            "north_angle_deg": north_angle_deg, "channel_type": channel_type,
            "bbox_m": {"size": [round((mx[i] - mn[i]) * scale, 6) for i in range(3)]},
            "map_source": map_source, "tool_version": tool_version, "timestamp": timestamp}


def material_summary(parsed, material_map, apertures):
    """One row per group: type, refl/tvis if present, and aperture angles for glass groups."""
    ap = {a["group"]: a for a in apertures}
    rows = []
    for g in parsed["groups"]:
        if g not in material_map:
            continue                      # e.g. parse_obj's implicit default group
        spec, _ = resolve_spec(material_map[g])
        row = {"group": g, "type": spec.get("type", "plastic")}
        if "refl" in spec:
            row["refl"] = spec["refl"]
        if "tvis" in spec:
            row["tvis"] = spec["tvis"]
        if g in ap:
            row["azimuth_deg"] = ap[g]["azimuth_deg"]
            row["tilt_deg"] = ap[g]["tilt_deg"]
        rows.append(row)
    return rows


def annotate_steps(scene_files, out_hdr, view, fc_out, work_dir, available):
    """Build and (emit-)run oconv -> rpict -> falsecolor annotation pipeline."""
    oct_step = {"cmd": build_oconv(scene_files, "annot.oct"), "stdout": "annot.oct"}
    pic_step = {"cmd": build_rpict("annot.oct", view=view), "stdout": out_hdr}
    fc_step = {"cmd": ["falsecolor", "-i", out_hdr, "-s", "5", "-l", "Lux"], "stdout": fc_out}
    return run_sequence([oct_step, pic_step, fc_step], work_dir, available)


def import_geometry(obj_path, *, material_map=None, units=None, up_axis=None,
                    channel_type=1, work_dir, run=True, north_angle_deg=None,
                    dry_run=False, sidecar=None, derive_sensors=False,
                    annotate=False, strict=False, eye_heights=(1.2, 1.6), workplane_h=0.8, spacing=0.6):
    """Import a .obj into a per-channel Radiance scene (spec §6).

    Returns geometry_set + material_sets (index-aligned per channel-set) plus the
    discovered groups and warnings.  On the emit path (Radiance absent) the
    obj2rad/xform commands are returned but geometry .rad are not yet produced;
    material .rad and mapfiles are always written (pure Python).

    New in v2:
    - sidecar: path to a JSON file supplying defaults (explicit kwargs always win).
    - dry_run=True: return a discovery payload without binding materials or running Radiance.
    - north_angle_deg: clockwise azimuth (degrees) for -rz rotation.
    - material_map values may be library name strings (resolved via surface_library).
    - derive_sensors: emit work-plane grid + dual-height observer_sets + glare_views.
    - annotate: build the falsecolor colored-by-material render (oconv -> rpict -> falsecolor).
    - strict: raise GeometryHealthError when the health report holds error findings. strict has NO
      effect when dry_run=True: that path returns before materials are bound, so no health report
      is computed to raise on.
    - eye_heights / workplane_h / spacing: sensor layout parameters consumed by derive_sensors.
    """
    obj_path = os.path.abspath(obj_path)
    os.makedirs(work_dir, exist_ok=True)
    abs_work = os.path.abspath(work_dir)

    # 1a. An INLINE material_map may carry the same metadata a sidecar file does — a caller who
    # read the sidecar JSON and passed its parsed contents is doing the obvious thing, so it must
    # not die on the `_README` key (DEF-INLINE-MAP). Same convention as the file path, one
    # function; scalars found here are absorbed only where the caller left the argument unset.
    if material_map:
        material_map, _inline_scalars = split_map_metadata(material_map)
        if units is None:
            units = _inline_scalars.get("units")
        if up_axis is None:
            up_axis = _inline_scalars.get("up_axis")
        if north_angle_deg is None:
            north_angle_deg = _inline_scalars.get("north_angle_deg")

    # 1. Sidecar merge — explicit kwargs always win.
    if sidecar is not None:
        sc = load_sidecar(sidecar)
        material_map = material_map if material_map else sc.get("material_map")
        units = units if units is not None else sc.get("units")
        up_axis = up_axis if up_axis is not None else sc.get("up_axis")
        if north_angle_deg is None:
            north_angle_deg = sc.get("north_angle_deg")
        # channel_type has a default of 1; don't override unless sidecar had it
        # and the caller left channel_type at the default.  Since we can't
        # distinguish "caller passed 1" from "default 1" with a keyword-only arg
        # that has a default, we simply don't override channel_type from sidecar
        # here (the brief says keep it simple).

    def _abs(p):
        return p if os.path.isabs(p) else os.path.join(abs_work, p)

    with open(obj_path) as fh:
        obj_text = fh.read()

    # 3. dry_run early return (before validation / binding).
    if dry_run:
        scale = scale_factor(units) if units is not None else 1.0
        parsed = parse_obj(obj_text)
        return _discovery_payload(obj_path, parsed, units, scale)

    ungrouped = obj_ungrouped_faces(obj_text)
    if ungrouped:
        raise ValueError(
            f"{ungrouped} face(s) come before the first `g` line and so belong to no group. "
            "obj2rad would drop them silently and the room would be missing a surface. Put a "
            "`g <name>` line before them (and map that name in material_map).")
    groups = parse_obj_groups(obj_text)
    # Every group becomes <work_dir>/<group>.rad and a line of the obj2rad map file.
    for g in groups:
        require_safe_name(g, "OBJ group / material")
    bbox = parse_obj_bbox(obj_text)
    missing_normals = not obj_has_normals(obj_text)
    # DEF-8: a forgotten `units` must not mask the more actionable unmapped-groups error. Use a
    # provisional scale for the discovery/error payload; hard-require units only after the map checks.
    scale = scale_factor(units) if units is not None else 1.0
    # Parse OBJ once; reuse for the discovery/error payload, apertures and sensors.
    parsed_rich = parse_obj(obj_text)

    # 4. Resolve string specs before validation/binding.
    resolved_map = {g: resolve_spec(v)[0] for g, v in (material_map or {}).items()}
    illustrative = [
        g for g, v in (material_map or {}).items()
        if isinstance(v, str) and surface_meta(v)["illustrative"]
    ]

    # Unmapped groups hard-fail with a structured .payload that doubles as discovery (D6).
    validate_material_map(groups, material_map, bbox=bbox, units=units,
                          missing_normals=missing_normals, parsed=parsed_rich,
                          scale=scale, obj_path=obj_path)

    # DEF-8: groups are all mapped — now require a real `units` (raises the clear units error if None).
    scale = scale_factor(units)

    dropped = obj_unmaterialized_faces(obj_text)
    if dropped:
        raise ValueError(
            f"{dropped} face(s) have no active usemtl and would be silently dropped by obj2rad. "
            "Assign usemtl to every face or remove all usemtl lines to use group-only mode.")

    qualifier = obj_group_qualifier(obj_text)

    # Pass resolved_map so library-string specs bind correctly.
    # Exclude luminaire groups — they have no geometry faces and no refl/tvis.
    scene_map = {g: v for g, v in resolved_map.items()
                 if not (isinstance(v, dict) and v.get("type") == "luminaire")}
    material_sets = build_material_sets(scene_map, channel_type, abs_work)

    steps, geometry_set = [], []
    for suffix in _SUFFIXES[channel_type]:
        mapfile = f"mapfile{suffix}.txt"
        with open(os.path.join(abs_work, mapfile), "w") as fh:
            # Map only the groups that scene_map defines a material for. A luminaire group is
            # excluded there by design, so naming it here would make obj2rad emit faces whose
            # modifier nothing defines and oconv would abort with `undefined modifier` (D-5).
            # Left out of the mapfile, obj2rad drops those faces instead — which is what we want:
            # the luminous opening comes from the ies2rad emitter, not from a dummy diffuse face
            # sitting 0.25 mm off it. Model a visible housing as its own non-luminaire group.
            fh.write(build_material_mapfile([g for g in groups if g in scene_map],
                                            suffix, qualifier))
        raw = f"raw{suffix}.rad"
        geom = f"geometry{suffix}.rad"
        steps.append({"cmd": build_obj2rad(obj_path, mapfile), "stdout": raw})
        # 5. Thread north into the xform step.
        # Use an absolute path for the xform input: Radiance xform searches RAYPATH for .rad
        # files by name (not cwd), so a relative name fails even when cwd is correct.
        steps.append({"cmd": build_xform(_abs(raw), scale=scale, up_axis=up_axis,
                                         north_angle_deg=north_angle_deg),
                      "stdout": geom})
        geometry_set.append(_abs(geom))

    result = run_sequence(steps, work_dir=abs_work, available=run and _available())
    _ctx_for_bbox = _context_groups(resolved_map)
    _sanity = _noncontext_model_bbox(parsed_rich, _ctx_for_bbox) if _ctx_for_bbox else None
    warnings = _bbox_warnings(bbox, scale, missing_normals, sanity_bbox=_sanity)
    # 6. Append illustrative-library warning.
    if illustrative:
        warnings.append(
            "illustrative library reflectances (not measured): "
            + ", ".join(sorted(illustrative)))

    out = {"ran": result["ran"], "commands": result.get("commands", []),
           "geometry_set": geometry_set, "material_sets": material_sets,
           "channel_type": channel_type, "groups": groups,
           "warnings": warnings, "work_dir": abs_work}
    if not result["ran"]:
        out["reason"] = result.get("reason")
    elif result.get("returncode", 0) != 0:
        out["error"] = result.get("error")
        out["failed_step"] = result.get("failed_step")
    out["apertures"] = aperture_report(parsed_rich, resolved_map, scale,
                                       up_axis=up_axis, north_angle_deg=north_angle_deg)
    _ctx = sorted(_context_groups(resolved_map))
    if _ctx:
        out["context_groups"] = _ctx
    ground_albedo, ground_kind = derive_ground_albedo(parsed_rich, resolved_map)
    if ground_albedo is not None:
        out["ground_albedo"] = ground_albedo
        out["ground_albedo_kind"] = ground_kind
    if derive_sensors:
        out.update(derive_sensor_outputs(parsed_rich, resolved_map, scale,
                                         up_axis=up_axis, north_angle_deg=north_angle_deg,
                                         eye_heights=eye_heights, workplane_h=workplane_h,
                                         spacing=spacing))
        # A concave plan drops the bounding-box lattice cells that fall outside the floor. Say so:
        # a silently smaller grid than the extent implies would otherwise look like a miscount.
        _clip = out.get("clipped") or {}
        if _clip.get("grid_dropped") or _clip.get("observers_dropped"):
            warnings.append(
                "derived sensors clipped to the floor footprint: dropped %d of %d grid point(s) "
                "and %d observer(s) that fell outside the floor (concave plan or a floor slab "
                "narrower than its bounding box)"
                % (_clip["grid_dropped"], _clip["grid_dropped"] + _clip["grid_kept"],
                   _clip["observers_dropped"]))

    # D5 — P8 additions.
    # Luminaires: wire if any type:"luminaire" group present.
    has_lum = any(
        isinstance(v, dict) and v.get("type") == "luminaire"
        for v in resolved_map.values()
    )
    if has_lum:
        el, el_warn = luminaire_electric_lights(parsed_rich, resolved_map, scale=scale,
                                                up_axis=up_axis, north_angle_deg=north_angle_deg)
        if el:
            out["electric_lights"] = el
        warnings.extend(el_warn)
        # v2 informational block retained for back-compat; its warnings overlap el_warn, so do
        # NOT re-extend `warnings` from it (avoids duplicate per-group messages).
        out["luminaires"] = luminaire_block(parsed_rich, resolved_map, scale=scale,
                                            up_axis=up_axis, north_angle_deg=north_angle_deg)

    # Manifest: always present.
    out["manifest"] = build_manifest(
        obj_path, units=units, up_axis=up_axis, north_angle_deg=north_angle_deg,
        channel_type=channel_type, parsed=parsed_rich, scale=scale,
        map_source=(sidecar or "inline"), tool_version="hcl-mcp",
        timestamp=time.time())
    manifest_path = os.path.join(abs_work, "manifest.json")
    with open(manifest_path, "w") as fh:
        _json.dump(out["manifest"], fh, indent=2, sort_keys=True)
    out["manifest_path"] = manifest_path

    # Embed provenance header into each geometry .rad file that exists on disk.
    for geom in out["geometry_set"]:
        if os.path.exists(geom):
            _embed_manifest_header(geom, out["manifest"])

    # Annotate: optional summary + emit-path commands.
    if annotate:
        out["summary"] = material_summary(parsed_rich, resolved_map, out["apertures"])
        scene = [*out["material_sets"][0], out["geometry_set"][0]]
        # `run and ...`: a dry run must execute nothing, the annotation render included.
        ann = annotate_steps(scene, "annot.hdr", "-vp 2 1 1.5 -vd 0 -1 0 -vh 60 -vv 60",
                             "annot_fc.hdr", abs_work, run and _available())
        out["annotate_commands"] = ann["commands"]

    # Health report: always computed, advisory by default (spec 2026-07-23).
    # Pass through the sensor/luminaire context already computed above -- otherwise the
    # report claims "no sensor or photosensor block supplied" / defers luminaire checks
    # even when derive_sensors and/or a luminaire group produced exactly that data a few
    # lines earlier, which is a false statement (code review, task 14).
    from hcl_radiance.geometry_health import GeometryHealthError, check_geometry_health
    out["health"] = check_geometry_health(
        parsed_rich, resolved_map,
        sensors=out.get("grid_points") if derive_sensors else None,
        electric_lights=out.get("electric_lights"),
        scale=scale)                      # tolerances are absolute metres; see _scaled_to_metres
    if strict and not out["health"]["ok"]:
        n = out["health"]["counts"]["error"]
        if out.get("error"):
            # A real Radiance failure already happened — a strict health raise must not
            # bury it. Fold both into the exception rather than discarding the Radiance
            # failure (see code review: previously the health raise silently ate it).
            payload = {**out["health"], "radiance_error": out["error"],
                      "radiance_failed_step": out.get("failed_step")}
            raise GeometryHealthError(
                f"Radiance step failed ({out.get('failed_step')!r}) and "
                f"{n} error-severity health finding(s); see .payload for both",
                payload)
        raise GeometryHealthError(
            f"{n} error-severity health finding(s); see .payload for the full report",
            out["health"])

    return out
