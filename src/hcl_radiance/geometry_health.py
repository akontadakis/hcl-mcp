"""Health report over an imported OBJ scene (spec 2026-07-23).

Pure Python; no Radiance binaries. Reports defects that would otherwise complete
silently and return a plausible number.

Severity contract:
  error   -- physically wrong or unsimulable; results WILL be incorrect. Reserved for
             findings that change traced physics.
  warning -- probably wrong, but legitimately valid in some models. Never blocks.
  info    -- a fact worth seeing so the user can catch by eye what no rule can decide.

Severity discipline: an INFERENTIAL check (one that guesses intent from geometry) may
never emit `error`. Its ceiling is `warning`.
"""

import math

from hcl_radiance.geometry_obj import face_area, face_normal

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def _is_finite_vertex(v):
    return math.isfinite(v[0]) and math.isfinite(v[1]) and math.isfinite(v[2])


def _face_is_finite(parsed, face):
    """True iff every vertex the face references has finite (x, y, z).

    A NaN or +/-inf coordinate (e.g. an exporter overflow that parsed `1e400` to inf)
    poisons every downstream float computation -- Newell's-method normals, centroids,
    `round()` in `_plane_key` -- turning a health check that must never raise into a
    crash. Geometric checks call this to SKIP such a face rather than trace it; the
    vertices themselves are reported once, by `check_finite_coordinates`.
    """
    verts = parsed["vertices"]
    return all(_is_finite_vertex(verts[i - 1]) for i in face["verts"])


class GeometryHealthError(ValueError):
    """Raised by import_geometry(strict=True) when the report holds error findings.

    Mirrors UnmappedGroupsError: `.payload` is the SAME report the non-strict path
    returns, so the failure body doubles as the diagnostic.
    """

    def __init__(self, message, payload):
        super().__init__(message)
        self.payload = payload


def finding(code, severity, category, message, *, subjects=None, detail=None, fix=None):
    """One health finding. `fix` is mandatory on error and warning."""
    if severity not in SEVERITY_ORDER:
        raise ValueError(
            f"severity must be one of {sorted(SEVERITY_ORDER)}, got {severity!r}")
    if severity in ("error", "warning") and not fix:
        raise ValueError(
            f"finding {code!r} has severity {severity!r} and must carry a `fix`; "
            "a finding the user cannot act on is not worth emitting")
    return {
        "code": code,
        "severity": severity,
        "category": category,
        "message": message,
        "subjects": list(subjects) if subjects else [],
        "detail": dict(detail) if detail else {},
        "fix": fix,
    }


def build_report(findings, *, checked, skipped=None, confidence=None):
    """Assemble the report: errors first, then warnings, then info."""
    ordered = sorted(findings, key=lambda f: SEVERITY_ORDER[f["severity"]])
    counts = {s: 0 for s in SEVERITY_ORDER}
    for f in ordered:
        counts[f["severity"]] += 1
    return {
        "ok": counts["error"] == 0,
        "counts": counts,
        "findings": ordered,
        "checked": list(checked),
        "skipped": list(skipped) if skipped else [],
        "confidence": confidence or {},
    }


def _plane_key(parsed, face, tol):
    """Quantised (nx, ny, nz, d) plane signature, sign-normalised so winding does not split
    a plane in two. Returns None for a degenerate face."""
    nx, ny, nz = face_normal(parsed, face)
    if nx == 0.0 and ny == 0.0 and nz == 0.0:
        return None
    # Sign-normalise: a reversed-wound copy of a face lies in the SAME plane.
    if (nx, ny, nz) < (-nx, -ny, -nz):
        nx, ny, nz = -nx, -ny, -nz
    v = parsed["vertices"][face["verts"][0] - 1]
    d = nx * v[0] + ny * v[1] + nz * v[2]
    q = max(tol, 1e-9)
    return (round(nx / q), round(ny / q), round(nz / q), round(d / q))


def _dominant_axis(parsed, face):
    """Index (0/1/2) of the face-normal component with the largest magnitude.

    This is the plane-normal axis. All faces sharing a `_plane_key` bucket share this
    axis, so it is computed once per bucket to pick a stable in-plane sweep axis.
    """
    nx, ny, nz = face_normal(parsed, face)
    n = (nx, ny, nz)
    return max(range(3), key=lambda k: abs(n[k]))


