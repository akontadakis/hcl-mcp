"""Face-level aperture extraction.

`geometry_import.aperture_report` area-weights each OBJ GROUP to one normal, which is
useless for LM-83 window grouping: a single `glazing` group spanning north and south
averages to a near-zero normal. LM-83 2.2.6 groups COPLANAR windows of similar
orientation, so grouping needs per-face normals AND per-face plane offsets.
"""
import math
import os

from hcl_radiance.geometry_import import _glass_groups


def _newell(verts):
    """Newell's method: area vector of a polygon, robust for non-triangular faces."""
    nx = ny = nz = 0.0
    n = len(verts)
    for i in range(n):
        x0, y0, z0 = verts[i]
        x1, y1, z1 = verts[(i + 1) % n]
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return (nx / 2.0, ny / 2.0, nz / 2.0)


def _centroid(verts):
    n = float(len(verts))
    return (sum(v[0] for v in verts) / n,
            sum(v[1] for v in verts) / n,
            sum(v[2] for v in verts) / n)


def glass_faces(parsed, material_map):
    """Every glass-material face, with its own area, normal, azimuth, tilt and plane.

    `parsed` is `geometry_obj.parse_obj` output, whose `faces[i]["verts"]` are 1-BASED
    INDICES into `parsed["vertices"]` -- they must be dereferenced, not read as points.

    Azimuth is a compass bearing in the OBJ's own frame with +Y north and +Z up:
    0 = north, 90 = east. Tilt is the angle from horizontal, so a vertical window is 90.
    `plane_offset` is the plane constant n.p, which distinguishes parallel-but-separate
    facades that azimuth alone would merge.
    """
    glass = _glass_groups(material_map)
    vertices = parsed.get("vertices", [])
    out = []
    for idx, face in enumerate(parsed.get("faces", [])):
        if face.get("group") not in glass:
            continue
        try:
            verts = [tuple(float(c) for c in vertices[i - 1]) for i in face["verts"]]
        except (IndexError, TypeError) as exc:
            raise ValueError(
                f"face {idx} of group {face.get('group')!r} references a vertex outside "
                f"the {len(vertices)} vertices parsed from this OBJ") from exc
        if len(verts) < 3:
            continue
        area_vec = _newell(verts)
        mag = math.sqrt(sum(c * c for c in area_vec))
        if mag <= 0.0:
            continue                      # degenerate face: no normal to speak of
        normal = tuple(c / mag for c in area_vec)
        centroid = _centroid(verts)
        out.append({
            "group": face["group"], "index": idx, "verts": verts,
            "area": mag, "normal": normal,
            "azimuth_deg": math.degrees(math.atan2(normal[0], normal[1])) % 360.0,
            "tilt_deg": math.degrees(math.acos(max(-1.0, min(1.0, normal[2])))),
            "centroid": centroid,
            "plane_offset": sum(n * c for n, c in zip(normal, centroid)),
        })
    return out


def faces_need_flip(faces, interior_point):
    """Whether `faces` must be reversed so their normals face `interior_point`.

    The V receiver has to face the sensors, and a wrong orientation fails SILENTLY --
    rfluxmtx returns a correctly shaped matrix of exactly zero. An OBJ exterior wall is
    conventionally wound outward, but nothing enforces that, so the direction is measured
    against a known interior point (the sensor-grid centroid) rather than assumed.
    """
    inward = 0.0
    for face in faces:
        to_room = tuple(i - c for i, c in zip(interior_point, face["centroid"]))
        inward += face["area"] * sum(n * t for n, t in zip(face["normal"], to_room))
    return inward < 0.0


def window_sender_rad(faces, name, *, flip=True):
    """`#@rfluxmtx`-annotated glow polygons for one window group.

    The window is redefined as a `glow` so rfluxmtx can use it as V's receiver and D's
    sender. The four reals MUST be `4 1 1 1 0`: a non-zero fourth real makes the glow
    self-illuminating, which silently corrupts both matrices rather than failing.

    ORIENTATION, established by live test (see .scratch/lm83/engine-findings.md):
    the V receiver's normal must point INTO the room, toward the sensors. rfluxmtx
    receives on a receiver's FRONT face, and V measures flux arriving at the sensors
    FROM the window, so the front has to face them. Measured on a 4x4x3 m room with a
    south window: normal (0,+1,0) into the room gave a V matrix summing to 3.83, and
    (0,-1,0) out of it gave exactly 0.0 -- a well-formed matrix, no error, no warning.
    D is winding-insensitive (measured identical both ways: rays leave the sender's back
    and the sky dome is reached either way), so one file serves both roles.

    An OBJ exterior wall is normally wound with its normal pointing OUT of the building,
    so `flip` defaults ON: callers pass faces straight from `glass_faces` and get the
    inward-facing receiver V needs.

    h=kf is the Klems full basis (145 bins); u=+Z is the up vector.
    """
    lines = ["#@rfluxmtx h=kf u=+Z", f"void glow {name}", "0", "0", "4 1 1 1 0", ""]
    for i, face in enumerate(faces):
        verts = list(reversed(face["verts"])) if flip else list(face["verts"])
        reals = " ".join(f"{c:g}" for v in verts for c in v)
        lines += [f"{name} polygon {name}.{i}", "0", "0",
                  f"{len(verts) * 3} {reals}", ""]
    return "\n".join(lines) + "\n"


def write_window_sender(faces, name, work_dir, *, interior_point=None):
    """Write the glow sender/receiver .rad for a window group. Returns its absolute path.

    ONE file serves both roles: D is winding-insensitive, and V needs the normal facing
    into the room. Pass `interior_point` (the sensor-grid centroid is ideal) to have the
    orientation measured rather than assumed; without it the OBJ's conventional outward
    winding is assumed and reversed.
    """
    os.makedirs(work_dir, exist_ok=True)
    flip = (faces_need_flip(faces, interior_point) if interior_point is not None
            else True)
    path = os.path.abspath(os.path.join(work_dir, f"{name}_sender.rad"))
    with open(path, "w") as fh:
        fh.write(window_sender_rad(faces, name, flip=flip))
    return path
