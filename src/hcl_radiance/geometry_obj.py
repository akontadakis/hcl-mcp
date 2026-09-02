"""Rich OBJ/MTL parser for hcl_radiance v2 geometry features.

This module is purely additive — it does NOT modify geometry_import.py.
It retains full vertex/face/point geometry for auto-sensors, aperture orientation,
luminaire markers, and mesh quality analysis.

Global constraints:
- Python stdlib only (math is used).
- OBJ indices are 1-based; kept 1-based in faces/points; convert only when indexing
  into the vertices list.
- parse_mtl is a HINT source only — never a material value.
"""

import math


def _resolve_index(idx: int, n_verts: int) -> int:
    """Resolve an OBJ vertex reference to a positive 1-based index.

    OBJ permits negative (relative) indices: -1 refers to the most recently defined vertex,
    -2 the one before it, and so on. Positive indices are returned unchanged. Raises ValueError
    for a reference that resolves outside the vertices defined so far (incl. 0, the invalid
    index) so callers get a clear error instead of an opaque IndexError downstream.
    """
    resolved = idx if idx > 0 else n_verts + 1 + idx
    if not 1 <= resolved <= n_verts:
        raise ValueError(
            f"OBJ vertex reference {idx} is out of range (vertices defined so far: {n_verts})")
    return resolved


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

def parse_obj(text: str) -> dict:
    """Parse OBJ text and return a dict with full geometry.

    Returns:
        groups: sorted unique effective identifiers (usemtl name > g name > 'white').
        qualifier: {group: 'Material'|'Group'|'white'} — how the group was discovered.
        vertices: list of (x, y, z) float triples, in file order (1-based externally).
        faces: list of {'group': str, 'verts': [int, ...]} (1-based vertex indices).
        n_faces: len(faces).
        n_missing_normals: count of f-lines where NO vert token references a normal.
        points: list of int vertex indices from p-lines (1-based).
        point_markers: list of {'vertex': int, 'group': str|None} tagged with the
            active g group (NOT usemtl) at point-emit time.
    """
    vertices = []
    faces = []
    points = []
    point_markers = []
    qualifier = {}  # group name → qualifier string

    active_g = None
    active_usemtl = None
    active_o = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue

        parts = line.split()
        keyword = parts[0]

        if keyword == 'v':
            vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))

        elif keyword == 'o':
            active_o = parts[1] if len(parts) > 1 else None

        elif keyword == 'g':
            # 'g name' sets group; bare 'g' clears it.
            # usemtl stays active across g lines — real OBJ/obj2rad semantics.
            # The spec allows several names ('g grp1 grp2'); obj2rad registers all of them and
            # paints the face with the LAST, so take parts[-1] to match what Radiance actually
            # traces. Taking parts[1] instead made the aperture report and every glazing-derived
            # check (gaze direction, facade pick) describe a different surface than the one the
            # renderer shaded -- e.g. 'g Glass Panel' reported an 18 m2 south window while
            # Radiance traced it as opaque wall.
            active_g = parts[-1] if len(parts) > 1 else None

        elif keyword == 'usemtl':
            active_usemtl = parts[1] if len(parts) > 1 else None

        elif keyword == 'f':
            tokens = parts[1:]
            # Effective group/qualifier
            if active_usemtl is not None:
                eff_name = active_usemtl
                qual = "Material"
            elif active_g is not None:
                eff_name = active_g
                qual = "Group"
            else:
                eff_name = "white"
                qual = "white"

            # Record qualifier only on first encounter (setdefault semantics).
            qualifier.setdefault(eff_name, qual)

            # Vertex indices (1-based); resolve negative (relative) refs against verts so far.
            verts = [_resolve_index(int(tok.split('/')[0]), len(vertices)) for tok in tokens]

            # Missing-normal detection: a vert has a normal iff the token has the
            # form a//c or a/b/c with a non-empty third field.
            face_has_any_normal = False
            for tok in tokens:
                sub = tok.split('/')
                if len(sub) >= 3 and sub[2] != '':
                    face_has_any_normal = True
                    break

            # Object name: 'o' takes precedence over 'g'.
            obj_name = active_o if active_o is not None else active_g

            faces.append({
                'group': eff_name,
                'object': obj_name,
                'verts': verts,
                '_has_normal': face_has_any_normal,  # internal; not part of the spec
            })

        elif keyword == 'p':
            tokens = parts[1:]
            for tok in tokens:
                vidx = _resolve_index(int(tok.split('/')[0]), len(vertices))
                points.append(vidx)
                point_markers.append({'vertex': vidx, 'group': active_g})

    # Strip internal flag from faces (keep only public keys).
    n_missing_normals = sum(1 for f in faces if not f['_has_normal'])
    clean_faces = [{'group': f['group'], 'object': f['object'], 'verts': f['verts']}
                   for f in faces]

    groups = sorted(qualifier.keys())

    return {
        'groups': groups,
        'qualifier': qualifier,
        'vertices': vertices,
        'faces': clean_faces,
        'n_faces': len(clean_faces),
        'n_missing_normals': n_missing_normals,
        'points': points,
        'point_markers': point_markers,
    }