# Upper bound (m2) on the CONTAINED face's own area for the containment exclusion in
# `_xy_extent_overlaps` to treat a subset-footprint pair as an occluding end-cap rather
# than a genuine overlap. `office_room.obj` -- the model the exclusion exists to clear --
# has its largest genuine end-cap (a full-height wall-thickness return) at ~1.10 m2; 2.0 m2
# leaves comfortable margin above that while staying well below the smallest contained
# footprint (4 m2, a 2x2 m patch on a 10x8 m floor) this fix is required to flag as real
# z-fighting. See the CONTAINMENT EXCLUSION section of `_xy_extent_overlaps`'s docstring.
_END_CAP_MAX_AREA_M2 = 2.0


def _xy_extent_overlaps(parsed, fa, fb, tol=0.0):
    """3-D AABB overlap test: reports faces coplanar within `tol` AND with a genuine
    POSITIVE-AREA overlap in the plane -- not merely touching, and not one face's
    footprint simply resting fully inside the other's.

    On the plane-normal axis, the predicate keeps the existing `tol / 2` inflation per
    box, so two faces separated by exactly `tol` (combined slack from both boxes) still
    register as coplanar: that slack absorbs coplanarity tolerance and is redundant with
    (but harmless alongside) `_plane_key`'s own `round(d/tol)` quantisation.

    On the two IN-PLANE axes, boxes are NOT inflated by `tol`: real building geometry
    tiles edge-to-edge constantly (a floor slab's edge face meeting a wall's inner face
    along their shared line, adjoining wall panels, etc.), and Radiance does not z-fight
    on faces that share only an edge or a corner -- they do not overlap in the plane at
    all. Treating that contact as "overlap" is the false-positive this predicate must
    avoid, and it is exactly what the old uniform `tol/2` inflation caused: it turned a
    zero-extent touch on an in-plane axis into a manufactured `tol`-wide "overlap".

    Each in-plane axis is required to overlap by strictly more than `eps`, derived from
    `tol` (never hardcoded): faces separated or merely touching (interval extent <= eps)
    are excluded, while faces genuinely stacked on top of each other (interval extent
    spanning the box) are still caught. `eps` intentionally stays far below `tol` itself
    -- it only needs to absorb floating-point slop from vertex coordinates, not the
    caller's coincidence tolerance.

    CONTAINMENT EXCLUSION: real box-modelled solids constantly produce a second, subtler
    false positive that plain "overlap > eps" does not catch -- a smaller solid's end-cap
    (a wall's own thickness cap at a corner, a table leg's bottom face, a window frame's
    mitred corner) resting inside, or flush against the inside edge of, a larger coplanar
    surface's footprint (the floor slab, the adjoining wall's full-depth face). That
    smaller face's own solid body permanently occludes the larger surface at every point
    of the overlap -- no ray can ever reach the larger surface there without first
    passing through the smaller solid, which is impossible for opaque geometry -- so it
    is never actually ray-visible ambiguity. This holds whether or not the smaller face
    happens to share one of its edges flush with the larger face's boundary (a wall
    sitting flush with the floor's own edge is exactly as occluded as one set back from
    it), so containment here allows a flush-shared edge on either side, not only a
    strict interior margin.

    That occlusion argument only holds for an end-cap-SIZED contained face: a table leg's
    bottom, a wall's thickness return, a frame's mitred corner are all small in absolute
    terms, however large the surface they rest inside. A pure bounding-box subset test
    has no such size discipline -- it fires identically for a 5 cm leg cap on a 30 m2
    floor and for a 2x2 m patch resting inside a 10x8 m floor, or a duplicate wall
    reproduced 10 mm smaller than the original on all sides. The latter two are genuine
    z-fighting: nothing about "one footprint sits inside the other" makes a multi-square-
    metre surface an occluding solid rather than a duplicate. So containment is additionally
    gated on absolute size: the CONTAINED face's own area must be at or below
    `_END_CAP_MAX_AREA_M2`, a generous but finite bound on how large a real end-cap gets in
    practice. `office_room.obj` (the model this exclusion was written to clear) has its
    largest genuine end-cap at ~1.10 m2 (a full-height wall-thickness return); the bound is
    set well above that and well below the 4 m2 patch this fix is required to catch, so it
    separates the two classes with margin on both sides rather than splitting them by
    ratio (which cannot: the fixture's worst-case contained/container ratio, ~7.5%, is
    already larger than the 2x2-in-10x8 case's 5%, so ratio alone would flag the wrong one).

    What "not swallow" must still cover is a true duplicate or a genuine partial (crossing)
    overlap, where neither face's extent is a subset of the other's. The two are told apart
    by equality: if one face's in-plane interval is a (flush-inclusive) SUBSET of the
    other's on some in-plane axis, and the two intervals are not equal on that axis, the
    pair is a candidate rest/corner junction (subject to the size gate above). Two identical
    (or reversed-wound) duplicate faces have EQUAL extents on BOTH in-plane axes --
    subset-but-not-equal never fires for them on either axis -- and a genuine crossing
    overlap (neither contains the other) is untouched, since neither axis satisfies the
    subset test there either.
    """
    half = tol / 2.0
    eps = max(tol * 1e-6, 1e-12)

    def box(f):
        pts = [parsed["vertices"][i - 1] for i in f["verts"]]
        return [(min(p[k] for p in pts), max(p[k] for p in pts)) for k in range(3)]
    ba, bb = box(fa), box(fb)
    axis = _dominant_axis(parsed, fa)

    def equal_ish(a, b):
        return abs(a[0] - b[0]) <= eps and abs(a[1] - b[1]) <= eps

    def subset_ish(inner, outer):
        return inner[0] >= outer[0] - eps and inner[1] <= outer[1] + eps

    contained_area = min(face_area(parsed, fa), face_area(parsed, fb))
    size_gated = contained_area <= _END_CAP_MAX_AREA_M2

    for k in range(3):
        if k == axis:
            lo = max(ba[k][0] - half, bb[k][0] - half)
            hi = min(ba[k][1] + half, bb[k][1] + half)
            if lo > hi:
                return False
        else:
            lo = max(ba[k][0], bb[k][0])
            hi = min(ba[k][1], bb[k][1])
            if hi - lo <= eps:
                return False
            if size_gated and not equal_ish(ba[k], bb[k]) and (
                    subset_ish(ba[k], bb[k]) or subset_ish(bb[k], ba[k])):
                return False
    return True


