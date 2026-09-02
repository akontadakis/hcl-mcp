import os
import time

import pytest

from hcl_radiance.geometry_health import (
    GeometryHealthError, build_report, check_coincident_surfaces,
    check_duplicate_faces, check_enclosure, check_geometry_health, check_mesh_quality,
    check_non_planar_faces, check_window_without_opening, finding,
)
from hcl_radiance.geometry_obj import parse_obj


def test_finding_shape():
    f = finding("COINCIDENT_SURFACES", "error", "geometry", "2 pairs coplanar",
                subjects=["walls"], detail={"pairs": 2}, fix="Delete the duplicate.")
    assert f["code"] == "COINCIDENT_SURFACES"
    assert f["severity"] == "error"
    assert f["category"] == "geometry"
    assert f["subjects"] == ["walls"]
    assert f["detail"] == {"pairs": 2}
    assert f["fix"] == "Delete the duplicate."


def test_finding_requires_fix_on_error_and_warning():
    with pytest.raises(ValueError, match="fix"):
        finding("X", "error", "geometry", "m")
    with pytest.raises(ValueError, match="fix"):
        finding("X", "warning", "geometry", "m")
    # info needs no fix
    assert finding("X", "info", "geometry", "m")["fix"] is None


def test_finding_rejects_unknown_severity():
    with pytest.raises(ValueError, match="severity"):
        finding("X", "fatal", "geometry", "m", fix="f")


def test_report_orders_errors_first_and_counts():
    fs = [
        finding("C", "info", "geometry", "i"),
        finding("A", "error", "geometry", "e", fix="f"),
        finding("B", "warning", "geometry", "w", fix="f"),
    ]
    r = build_report(fs, checked=["geometry"])
    assert [f["code"] for f in r["findings"]] == ["A", "B", "C"]
    assert r["counts"] == {"error": 1, "warning": 1, "info": 1}
    assert r["ok"] is False
    assert r["checked"] == ["geometry"]
    assert r["skipped"] == []


def test_report_ok_when_no_errors():
    r = build_report([finding("B", "warning", "geometry", "w", fix="f")],
                     checked=["geometry"])
    assert r["ok"] is True
    assert r["counts"]["error"] == 0


def test_report_records_skipped_and_confidence():
    r = build_report([], checked=["geometry"],
                     skipped=[{"category": "sensors", "reason": "no sensor block supplied"}],
                     confidence={"interior_reference": 0.94})
    assert r["skipped"] == [{"category": "sensors", "reason": "no sensor block supplied"}]
    assert r["confidence"] == {"interior_reference": 0.94}


def test_health_error_carries_payload():
    r = build_report([finding("A", "error", "geometry", "e", fix="f")], checked=["geometry"])
    err = GeometryHealthError("2 error-severity findings", r)
    assert err.payload is r
    assert isinstance(err, ValueError)


def test_finding_copies_its_inputs():
    """Ensure detail and subjects dicts are copied defensively, not stored by reference."""
    # Test detail copying
    detail_tmpl = {"pairs": 1}
    f1 = finding("A", "info", "geometry", "m", detail=detail_tmpl)
    detail_tmpl["pairs"] = 99
    assert f1["detail"]["pairs"] == 1, "mutating caller's detail dict should not change finding"

    # Test subjects copying
    subjects_list = ["wall_1"]
    f2 = finding("B", "info", "geometry", "m", subjects=subjects_list)
    subjects_list.append("wall_2")
    assert f2["subjects"] == ["wall_1"], "mutating caller's subjects list should not change finding"


_TWO_COPLANAR = """\
v 0 0 0
v 2 0 0
v 2 2 0
v 0 2 0
g wall_a
f 1 2 3 4
g wall_b
f 1 2 3 4
"""

_OFFSET = """\
v 0 0 0
v 2 0 0
v 2 2 0
v 0 2 0
v 0 0 1
v 2 0 1
v 2 2 1
v 0 2 1
g wall_a
f 1 2 3 4
g wall_b
f 5 6 7 8
"""


def test_coincident_surfaces_detected():
    fs = check_coincident_surfaces(parse_obj(_TWO_COPLANAR))
    assert len(fs) == 1
    assert fs[0]["code"] == "COINCIDENT_SURFACES"
    assert fs[0]["severity"] == "error"
    assert fs[0]["fix"]
    assert set(fs[0]["subjects"]) == {"wall_a", "wall_b"}


def test_separated_surfaces_are_clean():
    assert check_coincident_surfaces(parse_obj(_OFFSET)) == []


def test_coincidence_tolerance_is_respected():
    obj = _OFFSET.replace("v 0 0 1", "v 0 0 0.0005").replace(
        "v 2 0 1", "v 2 0 0.0005").replace(
        "v 2 2 1", "v 2 2 0.0005").replace("v 0 2 1", "v 0 2 0.0005")
    assert len(check_coincident_surfaces(parse_obj(obj), tol=0.001)) == 1
    assert check_coincident_surfaces(parse_obj(obj), tol=0.0001) == []


def _stacked_pair_with_z_gap(gap_m):
    """Two coplanar (in-plane-identical footprint) 2x2 m squares, stacked `gap_m` metres
    apart on the plane-normal (z) axis -- a genuine overlap if the planes are treated as
    coincident, clean otherwise."""
    return f"""\
v 0 0 0
v 2 0 0
v 2 2 0
v 0 2 0
g wall_a
f 1 2 3 4
v 0 0 {gap_m}
v 2 0 {gap_m}
v 2 2 {gap_m}
v 0 2 {gap_m}
g wall_b
f 5 6 7 8
"""


def test_coincident_surfaces_default_tolerance_is_1mm_not_wider():
    """Pins check_coincident_surfaces' default tol=0.001 (1 mm). A 10 mm z-separation sits
    strictly between the correct default (1 mm) and a loosened default (20 mm): calling
    WITHOUT tol= must NOT flag it, so a widened default (that would treat 10 mm as
    coincident) fails this test."""
    obj = parse_obj(_stacked_pair_with_z_gap(0.01))
    assert check_coincident_surfaces(obj) == []
    # Sanity: the same separation IS flagged at a loosened 20 mm tolerance, confirming the
    # fixture actually straddles the two tolerance values rather than being clean outright.
    assert len(check_coincident_surfaces(obj, tol=0.02)) == 1


def _coplanar_pair_with_gap(gap_m, z=0.0):
    """Two coplanar 2x2 m squares in the z=`z` plane, side by side with an in-plane
    gap of `gap_m` metres between wall_a's right edge and wall_b's left edge."""
    return f"""\
v 0 0 {z}
v 2 0 {z}
v 2 2 {z}
v 0 2 {z}
g wall_a
f 1 2 3 4
v {2 + gap_m} 0 {z}
v {4 + gap_m} 0 {z}
v {4 + gap_m} 2 {z}
v {2 + gap_m} 2 {z}
g wall_b
f 5 6 7 8
"""


def test_inplane_gap_within_tolerance_is_no_longer_a_finding():
    """A genuine 0.5 mm in-plane GAP (the faces do not touch at all) is not an overlap.

    Behaviour change (2026-07-23, positive-area-overlap fix): this used to be 1 finding,
    because the old predicate inflated both boxes by `tol/2` on every axis, so any two
    coplanar faces within `tol` of each other -- touching, gapped, or overlapping --
    registered as "overlapping". That inflation is what made every abutting slab-edge/
    wall junction in a real building model (see `office_room.obj`) a false positive.
    Once inflation is removed from the in-plane axes so touching faces correctly score
    zero overlap, a 0.5 mm SEPARATION (no overlap at all, `hi - lo < 0`) cannot
    simultaneously be excluded as "not touching" and included as "near enough to risk
    z-fighting" -- the two requirements are mutually exclusive for one eps/threshold.
    Zero is the more defensible choice: two surfaces with a genuine gap, however small,
    do not physically z-fight (there is no coordinate any ray can hit on both), so
    reporting them at `error` severity would be exactly the kind of false positive this
    fix removes elsewhere. Proximity this tight is better caught by a lint-level,
    non-blocking check if ever wanted -- not by COINCIDENT_SURFACES.
    """
    obj = parse_obj(_coplanar_pair_with_gap(0.0005))
    assert check_coincident_surfaces(obj, tol=0.001) == []


def test_inplane_gap_beyond_tolerance_is_not_a_false_positive():
    """A genuine 1.5 mm in-plane gap under tol=1 mm exceeds tolerance: no finding.

    Regression for the AABB double-counting bug: inflating both boxes by the full
    `tol` on in-plane axes let gaps up to 2*tol register as overlapping.
    """
    for gap_mm in (1.5, 1.9, 2.1):
        obj = parse_obj(_coplanar_pair_with_gap(gap_mm / 1000.0))
        assert check_coincident_surfaces(obj, tol=0.001) == [], (
            f"{gap_mm} mm in-plane gap should not be reported at tol=1 mm")


