"""End-to-end LM-83: real geometry, real Radiance, real blind operation.

The policy layer's arithmetic is unit-tested in test_lm83.py. What this module proves is
that it is WIRED -- that the zero-bounce sun matrix actually drives the trigger, that the
trigger actually selects among simulated states, and that the selection actually changes
the reported sDA. Every one of those links can be broken while every unit test passes.
"""
import os
import shutil
import pytest

from hcl_core.lm83 import lm83_schedule
from hcl_radiance.geometry_obj import parse_obj
from hcl_radiance.lm83_run import plan_lm83, run_lm83

pytestmark = pytest.mark.skipif(
    shutil.which("rfluxmtx") is None or shutil.which("dctimestep") is None,
    reason="Radiance not installed")

_MAT = """void plastic wall
0
0
5 0.5 0.5 0.5 0 0
void plastic floor
0
0
5 0.2 0.2 0.2 0 0
"""

_ROOM = """floor polygon flr
0
0
12  0 0 0  4 0 0  4 4 0  0 4 0
wall polygon ceil
0
0
12  0 0 3  0 4 3  4 4 3  4 0 3
wall polygon back
0
0
12  0 4 0  4 4 0  4 4 3  0 4 3
wall polygon left
0
0
12  0 0 0  0 4 0  0 4 3  0 0 3
wall polygon right
0
0
12  4 0 0  4 0 3  4 4 3  4 4 0
wall polygon south_a
0
0
12  0 0 0  4 0 0  4 0 0.8  0 0 0.8
wall polygon south_b
0
0
12  0 0 2.3  4 0 2.3  4 0 3  0 0 3
wall polygon south_c
0
0
12  0 0 0.8  0 0 2.3  1 0 2.3  1 0 0.8
wall polygon south_d
0
0
12  3 0 0.8  3 0 2.3  4 0 2.3  4 0 0.8
"""

_WINDOW_OBJ = """v 1 0 0.8
v 3 0 0.8
v 3 0 2.3
v 1 0 2.3
usemtl glazing
f 1 2 3 4
"""

_MAP = {"glazing": {"type": "glass", "tvis": 0.64}}
_FAST = {"v_params": "-ab 2 -ad 256 -lw 1e-2", "d_params": "-c 300 -ab 1 -ad 256"}


def _wea(work_dir, hours=(10.5, 11.5, 12.5, 13.5)):
    """A handful of clear DECEMBER hours: a low sun that reaches the workplane.

    December, not June, and the difference decides whether this file tests anything. At
    Athens on 21 June the sun is 55-74 deg up between 09:30 and 14:30, so the beam through
    a window with a 2.3 m head lands on the FLOOR within about a metre of the wall and
    never touches a 0.8 m workplane. The zero-bounce matrix is then legitimately all
    zeros, the trigger cannot fire, and every state resolves to blinds-open -- which reads
    exactly like a broken sun pass and was diagnosed as one
    (.scratch/lm83/open-sun-calibration.md, now closed). On 21 December the sun is ~28 deg
    up, the patch reaches the grid, and the sensors see 25-37 klx.
    """
    path = os.path.join(work_dir, "t.wea")
    with open(path, "w") as fh:
        fh.write("place ATHENS_GRC\nlatitude 37.9\nlongitude -23.7\n"
                 "time_zone -30\nsite_elevation 28.0\nweather_data_file_units 1\n")
        for h in hours:
            fh.write(f"12 21 {h} 850 100\n")
    return path


def _scene(work_dir):
    with open(os.path.join(work_dir, "mat.rad"), "w") as fh:
        fh.write(_MAT)
    with open(os.path.join(work_dir, "room.rad"), "w") as fh:
        fh.write(_ROOM)
    return {"materials": [os.path.join(work_dir, "mat.rad")],
            "geometry": os.path.join(work_dir, "room.rad"),
            "exterior": [], "sky_color": [1, 1, 1]}


def _points(work_dir):
    rows = [[x, y, 0.8, 0.0, 0.0, 1.0]
            for y in (0.6, 1.2, 1.8, 2.4, 3.0, 3.6) for x in (1.0, 2.0, 3.0)]
    path = os.path.join(work_dir, "p.pts")
    with open(path, "w") as fh:
        for r in rows:
            fh.write(" ".join(str(v) for v in r) + "\n")
    return path, rows


def _areas(n_points, area_m2=16.0):
    """One trigger area: 16 m2 = 172 sf, under 2.2.6's 200 sf band, so the limit is 1."""
    return [{"name": "room", "area_m2": area_m2, "point_indices": list(range(n_points))}]


