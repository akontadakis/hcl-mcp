"""The electric-only octree must contain no sky, and must say so when it cannot be sure.

`_select_non_sky` claims sky geometry "can never leak into the electric octree". It can. The
fallback is a basename regex, `(^|[^a-z])sky([^a-z]|$)` compiled IGNORECASE — which makes
[^a-z] exclude letters of BOTH cases, so any 'sky' followed by a letter fails to match.
skydome.rad, clearsky.rad and every gensky/gendaylit output named for the sky condition rather
than the word "sky" go straight into the electric-only octree, and the electric block then
reports daylight as if it came from the luminaires.

The reliable path exists but is unreachable from MCP: run_grid's server signature never
accepted sky_files, so a tool caller was forced onto the heuristic with no override.

Measured impact of one leak: 17705 lx reported where the true electric-only value was 1662 lx.
Nothing in the result said so; it was caught only by an external physical bound.
"""
import asyncio
import os

import pytest

import hcl_radiance.grid as grid
import hcl_mcp.server as S
from hcl_mcp.advisories import advise

_IES_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "synthetic_typeC.ies")

# What this codebase's own sky writers emit (hcl_radiance/sky.py _SKY_TAIL,
# hcl_radiance/sky_overcast.py _OVERCAST_GLOW).
COLORED_SKY_RAD = """\
!gendaylit 6 21 12 -a 37.9 -o -23.7 -m -30 -W 800 120

skyfunc glow sky_mat
0
0
4 1 1 1 0

sky_mat source sky
0
0
4 0 0 1 180

skyfunc glow ground_glow
0
0
4 1 1 1 0

ground_glow source ground
0
0
4 0 0 -1 180
"""

ROOM_RAD = """\
wall_mat polygon floor
0
0
12  0 0 0  4 0 0  4 4 0  0 4 0
"""


def _electric_oconv(out):
    cmds = [c for c in out["commands"] if "oconv" in c and "electric0.oct" in c]
    assert cmds, "no electric-only oconv in the emitted plan"
    return cmds[0]


# ---- the basename heuristic itself -------------------------------------------------

@pytest.mark.parametrize("name", [
    "skydome.rad", "SKYDOME.rad", "skyvault.rad", "clearsky.rad", "mysky1.rad",
])
def test_sky_named_files_the_regex_silently_misses(name):
    """'sky' adjacent to a letter: the [^a-z] guard rejects it under IGNORECASE."""
    assert grid._is_sky_file(name), f"{name} is a sky by name and must be detected"


# ---- content detection: the basename is a hint, the primitives are the evidence ----

def test_a_sky_is_detected_from_its_radiance_primitives(tmp_path):
    """A gendaylit/gensky sky is identifiable from what is IN it, whatever it is called."""
    p = tmp_path / "ambient_conditions.rad"
    p.write_text(COLORED_SKY_RAD)
    assert grid._is_sky_file(str(p))


# Each marker is asserted ALONE. Testing only the full sky above would let any single marker be
# deleted from the detector without a test noticing, because the others still match it.
@pytest.mark.parametrize("marker,body", [
    ("inline gendaylit", "!gendaylit 6 21 12 -a 37.9 -o -23.7 -m -30 -W 800 120\n"),
    ("inline gensky", "!gensky 3 21 14 -c -g 0.2\n"),
    ("gensky output header", "# gensky 3 21 14 -c\n\nvoid brightfunc skyfunc\n2 skybr skybright.cal\n"),
    ("skyfunc modifier", "skyfunc glow sky_glow\n0\n0\n4 1 1 1 0\n"),
    ("sky hemisphere", "sky_glow source sky\n0\n0\n4 0 0 1 180\n"),
    ("ground hemisphere", "ground_glow source ground\n0\n0\n4 0 0 -1 180\n"),
    ("gendaylit sun", "void light solar\n0\n0\n3 1e6 1e6 1e6\n"),
    # A hand-rolled sky: the brightness pattern is named by the author, so neither 'gensky' nor
    # 'skyfunc' appears anywhere — the .cal it evaluates is the only thing left to recognise it by.
    ("bare skybright.cal reference", "void brightfunc dome\n2 skybr skybright.cal\n0\n3 1 2 3\n"),
    ("bare perezlum.cal reference", "void brightfunc dome\n2 skybr perezlum.cal\n0\n3 1 2 3\n"),
])
def test_each_sky_primitive_is_detected_on_its_own(tmp_path, marker, body):
    p = tmp_path / "context.rad"          # a name with no 'sky' in it: content must carry it
    p.write_text(body)
    assert grid._is_sky_file(str(p)), f"{marker} alone must identify a sky"


def test_room_geometry_is_not_mistaken_for_a_sky(tmp_path):
    p = tmp_path / "room.rad"
    p.write_text(ROOM_RAD)
    assert not grid._is_sky_file(str(p))


def test_content_detected_sky_is_dropped_from_the_electric_octree(monkeypatch, tmp_path):
    """The end-to-end leak: an oddly-named sky must not reach the electric-only octree."""
    monkeypatch.setattr(grid, "_available", lambda: False)
    sky = tmp_path / "skydome.rad"
    sky.write_text(COLORED_SKY_RAD)
    room = tmp_path / "room.rad"
    room.write_text(ROOM_RAD)
    out = grid.run_grid(
        scene_sets=[[str(room), str(sky)]],
        points=[[0, 0, 1.2, 0, 0, 1]], channel_type=0, work_dir=str(tmp_path),
        electric_lights=[{"ies": _IES_FIX,
                          "placement": {"positions": [{"xyz": [2, 2, 3]}]}}],
        run=True)
    cmd = _electric_oconv(out)
    assert "skydome.rad" not in cmd, "sky leaked into the electric-only octree"
    assert "room.rad" in cmd, "real geometry must survive"