def test_exact_edge_to_edge_abutment_is_clean():
    """Two coplanar faces sharing an edge exactly (zero gap) tile the plane; they do not
    overlap. This is the regression the positive-area-overlap fix targets directly --
    see `test_coincident_surfaces_office_room_fixture_is_clean` for the real-model case
    this stands in for. Formerly named `test_exact_coplanar_overlap_detected` and
    asserted 1 finding; renamed because "exact coplanar overlap" was never an accurate
    description of an edge-to-edge touch."""
    obj = parse_obj(_coplanar_pair_with_gap(0.0))
    assert check_coincident_surfaces(obj, tol=0.001) == []


def test_opposite_winding_coplanar_duplicate_detected():
    obj = """\
v 0 0 0
v 2 0 0
v 2 2 0
v 0 2 0
g wall_a
f 1 2 3 4
g wall_b
f 4 3 2 1
"""
    fs = check_coincident_surfaces(parse_obj(obj))
    assert len(fs) == 1
    assert set(fs[0]["subjects"]) == {"wall_a", "wall_b"}


def test_two_coplanar_windows_far_apart_are_clean():
    """Two windows in the same wall plane, 1.5 m apart: not coincident geometry."""
    obj = parse_obj(_coplanar_pair_with_gap(1.5))
    assert check_coincident_surfaces(obj) == []


def test_coplanar_faces_meeting_only_at_a_corner_are_clean():
    """Two coplanar squares that touch at a single point (a shared corner) do not
    overlap on either in-plane axis simultaneously -- zero-area contact, not a
    positive-area overlap."""
    obj = parse_obj("""\
v 0 0 0
v 2 0 0
v 2 2 0
v 0 2 0
g wall_a
f 1 2 3 4
v 2 2 0
v 4 2 0
v 4 4 0
v 2 4 0
g wall_b
f 5 6 7 8
""")
    assert check_coincident_surfaces(obj, tol=0.001) == []


def test_coplanar_faces_with_genuine_partial_overlap_detected():
    """Two coplanar squares that genuinely cross (x in [0,2] vs x in [1,3], same y-range)
    -- neither face's footprint is a subset of the other's -- must still be flagged."""
    obj = parse_obj("""\
v 0 0 0
v 2 0 0
v 2 2 0
v 0 2 0
g wall_a
f 1 2 3 4
v 1 0 0
v 3 0 0
v 3 2 0
v 1 2 0
g wall_b
f 5 6 7 8
""")
    fs = check_coincident_surfaces(obj, tol=0.001)
    assert len(fs) == 1
    assert set(fs[0]["subjects"]) == {"wall_a", "wall_b"}


def test_small_coplanar_patch_inside_large_floor_is_flagged():
    """CRITICAL-2 regression: a 2x2 m patch coplanar and fully inside a 10x8 m floor is
    genuine, unoccluded z-fighting -- not an end-cap. The floor's absolute area (80 m2)
    and the patch's (4 m2) both dwarf any real end-cap in office_room.obj (largest ~1.10
    m2), so the containment exclusion's size gate must NOT suppress this pair."""
    obj = parse_obj("""\
v 0 0 0
v 10 0 0
v 10 8 0
v 0 8 0
g floor
f 1 2 3 4
v 4 3 0
v 6 3 0
v 6 5 0
v 4 5 0
g patch
f 5 6 7 8
""")
    fs = check_coincident_surfaces(obj)
    assert len(fs) == 1
    assert set(fs[0]["subjects"]) == {"floor", "patch"}


def test_small_coplanar_patch_proud_of_floor_is_flagged():
    """CRITICAL-2 regression: the same 2x2 m patch as above, but 0.1 mm PROUD of the
    floor's plane rather than exactly coplanar -- textbook z-fighting (the two surfaces
    render as if coincident at typical scene scales, and the containment exclusion must
    not treat 'proud' as safely occluded)."""
    obj = parse_obj("""\
v 0 0 0
v 10 0 0
v 10 8 0
v 0 8 0
g floor
f 1 2 3 4
v 4 3 0.0001
v 6 3 0.0001
v 6 5 0.0001
v 4 5 0.0001
g patch
f 5 6 7 8
""")
    fs = check_coincident_surfaces(obj, tol=0.001)
    assert len(fs) == 1
    assert set(fs[0]["subjects"]) == {"floor", "patch"}


def test_duplicate_wall_inset_10mm_is_flagged():
    """CRITICAL-2 regression: a wall reproduced 10 mm smaller than the original on every
    edge is a genuine duplicate (11.86 m2 contained inside 12 m2, ratio ~0.99) -- not an
    end-cap. A pure bounding-box subset test would exclude this identically to a real
    end-cap; the size gate (contained-face area 11.86 m2, far above the end-cap bound)
    must not let it through."""
    obj = parse_obj("""\
v 0 0 0
v 4 0 0
v 4 3 0
v 0 3 0
g wall_orig
f 1 2 3 4
v 0.01 0.01 0
v 3.99 0.01 0
v 3.99 2.99 0
v 0.01 2.99 0
g wall_dup
f 5 6 7 8
""")
    fs = check_coincident_surfaces(obj)
    assert len(fs) == 1
    assert set(fs[0]["subjects"]) == {"wall_orig", "wall_dup"}


def test_faces_one_metre_apart_in_depth_are_clean():
    obj = """\
v 0 0 0
v 2 0 0
v 2 2 0
v 0 2 0
g wall_a
f 1 2 3 4
v 0 0 1
v 2 0 1
v 2 2 1
v 0 2 1
g wall_b
f 5 6 7 8
"""
    assert check_coincident_surfaces(parse_obj(obj)) == []


def _tessellated_floor(n):
    """n x n coplanar, pairwise-disjoint square tiles, each its own group."""
    lines = []
    vi = 0
    for row in range(n):
        for col in range(n):
            x0, y0 = col * 1.0, row * 1.0
            x1, y1 = x0 + 0.5, y0 + 0.5
            lines.append(f"v {x0} {y0} 0")
            lines.append(f"v {x1} {y0} 0")
            lines.append(f"v {x1} {y1} 0")
            lines.append(f"v {x0} {y1} 0")
            lines.append(f"g tile_{row}_{col}")
            lines.append(f"f {vi + 1} {vi + 2} {vi + 3} {vi + 4}")
            vi += 4
    return parse_obj("\n".join(lines) + "\n")


def test_large_disjoint_tessellation_is_fast_and_clean():
    """3600 coplanar, pairwise-disjoint faces (a tessellated floor) must not pay the
    full O(n^2) pairwise-comparison cost of the naive scan.

    Asserted as a SCALING ratio, not a wall-clock budget: an absolute seconds limit is a
    machine-speed flake (it fails on a slow host and passes on a fast one regardless of the
    algorithm). Quadrupling the face count (900 -> 3600) costs ~16x under a naive O(n^2)
    scan but ~4x under the spatial partition, so a ratio well under 16 is the real signal.
    """
    small = _tessellated_floor(30)
    large = _tessellated_floor(60)
    assert len(small["faces"]) == 900
    assert len(large["faces"]) == 3600

    t0 = time.time()
    assert check_coincident_surfaces(small) == []
    small_elapsed = max(time.time() - t0, 1e-4)

    t0 = time.time()
    findings = check_coincident_surfaces(large)
    large_elapsed = time.time() - t0

    assert findings == []
    ratio = large_elapsed / small_elapsed
    assert ratio < 10.0, (
        f"4x the faces cost {ratio:.1f}x the time "
        f"({small_elapsed:.3f}s -> {large_elapsed:.3f}s); naive O(n^2) would be ~16x, "
        f"the spatial partition ~4x"
    )


def _full_width_coplanar_strips(n, width=100.0, strip_h=0.5):
    """`n` coplanar strips, each spanning the FULL width on the sweep axis (x) and stacked,
    pairwise-disjoint, along y. Adversarial for a sweep implementation whose pruning
    breaks down once the sweep axis stops discriminating: every strip's x-extent is
    identical (`[0, width]`), so a sweep that (wrongly) picks x still must consider every
    pair a candidate for the O(1) `_xy_extent_overlaps` test -- this is exactly the shape
    that reproduced the CRITICAL-1 running_max bug (a chain of same-axis overlapping
    extents defeats the `break`). It is a REGRESSION guard on the fixed sweep's own axis
    choice, not merely a naive-scan stress test: the fix must pick the axis that actually
    varies (y) to prune this case, since x offers no discrimination at all."""
    lines = []
    vi = 0
    for i in range(n):
        y0, y1 = i * 1.0, i * 1.0 + strip_h
        lines.append(f"v 0 {y0} 0")
        lines.append(f"v {width} {y0} 0")
        lines.append(f"v {width} {y1} 0")
        lines.append(f"v 0 {y1} 0")
        lines.append(f"g strip_{i}")
        lines.append(f"f {vi + 1} {vi + 2} {vi + 3} {vi + 4}")
        vi += 4
    return parse_obj("\n".join(lines) + "\n")