def check_coincident_surfaces(parsed, *, tol=0.001):
    """Faces coplanar within `tol` AND with a genuine POSITIVE-AREA overlap in the plane
    (spec: COINCIDENT_SURFACES).

    The coincidence predicate is strict about coplanarity (raising `tol` widens the
    coplanarity band) but requires actual in-plane overlap, not mere contact: faces that
    only share an edge or a corner -- or one whose footprint rests entirely inside
    another's, a wall/frame/furniture end-cap flush against a floor or an adjoining
    wall -- tile the plane edge-to-edge and cannot z-fight, however real building
    geometry is full of exactly these junctions. See `_xy_extent_overlaps` for the
    overlap and containment tests.

    Radiance resolves a ray hitting two coplanar surfaces non-deterministically, so the run
    completes with speckled output and illuminance that drifts between runs.
    """
    by_plane = {}
    for f in parsed["faces"]:
        if not _face_is_finite(parsed, f):
            continue                      # reported once by check_finite_coordinates
        if face_area(parsed, f) <= 0.0:
            continue
        key = _plane_key(parsed, f, tol)
        if key is not None:
            by_plane.setdefault(key, []).append(f)
            # Also register in the NEXT offset bucket. `_plane_key` quantises the plane offset by
            # `tol`, so a pair separated by almost exactly `tol` can straddle a bucket edge and
            # never be compared -- a real z-fight then reads as clean. (Exact `tol/2` rounds to the
            # lower bucket, but a float hair over it rounds up, so whether the defect is caught
            # would otherwise depend on unit-conversion round-off.) Buckets hold references, and
            # pairs are de-duplicated by face identity below, so this cannot double-count.
            by_plane.setdefault((key[0], key[1], key[2], key[3] + 1), []).append(f)

    # A face is registered in two offset buckets (see above), so the same pair can be found
    # twice. Count each unordered pair once, keyed on face identity.
    seen_pairs, groups = set(), set()
    for faces in by_plane.values():
        if len(faces) < 2:
            continue
        # Invariant: all faces in a bucket share the same quantised normal (part of the
        # _plane_key), so they share one dominant (normal) axis. Compute it once from
        # faces[0]; the two IN-PLANE axes are both eligible to sweep on, but which one
        # actually prunes anything depends on the data -- a tessellated floor tiled along X
        # (each tile full-height in Y) is only prunable by sweeping X, and vice versa. Of the
        # two, sweep on whichever axis has the LARGER combined extent across every face in
        # the bucket: a full-width-in-X batch of strips varies in Y, so its Y-spread exceeds
        # its X-spread, and sweeping Y (not the arbitrary "other" axis) is what actually
        # separates the strips into non-overlapping intervals. Sorting by that axis's
        # minimum and stopping each inner scan once a face's minimum passes the current
        # face's maximum turns the common case (many disjoint coplanar faces) near-linear
        # instead of full O(n^2) pairwise, while still comparing every pair that could
        # plausibly overlap (genuinely stacked/clustered geometry keeps its worst-case
        # O(n^2), which no single-axis sweep can avoid).
        axis = _dominant_axis(parsed, faces[0])
        in_plane_axes = [k for k in range(3) if k != axis]
        half = tol / 2.0

        def _face_bounds(f, k):
            pts = [parsed["vertices"][i - 1] for i in f["verts"]]
            return (min(p[k] for p in pts), max(p[k] for p in pts))

        def _bucket_spread(k):
            bounds = [_face_bounds(f, k) for f in faces]
            return max(b[1] for b in bounds) - min(b[0] for b in bounds)

        spreads = [_bucket_spread(k) for k in in_plane_axes]
        sweep_axis = in_plane_axes[0] if spreads[0] >= spreads[1] else in_plane_axes[1]

        def extent(f):
            # Inflated by `half`: the sweep is only a cheap necessary pre-filter, so it
            # must stay a superset of what the authoritative test in
            # `_xy_extent_overlaps` would accept. That test no longer inflates in-plane
            # axes (touching must score zero overlap there), so this `half` inflation is
            # now strictly looser than necessary -- which is exactly what a pre-filter
            # is for: it may over-admit candidate pairs, it must never under-admit one.
            lo, hi = _face_bounds(f, sweep_axis)
            return (lo - half, hi + half)

        # Prune against face i's OWN end, not a running maximum over everything scanned
        # since i: `ordered` is sorted by interval start, so once extents[j][0] exceeds
        # extents[i][1], every later j also starts beyond i's end (starts are
        # non-decreasing) and cannot overlap i on this axis either -- the break is sound.
        # A running maximum instead grows monotonically as the inner loop advances, so once
        # any face chains past i's own end it can never fall back below a later j's start:
        # the break then never fires and the scan degrades to full O(n^2).
        ordered = sorted(faces, key=lambda f: extent(f)[0])
        extents = [extent(f) for f in ordered]
        for i in range(len(ordered)):
            i_end = extents[i][1]
            for j in range(i + 1, len(ordered)):
                if extents[j][0] > i_end:
                    break
                if _xy_extent_overlaps(parsed, ordered[i], ordered[j], tol):
                    a, b = id(ordered[i]), id(ordered[j])
                    seen_pairs.add((a, b) if a < b else (b, a))
                    groups.add(ordered[i]["group"])
                    groups.add(ordered[j]["group"])
    pairs = len(seen_pairs)
    if not pairs:
        return []
    return [finding(
        "COINCIDENT_SURFACES", "error", "geometry",
        f"{pairs} face pair(s) are coplanar within {tol * 1000:.3g} mm and overlap",
        subjects=sorted(groups),
        detail={"pairs": pairs, "tolerance_m": tol},
        fix=("Delete the duplicated surface, or offset one by more than "
             f"{tol * 1000:.3g} mm. Radiance selects between coplanar surfaces "
             "non-deterministically per ray, so results drift between runs."))]