def test_plan_names_one_south_group_and_a_five_percent_blind(tmp_path):
    work = str(tmp_path)
    plan = plan_lm83(_scene(work), parse_obj(_WINDOW_OBJ), _MAP, _wea(work), "p.pts", 18,
                     work_dir=work, **_FAST)
    assert len(plan["window_groups"]) == 1
    assert round(plan["window_groups"][0]["azimuth_deg"]) == 180
    assert plan["blind_source"] == "lm83_2_2_7_unknown_shade"
    assert len(plan["states"]) == 2          # open + closed


def test_every_group_has_a_sun_series_and_a_lone_groups_is_the_whole_models(tmp_path):
    """Sharing one whole-model series between SEVERAL groups lets a closure cancel beam
    another group admitted, satisfying the criterion with the wrong blind down -- that case,
    and how each group is isolated, is in test_lm83_plan.py. With a single group there is
    nothing to separate: its sun is the model's, and one pass serves both."""
    work = str(tmp_path)
    plan = plan_lm83(_scene(work), parse_obj(_WINDOW_OBJ), _MAP, _wea(work), "p.pts", 18,
                     work_dir=work, **_FAST)
    assert set(plan["sun_ill"]) == {g["name"] for g in plan["window_groups"]}
    assert list(plan["sun_ill"].values()) == [plan["sun_total_ill"]]
    assert any("-ab 0" in c for c in plan["commands"])


def test_the_sun_pass_reads_a_hard_edged_patch_of_the_right_magnitude(tmp_path):
    """Calibrate the zero-bounce quantity itself, not just its plumbing.

    This is the assertion whose absence let a correct all-zero June result be diagnosed as
    a broken sun pass for a whole session. It pins two independent properties:

    * MAGNITUDE -- this is the one that kills the historical artefact. A 850 W/m2 direct
      normal beam at ~28 deg altitude puts roughly 850*sin(28) = 400 W/m2 on the
      horizontal, about 70 klx before glazing; through tvis 0.64 the sunlit points must
      read in the tens of thousands. The measured -ab 2 leak peaks at 120 lux, so a 10 klx
      floor sits two orders above it and well below the true value.
    * HARD EDGE. Direct sun at zero bounce either lands on a point or does not, so some
      point must read exactly zero. Note this does NOT by itself distinguish beam from
      wash: the measured -ab 2 artefact had 31 of 108 cells at zero and would pass this
      check alone. It catches the opposite failure -- a uniformly bright pass, e.g. a
      coefficient matrix that lost its binning -- which magnitude alone would accept.

    The two are independent and both are needed; neither one alone covers both directions.
    """
    work = str(tmp_path)
    pts, rows = _points(work)
    out = run_lm83(_scene(work), parse_obj(_WINDOW_OBJ), _MAP, _wea(work), pts, len(rows),
                   work_dir=work, areas=_areas(len(rows)), point_rows=rows, **_FAST)
    assert out["ran"] is True, out.get("reason") or out.get("error")

    from hcl_radiance.lm83_sun import parse_lux_matrix
    with open(os.path.join(work, "sun_all.ill")) as fh:
        lux = parse_lux_matrix(fh.read())
    flat = [v for row in lux for v in row]
    assert max(flat) > 10000, (
        f"the direct-sun pass peaks at {max(flat):.0f} lux; a low winter beam through this "
        "aperture must reach tens of thousands. A few hundred lux, spread evenly, is "
        "inter-reflected light leaking into a pass that must be zero-bounce")
    assert any(v == 0.0 for v in flat), (
        "no sensor/hour reads exactly zero, so this is not a hard-edged beam")


def test_the_full_run_produces_metrics_not_paths(tmp_path):
    """v1 of this plan built the whole policy layer and then never called it."""
    work = str(tmp_path)
    pts, rows = _points(work)
    out = run_lm83(_scene(work), parse_obj(_WINDOW_OBJ), _MAP, _wea(work), pts, len(rows),
                   work_dir=work, areas=_areas(len(rows)), point_rows=rows, **_FAST)
    assert out["ran"] is True, out.get("reason") or out.get("error")
    assert "metrics" in out
    m = out["metrics"]
    assert 0.0 <= m["sDA"] <= 1.0
    assert 0.0 <= m["ASE"] <= 1.0
    assert m["conditions"]["lm83_method_conformant"] is False   # model inputs out of scope
    assert any("2.2.8" in d for d in m["conditions"]["departures"])