def test_full_width_strips_2000_is_fast_and_clean():
    """Performance regression for CRITICAL-1 (the broken running_max sweep never pruned
    once faces chained along the sweep axis, making this O(n^2): ~13-19s at 2000 faces
    before the fix). 2000 disjoint full-width strips must complete well under 2s and
    report the correct (zero) finding count."""
    obj = _full_width_coplanar_strips(2000)
    assert len(obj["faces"]) == 2000

    t0 = time.time()
    findings = check_coincident_surfaces(obj)
    elapsed = time.time() - t0

    assert findings == []
    assert elapsed < 2.0, f"2000 full-width coplanar strips took {elapsed:.2f}s (limit 2s)"


def _naive_coincident_pair_count(parsed, tol=0.001):
    """Reference implementation: every pair, no sweep pre-filter at all. Used ONLY as the
    ground truth for the differential test below -- deliberately re-imports the same
    `_xy_extent_overlaps` predicate the swept implementation uses, so this isolates the
    SWEEP's correctness (does pruning ever drop a pair the predicate would accept?) from
    the predicate's own correctness (covered by the dedicated fixture tests elsewhere)."""
    from hcl_radiance.geometry_health import _plane_key
    from hcl_radiance.geometry_obj import face_area as _face_area
    import itertools as _it
    by_plane = {}
    for f in parsed["faces"]:
        if _face_area(parsed, f) <= 0.0:
            continue
        key = _plane_key(parsed, f, tol)
        if key is not None:
            by_plane.setdefault(key, []).append(f)
    pairs = 0
    for faces in by_plane.values():
        for fa, fb in _it.combinations(faces, 2):
            from hcl_radiance.geometry_health import _xy_extent_overlaps
            if _xy_extent_overlaps(parsed, fa, fb, tol):
                pairs += 1
    return pairs


def _swept_pair_count(parsed, tol=0.001):
    fs = check_coincident_surfaces(parsed, tol=tol)
    return fs[0]["detail"]["pairs"] if fs else 0


def test_swept_sweep_matches_naive_all_pairs_reference_randomised():
    """Differential test for CRITICAL-1: on many randomised coplanar face sets, the swept
    implementation's finding count must equal the naive all-pairs reference exactly. A
    sweep that under-prunes would UNDER-count (miss genuinely overlapping pairs); this
    catches that directly rather than relying on hand-picked fixtures alone."""
    import random
    rng = random.Random(20260723)
    for trial in range(300):
        n = rng.randint(2, 14)
        lines = []
        vi = 0
        for i in range(n):
            x0 = rng.uniform(0, 8)
            y0 = rng.uniform(0, 8)
            w = rng.uniform(0.5, 4.0)
            h = rng.uniform(0.5, 4.0)
            x1, y1 = x0 + w, y0 + h
            lines.append(f"v {x0} {y0} 0")
            lines.append(f"v {x1} {y0} 0")
            lines.append(f"v {x1} {y1} 0")
            lines.append(f"v {x0} {y1} 0")
            lines.append(f"g face_{trial}_{i}")
            lines.append(f"f {vi + 1} {vi + 2} {vi + 3} {vi + 4}")
            vi += 4
        obj = parse_obj("\n".join(lines) + "\n")
        naive = _naive_coincident_pair_count(obj)
        swept = _swept_pair_count(obj)
        assert swept == naive, (
            f"trial {trial} (n={n}): swept={swept} naive={naive}, sweep dropped a pair")


import json
import os

from hcl_radiance.geometry_import import split_map_metadata

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_office_room():
    """The project's real reference model + its real (flat) material map sidecar.

    office_room_material_map.json is a FLAT map: group specs sit at the top level
    alongside units/up_axis/north_angle_deg and a `_README`. `split_map_metadata`
    handles both the flat and wrapped shapes; hand-rolling the split and passing the
    raw dict straight to a group-spec consumer would misread `units`/`_README` as
    group names.
    """
    with open(os.path.join(_FIXTURES, "office_room.obj")) as fh:
        parsed = parse_obj(fh.read())
    with open(os.path.join(_FIXTURES, "office_room_material_map.json")) as fh:
        material_map, _scalars = split_map_metadata(json.load(fh))
    return parsed, material_map


def test_coincident_surfaces_office_room_fixture_is_clean():
    """Regression for the false positive found by running the checker against the
    project's real reference model (published in the paper): the floor slab's edge
    face, wall/frame end-caps, and furniture-leg bottom caps all abut or rest flush
    against other coplanar surfaces -- correctly modelled, not duplicated -- and must
    not be reported."""
    parsed, _material_map = _load_office_room()
    assert check_coincident_surfaces(parsed) == []


def test_not_enclosed_office_room_fixture_is_unchanged():
    """check_enclosure is NOT part of this fix (investigated, not touched): confirms the
    reference model still reports its 20 pre-existing boundary edges (glazing reveal /
    open-shell furniture), unaffected by the coincident-surfaces change."""
    parsed, material_map = _load_office_room()
    fs = check_enclosure(parsed, material_map)
    assert len(fs) == 1
    assert fs[0]["detail"]["boundary_edges"] == 20


_DUP = """\
v 0 0 0
v 2 0 0
v 2 2 0
g wall
f 1 2 3
f 1 2 3
"""

_NON_PLANAR = """\
v 0 0 0
v 2 0 0
v 2 2 0.5
v 0 2 0
g wall
f 1 2 3 4
"""

_PLANAR_QUAD = """\
v 0 0 0
v 2 0 0
v 2 2 0
v 0 2 0
g wall
f 1 2 3 4
"""


def test_duplicate_faces_detected():
    fs = check_duplicate_faces(parse_obj(_DUP))
    assert len(fs) == 1
    assert fs[0]["code"] == "DUPLICATE_FACES"
    assert fs[0]["severity"] == "warning"
    assert fs[0]["subjects"] == ["wall"]
    assert fs[0]["detail"]["duplicates"] == 1
    assert fs[0]["fix"]


def test_duplicate_faces_ignores_winding_order():
    """f 1 2 3 and f 3 2 1 are the same surface twice."""
    fs = check_duplicate_faces(parse_obj(_DUP.replace("f 1 2 3\nf 1 2 3", "f 1 2 3\nf 3 2 1")))
    assert len(fs) == 1


def test_planar_quad_is_clean():
    assert check_non_planar_faces(parse_obj(_PLANAR_QUAD)) == []
    assert check_duplicate_faces(parse_obj(_PLANAR_QUAD)) == []


def test_non_planar_face_detected():
    fs = check_non_planar_faces(parse_obj(_NON_PLANAR))
    assert len(fs) == 1
    assert fs[0]["code"] == "NON_PLANAR_FACE"
    assert fs[0]["severity"] == "warning"
    assert fs[0]["detail"]["worst_deviation_m"] > 0.005


# A quad warped by exactly 20 mm on one vertex (worst_deviation_m ~ 10 mm, the centroid-
# anchored peak-to-peak spread), squarely between the default tol (5 mm) and a 10x-loosened
# tol (50 mm). Called WITHOUT tol= so this only passes at the true default.
_QUAD_WARPED_10MM = """\
v 0 0 0
v 2 0 0
v 2 2 0.02
v 0 2 0
g wall
f 1 2 3 4
"""


def test_non_planar_face_at_default_tolerance_is_flagged():
    """Kills `tol=0.005 -> tol=0.05`: a 10 mm deviation is well above the true 5 mm default
    but well below a 10x-loosened 50 mm one, and this call passes NO tol= override."""
    fs = check_non_planar_faces(parse_obj(_QUAD_WARPED_10MM))
    assert len(fs) == 1
    assert fs[0]["code"] == "NON_PLANAR_FACE"
    assert 0.005 < fs[0]["detail"]["worst_deviation_m"] < 0.05


def test_triangle_is_never_reported_regardless_of_vertex_arrangement():
    """Kills `if len(verts) < 4 -> if len(verts) < 3`: a triangle is planar by construction,
    so the guard must skip every triangle before any deviation math runs. A truly planar
    triangle would report zero deviation even without the guard (that alone can't tell the
    two implementations apart), so this uses a badly spread, highly non-coplanar-LOOKING
    triangle -- still trivially planar as three points always are -- to prove the guard
    itself is what suppresses it. Paired with the default-tolerance test above (which DOES
    get reported), so this cannot pass merely because the check is dead.
    """
    obj = """\
v 0 0 0
v 5 0 3
v -2 4 -3
g wall
f 1 2 3
"""
    fs = check_non_planar_faces(parse_obj(obj), tol=0.0)
    assert fs == [], "a triangle must never be reported non-planar, at any tolerance"
    # Sanity: the check is not simply dead -- the quad case above IS found at tol=0.0 too.
    assert check_non_planar_faces(parse_obj(_QUAD_WARPED_10MM), tol=0.0) != []