def check_duplicate_faces(parsed):
    """Faces with identical vertex sets (spec: DUPLICATE_FACES).

    A doubled surface doubles its group's area, which silently corrupts every area-weighted
    quantity: aperture areas, ground-albedo weighting, and glazing_wall's dominant-facade
    pick -- which can place every photosensor against the wrong wall.
    """
    seen, dupes, groups = set(), 0, set()
    for f in parsed["faces"]:
        # frozenset: a reversed-wound copy is the same surface. Accepted limitation: this
        # also collapses vertex order entirely, so a self-intersecting "bowtie" reordering
        # of the same vertices (`f 1 2 3 4` vs `f 1 3 2 4`) reads as a duplicate too --
        # exporters essentially never emit that degenerate shape, and Radiance would
        # mishandle such a face regardless.
        key = frozenset(f["verts"])
        if len(key) < 3:
            continue
        if key in seen:
            dupes += 1
            groups.add(f["group"])
        else:
            seen.add(key)
    if not dupes:
        return []
    return [finding(
        "DUPLICATE_FACES", "warning", "geometry",
        f"{dupes} face(s) duplicate another face's vertex set",
        subjects=sorted(groups), detail={"duplicates": dupes},
        fix=("Delete the duplicated faces. A doubled surface doubles its group's area and "
             "silently biases aperture areas, ground albedo and facade selection."))]


