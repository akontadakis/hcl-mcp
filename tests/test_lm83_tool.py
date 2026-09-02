"""The lm83_daylight MCP tool, driven end to end against real Radiance.

The point of this module is that the tool is WIRED to the method, not merely registered.
An LM-83 tool that returns a plausible sDA while the blind never moves is the failure mode
worth guarding, so the load-bearing test here asserts the trigger fired and that operating
the blind changed the answer.

pytest-asyncio is not installed; the async tools are driven with asyncio.run.
"""
import asyncio
import os
import shutil

import pytest

from hcl_mcp.server import lm83_daylight, _TOOL_FUNCS

pytestmark = pytest.mark.skipif(
    shutil.which("rfluxmtx") is None or shutil.which("dctimestep") is None,
    reason="Radiance not installed")

# A 4 x 4 x 3 m room with a 2 x 1.5 m south window, as an OBJ. The south wall is built from
# four faces around the opening so the window is a real hole, not a coplanar overlay.
_OBJ = """v 0 0 0
v 4 0 0
v 4 4 0
v 0 4 0
v 0 0 3
v 4 0 3
v 4 4 3
v 0 4 3
v 1 0 0.8
v 3 0 0.8
v 3 0 2.3
v 1 0 2.3
v 0 0 0.8
v 4 0 0.8
v 0 0 2.3
v 4 0 2.3
usemtl floor_mat
f 1 2 3 4
usemtl wall_mat
f 5 8 7 6
f 4 3 7 8
f 1 4 8 5
f 2 6 7 3
f 1 2 14 13
f 15 16 6 5
f 13 15 12 9
f 10 11 16 14
usemtl glazing
f 9 10 11 12
"""

_MAP = {
    "floor_mat": {"type": "floor", "refl": 0.2},
    "wall_mat": {"type": "plastic", "refl": 0.5},
    "glazing": {"type": "glass", "tvis": 0.64},
}

# December, not June: at Athens a June sun sits 55-74 deg up and its beam lands on the floor
# rather than the workplane, so the trigger is unfirable and the test proves nothing.
_WEA = ("place ATHENS_GRC\nlatitude 37.9\nlongitude -23.7\ntime_zone -30\n"
        "site_elevation 28.0\nweather_data_file_units 1\n"
        "12 21 10.5 850 100\n12 21 11.5 850 100\n"
        "12 21 12.5 850 100\n12 21 13.5 850 100\n")

_FAST = {"v_params": "-ab 2 -ad 256 -lw 1e-2", "d_params": "-c 300 -ab 1 -ad 256"}


def _setup(tmp_path):
    work = str(tmp_path)
    os.makedirs(work, exist_ok=True)
    obj = os.path.join(work, "room.obj")
    with open(obj, "w") as fh:
        fh.write(_OBJ)
    wea = os.path.join(work, "t.wea")
    with open(wea, "w") as fh:
        fh.write(_WEA)
    points = [[x, y, 0.8, 0.0, 0.0, 1.0]
              for y in (0.6, 1.2, 1.8, 2.4, 3.0, 3.6) for x in (1.0, 2.0, 3.0)]
    return work, obj, wea, points


def _call(**kw):
    return asyncio.run(lm83_daylight(**kw))


def test_the_tool_is_registered():
    assert lm83_daylight in _TOOL_FUNCS


def test_it_returns_lm83_metrics_and_the_blind_actually_operates(tmp_path):
    """The load-bearing check. sDA and ASE alone prove nothing: if the trigger never fires,
    every hour resolves to blinds-open and the tool reports the unshaded upper bound while
    looking entirely healthy."""
    work, obj, wea, points = _setup(tmp_path)
    out = _call(obj_path=obj, material_map=_MAP, wea=wea, points=points,
                floor_area_m2=16.0, work_dir=work, **_FAST)
    assert out["ran"] is True, out.get("reason") or out.get("error")
    assert out["blind_hours"] > 0, "the trigger never fired: the sun pass is not driving states"
    m = out["metrics"]
    assert 0.0 <= m["sDA"] <= 1.0
    assert len(m["per_point_DA"]) == len(points)
    assert out["blind_source"] == "lm83_2_2_7_unknown_shade"

    # ASE itself is necessarily 0.0 on a 4-hour wea -- the criterion is >250 h, so a bound
    # of 0<=ASE<=1 would pass against an ASE that was never computed at all. The honest
    # check on a short run is the per-point hour count behind it, which must show the
    # near-window points accumulating direct sun and the back of the room none.
    hours = m["ASE_per_point_hours"]
    assert len(hours) == len(points)
    assert max(hours) > 0, "no point accumulated any direct-sun hour: ASE is not computed"
    assert min(hours) == 0, "every point is sunlit; expected the back of the room shaded"
    front = hours[:3]     # y = 0.6 m, nearest the window
    back = hours[-3:]     # y = 3.6 m, furthest
    assert min(front) > max(back), (
        f"direct-sun hours do not fall with distance from the window: {hours}")