# ---------------------------------------------------------------------------
# Bounding box
# ---------------------------------------------------------------------------

def bbox(parsed: dict) -> tuple:
    """Return ((minx, miny, minz), (maxx, maxy, maxz)) over all vertices.

    Returns ((0,0,0),(0,0,0)) when there are no vertices.
    """
    verts = parsed['vertices']
    if not verts:
        return ((0, 0, 0), (0, 0, 0))
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    return ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))


# ---------------------------------------------------------------------------
# Mesh quality
# ---------------------------------------------------------------------------

def mesh_quality(parsed: dict) -> dict:
    """Return mesh quality metrics.

    Returns:
        degenerate_faces: faces with fewer than 3 unique vertex indices.
        missing_normals: parsed['n_missing_normals'].
        non_manifold_edges: edges used by more than 2 faces.
        worst_group: face group with the most degenerate faces, else None.
    """
    degenerate_count = {}  # group -> count of degenerate faces
    edge_use = {}  # (min_idx, max_idx) -> count

    for face in parsed['faces']:
        verts = face['verts']
        unique_verts = set(verts)
        if len(unique_verts) < 3:
            g = face['group']
            degenerate_count[g] = degenerate_count.get(g, 0) + 1

        # Build edge-use counts (undirected, deduped per face).
        n = len(verts)
        face_edges = set()
        for i in range(n):
            e = (min(verts[i], verts[(i + 1) % n]), max(verts[i], verts[(i + 1) % n]))
            face_edges.add(e)
        for e in face_edges:
            edge_use[e] = edge_use.get(e, 0) + 1

    degenerate_faces = sum(degenerate_count.values())
    non_manifold_edges = sum(1 for c in edge_use.values() if c > 2)

    if degenerate_count:
        worst_group = max(degenerate_count, key=lambda g: degenerate_count[g])
    else:
        worst_group = None

    return {
        'degenerate_faces': degenerate_faces,
        'missing_normals': parsed['n_missing_normals'],
        'non_manifold_edges': non_manifold_edges,
        'worst_group': worst_group,
    }


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _vert(parsed: dict, idx: int) -> tuple:
    """Return (x, y, z) for 1-based vertex index idx."""
    return parsed['vertices'][idx - 1]


def _cross(a: tuple, b: tuple) -> tuple:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def face_normal(parsed: dict, face: dict) -> tuple:
    """Return unit face normal via Newell's method (model coordinates)."""
    verts = [_vert(parsed, i) for i in face['verts']]
    n = len(verts)
    cx = cy = cz = 0.0
    for i in range(n):
        v1 = verts[i]
        v2 = verts[(i + 1) % n]
        c = _cross(v1, v2)
        cx += c[0]
        cy += c[1]
        cz += c[2]
    mag = math.sqrt(cx * cx + cy * cy + cz * cz)
    if mag == 0.0:
        return (0.0, 0.0, 0.0)
    return (cx / mag, cy / mag, cz / mag)


def face_area(parsed: dict, face: dict) -> float:
    """Return polygon area (m²) via the cross-product / shoelace-in-3D magnitude.

    area = 0.5 * |Σ vᵢ × vᵢ₊₁|  (Newell's method magnitude)
    """
    verts = [_vert(parsed, i) for i in face['verts']]
    n = len(verts)
    cx = cy = cz = 0.0
    for i in range(n):
        v1 = verts[i]
        v2 = verts[(i + 1) % n]
        c = _cross(v1, v2)
        cx += c[0]
        cy += c[1]
        cz += c[2]
    return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)


def horizontal_floor_faces(parsed: dict, floor_names) -> list:
    """Return faces whose group is in floor_names."""
    floor_set = set(floor_names)
    return [f for f in parsed['faces'] if f['group'] in floor_set]