def check_non_planar_faces(parsed, *, tol=0.005):
    """Polygons whose vertices do not lie in one plane (spec: NON_PLANAR_FACE).

    face_normal uses Newell's method, which returns an area-weighted average for a
    non-planar polygon without complaint; Radiance `polygon` requires planarity.

    Deviation is the peak-to-peak spread of the signed projections onto the
    normal (`max - min`), the true out-of-plane thickness of the polygon.
    That fix -- max-abs-deviation replaced by peak-to-peak spread -- is what
    makes the result invariant to OBJ face-vertex order (exporter-arbitrary,
    so the reported deviation must not depend on it). The reference point the
    projections are measured from (the face centroid, below) is inert to
    that invariance: peak-to-peak spread is translation-invariant by
    construction, so substituting any other anchor (e.g. `verts[0]`) leaves
    the result unchanged.
    """
    worst, count, groups = 0.0, 0, set()
    for f in parsed["faces"]:
        verts = f["verts"]
        if len(verts) < 4:
            continue                      # a triangle is planar by construction
        if not _face_is_finite(parsed, f):
            continue                      # reported once by check_finite_coordinates
        nx, ny, nz = face_normal(parsed, f)
        if (nx, ny, nz) == (0.0, 0.0, 0.0):
            continue
        pts = [parsed["vertices"][i - 1] for i in verts]
        n = len(pts)
        cx = sum(p[0] for p in pts) / n
        cy = sum(p[1] for p in pts) / n
        cz = sum(p[2] for p in pts) / n
        signed = [nx * (p[0] - cx) + ny * (p[1] - cy) + nz * (p[2] - cz) for p in pts]
        dev = max(signed) - min(signed)
        if dev > tol:
            count += 1
            groups.add(f["group"])
            worst = max(worst, dev)
    if not count:
        return []
    return [finding(
        "NON_PLANAR_FACE", "warning", "geometry",
        f"{count} polygon(s) deviate from planar by up to {worst * 1000:.1f} mm",
        subjects=sorted(groups),
        detail={"faces": count, "worst_deviation_m": round(worst, 6), "tolerance_m": tol},
        fix=("Triangulate the offending polygons on export. Radiance `polygon` requires "
             "planar vertices; a warped quad gets undefined shading."))]


def _face_centroid(parsed, face):
    pts = [parsed["vertices"][i - 1] for i in face["verts"]]
    n = len(pts)
    return (sum(p[0] for p in pts) / n,
            sum(p[1] for p in pts) / n,
            sum(p[2] for p in pts) / n)


def _on_segment(x, y, x0, y0, x1, y1, eps):
    """True if (x, y) lies within `eps` of the segment (x0, y0)-(x1, y1)."""
    dx, dy = x1 - x0, y1 - y0
    seg_len2 = dx * dx + dy * dy
    if seg_len2 == 0.0:
        # Degenerate segment: just a point.
        return (x - x0) ** 2 + (y - y0) ** 2 <= eps * eps
    t = ((x - x0) * dx + (y - y0) * dy) / seg_len2
    t = max(0.0, min(1.0, t))
    px, py = x0 + t * dx, y0 + t * dy
    return (x - px) ** 2 + (y - py) ** 2 <= eps * eps