def test_the_blind_trigger_actually_fires_on_a_sunny_south_room(tmp_path):
    """A 2 x 1.5 m south window under a clear low sun must put more than one point of a
    172 sf room in >=1000 lux of direct beam, so 2.2.6 closes the blind."""
    work = str(tmp_path)
    pts, rows = _points(work)
    out = run_lm83(_scene(work), parse_obj(_WINDOW_OBJ), _MAP, _wea(work), pts, len(rows),
                   work_dir=work, areas=_areas(len(rows)), point_rows=rows, **_FAST)
    assert out["ran"] is True and "metrics" in out
    assert out["blind_hours"] > 0, "the trigger never fired: sun matrix not driving states"


def test_operating_the_blind_lowers_sda_below_the_never_shaded_case(tmp_path):
    """The load-bearing wiring check. If selection is broken, the operated result equals
    the open state and this is an equality rather than a strict inequality."""
    work = str(tmp_path)
    pts, rows = _points(work)
    out = run_lm83(_scene(work), parse_obj(_WINDOW_OBJ), _MAP, _wea(work), pts, len(rows),
                   work_dir=work, areas=_areas(len(rows)), point_rows=rows,
                   declared_no_blinds=True, **_FAST)
    assert out["ran"] is True and "metrics" in out
    m = out["metrics"]
    assert "no_blind_case" in m
    # Blinds down for some hours can only remove daylight, never add it.
    assert m["sDA"] <= m["no_blind_case"]["sDA"]
    if out["blind_hours"] > 0:
        assert m["per_point_DA"] != [1.0] * len(rows) or m["no_blind_case"]["sDA"] == 1.0


def test_ase_is_computed_with_blinds_open(tmp_path):
    """3.2.6: ASE uses the blinds-open direct-sun series, so it must not move when the
    blind gets darker."""
    work = str(tmp_path)
    pts, rows = _points(work)
    common = dict(work_dir=work, areas=_areas(len(rows)), point_rows=rows, **_FAST)
    light = run_lm83(_scene(work), parse_obj(_WINDOW_OBJ), _MAP, _wea(work), pts,
                     len(rows), blind={"shade_type": "louver", "reflectance": 0.85},
                     **common)
    work2 = str(tmp_path / "b")
    os.makedirs(work2, exist_ok=True)
    pts2, rows2 = _points(work2)
    dark = run_lm83(_scene(work2), parse_obj(_WINDOW_OBJ), _MAP, _wea(work2), pts2,
                    len(rows2), work_dir=work2, areas=_areas(len(rows2)),
                    point_rows=rows2, **_FAST)
    assert light["ran"] and dark["ran"]
    assert light["metrics"]["ASE"] == dark["metrics"]["ASE"]


def test_a_darker_blind_gives_a_lower_or_equal_sda(tmp_path):
    """2.2.7's 5% unknown-shade default must admit no more light than a 20% louver."""
    work_a = str(tmp_path / "louver")
    work_b = str(tmp_path / "unknown")
    for w in (work_a, work_b):
        os.makedirs(w, exist_ok=True)
    pts_a, rows_a = _points(work_a)
    pts_b, rows_b = _points(work_b)
    louver = run_lm83(_scene(work_a), parse_obj(_WINDOW_OBJ), _MAP, _wea(work_a), pts_a,
                      len(rows_a), work_dir=work_a, areas=_areas(len(rows_a)),
                      point_rows=rows_a,
                      blind={"shade_type": "louver", "reflectance": 0.85}, **_FAST)
    unknown = run_lm83(_scene(work_b), parse_obj(_WINDOW_OBJ), _MAP, _wea(work_b), pts_b,
                       len(rows_b), work_dir=work_b, areas=_areas(len(rows_b)),
                       point_rows=rows_b, **_FAST)
    assert louver["ran"] and unknown["ran"]
    assert unknown["metrics"]["sDA"] <= louver["metrics"]["sDA"]


def test_an_oversized_trigger_area_is_refused_before_any_radiance_runs(tmp_path):
    work = str(tmp_path)
    pts, rows = _points(work)
    out = run_lm83(_scene(work), parse_obj(_WINDOW_OBJ), _MAP, _wea(work), pts, len(rows),
                   work_dir=work, point_rows=rows,
                   areas=[{"name": "floor", "area_m2": 2000.0,
                           "point_indices": list(range(len(rows)))}], **_FAST)
    assert out["ran"] is False
    assert "10,000 sf" in out["reason"]


def test_a_model_with_no_glass_is_refused(tmp_path):
    work = str(tmp_path)
    pts, rows = _points(work)
    out = run_lm83(_scene(work), {"vertices": [], "faces": []}, {}, _wea(work), pts,
                   len(rows), work_dir=work, areas=_areas(len(rows)), point_rows=rows,
                   **_FAST)
    assert out["ran"] is False
    assert "no glass" in out["reason"].lower()