def test_tilted_planar_quad_is_clean():
    """A quad tilted 45 degrees in space is still exactly planar; the centroid-anchored
    peak-to-peak deviation must be ~0 regardless of orientation."""
    import math
    c, s = math.cos(math.radians(45)), math.sin(math.radians(45))
    # Unit square in the XY plane, rotated 45 deg about the X axis.
    pts = [(0, 0, 0), (2, 0, 0), (2, 2 * c, 2 * s), (0, 2 * c, 2 * s)]
    lines = [f"v {x} {y} {z}" for x, y, z in pts]
    lines.append("g wall")
    lines.append("f 1 2 3 4")
    obj = parse_obj("\n".join(lines) + "\n")
    assert check_non_planar_faces(obj) == []


def test_collinear_planar_quad_is_clean():
    """A degenerate quad with three collinear vertices is still planar (zero-area or
    not), and must not be reported as non-planar."""
    lines = [
        "v 0 0 0",
        "v 1 0 0",
        "v 2 0 0",   # collinear with the previous two
        "v 2 2 0",
        "g wall",
        "f 1 2 3 4",
    ]
    obj = parse_obj("\n".join(lines) + "\n")
    assert check_non_planar_faces(obj) == []


def test_non_planar_deviation_is_invariant_to_vertex_rotation():
    """OBJ face-vertex order is exporter-arbitrary. The reported worst_deviation_m for an
    irregular warped pentagon must be identical no matter which vertex the exporter wrote
    first -- anchoring the plane at the centroid (not verts[0]) guarantees this."""
    pentagon_verts = [
        (0.0, 0.0, 0.0),
        (2.0, 0.0, 0.15),
        (3.0, 1.5, 0.0),
        (1.2, 2.5, 0.3),
        (-0.5, 1.0, 0.05),
    ]
    n = len(pentagon_verts)

    def make_obj(rot):
        order = [pentagon_verts[(i + rot) % n] for i in range(n)]
        lines = [f"v {x} {y} {z}" for x, y, z in order]
        lines.append("g wall")
        lines.append("f " + " ".join(str(i + 1) for i in range(n)))
        return "\n".join(lines) + "\n"

    deviations = []
    for rot in range(n):
        fs = check_non_planar_faces(parse_obj(make_obj(rot)), tol=0.0)
        assert len(fs) == 1
        deviations.append(fs[0]["detail"]["worst_deviation_m"])

    for dev in deviations[1:]:
        assert dev == pytest.approx(deviations[0], abs=1e-9)


# A 4x3 m wall in the z=0 plane with a 2x1 m window inside it, and NO hole cut.
_BLOCKED = """\
v 0 0 0
v 4 0 0
v 4 3 0
v 0 3 0
v 1 1 0
v 3 1 0
v 3 2 0
v 1 2 0
g wall
f 1 2 3 4
g glass
f 5 6 7 8
"""

# Same window, wall moved to a different plane (a real opening elsewhere).
_OPEN = _BLOCKED.replace("v 0 0 0\nv 4 0 0\nv 4 3 0\nv 0 3 0",
                         "v 0 0 2\nv 4 0 2\nv 4 3 2\nv 0 3 2")

_MAP = {"wall": {"refl": 0.5}, "glass": {"type": "glass", "tvis": 0.7}}


def test_window_without_opening_detected():
    fs = check_window_without_opening(parse_obj(_BLOCKED), _MAP)
    assert len(fs) == 1
    assert fs[0]["code"] == "WINDOW_WITHOUT_OPENING"
    assert fs[0]["severity"] == "error"
    assert fs[0]["subjects"] == ["glass"]
    assert fs[0]["fix"]


def test_window_with_opening_is_clean():
    assert check_window_without_opening(parse_obj(_OPEN), _MAP) == []


def test_no_glazing_is_clean():
    assert check_window_without_opening(parse_obj(_BLOCKED), {"wall": {"refl": 0.5}}) == []


def _blocked_with_z_gap(gap_m):
    """The _BLOCKED wall/glass pair, but the glazing sits `gap_m` metres proud of the
    wall's plane instead of exactly coplanar."""
    return f"""\
v 0 0 0
v 4 0 0
v 4 3 0
v 0 3 0
v 1 1 {gap_m}
v 3 1 {gap_m}
v 3 2 {gap_m}
v 1 2 {gap_m}
g wall
f 1 2 3 4
g glass
f 5 6 7 8
"""


def test_window_without_opening_default_tolerance_is_1mm_not_wider():
    """Pins check_window_without_opening's default tol=0.001 (1 mm). A 10 mm gap between
    the glazing and the wall plane sits strictly between the correct default (1 mm) and a
    loosened default (50 mm): calling WITHOUT tol= must NOT flag it as coplanar-and-blocked,
    so a widened default fails this test."""
    obj = parse_obj(_blocked_with_z_gap(0.01))
    assert check_window_without_opening(obj, _MAP) == []
    # Sanity: the same gap IS flagged at a loosened 50 mm tolerance, confirming the fixture
    # actually straddles the two tolerance values rather than being clean outright.
    assert len(check_window_without_opening(obj, _MAP, tol=0.05)) == 1


def test_context_wall_is_clean():
    # Same geometry as _BLOCKED, but the wall is typed "context" -- should not be
    # treated as an opaque blocker.
    ctx_map = {"wall": {"type": "context", "refl": 0.5},
               "glass": {"type": "glass", "tvis": 0.7}}
    assert check_window_without_opening(parse_obj(_BLOCKED), ctx_map) == []


# A wall with a REAL opening: four faces (sill, head, two jambs) framing a 2x1 m void at
# the same location as the glazing, none of which individually contains the glazing
# centroid.
_REAL_OPENING = """\
v 0 0 0
v 4 0 0
v 4 3 0
v 0 3 0
v 1 1 0
v 3 1 0
v 3 2 0
v 1 2 0
g wall
f 1 2 6 5
f 7 3 4 8
f 5 8 4 1
f 2 3 7 6
g glass
f 5 6 7 8
"""


def test_window_with_real_opening_is_clean():
    assert check_window_without_opening(parse_obj(_REAL_OPENING), _MAP) == []


# The glazing is coplanar with the wall but entirely outside the wall's outline.
_OUTSIDE_OUTLINE = """\
v 0 0 0
v 4 0 0
v 4 3 0
v 0 3 0
v 5 1 0
v 7 1 0
v 7 2 0
v 5 2 0
g wall
f 1 2 3 4
g glass
f 5 6 7 8
"""


def test_glazing_coplanar_but_outside_outline_is_clean():
    assert check_window_without_opening(parse_obj(_OUTSIDE_OUTLINE), _MAP) == []


# Two glazing faces in the same wall plane: one sits inside the unbroken wall (blocked),
# the other sits over a real opening cut from a second wall (not blocked). wall_b spans
# x in [10,14], y in [0,3] with a 2x1 m opening at x in [11,13], y in [1,2], framed by
# four non-overlapping rectangles (sill/head/jamb1/jamb2).
_PARTIAL_BLOCK = """\
v 0 0 0
v 4 0 0
v 4 3 0
v 0 3 0
v 1 1 0
v 2 1 0
v 2 2 0
v 1 2 0
v 10 0 0
v 14 0 0
v 14 1 0
v 10 1 0
v 10 2 0
v 14 2 0
v 14 3 0
v 10 3 0
v 11 1 0
v 13 1 0
v 13 2 0
v 11 2 0
g wall_a
f 1 2 3 4
g wall_b_sill
f 9 10 11 12
g wall_b_head
f 13 14 15 16
g wall_b_jamb1
f 12 17 20 13
g wall_b_jamb2
f 18 11 14 19
g glass
f 5 6 7 8
f 17 18 19 20
"""


def test_partial_block_counts_only_blocked_faces():
    fs = check_window_without_opening(parse_obj(_PARTIAL_BLOCK), _MAP)
    assert len(fs) == 1
    assert fs[0]["detail"]["blocked_faces"] == 1
    assert fs[0]["subjects"] == ["glass"]


# The same 4x3 wall as _BLOCKED, but the glazing centroid is placed exactly ON each of
# the four wall edges rather than inside the wall outline. A boundary tie must resolve to
# NOT-inside on all four edges -- the ray-crossing test is asymmetric across edges if this
# case is not handled explicitly.
def _wall_with_centroid_on_edge(cx, cy):
    return f"""\
v 0 0 0
v 4 0 0
v 4 3 0
v 0 3 0
v {cx - 0.5} {cy - 0.5} 0
v {cx + 0.5} {cy - 0.5} 0
v {cx + 0.5} {cy + 0.5} 0
v {cx - 0.5} {cy + 0.5} 0
g wall
f 1 2 3 4
g glass
f 5 6 7 8
"""