def _point_in_polygon_3d(parsed, face, pt, tol=0.0):
    """Ray-crossing test for `pt` inside `face`, projected onto the face's dominant axis
    plane so the 2-D test is well conditioned.

    A point within `tol` of any polygon edge is treated as on-the-boundary and reported
    NOT inside, checked before the ray-crossing loop. Without this, the standard half-open
    ray-crossing test is asymmetric on ties: a point sitting exactly on the bottom/left
    edges of a rectangle crosses as inside, the top/right edges as outside. For an
    `error`-severity caller that must bias a boundary tie toward NOT reporting (a missed
    defect is recoverable; a false error on correct geometry is not), that asymmetry is
    unsafe, so it is resolved uniformly here rather than left to fall out of the scan.
    """
    nx, ny, nz = face_normal(parsed, face)
    ax = max(range(3), key=lambda k: abs((nx, ny, nz)[k]))
    u, v = [k for k in range(3) if k != ax]
    poly = [parsed["vertices"][i - 1] for i in face["verts"]]
    x, y = pt[u], pt[v]
    n = len(poly)
    if tol > 0.0:
        for i in range(n):
            x0, y0 = poly[i][u], poly[i][v]
            x1, y1 = poly[(i + 1) % n][u], poly[(i + 1) % n][v]
            if _on_segment(x, y, x0, y0, x1, y1, tol):
                return False
    inside = False
    for i in range(n):
        x0, y0 = poly[i][u], poly[i][v]
        x1, y1 = poly[(i + 1) % n][u], poly[(i + 1) % n][v]
        if (y0 > y) != (y1 > y):
            xint = x0 + (y - y0) * (x1 - x0) / ((y1 - y0) or 1e-30)
            if x < xint:
                inside = not inside
    return inside


def check_window_without_opening(parsed, material_map, *, tol=0.001):
    """Glazing sitting inside an unbroken opaque face in the same plane.

    Radiance traces the opaque surface, so the room goes dark (or nearly dark, if the wall
    sits a fraction of a millimetre proud) while the run completes and reports a plausible
    low daylight autonomy.

    This is a CENTROID probe: only the glazing face's centroid is tested against the
    opaque faces sharing its plane, not the glazing outline as a whole. A window that only
    partially overlaps an opaque face (centroid clear of the opaque face, but part of the
    glazing still covered by it) is therefore missed. That is deliberate: the miss
    direction is safe for an `error`-severity check (a missed defect is recoverable; a
    false error on correct geometry is not), and this check targets the common,
    unambiguous defect -- a window exporter forgot to cut the opening -- not partial-clip
    geometry, which would need full polygon clipping for a check this narrowly scoped.
    """
    from hcl_radiance.geometry_import import _context_groups, _glass_groups
    glass = _glass_groups(material_map)
    if not glass:
        return []
    ctx = _context_groups(material_map)
    opaque = [f for f in parsed["faces"]
              if f["group"] not in glass and f["group"] not in ctx
              and _face_is_finite(parsed, f) and face_area(parsed, f) > 0.0]

    by_plane = {}
    for of in opaque:
        key = _plane_key(parsed, of, tol)
        if key is not None:
            by_plane.setdefault(key, []).append(of)

    blocked, groups = 0, set()
    for gf in parsed["faces"]:
        if gf["group"] not in glass or not _face_is_finite(parsed, gf) or face_area(parsed, gf) <= 0.0:
            continue
        gkey = _plane_key(parsed, gf, tol)
        if gkey is None:
            continue
        c = _face_centroid(parsed, gf)
        for of in by_plane.get(gkey, []):
            if _point_in_polygon_3d(parsed, of, c, tol):
                blocked += 1
                groups.add(gf["group"])
                break
    if not blocked:
        return []
    return [finding(
        "WINDOW_WITHOUT_OPENING", "error", "geometry",
        f"{blocked} glazing face(s) sit inside an unbroken opaque surface in the same plane",
        subjects=sorted(groups), detail={"blocked_faces": blocked},
        fix=("Cut the window opening out of the wall surface. Radiance traces the opaque "
             "face, so the room renders dark while the run still completes."))]


