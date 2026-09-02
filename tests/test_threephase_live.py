"""End-to-end: build the steps, run them through the real runner, parse real lux.

A passing unit test only proves the argv shapes are what we wrote down. Every defect
that mattered in this engine -- the receiver winding, the sky in the D octree, the
missing ground patch, the BSDF basis name -- produced a well-formed command that ran
cleanly and yielded zeros or a fatal at multiply time. Only a live run distinguishes
those, so this module builds a real room, runs the real chain, and asserts a physically
sane result.
"""
import os
import shutil
import pytest

from hcl_core.klems import clear_glazing_tmatrix, write_klems_xml
from hcl_radiance.aperture import glass_faces, write_window_sender
from hcl_radiance.geometry_obj import parse_obj
from hcl_radiance.runner import run_sequence
from hcl_radiance.threephase import build_threephase_steps, multiply_steps

pytestmark = pytest.mark.skipif(
    shutil.which("rfluxmtx") is None or shutil.which("dctimestep") is None,
    reason="Radiance not installed")

_WEA = os.path.join(os.path.dirname(__file__), "fixtures", "threephase_min.wea")

_MAT = """void plastic wall
0
0
5 0.5 0.5 0.5 0 0
void plastic floor
0
0
5 0.2 0.2 0.2 0 0
"""

# 4x4x3 m room; the south wall (y=0) is split around a 2 x 1.5 m opening.
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

# The glazing as an OBJ, wound so the face normal points out of the room (-Y).
_WINDOW_OBJ = """v 1 0 0.8
v 3 0 0.8
v 3 0 2.3
v 1 0 2.3
usemtl glazing
f 1 2 3 4
"""


def _write_wea(path):
    """Three clear-sky midday hours: enough to exercise the chain, fast to run."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write("place ATHENS_GRC\nlatitude 37.9\nlongitude -23.7\n"
                 "time_zone -30\nsite_elevation 28.0\nweather_data_file_units 1\n")
        for hour in (10.5, 11.5, 12.5):
            fh.write(f"6 21 {hour} 800 100\n")


def _build(work_dir):
    with open(os.path.join(work_dir, "mat.rad"), "w") as fh:
        fh.write(_MAT)
    with open(os.path.join(work_dir, "room.rad"), "w") as fh:
        fh.write(_ROOM)
    faces = glass_faces(parse_obj(_WINDOW_OBJ), {"glazing": {"type": "glass", "tvis": 0.64}})
    sender = write_window_sender(faces, "wg_s", work_dir)
    points = os.path.join(work_dir, "p.pts")
    with open(points, "w") as fh:
        for y in (1.0, 3.0):
            for x in (1.0, 2.0):
                fh.write(f"{x} {y} 0.8 0 0 1\n")
    scene = {"materials": [os.path.join(work_dir, "mat.rad")],
             "geometry": os.path.join(work_dir, "room.rad"),
             "exterior": [], "sky_color": [1, 1, 1]}
    return scene, {"wg_s": sender}, points, faces


def _parse(path):
    lines = open(path).read().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "") + 1
    return [[float(v) for v in ln.split()] for ln in lines[start:] if ln.strip()]


def test_the_chain_runs_and_yields_plausible_lux(tmp_path):
    work = str(tmp_path)
    _write_wea(_WEA)
    scene, senders, points, _faces = _build(work)

    steps, outputs = build_threephase_steps(
        scene, senders, _WEA, "p.pts", 4, work_dir=work,
        v_params="-ab 3 -ad 512 -lw 2e-3", d_params="-c 500 -ab 1 -ad 512")
    t_open = write_klems_xml(clear_glazing_tmatrix(0.64),
                             os.path.join(work, "t_open.xml"), name="clear")
    mul, ill = multiply_steps(outputs, {"wg_s": t_open}, "open")

    res = run_sequence(steps + mul, work, True)
    assert res.get("ran") is True, res.get("reason")
    assert not res.get("error"), f"{res.get('failed_step')}: {res.get('error')}"

    matrix = _parse(os.path.join(work, ill))
    assert len(matrix) == 4, "one row per sensor point"
    assert len(matrix[0]) == 3, "one column per weather timestep"

    # The V matrix must not be silently zero -- the failure mode a wrong receiver
    # winding produces, which yields a well-formed matrix of exactly 0.0.
    assert any(v > 0 for row in matrix for v in row), "every sensor is dark: check winding"
    # A workplane a metre inside a 2 x 1.5 m south window under a clear June midday sky
    # sits in the hundreds of lux; four orders of magnitude either way means a broken
    # matrix chain rather than a modelling choice.
    peak = max(v for row in matrix for v in row)
    assert 10.0 < peak < 20000.0, f"implausible peak illuminance {peak:.1f} lux"


def test_points_nearer_the_window_are_brighter(tmp_path):
    """A sanity check no shape assertion can make: the physics must have a gradient."""
    work = str(tmp_path)
    _write_wea(_WEA)
    scene, senders, points, _faces = _build(work)
    steps, outputs = build_threephase_steps(
        scene, senders, _WEA, "p.pts", 4, work_dir=work,
        v_params="-ab 3 -ad 512 -lw 2e-3", d_params="-c 500 -ab 1 -ad 512")
    t_open = write_klems_xml(clear_glazing_tmatrix(0.64),
                            os.path.join(work, "t_open.xml"), name="clear")
    mul, ill = multiply_steps(outputs, {"wg_s": t_open}, "open")
    res = run_sequence(steps + mul, work, True)
    assert res.get("ran") is True and not res.get("error")

    matrix = _parse(os.path.join(work, ill))
    # Points are written y=1 (near the south window) then y=3 (deep); rows 0,1 vs 2,3.
    near = sum(matrix[0]) + sum(matrix[1])
    deep = sum(matrix[2]) + sum(matrix[3])
    assert near > deep, f"near-window {near:.1f} should exceed deep-plan {deep:.1f}"


def test_a_darker_t_matrix_lets_less_light_through(tmp_path):
    """The T matrix must actually modulate the result -- this is what makes a blind
    state cheap AND what proves dctimestep is reading our BSDF rather than ignoring it."""
    work = str(tmp_path)
    _write_wea(_WEA)
    scene, senders, points, _faces = _build(work)
    steps, outputs = build_threephase_steps(
        scene, senders, _WEA, "p.pts", 4, work_dir=work,
        v_params="-ab 3 -ad 512 -lw 2e-3", d_params="-c 500 -ab 1 -ad 512")

    totals = {}
    extra = []
    for tag, tvis in (("open", 0.64), ("blind", 0.05)):
        xml = write_klems_xml(clear_glazing_tmatrix(tvis),
                              os.path.join(work, f"t_{tag}.xml"), name=tag)
        mul, ill = multiply_steps(outputs, {"wg_s": xml}, tag)
        extra += mul
        totals[tag] = ill
    res = run_sequence(steps + extra, work, True)
    assert res.get("ran") is True and not res.get("error")

    bright = sum(v for row in _parse(os.path.join(work, totals["open"])) for v in row)
    dim = sum(v for row in _parse(os.path.join(work, totals["blind"])) for v in row)
    assert dim < bright, f"5% blind ({dim:.1f}) must admit less than 64% glass ({bright:.1f})"
    # 0.05/0.64 = 7.8%; allow generous slack for sampling noise in a cheap-parameter run.
    assert dim < 0.5 * bright