@pytest.mark.parametrize("edge,cx,cy", [
    ("bottom", 2.0, 0.0),
    ("top", 2.0, 3.0),
    ("left", 0.0, 1.5),
    ("right", 4.0, 1.5),
])
def test_glazing_centroid_on_wall_edge_is_clean(edge, cx, cy):
    obj = _wall_with_centroid_on_edge(cx, cy)
    assert check_window_without_opening(parse_obj(obj), _MAP) == [], (
        f"glazing centroid on the {edge} edge was reported as blocked")


_DEGENERATE = """\
v 0 0 0
v 2 0 0
g wall
f 1 2 1
"""

_OPEN_BOX = """\
v 0 0 0
v 2 0 0
v 2 2 0
v 0 2 0
g floor
f 1 2 3 4
"""


def test_mesh_quality_recodes_degenerate_and_normals():
    fs = check_mesh_quality(parse_obj(_DEGENERATE))
    by_code = {f["code"]: f for f in fs}
    assert "DEGENERATE_FACES" in by_code
    assert "NO_VERTEX_NORMALS" in by_code
    assert by_code["DEGENERATE_FACES"]["detail"]["count"] == 1
    for f in fs:
        assert f["severity"] == "warning"
        assert f["fix"]


# A triangle fan: three faces all sharing the edge (1, 2). That edge is used by 3 faces,
# so it is non-manifold (a real mesh edge belongs to exactly 2 faces, or 1 on a boundary).
_NON_MANIFOLD = """\
v 0 0 0
v 2 0 0
v 0 2 0
v 0 -2 0
v -2 0 0
g fan
f 1 2 3
f 1 2 4
f 1 2 5
"""


def test_mesh_quality_detects_non_manifold_edge():
    fs = check_mesh_quality(parse_obj(_NON_MANIFOLD))
    by_code = {f["code"]: f for f in fs}
    assert "NON_MANIFOLD_EDGES" in by_code
    nm = by_code["NON_MANIFOLD_EDGES"]
    assert nm["severity"] == "warning"
    assert nm["detail"]["count"] == 1
    assert nm["fix"]


def test_enclosure_flags_boundary_edges():
    fs = check_enclosure(parse_obj(_OPEN_BOX), {"floor": {"refl": 0.2}})
    assert len(fs) == 1
    assert fs[0]["code"] == "NOT_ENCLOSED"
    assert fs[0]["severity"] == "warning"
    assert fs[0]["detail"]["boundary_edges"] == 4


def test_enclosure_ignores_context_groups():
    obj = _OPEN_BOX.replace("g floor", "g site")
    assert check_enclosure(parse_obj(obj), {"site": {"type": "context", "refl": 0.2}}) == []


def test_enclosure_skips_self_loops_and_dedupes_per_face():
    """Regression: a degenerate face with a repeated vertex (e.g., f 1 2 3 3) must not
    produce spurious self-loop edges. This face has 3 edges, not 4."""
    obj = parse_obj("""\
v 0 0 0
v 1 0 0
v 1 1 0
g wall
f 1 2 3 3
""")
    fs = check_enclosure(obj, {"wall": {"refl": 0.5}})
    assert len(fs) == 1
    assert fs[0]["detail"]["boundary_edges"] == 3


_CLEAN_ROOM = """\
v 0 0 0
v 4 0 0
v 4 4 0
v 0 4 0
v 0 0 3
v 4 0 3
v 4 4 3
v 0 4 3
g floor
f 1 2 3 4
g ceiling
f 5 6 7 8
g walls
f 1 2 6 5
f 2 3 7 6
f 3 4 8 7
f 4 1 5 8
"""

_ROOM_MAP = {"floor": {"refl": 0.25}, "ceiling": {"refl": 0.8}, "walls": {"refl": 0.7}}


def test_health_report_shape_on_a_closed_room():
    r = check_geometry_health(parse_obj(_CLEAN_ROOM), _ROOM_MAP)
    assert set(r) == {"ok", "counts", "findings", "checked", "skipped", "confidence"}
    assert "geometry" in r["checked"]
    assert r["counts"]["error"] == 0
    assert r["ok"] is True


def test_health_report_reports_skipped_categories():
    r = check_geometry_health(parse_obj(_CLEAN_ROOM), _ROOM_MAP)
    skipped = {s["category"] for s in r["skipped"]}
    assert "sensors" in skipped
    for s in r["skipped"]:
        assert s["category"]
        assert s["reason"]


def _luminaires_reason(report):
    for s in report["skipped"]:
        if s["category"] == "luminaires":
            return s["reason"]
    raise AssertionError("no 'luminaires' entry in skipped")


def test_electric_lights_supplied_is_not_silently_ignored():
    r = check_geometry_health(parse_obj(_CLEAN_ROOM), _ROOM_MAP,
                               electric_lights=[{"group": "lum1"}])
    with_block = _luminaires_reason(r)

    r_none = check_geometry_health(parse_obj(_CLEAN_ROOM), _ROOM_MAP)
    without_block = _luminaires_reason(r_none)

    assert with_block != without_block
    assert "electric_lights" in with_block


def test_electric_lights_omitted_keeps_deferred_reason():
    r = check_geometry_health(parse_obj(_CLEAN_ROOM), _ROOM_MAP)
    assert _luminaires_reason(r) == "luminaire checks land in tier 2"


def test_confidence_is_explicit_not_empty():
    r = check_geometry_health(parse_obj(_CLEAN_ROOM), _ROOM_MAP)
    assert r["confidence"] != {}
    assert r["confidence"]["interior_reference"] is None
    assert isinstance(r["confidence"]["interior_reference"], (type(None),))
    assert not isinstance(r["confidence"]["interior_reference"], (int, float))


def test_health_report_surfaces_an_error():
    r = check_geometry_health(parse_obj(_TWO_COPLANAR), {"wall_a": {"refl": 0.5},
                                                        "wall_b": {"refl": 0.5}})
    assert r["ok"] is False
    assert r["findings"][0]["severity"] == "error"
    assert "COINCIDENT_SURFACES" in {f["code"] for f in r["findings"]}


# --- Composition guard: all six checks must be reachable THROUGH check_geometry_health ---
#
# Every check above is verified by calling it DIRECTLY. That alone is not enough: nothing
# stops `check_geometry_health` itself from silently dropping a `findings += check_x(...)`
# line -- the direct-call tests above would still pass, and _CLEAN_ROOM/_TWO_COPLANAR (the
# only fixtures the pre-existing composition tests use) only ever trip COINCIDENT_SURFACES.
# This fixture is built to trip all SIX checks (eight finding codes: check_mesh_quality
# alone emits three) simultaneously, so dropping any one `findings +=` line in
# check_geometry_health changes the returned code SET and fails the exact-set assertion
# below.
#
# Independent, non-interfering defects, kept spatially apart so none of the geometric
# predicates (coplanarity, containment, edge-adjacency) accidentally cancel or merge two
# defects into one finding:
#   - floor/ceiling + 3 of 4 walls (one wall omitted)  -> NOT_ENCLOSED (open boundary edges)
#   - glazing inside the unbroken front wall, no cut   -> WINDOW_WITHOUT_OPENING
#   - dup_a / dup_b: identical vertex sets              -> DUPLICATE_FACES
#                     (also a genuine coplanar positive-area overlap -> COINCIDENT_SURFACES)
#   - overlap_a / overlap_b: distinct vertices, same coplanar overlapping footprint
#                                                         -> COINCIDENT_SURFACES (2nd pair)
#   - warped: a non-planar quad                          -> NON_PLANAR_FACE
#   - degenerate: a face with a repeated vertex           -> DEGENERATE_FACES
#   - nonmanifold: 3 triangles fanned off one shared edge -> NON_MANIFOLD_EDGES
#   - no `vn` lines anywhere in the fixture               -> NO_VERTEX_NORMALS
#   - nonfinite: one vertex is `nan`, isolated far from everything else
#                                                         -> NON_FINITE_COORDINATES
#   - "floor" group exists but is never typed type:"floor" in the material map
#                                                         -> NO_FLOOR_GROUP
_ALL_SIX_CHECKS_TRIPPED = """\
v 0 0 0
v 4 0 0
v 4 4 0
v 0 4 0
v 0 0 3
v 4 0 3
v 4 4 3
v 0 4 3
v 1 0 1
v 3 0 1
v 3 0 2
v 1 0 2
v 20 0 10
v 22 0 10
v 22 2 10
v 20 2 10
v 20 0 10
v 22 0 10
v 22 2 10
v 20 2 10
v 30 0 0
v 32 0 0
v 32 2 0.5
v 30 2 0
v 40 0 0
v 42 0 0
v 50 0 0
v 52 0 0
v 50 2 0
v 50 -2 0
v 48 0 0
v 60 0 0
v 62 0 0
v 62 2 0
v 60 2 0
v nan 0 0
v 100 100 100
v 100 102 100
v 98 102 100
g floor
f 1 2 3 4
g ceiling
f 5 6 7 8
g walls
f 1 2 6 5
f 2 3 7 6
f 3 4 8 7
g glass
f 9 10 11 12
g dup_a
f 32 33 34 35
g dup_b
f 32 33 34 35
g overlap_a
f 13 14 15 16
g overlap_b
f 17 18 19 20
g warped
f 21 22 23 24
g degenerate
f 25 26 25
g nonmanifold
f 27 28 29
f 27 28 30
f 27 28 31
g nonfinite
f 36 37 38 39
"""

