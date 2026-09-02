"""Phase 5 gated end-to-end live harness (XCUT-3 / DAYSIM-2/5 / RAD-11).

The live simulation paths (sub-hourly Daysim, annual Radiance) have never been
exercised end-to-end against real binaries. This file is the vehicle to run them
WHEN the binaries exist, and to prove XCUT-1's time-varying solar zeniths LIVE
(not the constant-zenith fallback).

Gating: the whole module SKIPS unless both Radiance and Daysim are available
(via HCL_RADIANCE_BIN/HCL_DAYSIM_BIN or PATH), or the operator explicitly opts
in with HCL_LIVE=1. On dev/CI (no binaries) these tests SKIP — they never fail.

Run:  PYTHONPATH=src python -m pytest tests/test_live_phase5.py -v
Live: HCL_LIVE=1 HCL_TEST_EPW=/path/to.epw \
      HCL_RADIANCE_BIN=... HCL_DAYSIM_BIN=... \
      PYTHONPATH=src python -m pytest tests/test_live_phase5.py -v
"""
import os

import pytest

from hcl_daysim.discover import daysim_status
from hcl_daysim.subhourly import generate_subhourly_wea
from hcl_radiance.discover import radiance_status
from hcl_radiance.annual import run_annual
from hcl_radiance.annual_results import parse_ill

# Gate on REAL binaries (both adapters report {"available": bool, ...}); HCL_LIVE=1 forces an attempt.
LIVE = (radiance_status()["available"] and daysim_status()["available"]) or \
    os.environ.get("HCL_LIVE") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE,
    reason="live harness: needs Radiance+Daysim binaries (HCL_RADIANCE_BIN/HCL_DAYSIM_BIN or PATH) "
           "or HCL_LIVE=1",
)


def test_daysim_build_then_generate_subhourly(tmp_path):
    """DAYSIM-2/5 + XCUT-1: real epw2wea -> ds_shortterm sub-hourly .wea, with time-varying zeniths.

    Proves XCUT-1 LIVE: the solar zeniths parsed from the produced sub-hourly .wea VARY across the
    day (not the constant 30 the offline fallback uses), and at least one is daytime (< 90 deg).
    """
    epw = os.environ.get("HCL_TEST_EPW")
    if not epw:
        pytest.skip("set HCL_TEST_EPW to a small real EPW to run the sub-hourly live test")
    assert os.path.isfile(epw), f"HCL_TEST_EPW does not exist: {epw}"

    # 6-min steps (0.1 h) — in the ds_shortterm allow-set and satisfies the nvRD delta guard.
    # Site values (lat/long/tz) default from the EPW LOCATION line in DAYSIM convention.
    out = generate_subhourly_wea(epw=epw, timestep_min=6, work_dir=str(tmp_path), run=True)

    assert out["ran"] is True, out
    assert os.path.isfile(out["wea"]) and os.path.getsize(out["wea"]) > 0, out

    timestamps = out["timestamps"]
    zeniths = out["solar_zeniths"]
    assert timestamps, "expected non-empty timestamps from the produced .wea"
    assert zeniths, "expected non-empty solar_zeniths from the produced .wea"
    assert len(timestamps) == len(zeniths)

    # Daytime: at least one sun above the horizon.
    assert any(z < 90 for z in zeniths), f"expected at least one daytime zenith (<90), got {zeniths!r}"

    # XCUT-1 live: zeniths must VARY across the day (not a single constant value like 30).
    distinct = {round(z) for z in zeniths}
    assert len(distinct) > 1, (
        f"expected time-varying solar zeniths across the day (XCUT-1), got constant set {distinct!r}")


def test_annual_ill_roundtrip_ascii(tmp_path):
    """RAD-11: minimal annual run end-to-end + parse_ill on the real .ill, asserting finite rows.

    A full annual run needs real scene assets (materials/geometry .rad, a .wea, a points file).
    Rather than carry a dead unconditional skip, this test reads the scene from a JSON descriptor
    pointed at by HCL_TEST_ANNUAL_SCENE, e.g.:

        {"materials": "materials.rad", "geometry": "geometry.rad", "points": "sensors.pts",
         "wea": "scene.wea", "sky_color": [1.0, 1.0, 1.0]}

    Paths in the descriptor are absolute or relative to the descriptor's own directory. When the
    env var is unset the test SKIPS cleanly (with a message naming the env var); when it is set AND
    the module-level binary gate is satisfied, the annual run actually executes.
    """
    scene_env = os.environ.get("HCL_TEST_ANNUAL_SCENE")
    if not scene_env:
        pytest.skip("set HCL_TEST_ANNUAL_SCENE=/path/to/scene.json "
                    "(materials/geometry/points/wea[/sky_color]) to run the live annual .ill roundtrip")

    import json
    assert os.path.isfile(scene_env), f"HCL_TEST_ANNUAL_SCENE does not exist: {scene_env}"
    with open(scene_env) as fh:
        scene = json.load(fh)
    base = os.path.dirname(os.path.abspath(scene_env))

    def _resolve(p):
        return p if os.path.isabs(p) else os.path.join(base, p)

    materials = _resolve(scene["materials"])
    geometry = _resolve(scene["geometry"])
    points = _resolve(scene["points"])
    wea = _resolve(scene["wea"])
    sky_color = scene.get("sky_color", [1.0, 1.0, 1.0])

    channel_scenes = [{"materials": materials, "geometry": geometry, "sky_color": sky_color}]

    # channel_type=0 -> 3-channel (single scene). Returns {ran, n_timesteps, metrics}.
    out = run_annual(channel_scenes, wea, points, channel_type=0, work_dir=str(tmp_path), run=True)
    assert out["ran"] is True, out
    assert out["n_timesteps"] > 0, out

    # RAD-11: parse the real sky .ill produced by dctimestep and assert finite per-timestep RGB rows.
    sky_ill = tmp_path / "annual_sky0.ill"
    assert sky_ill.is_file(), f"expected dctimestep sky output at {sky_ill}"
    series = parse_ill(sky_ill.read_text())  # -> list of [R, G, B] per timestep for sensor 0
    assert series, "parse_ill returned no rows from the real .ill"
    import math
    for row in series:
        assert len(row) == 3
        assert all(math.isfinite(v) for v in row), f"non-finite value in .ill row: {row!r}"
