"""What the LM-83 plan is made of, checked without running Radiance.

`plan_lm83` writes its small input files (matrices, senders, blockers) and returns the step
list; nothing here needs the engine. The physics of the result is tested against a ray trace
in test_lm83_reference.py; these tests pin the decisions that test cannot isolate.
"""
import math
import os
import re

import pytest

from hcl_core.klems import klems_projected_solid_angles
from hcl_core.lm83 import add_direct_sun
from hcl_radiance.geometry_obj import parse_obj
from hcl_radiance.lm83_run import plan_lm83
from test_lm83_tool import _MAP, _OBJ

_SCENE = {"materials": ["mat.rad"], "geometry": "room.rad", "exterior": [], "sky_color": [1, 1, 1]}

#: The test room with a second window, on the west wall, in its own glazing material.
#: Its pane is wound outward (normal -x), as the south pane is: a group's reported azimuth
#: is read from the winding.
TWO_WINDOW_OBJ = _OBJ.replace("f 1 4 8 5\n", "") + """v 0 1 0.8
v 0 3 0.8
v 0 3 2.3
v 0 1 2.3
v 0 0 0.8
v 0 4 0.8
v 0 0 2.3
v 0 4 2.3
usemtl wall_mat
f 1 4 22 21
f 23 24 8 5
f 21 17 20 23
f 18 22 24 19
usemtl glazing_w
f 20 19 18 17
"""
TWO_WINDOW_MAP = {**_MAP, "glazing_w": {"type": "glass", "tvis": 0.64}}


def _plan(tmp_path, obj=_OBJ, material_map=_MAP, **kwargs):
    return plan_lm83(_SCENE, parse_obj(obj), material_map, "t.wea", "p.pts", 18,
                     work_dir=str(tmp_path), interior_point=(2.0, 2.0, 0.8), **kwargs)


def _first_transmission_row(xml_path):
    text = open(xml_path).read()
    block = text[text.index("Transmission Front"):]
    data = block[block.index("<ScatteringData>") + len("<ScatteringData>"):]
    return [float(v) for v in data.strip().splitlines()[0].rstrip(",").split(",")]


def test_the_closed_blind_stands_behind_the_glazing(tmp_path):
    """LM-83 2.2.7 gives the SHADE's transmittance. The window does not stop being glazed when
    the shade comes down: 5 % of the 64 % that the glass passes, not 5 % of everything."""
    _plan(tmp_path)
    row = _first_transmission_row(os.path.join(tmp_path, "t_blind.xml"))
    weights = klems_projected_solid_angles()
    through = sum(value * weight for value, weight in zip(row, weights))
    assert math.isclose(through, 0.05 * 0.64, rel_tol=1e-4)


def test_the_beam_a_closed_fabric_shade_still_passes_is_its_openness_factor(tmp_path):
    """2.2.7: "The specular transmittance should be equal to the openness factor". A shade of
    5 % VLT and 3 % openness passes 3 % of the beam -- not 3/5 of it, which is what dividing
    the openness by the VLT gave the blind trigger."""
    plan = _plan(tmp_path, blind={"shade_type": "fabric", "vlt": 0.05, "openness": 0.03})
    assert list(plan["beam_pass_fraction"].values()) == [pytest.approx(0.03)]


def test_the_direct_sun_pass_adds_no_pane_of_its_own(tmp_path):
    """The room geometry already holds the glazing, at its real transmittance. A second pane
    laid over it at 100 % made the pair coincident, and the clear one won: direct sun came out
    1/tvis too strong, for ASE and for the trigger alike."""
    plan = _plan(tmp_path)
    for name in os.listdir(tmp_path):
        if name.endswith(".rad"):
            assert not re.search(r"void\s+glass\b", open(os.path.join(tmp_path, name)).read()), name
    assert not any("_glazing.rad" in command for command in plan["commands"])


def test_with_one_window_group_its_sun_is_the_whole_models_sun(tmp_path):
    plan = _plan(tmp_path)
    assert list(plan["sun_ill"].values()) == [plan["sun_total_ill"]]


def test_each_groups_sun_pass_shuts_the_other_groups_windows(tmp_path):
    """The trigger needs to know how much beam EACH group admits. All the glazing is in the
    room geometry, so a group is isolated by standing an opaque sheet just outside every
    other group's panes."""
    plan = _plan(tmp_path, obj=TWO_WINDOW_OBJ, material_map=TWO_WINDOW_MAP)
    names = [group["name"] for group in plan["window_groups"]]
    assert len(names) == 2
    octrees = {name: next(c for c in plan["commands"]
                          if c.startswith("oconv") and f"sun_{name}.oct" in c) for name in names}
    for name in names:
        other = next(n for n in names if n != name)
        assert f"{other}_blocked.rad" in octrees[name] and f"{name}_blocked.rad" not in octrees[name]
    whole = next(c for c in plan["commands"] if c.startswith("oconv") and "sun_all.oct" in c)
    assert "_blocked.rad" not in whole


def test_a_blocker_sits_outside_the_pane_not_on_it(tmp_path):
    """Coincident surfaces are what broke the old pass. The sheet for the south window (in the
    plane y = 0, room at y > 0) must lie at y < 0."""
    plan = _plan(tmp_path, obj=TWO_WINDOW_OBJ, material_map=TWO_WINDOW_MAP)
    south = next(g["name"] for g in plan["window_groups"] if abs(g["azimuth_deg"] - 180.0) < 1)
    text = open(os.path.join(tmp_path, f"{south}_blocked.rad")).read()
    reals = [float(v) for v in text.split("\n12 ")[1].split()[:12]]
    ys = reals[1::3]
    assert all(-0.05 < y < 0.0 for y in ys), ys


# ---- adding the exact direct sun to the operated illuminance ----

def test_direct_sun_is_added_for_open_groups_and_not_for_closed_ones():
    operated = [[100.0, 100.0, 100.0]]                      # one point, three hours
    sun = {"south": [[5000.0, 5000.0, 5000.0]], "west": [[70.0, 70.0, 70.0]]}
    states = [frozenset(), frozenset({"south"}), frozenset({"south", "west"})]
    assert add_direct_sun(operated, states, sun) == [[5170.0, 170.0, 100.0]]


def test_adding_direct_sun_leaves_its_inputs_alone():
    operated = [[100.0]]
    add_direct_sun(operated, [frozenset()], {"south": [[5000.0]]})
    assert operated == [[100.0]]