_ALL_SIX_CHECKS_MAP = {
    "floor": {"refl": 0.25},
    "ceiling": {"refl": 0.8},
    "walls": {"refl": 0.7},
    "glass": {"type": "glass", "tvis": 0.7},
    "dup_a": {"refl": 0.5},
    "dup_b": {"refl": 0.5},
    "overlap_a": {"refl": 0.5},
    "overlap_b": {"refl": 0.5},
    "warped": {"refl": 0.5},
    "degenerate": {"refl": 0.5},
    "nonmanifold": {"refl": 0.5},
    "nonfinite": {"refl": 0.5},
}

_ALL_SIX_CHECKS_EXPECTED_CODES = {
    "COINCIDENT_SURFACES", "WINDOW_WITHOUT_OPENING", "DUPLICATE_FACES", "NON_PLANAR_FACE",
    "DEGENERATE_FACES", "NON_MANIFOLD_EDGES", "NO_VERTEX_NORMALS", "NOT_ENCLOSED",
    "NON_FINITE_COORDINATES", "NO_FLOOR_GROUP",
}


def test_check_geometry_health_composition_trips_every_check():
    """Guards against a check being silently unwired from check_geometry_health: replacing
    any one of its six `findings += check_x(...)` lines with `findings += []` must drop at
    least one code from this exact set and fail here, even though every check still passes
    its own direct-call unit tests above."""
    r = check_geometry_health(parse_obj(_ALL_SIX_CHECKS_TRIPPED), _ALL_SIX_CHECKS_MAP)
    codes = {f["code"] for f in r["findings"]}
    assert codes == _ALL_SIX_CHECKS_EXPECTED_CODES, (
        f"missing={_ALL_SIX_CHECKS_EXPECTED_CODES - codes}, "
        f"unexpected={codes - _ALL_SIX_CHECKS_EXPECTED_CODES}")


def test_check_geometry_health_skipped_is_never_silently_emptied():
    """Guards against `skipped = []` on the build_report call: the five documented Tier-1
    skip categories must always be present and non-empty."""
    r = check_geometry_health(parse_obj(_CLEAN_ROOM), _ROOM_MAP)
    assert r["skipped"], "skipped must not be empty"
    categories = {s["category"] for s in r["skipped"]}
    assert categories == {"materials", "apertures", "conventions", "sensors", "luminaires"}


_NAN_VERTEX = """\
v nan 0 0
v 2 0 0
v 2 2 0
v 0 2 0
g wall
f 1 2 3 4
"""


def test_no_inferential_check_emits_error():
    """Severity discipline: only checks that change traced physics may be `error`.

    NON_FINITE_COORDINATES belongs in `allowed`: it is not inferential (it reads a fact
    off the model, not a guess at intent) and a NaN/inf vertex genuinely cannot be traced,
    so it stays a real member of this set rather than one this test merely fails to reject.
    """
    allowed = {"COINCIDENT_SURFACES", "WINDOW_WITHOUT_OPENING", "NON_FINITE_COORDINATES"}
    for obj, mp in ((_TWO_COPLANAR, {"wall_a": {"refl": 0.5}, "wall_b": {"refl": 0.5}}),
                    (_BLOCKED, _MAP), (_CLEAN_ROOM, _ROOM_MAP), (_DEGENERATE, {"wall": {"refl": 0.5}}),
                    (_NAN_VERTEX, {"wall": {"refl": 0.5}})):
        r = check_geometry_health(parse_obj(obj), mp)
        for f in r["findings"]:
            if f["severity"] == "error":
                assert f["code"] in allowed, f["code"]


def test_no_inferential_check_emits_error_rejects_a_promoted_warning():
    """The allow-set discipline must still reject any OTHER code being promoted to error --
    confirm this by asserting a genuinely warning-severity code is NOT in the allowed set."""
    allowed = {"COINCIDENT_SURFACES", "WINDOW_WITHOUT_OPENING", "NON_FINITE_COORDINATES"}
    assert "NO_FLOOR_GROUP" not in allowed
    assert "NON_PLANAR_FACE" not in allowed
    r = check_geometry_health(parse_obj(_NAN_VERTEX), {"wall": {"refl": 0.5}})
    codes_by_severity = {f["code"]: f["severity"] for f in r["findings"]}
    assert codes_by_severity.get("NO_FLOOR_GROUP") == "warning"


import hcl_radiance.geometry_import as gi_mod


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def test_import_geometry_embeds_health(tmp_path):
    obj = _write(tmp_path, "room.obj", _CLEAN_ROOM)
    r = gi_mod.import_geometry(obj, material_map=_ROOM_MAP, units="m", up_axis="Z",
                               work_dir=str(tmp_path), run=False)
    assert "health" in r
    assert r["health"]["ok"] is True
    assert "geometry" in r["health"]["checked"]


def test_strict_raises_on_error_findings(tmp_path):
    obj = _write(tmp_path, "bad.obj", _TWO_COPLANAR)
    mp = {"wall_a": {"refl": 0.5}, "wall_b": {"refl": 0.5}}
    with pytest.raises(GeometryHealthError) as ei:
        gi_mod.import_geometry(obj, material_map=mp, units="m", up_axis="Z",
                               work_dir=str(tmp_path), run=False, strict=True)
    assert ei.value.payload["ok"] is False
    assert "COINCIDENT_SURFACES" in {f["code"] for f in ei.value.payload["findings"]}


def test_strict_does_not_raise_on_a_clean_model(tmp_path):
    obj = _write(tmp_path, "room.obj", _CLEAN_ROOM)
    r = gi_mod.import_geometry(obj, material_map=_ROOM_MAP, units="m", up_axis="Z",
                               work_dir=str(tmp_path), run=False, strict=True)
    assert r["health"]["ok"] is True


def test_default_is_report_only(tmp_path):
    """Back-compat: a model with error findings must still import by default."""
    obj = _write(tmp_path, "bad.obj", _TWO_COPLANAR)
    mp = {"wall_a": {"refl": 0.5}, "wall_b": {"refl": 0.5}}
    r = gi_mod.import_geometry(obj, material_map=mp, units="m", up_axis="Z",
                               work_dir=str(tmp_path), run=False)
    assert r["health"]["ok"] is False
    assert r["groups"] == ["wall_a", "wall_b"]


def _fake_run_failure(steps, work_dir, available):
    """Mirrors hcl_core.proc.run_sequence's shape on a non-zero subprocess return."""
    return {
        "ran": True,
        "returncode": 1,
        "commands": ["oconv ...", "rtrace ..."],
        "error": "rtrace: fatal - boom",
        "failed_step": "rtrace scene.oct",
    }


def test_strict_radiance_failure_and_error_findings_raises_with_both(monkeypatch, tmp_path):
    """Reviewer-verified precedence bug: a Radiance failure must not be silently discarded
    by a strict health raise. The exception must name the failed step AND the health-finding
    count, and .payload must carry both the health report and the Radiance failure."""
    obj = _write(tmp_path, "bad.obj", _TWO_COPLANAR)
    mp = {"wall_a": {"refl": 0.5}, "wall_b": {"refl": 0.5}}
    monkeypatch.setattr(gi_mod, "_available", lambda: True)
    monkeypatch.setattr(gi_mod, "run_sequence", _fake_run_failure)

    with pytest.raises(GeometryHealthError) as ei:
        gi_mod.import_geometry(obj, material_map=mp, units="m", up_axis="Z",
                               work_dir=str(tmp_path), run=True, strict=True)

    msg = str(ei.value)
    assert "rtrace scene.oct" in msg, "message must name the failed Radiance step"
    assert "error-severity health finding" in msg, "message must mention the health findings"

    payload = ei.value.payload
    assert payload["ok"] is False
    assert "COINCIDENT_SURFACES" in {f["code"] for f in payload["findings"]}
    assert payload["radiance_error"] == "rtrace: fatal - boom"
    assert payload["radiance_failed_step"] == "rtrace scene.oct"


def test_strict_radiance_failure_without_error_findings_is_unchanged(monkeypatch, tmp_path):
    """Today's behaviour when Radiance fails but the geometry itself is clean: no health
    raise at all (strict only fires on error-severity findings) -- the failure is reported
    the normal way, through the returned dict."""
    obj = _write(tmp_path, "room.obj", _CLEAN_ROOM)
    monkeypatch.setattr(gi_mod, "_available", lambda: True)
    monkeypatch.setattr(gi_mod, "run_sequence", _fake_run_failure)

    r = gi_mod.import_geometry(obj, material_map=_ROOM_MAP, units="m", up_axis="Z",
                               work_dir=str(tmp_path), run=True, strict=True)

    assert r["health"]["ok"] is True
    assert r["error"] == "rtrace: fatal - boom"
    assert r["failed_step"] == "rtrace scene.oct"


