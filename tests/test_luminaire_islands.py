"""A luminaire group holding several separate housings must yield one emitter per housing.

Regression: `marker_positions` returned a single centroid for a whole group, so N fittings that
share one `usemtl` imported as ONE emitter at their common centre. The run completed normally at
1/N of the drawn installed load, with nothing in the return to distinguish it from a genuine
single fitting.

Separate housings are disconnected mesh islands (no shared vertices), so they can be told apart
from one modelled fitting without asking the caller to name materials a particular way.
"""
from hcl_radiance.geometry_obj import parse_obj, marker_positions

# Four unit-square "housings" at z=3, one per quadrant, ALL under one usemtl.
_FOUR_PANELS = """
usemtl Rad_Luminaire
v -1.5 -1.5 3.0
v -0.5 -1.5 3.0
v -0.5 -0.5 3.0
v -1.5 -0.5 3.0
f 1 2 3 4
v 0.5 -1.5 3.0
v 1.5 -1.5 3.0
v 1.5 -0.5 3.0
v 0.5 -0.5 3.0
f 5 6 7 8
v -1.5 0.5 3.0
v -0.5 0.5 3.0
v -0.5 1.5 3.0
v -1.5 1.5 3.0
f 9 10 11 12
v 0.5 0.5 3.0
v 1.5 0.5 3.0
v 1.5 1.5 3.0
v 0.5 1.5 3.0
f 13 14 15 16
"""

# One fitting built from two faces that SHARE an edge -> a single island, must stay one emitter.
_ONE_SPLIT_FITTING = """
usemtl Rad_Luminaire
v -1.0 -0.5 3.0
v 0.0 -0.5 3.0
v 0.0 0.5 3.0
v -1.0 0.5 3.0
f 1 2 3 4
v 1.0 -0.5 3.0
v 1.0 0.5 3.0
f 2 5 6 3
"""


def test_four_disconnected_housings_give_four_markers():
    pts = marker_positions(parse_obj(_FOUR_PANELS), group="Rad_Luminaire")
    assert len(pts) == 4, f"expected one marker per housing, got {len(pts)}: {pts}"


def test_each_marker_sits_at_its_own_housing_centre():
    pts = sorted(marker_positions(parse_obj(_FOUR_PANELS), group="Rad_Luminaire"))
    want = sorted([(-1.0, -1.0, 3.0), (1.0, -1.0, 3.0), (-1.0, 1.0, 3.0), (1.0, 1.0, 3.0)])
    for got, exp in zip(pts, want):
        assert all(abs(a - b) < 1e-9 for a, b in zip(got, exp)), f"{got} != {exp}"


def test_no_marker_lands_at_the_group_centroid():
    """The collapse put a single emitter at (0,0,3) -- the centre of an empty ceiling."""
    pts = marker_positions(parse_obj(_FOUR_PANELS), group="Rad_Luminaire")
    assert not any(abs(p[0]) < 1e-9 and abs(p[1]) < 1e-9 for p in pts), (
        "an emitter sits at the group centroid, where no housing is")


def test_one_fitting_of_several_connected_faces_stays_one_marker():
    """Multi-face single fittings must NOT be split -- connectivity is the discriminator."""
    pts = marker_positions(parse_obj(_ONE_SPLIT_FITTING), group="Rad_Luminaire")
    assert len(pts) == 1, f"connected faces split into {len(pts)} emitters"


def test_explicit_point_markers_still_win():
    """A `p` primitive is an explicit authored marker and must override island detection.

    Markers are tagged with the active `g`/`o` group (not `usemtl`), so the fixture names the
    group both ways — that is the existing parse contract, unchanged here.
    """
    obj = ("g Rad_Luminaire\n" + _FOUR_PANELS + "\nv 0.0 0.0 2.5\np 17\n")
    pts = marker_positions(parse_obj(obj), group="Rad_Luminaire")
    assert pts == [(0.0, 0.0, 2.5)]


def test_electric_lights_payload_carries_every_housing():
    from hcl_radiance.geometry_import import luminaire_electric_lights
    parsed = parse_obj(_FOUR_PANELS)
    mmap = {"Rad_Luminaire": {"type": "luminaire", "ies": "/tmp/x.ies"}}
    out, _warn = luminaire_electric_lights(parsed, mmap, scale=1.0, up_axis="Z")
    positions = [p for spec in out for p in spec["placement"]["positions"]]
    assert len(positions) == 4, f"electric_lights carries {len(positions)} emitters, expected 4"