def test_the_conformance_flag_is_false_and_names_the_out_of_scope_clauses(tmp_path):
    """A caller must not be able to read this number as an LM-83 submission. The model-input
    departure is unconditional, so the flag can never come back true."""
    work, obj, wea, points = _setup(tmp_path)
    out = _call(obj_path=obj, material_map=_MAP, wea=wea, points=points,
                floor_area_m2=16.0, work_dir=work, **_FAST)
    cond = out["metrics"]["conditions"]
    assert cond["lm83_method_conformant"] is False
    assert any("2.2.8" in d for d in cond["departures"])


def test_grid_conditions_are_measured_from_the_points_not_asserted(tmp_path):
    """2.2.5's spacing and workplane height are properties of the grid, so a caller cannot
    declare them -- the 0.6 m spacing and 0.8 m height here must be recovered."""
    work, obj, wea, points = _setup(tmp_path)
    out = _call(obj_path=obj, material_map=_MAP, wea=wea, points=points,
                floor_area_m2=16.0, work_dir=work, **_FAST)
    grid = out["metrics"]["conditions"]["grid"]
    assert abs(grid["spacing_m"] - 0.6) < 0.05
    assert abs(grid["workplane_z"] - 0.8) < 0.05
    assert grid["n_points"] == 18


def test_a_darker_blind_cannot_raise_sda(tmp_path):
    """2.2.7's 5% unknown-shade default must admit no more light than a 20% white louver.
    This only has force because the trigger fires -- with blinds always open the two runs
    are identical and the assertion is vacuous."""
    work_a, obj_a, wea_a, points = _setup(tmp_path / "louver")
    work_b, obj_b, wea_b, _ = _setup(tmp_path / "unknown")
    louver = _call(obj_path=obj_a, material_map=_MAP, wea=wea_a, points=points,
                   floor_area_m2=16.0, work_dir=work_a,
                   blind={"shade_type": "louver", "reflectance": 0.85}, **_FAST)
    unknown = _call(obj_path=obj_b, material_map=_MAP, wea=wea_b, points=points,
                    floor_area_m2=16.0, work_dir=work_b, **_FAST)
    assert louver["ran"] and unknown["ran"]
    assert louver["blind_hours"] > 0 and unknown["blind_hours"] > 0
    assert unknown["metrics"]["sDA"] <= louver["metrics"]["sDA"]
    # <= alone would hold if the blind never entered the calculation at all and both runs
    # returned the same number. On this scene the two T matrices are far enough apart to
    # separate the results, so require that they actually differ.
    assert unknown["metrics"]["sDA"] < louver["metrics"]["sDA"], (
        "the 5% and 20% blinds give an identical sDA; the T matrix is not reaching the "
        "multiply, so this comparison is vacuous")


def test_a_dry_run_still_reports_how_the_windows_were_grouped(tmp_path):
    """run=False must say WHY it did not run and show the grouping. 2.2.6 grouping drives
    both the trigger and the state count and is decided before any Radiance step, so it is
    the main thing a dry run is for; a bare command list with no reason also leaves a caller
    unable to tell a deliberate preview from a missing Radiance install."""
    work, obj, wea, points = _setup(tmp_path)
    out = _call(obj_path=obj, material_map=_MAP, wea=wea, points=points,
                floor_area_m2=16.0, work_dir=work, run=False, **_FAST)
    assert out["ran"] is False
    assert out["reason"]
    assert out["commands"]
    assert len(out["window_groups"]) == 1
    assert out["blind_source"] == "lm83_2_2_7_unknown_shade"