def test_non_strict_radiance_failure_returns_normally(monkeypatch, tmp_path):
    """strict=False must be completely unaffected by this fix: a failed Radiance run still
    returns normally with 'error' set and 'health' present, regardless of health findings."""
    obj = _write(tmp_path, "bad.obj", _TWO_COPLANAR)
    mp = {"wall_a": {"refl": 0.5}, "wall_b": {"refl": 0.5}}
    monkeypatch.setattr(gi_mod, "_available", lambda: True)
    monkeypatch.setattr(gi_mod, "run_sequence", _fake_run_failure)

    r = gi_mod.import_geometry(obj, material_map=mp, units="m", up_axis="Z",
                               work_dir=str(tmp_path), run=True, strict=False)

    assert r["error"] == "rtrace: fatal - boom"
    assert r["failed_step"] == "rtrace scene.oct"
    assert r["health"]["ok"] is False


def test_check_geometry_tool_returns_a_report(tmp_path):
    import asyncio
    import hcl_mcp.server as srv
    obj = _write(tmp_path, "room.obj", _CLEAN_ROOM)
    r = asyncio.run(srv.check_geometry(obj, material_map=_ROOM_MAP, units="m", up_axis="Z"))
    assert r["ok"] is True
    assert "geometry" in r["checked"]
    assert r["counts"]["error"] == 0


def test_check_geometry_tool_flags_a_defect(tmp_path):
    import asyncio
    import hcl_mcp.server as srv
    obj = _write(tmp_path, "bad.obj", _TWO_COPLANAR)
    r = asyncio.run(srv.check_geometry(
        obj, material_map={"wall_a": {"refl": 0.5}, "wall_b": {"refl": 0.5}},
        units="m", up_axis="Z"))
    assert r["ok"] is False
    assert "COINCIDENT_SURFACES" in {f["code"] for f in r["findings"]}


def test_check_geometry_tool_needs_no_radiance(tmp_path):
    """The whole point: auditable without a scene build."""
    import asyncio
    import hcl_mcp.server as srv
    obj = _write(tmp_path, "room.obj", _CLEAN_ROOM)
    r = asyncio.run(srv.check_geometry(obj, material_map=_ROOM_MAP, units="m", up_axis="Z"))
    assert "commands" not in r and "geometry_set" not in r


def test_check_geometry_tool_accepts_flat_material_map_sidecar(tmp_path):
    """office_room_material_map.json-style sidecars put group specs at the TOP level
    alongside units/up_axis/north_angle_deg and a _README. Must not raise KeyError."""
    import asyncio
    import json
    import hcl_mcp.server as srv
    obj = _write(tmp_path, "room.obj", _CLEAN_ROOM)
    flat = {
        "_README": "not a surface name",
        "units": "m",
        "up_axis": "Z",
        "floor": {"refl": 0.25},
        "ceiling": {"refl": 0.8},
        "walls": {"refl": 0.7},
    }
    sidecar_path = tmp_path / "flat_map.json"
    sidecar_path.write_text(json.dumps(flat))
    r = asyncio.run(srv.check_geometry(obj, sidecar=str(sidecar_path)))
    assert r["ok"] is True
    assert "geometry" in r["checked"]


def test_check_geometry_tool_accepts_flat_material_map_dict(tmp_path):
    """Direct call with material_map= containing group specs at TOP level alongside
    units/up_axis and a _README exercises check_geometry's split_map_metadata block.
    When the block is removed, resolve_spec reads 'units' as a surface-library name,
    raising KeyError: unknown surface 'units'."""
    import asyncio
    import hcl_mcp.server as srv
    obj = _write(tmp_path, "room.obj", _CLEAN_ROOM)
    flat = {
        "_README": "not a surface name",
        "units": "m",
        "up_axis": "Z",
        "floor": {"refl": 0.25},
        "ceiling": {"refl": 0.8},
        "walls": {"refl": 0.7},
    }
    r = asyncio.run(srv.check_geometry(obj, material_map=flat))
    assert r["ok"] is True
    assert "geometry" in r["checked"]
    assert r["counts"]["error"] == 0


def test_check_geometry_tool_bad_up_axis_raises_value_error(tmp_path):
    import asyncio
    import hcl_mcp.server as srv
    obj = _write(tmp_path, "room.obj", _CLEAN_ROOM)
    with pytest.raises(ValueError, match="up_axis"):
        asyncio.run(srv.check_geometry(obj, material_map=_ROOM_MAP, units="m",
                                       up_axis="sideways"))


def test_mcp_import_geometry_strict_passthrough_raises(tmp_path, monkeypatch):
    """MCP import_geometry had no strict= param, so the Python-API strict=True behaviour
    (raise on error-severity health findings) was unreachable through MCP."""
    import asyncio
    import hcl_mcp.server as srv
    obj = _write(tmp_path, "bad.obj", _TWO_COPLANAR)
    mp = {"wall_a": {"refl": 0.5}, "wall_b": {"refl": 0.5}}
    with pytest.raises(GeometryHealthError):
        asyncio.run(srv.import_geometry(obj, material_map=mp, units="m", up_axis="Z",
                                        run=False, strict=True,
                                        work_dir=str(tmp_path)))


# --- Task 13: whole-suite (check_geometry_health) validation against real fixtures -------
#
# The tests above exercise individual checks (check_coincident_surfaces, check_enclosure)
# directly against office_room.obj. These exercise the top-level check_geometry_health
# entry point -- the same one the MCP tool and import_geometry call -- against both the
# published reference model and a second real model with internal shading (blinds).


def _load_fixture(obj_name="office_room.obj", map_name="office_room_material_map.json"):
    """Parsed OBJ + resolved material map for a bundled fixture."""
    from hcl_radiance.geometry_import import resolve_spec, split_map_metadata
    with open(os.path.join(_FIXTURES, obj_name)) as fh:
        parsed = parse_obj(fh.read())
    with open(os.path.join(_FIXTURES, map_name)) as fh:
        mm, _scalars = split_map_metadata(json.load(fh))
    return parsed, {g: resolve_spec(v)[0] for g, v in mm.items()}


def test_office_room_fixture_has_no_error_findings():
    """The spec requires the reference model to come back clean of ERROR-severity
    findings. It does NOT require zero findings overall: the fixture's glazing pane and
    four luminaire emitter patches are legitimately open-shell (single-quad, no back
    face), so NOT_ENCLOSED is expected to fire at `warning` -- see the assertion below."""
    parsed, resolved = _load_fixture()
    r = check_geometry_health(parsed, resolved)
    errors = [f for f in r["findings"] if f["severity"] == "error"]
    assert errors == [], [(f["code"], f["message"]) for f in errors]

    # Document the expected warning explicitly so a future regression that changes its
    # shape (count, code, or boundary-edge total) is visible here rather than silently
    # swallowed by the error-only assertion above.
    warnings = [f for f in r["findings"] if f["severity"] == "warning"]
    assert len(warnings) == 1
    assert warnings[0]["code"] == "NOT_ENCLOSED"
    assert warnings[0]["detail"]["boundary_edges"] == 20


def test_every_error_and_warning_carries_a_fix():
    parsed, resolved = _load_fixture()
    r = check_geometry_health(parsed, resolved)
    for f in r["findings"]:
        if f["severity"] in ("error", "warning"):
            assert f["fix"], f["code"]


def test_blinds_fixture_runs_without_crashing():
    """Real internal-shading geometry: the checks must survive it, whatever they report."""
    import os.path as _p
    blinds = _p.join(_p.dirname(_FIXTURES), "..", "hcl_validation", "inputs",
                     "geometry", "office_room_blinds.obj")
    if not _p.exists(blinds):
        pytest.skip("office_room_blinds.obj not present")
    with open(blinds) as fh:
        parsed = parse_obj(fh.read())
    mm = {g: {"refl": 0.5} for g in parsed["groups"]}
    r = check_geometry_health(parsed, mm)
    assert set(r) == {"ok", "counts", "findings", "checked", "skipped", "confidence"}


# ---------------------------------------------------------------------------
# Documentation-drift guard.
#
# Twice now a finding code has shipped in geometry_health.py without a matching
# entry in docs/technical-reference.md, and the drift sat unnoticed until someone
# happened to compare the two by hand. This section makes that comparison a test.
# ---------------------------------------------------------------------------

import ast
import re
from pathlib import Path

# Resolved relative to THIS file, not the shell cwd or an absolute path, so the
# suite passes regardless of where pytest is invoked from.
_SRC_FILE = Path(__file__).parent.parent / "src" / "hcl_radiance" / "geometry_health.py"
_DOC_FILE = Path(__file__).parent.parent / "docs" / "technical-reference.md"