def marker_positions(parsed: dict, group: str = None) -> list:
    """Return model-coordinate positions for point markers.

    If point_markers is non-empty:
        Select markers matching group (or all when group is None).
        Return their model coords.
        If that selection is empty AND group is not None, fall through to centroid.
    Else / fallback:
        If group is not None, return the centroid of the UNIQUE vertices of faces in that
        group (each vertex weighted once, matching object_centroid), or [] if no such faces.
    Return [] when nothing matches.
    """
    markers = parsed['point_markers']

    if markers:
        if group is None:
            selected = markers
        else:
            selected = [m for m in markers if m['group'] == group]

        if selected:
            return [_vert(parsed, m['vertex']) for m in selected]

        # selected is empty and group is not None → fall through to centroid
        if group is None:
            return []

    # Centroid fallback (reached when markers is empty, OR selection was empty with a group)
    if group is None:
        return []

    faces = [f for f in parsed['faces'] if f['group'] == group]
    if not faces:
        return []

    # ONE MARKER PER CONNECTED ISLAND, not one per group. Several fittings that share a usemtl
    # are disconnected meshes; collapsing them to a single group centroid put one emitter in the
    # middle of an empty ceiling at 1/N of the drawn load, silently. Faces of a single fitting
    # share vertices, so connectivity separates "four housings" from "one multi-face housing"
    # without requiring the caller to name materials a particular way.
    return [_centroid_of(parsed, vs) for vs in _vertex_islands(faces)]


def _vertex_islands(faces):
    """Group face-vertex sets into connected components by shared vertex index.

    Returns a list of vertex-index sets, ordered by first appearance so output is deterministic.
    """
    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    order = []
    for f in faces:
        vs = f['verts']
        for v in vs:
            if v not in parent:
                parent[v] = v
                order.append(v)
        for v in vs[1:]:
            union(vs[0], v)

    islands, seen = [], {}
    for v in order:
        r = find(v)
        if r not in seen:
            seen[r] = len(islands)
            islands.append(set())
        islands[seen[r]].add(v)
    return islands


def _centroid_of(parsed, vert_indices):
    """Mean of the UNIQUE vertices given, weighting each once regardless of face valence
    (matching object_centroid; a face-multiplicity-weighted mean would bias toward high-valence
    vertices on a triangulated mesh)."""
    coords = [_vert(parsed, i) for i in vert_indices]
    n = len(coords)
    return (sum(c[0] for c in coords) / n,
            sum(c[1] for c in coords) / n,
            sum(c[2] for c in coords) / n)


def object_centroid(parsed: dict, name: str, scale: float = 1.0, up_axis: str = "Z") -> tuple:
    """World-space (x,y,z) mean of vertices of faces whose 'object' == name.

    up_axis remap matches _to_world ('Y' -> -rx90); north is NOT applied here. Returns
    (0.0, 0.0, 0.0) when no face carries that object name.
    """
    idxs = {i for f in parsed['faces'] if f.get('object') == name for i in f['verts']}
    if not idxs:
        return (0.0, 0.0, 0.0)
    sx = sy = sz = 0.0
    for i in idxs:
        x, y, z = parsed['vertices'][i - 1]
        x, y, z = x * scale, y * scale, z * scale
        if str(up_axis).strip().upper() == "Y":
            x, y, z = x, -z, y
        sx += x; sy += y; sz += z
    n = len(idxs)
    return (sx / n, sy / n, sz / n)


# ---------------------------------------------------------------------------
# MTL parser (hint source only)
# ---------------------------------------------------------------------------

def parse_mtl(text: str) -> dict:
    """Parse MTL text and return {name: {'kd': [r,g,b]|None, 'map_kd': str|None}}.

    Parses ONLY: newmtl, Kd, map_Kd (case as written).
    This is a HINT source only — never a material reflectance value.
    """
    result = {}
    current = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue

        parts = line.split()
        keyword = parts[0]

        if keyword == 'newmtl':
            name = parts[1] if len(parts) > 1 else ''
            current = name
            result[current] = {'kd': None, 'map_kd': None}

        elif keyword == 'Kd' and current is not None:
            result[current]['kd'] = [float(parts[1]), float(parts[2]), float(parts[3])]

        elif keyword == 'map_Kd' and current is not None:
            # Value = last token
            result[current]['map_kd'] = parts[-1]

    return result


# ---------------------------------------------------------------------------
# MTL suggestions (hint layer, not material values)
# ---------------------------------------------------------------------------

def mtl_suggestions(mtl_map: dict, groups) -> dict:
    """Return {group: {'suggested_refl': float|None, 'map_kd': str|None}}.

    suggested_refl = round(mean(kd), 4) when kd is available, else None.
    Only groups present in mtl_map are included; others are skipped.
    """
    result = {}
    for g in groups:
        if g not in mtl_map:
            continue
        entry = mtl_map[g]
        kd = entry.get('kd')
        if kd is not None:
            suggested_refl = round(sum(kd) / 3.0, 4)
        else:
            suggested_refl = None
        result[g] = {
            'suggested_refl': suggested_refl,
            'map_kd': entry.get('map_kd'),
        }
    return result