def check_mesh_quality(parsed):
    """Re-emit the existing mesh_quality metrics as coded findings."""
    from hcl_radiance.geometry_obj import mesh_quality
    mq = mesh_quality(parsed)
    out = []
    if mq["degenerate_faces"]:
        out.append(finding(
            "DEGENERATE_FACES", "warning", "geometry",
            f"{mq['degenerate_faces']} face(s) have fewer than 3 unique vertices",
            subjects=[mq["worst_group"]] if mq["worst_group"] else [],
            detail={"count": mq["degenerate_faces"], "worst_group": mq["worst_group"]},
            fix="Remove the degenerate faces; they contribute no surface to the trace."))
    if mq["non_manifold_edges"]:
        out.append(finding(
            "NON_MANIFOLD_EDGES", "warning", "geometry",
            f"{mq['non_manifold_edges']} edge(s) are shared by more than 2 faces",
            detail={"count": mq["non_manifold_edges"]},
            fix="Split the non-manifold junctions; T-junctions leak light in some engines."))
    if mq["missing_normals"]:
        out.append(finding(
            "NO_VERTEX_NORMALS", "warning", "geometry",
            "the OBJ declares no vertex normals (vn); orientation relies on winding",
            detail={"missing_normals": mq["missing_normals"]},
            fix=("Export with normals. Radiance polygons are two-sided so this does not "
                 "change traced physics, but it removes the only independent check on "
                 "face orientation.")))
    return out


def check_enclosure(parsed, material_map):
    """Boundary edges (used by exactly ONE face) on non-context groups.

    mesh_quality counts only edges used by MORE than two faces, so an open room -- one
    that leaks light -- is invisible to it. Warning, not error: top-lit test cases,
    single-facade models and ground planes legitimately have open edges.
    """
    from hcl_radiance.geometry_import import _context_groups
    ctx = _context_groups(material_map)
    edge_use, groups = {}, {}
    for f in parsed["faces"]:
        if f["group"] in ctx:
            continue
        verts = f["verts"]
        n = len(verts)
        # Build per-face edge set to dedupe edges within a single face and skip self-loops.
        face_edges = set()
        for i in range(n):
            a, b = verts[i], verts[(i + 1) % n]
            # Skip self-loop edges (e.g., from f 1 2 3 3 producing a spurious (3, 3) edge).
            if a == b:
                continue
            e = (min(a, b), max(a, b))
            face_edges.add(e)
        for e in face_edges:
            edge_use[e] = edge_use.get(e, 0) + 1
            groups.setdefault(e, set()).add(f["group"])
    boundary = [e for e, c in edge_use.items() if c == 1]
    if not boundary:
        return []
    subjects = sorted({g for e in boundary for g in groups[e]})
    return [finding(
        "NOT_ENCLOSED", "warning", "geometry",
        f"{len(boundary)} boundary edge(s) belong to only one face; the room is not closed",
        subjects=subjects, detail={"boundary_edges": len(boundary)},
        fix=("Close the enclosure, or type exterior/site geometry as `type:\"context\"` so "
             "it is excluded. An open room leaks light and inflates daylight metrics."))]


def check_finite_coordinates(parsed):
    """Vertices whose coordinates are not finite (NaN or +/-inf) (spec: NON_FINITE_COORDINATES).

    A plausible exporter defect, not a contrived one: `1e400` parses as +inf in both Python
    and the OBJ spec's plain-text float grammar, so a single overflowing coordinate in an
    otherwise well-formed OBJ reaches this check. Radiance cannot trace a NaN or infinite
    vertex, so this is one of the few findings that changes traced physics outright and is
    therefore `error`-severity -- but the health report itself must still return normally
    (never raise): every OTHER geometric check skips faces that reference a non-finite
    vertex (see `_face_is_finite`) rather than crashing on them, so this is the one place
    the defect is actually surfaced.
    """
    bad = sum(1 for v in parsed["vertices"] if not _is_finite_vertex(v))
    if not bad:
        return []
    return [finding(
        "NON_FINITE_COORDINATES", "error", "geometry",
        f"{bad} vertex/vertices have a non-finite coordinate (NaN or infinite)",
        detail={"vertices": bad},
        fix=("Repair or re-export the model: locate the offending `v` line(s) and correct "
             "the coordinate. Radiance cannot trace a NaN or infinite vertex; every face "
             "referencing one is skipped by the other checks rather than traced."))]