def _extract_source_codes():
    """(code -> severity) for every `finding(...)` call in geometry_health.py.

    Uses `ast` rather than a regex. Every `finding(...)` call in the module wraps
    its arguments across lines:

        return [finding(
            "COINCIDENT_SURFACES", "error", "geometry",
            f"...",

    A regex anchored to something like `finding\\(\\s*"([A-Z_]+)"` (code expected
    on the SAME line as the open-paren) matches nothing against this module, and
    the drift-guard this test exists to provide would silently pass on an empty
    set -- exactly the failure mode we're defending against. Walking the AST and
    reading the first two positional string-constant arguments of every call
    whose callee is named `finding` sidesteps line-wrapping entirely and is
    immune to reformatting, so it is used in preference to a regex here.
    """
    tree = ast.parse(_SRC_FILE.read_text())
    codes = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "finding"):
            continue
        args = node.args
        if (len(args) >= 2
                and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str)
                and isinstance(args[1], ast.Constant) and isinstance(args[1].value, str)):
            codes[args[0].value] = args[1].value
    return codes


# The module ships 10 finding codes today (verified above via `ast`). If a future
# reformat of geometry_health.py somehow defeats the AST walk (e.g. `finding` gets
# aliased or called indirectly) this floor catches the resulting empty/partial
# extraction and fails LOUDLY, rather than letting the per-code assertions below
# pass vacuously over zero codes -- the exact silent-pass failure mode this test
# exists to prevent. Lower this only if a code is deliberately removed, and raise
# it when a code is added.
_MIN_KNOWN_CODES = 10


def _extract_doc_severities():
    """(code -> documented severity) parsed out of technical-reference.md.

    Doc lines look like:
        - `CODE` (**severity**, `function_name`, `:line`) -- explanation
    with one exception where several codes share one entry:
        - `A`, `B`, `C` (all **severity**, `function_name`, `:line`) -- explanation
    Both are matched by allowing one-or-more backtick-quoted codes ahead of an
    optional "all" before the bolded severity word.
    """
    doc = _DOC_FILE.read_text()
    pattern = re.compile(
        r'^\s*-\s+((?:`[A-Z_]{3,}`,?\s*)+)\(?(?:all\s+)?\*\*(error|warning|info)\*\*',
        re.MULTILINE,
    )
    severities = {}
    for m in pattern.finditer(doc):
        codes_blob, sev = m.group(1), m.group(2)
        for code in re.findall(r'`([A-Z_]{3,})`', codes_blob):
            severities[code] = sev
    return severities


def test_every_finding_code_extraction_is_not_vacuous():
    """Guard the guard: if this ever finds fewer than the known-shipping count,
    the extraction itself is broken (e.g. defeated by a reformat) and every other
    assertion in this section would otherwise pass vacuously over an empty set."""
    codes = _extract_source_codes()
    assert codes, (
        "_extract_source_codes() found ZERO finding(...) calls in "
        f"{_SRC_FILE}. The AST extraction is broken -- fix it before trusting "
        "any other assertion in this file.")
    assert len(codes) >= _MIN_KNOWN_CODES, (
        f"_extract_source_codes() found only {len(codes)} finding code(s) "
        f"({sorted(codes)}), fewer than the {_MIN_KNOWN_CODES} known to ship. "
        "The extraction likely broke on a reformat -- fix it before trusting "
        "any other assertion in this file.")


def test_every_finding_code_is_documented_with_the_correct_severity():
    """Every code `finding()` can emit must appear in docs/technical-reference.md
    §4.5a with the SAME severity it carries in source. This is the regression
    test for the actual incident: a finding code shipped and the doc went stale
    until someone noticed by hand."""
    source_codes = _extract_source_codes()
    doc_severities = _extract_doc_severities()

    undocumented = sorted(c for c in source_codes if c not in doc_severities)
    assert not undocumented, (
        f"finding code(s) {undocumented} are emitted by geometry_health.py but "
        f"not documented in {_DOC_FILE.name}. Add each one to §4.5a as "
        "`- `CODE` (**severity**, `function_name`, `:line`) -- explanation` "
        "with the severity it actually carries in source.")

    mismatched = sorted(
        c for c in source_codes
        if c in doc_severities and doc_severities[c] != source_codes[c]
    )
    assert not mismatched, (
        "documented severity drifted from the source severity for "
        f"{mismatched}: " +
        "; ".join(
            f"`{c}` is `{source_codes[c]}` in source but documented as "
            f"`{doc_severities[c]}`" for c in mismatched
        ) +
        f". Fix the severity word in {_DOC_FILE.name} §4.5a to match source "
        "(or, if source is wrong, fix source -- but the two must agree)."
    )


# ---- unit scaling: every tolerance here is absolute metres, so the model's scale must reach
# ---- the checks. Getting this wrong breaks BOTH ways (missed z-fight / valid model hard-failed).

_FIXDIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _rescaled_obj(text, factor):
    """Same geometry, vertices re-expressed in another unit system."""
    out = []
    for ln in text.splitlines():
        p = ln.split()
        if p and p[0] == "v" and len(p) >= 4:
            out.append("v %.9g %.9g %.9g" % (float(p[1]) * factor, float(p[2]) * factor,
                                             float(p[3]) * factor))
        else:
            out.append(ln)
    return "\n".join(out) + "\n"


_UNIT_CASES = (("m", 1.0, 1.0), ("mm", 1000.0, 0.001), ("cm", 100.0, 0.01),
               ("ft", 1.0 / 0.3048, 0.3048))


def _zfight_obj(factor, sep_m=0.0005):
    """A floor plus a coplanar duplicate a real 0.5 mm above it -> a genuine z-fight."""
    L = ["g Floor"] + ["v %.9g %.9g %.9g" % (x * factor, y * factor, z * factor)
                       for x, y, z in [(0, 0, 0), (4, 0, 0), (4, 3, 0), (0, 3, 0)]]
    L += ["g Floor2"] + ["v %.9g %.9g %.9g" % (x * factor, y * factor, z * factor)
                         for x, y, z in [(0, 0, sep_m), (4, 0, sep_m),
                                         (4, 3, sep_m), (0, 3, sep_m)]]
    return "\n".join(L + ["f 1 2 3 4", "f 5 6 7 8"]) + "\n"


def test_real_zfight_is_caught_in_every_unit_system():
    mm = {"Floor": {"type": "floor"}, "Floor2": {"type": "floor"}}
    for name, factor, scale in _UNIT_CASES:
        rep = check_geometry_health(parse_obj(_zfight_obj(factor)), mm, scale=scale)
        codes = [f["code"] for f in rep["findings"]]
        assert "COINCIDENT_SURFACES" in codes, f"{name}: real 0.5 mm z-fight missed"


def test_valid_model_is_not_hard_failed_in_every_unit_system():
    # REGRESSION (false POSITIVE): _END_CAP_MAX_AREA_M2 is an absolute 2 m2 gate, so an unscaled
    # mm model read a 1x1 m end-cap as 1e6 units2, skipped the containment exclusion, and errored.
    src = open(os.path.join(_FIXDIR, "office_room.obj")).read()
    mm = {"Rad_Floor_R020": {"type": "floor"}, "Rad_Glazing_T073": {"type": "glass"}}
    for name, factor, scale in _UNIT_CASES:
        rep = check_geometry_health(parse_obj(_rescaled_obj(src, factor)), mm, scale=scale)
        assert rep["ok"], (f"{name}: valid reference model reported "
                           f"{rep['counts']['error']} error(s): "
                           f"{[f['code'] for f in rep['findings'] if f['severity'] == 'error']}")


def test_metre_path_is_unchanged_by_the_scale_parameter():
    # scale=1.0 must be byte-identical to omitting it, so no metre-model result moves.
    src = open(os.path.join(_FIXDIR, "office_room.obj")).read()
    mm = {"Rad_Floor_R020": {"type": "floor"}, "Rad_Glazing_T073": {"type": "glass"}}
    parsed = parse_obj(src)
    assert check_geometry_health(parsed, mm) == check_geometry_health(parsed, mm, scale=1.0)


def test_non_planar_deviation_is_reported_in_metres():
    # a real 20 mm warp must read ~0.02 m, not the raw 20 (model units) it reported in mm
    L = ["g Wall"] + ["v %.9g %.9g %.9g" % (x * 1000.0, y * 1000.0, z * 1000.0)
                      for x, y, z in [(0, 0, 0), (4, 0, 0), (4, 0, 3), (0, 0.02, 3)]]
    rep = check_geometry_health(parse_obj("\n".join(L + ["f 1 2 3 4"]) + "\n"),
                               {"Wall": {"type": "plastic", "refl": 0.5}}, scale=0.001)
    np = [f for f in rep["findings"] if f["code"] == "NON_PLANAR_FACE"]
    if np:                                  # only assert the unit, not that it fires
        dev = np[0]["detail"]["worst_deviation_m"]
        assert dev < 0.1, f"deviation {dev} looks like raw model units, not metres"