# ---- the reliable override must be reachable from the public tool ------------------

def test_mcp_run_grid_accepts_and_forwards_sky_files(monkeypatch, tmp_path):
    """Without this, an MCP caller cannot override the heuristic at all."""
    seen = {}

    def fake(scene_sets, points, channel_type, **kw):
        seen.update(kw)
        return {"ran": False, "commands": []}

    monkeypatch.setattr(S, "_run_grid", fake)
    asyncio.run(S.run_grid(scene_sets=[["m.rad", "ambient.rad"]],
                           points=[[0, 0, 1.2, 0, 0, 1]], channel_type=0,
                           work_dir=str(tmp_path), run=False,
                           electric_lights=[{"ies": _IES_FIX,
                                             "placement": {"positions": [{"xyz": [0, 0, 3]}]}}],
                           sky_files=["ambient.rad"]))
    assert seen.get("sky_files") == ["ambient.rad"]


# ---- the bound that catches this whole class of error ------------------------------

def test_electric_result_carries_the_lumen_bound(monkeypatch, tmp_path):
    """Sum(luminaire lumens) / area is the perfect-utilisation ceiling for the mean.

    The leak that prompted this reported 17705 lx against a 2737 lx ceiling. The bound is
    cheap, needs nothing the run does not already hold, and catches any over-count of the
    electric block regardless of cause.
    """
    monkeypatch.setattr(grid, "_available", lambda: True)

    def fake_run(steps, work_dir, available):
        for s in steps:
            out = s.get("stdout", "")
            if out.endswith(".res"):
                # ~17700 lx at every point: far above anything this one 10 W fixture can do.
                open(os.path.join(work_dir, out), "w").write("100 100 100\n" * 4)
        return {"ran": True, "returncode": 0, "commands": [], "outputs": []}

    monkeypatch.setattr(grid, "run_sequence", fake_run)
    out = grid.run_grid(
        scene_sets=[["m.rad"]],
        points=[[0, 0, 0.8, 0, 0, 1], [4, 0, 0.8, 0, 0, 1],
                [4, 4, 0.8, 0, 0, 1], [0, 4, 0.8, 0, 0, 1]],
        channel_type=0, work_dir=str(tmp_path),
        electric_lights=[{"ies": _IES_FIX,
                          "placement": {"positions": [{"xyz": [2, 2, 3]}]}}],
        run=True)
    bound = out["electric"]["lumen_bound"]
    assert bound["exceeded"] is True
    assert bound["ceiling_lux"] > 0 and bound["mean_lux"] > bound["ceiling_lux"]


def test_lumen_bound_passes_a_physically_possible_electric_result(monkeypatch, tmp_path):
    """The complement of the test above, and the one that stops `exceeded` being a constant.

    A bound that reports 'exceeded' on every run is not a bound, it is an alarm — and it would
    train a reader to ignore the one case that matters.
    """
    monkeypatch.setattr(grid, "_available", lambda: True)

    def fake_run(steps, work_dir, available):
        for s in steps:
            out = s.get("stdout", "")
            if out.endswith(".res"):
                # 89.5 lx mean, against a 172.9 lx ceiling (2766 lm over the 4x4 m grid box):
                # a utilisation factor of 0.52, which is an ordinary office number.
                open(os.path.join(work_dir, out), "w").write("0.5 0.5 0.5\n" * 4)
        return {"ran": True, "returncode": 0, "commands": [], "outputs": []}

    monkeypatch.setattr(grid, "run_sequence", fake_run)
    out = grid.run_grid(
        scene_sets=[["m.rad"]],
        points=[[0, 0, 0.8, 0, 0, 1], [4, 0, 0.8, 0, 0, 1],
                [4, 4, 0.8, 0, 0, 1], [0, 4, 0.8, 0, 0, 1]],
        channel_type=0, work_dir=str(tmp_path),
        electric_lights=[{"ies": _IES_FIX,
                          "placement": {"positions": [{"xyz": [2, 2, 3]}]}}],
        run=True)
    bound = out["electric"]["lumen_bound"]
    assert bound["exceeded"] is False
    assert bound["mean_lux"] < bound["ceiling_lux"]
    codes = [a["code"] for a in advise("run_grid", {}, out)]
    assert "ELECTRIC_EXCEEDS_LUMEN_BOUND" not in codes


def test_lumen_bound_advisory_fires_on_an_impossible_electric_result():
    result = {"ran": True, "electric": {"lumen_bound": {
        "exceeded": True, "mean_lux": 17705.0, "ceiling_lux": 2737.0,
        "lamp_lumens": 206880.0, "area_m2": 75.6}}}
    codes = [a["code"] for a in advise("run_grid", {}, result)]
    assert "ELECTRIC_EXCEEDS_LUMEN_BOUND" in codes


def test_lumen_bound_advisory_silent_when_the_result_is_physical():
    result = {"ran": True, "electric": {"lumen_bound": {
        "exceeded": False, "mean_lux": 480.0, "ceiling_lux": 2737.0,
        "lamp_lumens": 206880.0, "area_m2": 75.6}}}
    codes = [a["code"] for a in advise("run_grid", {}, result)]
    assert "ELECTRIC_EXCEEDS_LUMEN_BOUND" not in codes