def test_no_quality_setting_can_put_ambient_bounces_into_the_sun_pass(tmp_path):
    """3.2.2 defines ASE and the 2.2.6 trigger at ZERO bounce. The ambient knobs this tool
    exposes tune V and D only; if any of them reached the solar rcontrib, inter-reflected
    light would be counted as direct sun -- the exact artefact that a faint uniform wash was
    once mistaken for. Assert it on the emitted plan, where it is checkable without a run."""
    work, obj, wea, points = _setup(tmp_path)
    out = _call(obj_path=obj, material_map=_MAP, wea=wea, points=points,
                floor_area_m2=16.0, work_dir=work, run=False,
                v_params="-ab 6 -ad 4096", d_params="-ab 6", quality="high")
    solar = [c for c in out["commands"] if "rcontrib" in c and "-m solar" in c]
    assert solar, "no solar rcontrib step was planned"
    for cmd in solar:
        assert "-ab 0" in cmd, f"sun pass is not zero-bounce: {cmd}"


def test_a_named_sensor_set_resolves_to_the_same_grid_as_inline_points(tmp_path):
    """sensor_set is a supported input, and n_pts (which sets rcontrib -y) and the measured
    point rows come from two different helpers -- so they can disagree without any error."""
    from hcl_mcp.server import sensors
    work, obj, wea, points = _setup(tmp_path)
    asyncio.run(sensors(action="create", name="grid", points=points, work_dir=work))
    out = _call(obj_path=obj, material_map=_MAP, wea=wea, sensor_set="grid",
                floor_area_m2=16.0, work_dir=work, **_FAST)
    assert out["ran"] is True, out.get("reason") or out.get("error")
    assert len(out["metrics"]["per_point_DA"]) == len(points)
    assert out["metrics"]["conditions"]["grid"]["n_points"] == len(points)


def test_a_declared_window_group_overrides_auto_clustering_and_keeps_its_role(tmp_path):
    """Role cannot be inferred from azimuth, and 2.2.6 asks that view groups close before
    clerestory ones -- so a declared role has to survive into the result."""
    work, obj, wea, points = _setup(tmp_path)
    out = _call(obj_path=obj, material_map=_MAP, wea=wea, points=points,
                floor_area_m2=16.0, work_dir=work,
                window_groups=[{"name": "view_s", "face_indices": [9], "role": "view"}],
                **_FAST)
    assert out["ran"] is True, out.get("reason") or out.get("error")
    group = out["window_groups"][0]
    assert group["name"] == "view_s"
    assert group["role"] == "view"
    assert group["source"] == "declared"


def test_a_latitude_outside_the_supporting_research_band_is_recorded(tmp_path):
    """2.2.1's 37-48 deg caveat is only useful if the parameter actually reaches it."""
    work, obj, wea, points = _setup(tmp_path)
    out = _call(obj_path=obj, material_map=_MAP, wea=wea, points=points,
                floor_area_m2=16.0, work_dir=work, latitude=5.0, **_FAST)
    assert any("latitude" in d for d in out["metrics"]["conditions"]["departures"])


def test_an_oversized_trigger_area_is_refused_before_any_radiance_runs(tmp_path):
    work, obj, wea, points = _setup(tmp_path)
    out = _call(obj_path=obj, material_map=_MAP, wea=wea, points=points,
                areas=[{"name": "floor", "area_m2": 2000.0,
                        "point_indices": list(range(len(points)))}],
                work_dir=work, **_FAST)
    assert out["ran"] is False
    assert "10,000 sf" in out["reason"]


def test_areas_must_be_given_one_way_or_the_other(tmp_path):
    """2.2.6 evaluates the trigger per area. Silently pooling every facade into one area
    dilutes the sunlit fraction and closes the blinds later than the standard requires, so
    the caller has to choose rather than get a default."""
    work, obj, wea, points = _setup(tmp_path)
    with pytest.raises(ValueError, match="per analysis area"):
        _call(obj_path=obj, material_map=_MAP, wea=wea, points=points, work_dir=work,
              **_FAST)


def test_a_model_with_no_glazing_is_refused_with_a_reason(tmp_path):
    """No glass face means no window group, and 2.2.6 requires every exterior window to
    carry an operable blind. Failing loudly beats reporting an unshaded sDA."""
    work, obj, wea, points = _setup(tmp_path)
    opaque = dict(_MAP, glazing={"type": "plastic", "refl": 0.5})
    out = _call(obj_path=obj, material_map=opaque, wea=wea, points=points,
                floor_area_m2=16.0, work_dir=work, **_FAST)
    assert out["ran"] is False
    assert "glass" in out["reason"]