def check_no_floor_group(parsed, material_map):
    """No group resolves to `type:"floor"` (spec: NO_FLOOR_GROUP).

    Several derived quantities -- floor-top height, the interior reference used to orient
    "inward" from the glazing, sensor and observer heights -- key off the floor group when
    one is typed, and fall back to an ESTIMATE (the lowest horizontal face, or the centroid
    of all non-context geometry) when none is. That estimate is usually right but is a
    guess, not a fact read off the model, so this is INFERENTIAL and capped at `warning`.
    """
    from hcl_radiance.geometry_import import _floor_groups
    if _floor_groups(material_map, None):
        return []
    return [finding(
        "NO_FLOOR_GROUP", "warning", "geometry",
        "no group is typed type:\"floor\"",
        detail={},
        fix=("Type the floor group as `type:\"floor\"` in the material map. Without it, "
             "derived heights and the interior reference (used to orient sensor and gaze "
             "direction inward) are estimated from the geometry instead of read directly."))]


_TIER1_SKIPPED = (
    ("materials", "material checks land in tier 2"),
    ("apertures", "aperture and shading checks land in tier 3"),
    ("conventions", "winding and north checks land in tier 3"),
)


def _scaled_to_metres(parsed, scale):
    """`parsed` with every vertex multiplied by `scale`, so all checks work in METRES.

    Every tolerance in this module is an absolute physical length or area (`tol=0.001` = 1 mm,
    `_END_CAP_MAX_AREA_M2` = 2 m2). Comparing those against raw model units breaks BOTH ways: a
    real 0.5 mm z-fight in a millimetre model reads as a 0.5-unit separation and is missed, while
    a 1x1 m end-cap reads as 1e6 units2, blows past the containment gate, and a VALID model is
    hard-failed with a spurious COINCIDENT_SURFACES (which `strict=True` then raises on).

    Scale only: the checks are rotation-invariant, so up_axis/north never affect a finding.
    Returns `parsed` unchanged when scale is 1.0 so the metre path stays byte-identical.
    """
    if scale == 1.0:
        return parsed
    s = float(scale)
    return {**parsed, "vertices": [(v[0] * s, v[1] * s, v[2] * s) for v in parsed["vertices"]]}


def check_geometry_health(parsed, material_map, *, sensors=None, photosensors=None,
                          electric_lights=None, scale=1.0):
    """Run every implemented check and assemble the report (spec: tier 1).

    Categories with no checks implemented yet are reported in `skipped`, never silently
    omitted -- an absent category must not read as "nothing wrong there".

    `scale` converts model units to metres (as `import_geometry`'s `units` does). Every tolerance
    here is absolute metres/m2, so callers MUST pass the model's scale or the checks silently
    change meaning with the unit system -- see `_scaled_to_metres`.
    """
    parsed = _scaled_to_metres(parsed, scale)
    findings = []
    findings += check_finite_coordinates(parsed)
    findings += check_coincident_surfaces(parsed)
    findings += check_duplicate_faces(parsed)
    findings += check_non_planar_faces(parsed)
    findings += check_window_without_opening(parsed, material_map)
    findings += check_mesh_quality(parsed)
    findings += check_enclosure(parsed, material_map)
    findings += check_no_floor_group(parsed, material_map)

    skipped = [{"category": c, "reason": r} for c, r in _TIER1_SKIPPED]
    if sensors is None and photosensors is None:
        skipped.append({"category": "sensors",
                        "reason": "no sensor or photosensor block supplied"})
    else:
        skipped.append({"category": "sensors", "reason": "sensor checks land in tier 3"})
    if electric_lights is None:
        skipped.append({"category": "luminaires",
                        "reason": "luminaire checks land in tier 2"})
    else:
        skipped.append({"category": "luminaires",
                        "reason": "electric_lights supplied; luminaire checks land in tier 2"})

    confidence = {
        "interior_reference": None,
        "note": ("interior-reference confidence (downgrades findings on a non-convex room "
                 "plan) is not computed in this tier; it feeds normal-orientation and "
                 "convention checks, which land in tier 3"),
    }
    return build_report(findings, checked=["geometry"], skipped=skipped, confidence=confidence)
