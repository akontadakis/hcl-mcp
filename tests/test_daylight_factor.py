import os

import pytest

from hcl_radiance.daylight_factor import run_daylight_factor
from hcl_radiance.discover import resolve_bin

# This one test executes the REAL overcast-sky steps, so it needs a real `gensky` on disk.
# Without it the sky file is never written and the run degrades to emit, which is correct
# behaviour, not a regression — so skip rather than fail. The emit path is covered by
# test_daylight_factor_emits_when_not_run, and the ordering contract by the stubbed tests.
requires_gensky = pytest.mark.skipif(
    resolve_bin("gensky") is None, reason="Radiance gensky not installed")


@requires_gensky
def test_daylight_factor_writes_overcast_sky_before_indoor_grid(monkeypatch, tmp_path):
    """Regression: run_grid's indoor octree includes overcast_sky.rad, so that file must be
    physically written into work_dir BEFORE the indoor run_grid call executes (real oconv would
    otherwise fail with 'cannot open scene file overcast_sky.rad'). Stub _available()=True and
    run_sequence so this runs without a live Radiance install, but exercise the REAL
    write_overcast_sky steps so the actual sky file lands on disk in the right order."""
    import hcl_radiance.daylight_factor as df
    monkeypatch.setattr(df, "_available", lambda: True)

    order = []
    real_run_sequence = df.run_sequence

    def spy_run_sequence(steps, work_dir, available):
        order.append("sky")
        return real_run_sequence(steps, work_dir, available)
    monkeypatch.setattr(df, "run_sequence", spy_run_sequence)

    sky_path = os.path.join(str(tmp_path), "overcast_sky.rad")

    def fake_run_grid(scene_sets, points, channel_type, **kw):
        order.append("grid")
        # The critical assertion: by the time run_grid (which builds the indoor octree
        # containing overcast_sky.rad) is called, the sky file must already exist.
        assert os.path.exists(sky_path), "overcast_sky.rad must be written before run_grid"
        return {"ran": True, "daylight": {"metrics": [{"photopic_lux": 300.0}]}}
    monkeypatch.setattr(df, "_run_grid", fake_run_grid)

    out = run_daylight_factor([["m.rad", "g.rad"]], [[1, 1, 0.8, 0, 0, 1]],
                              work_dir=str(tmp_path), run=True)
    assert out["ran"] is True
    assert os.path.exists(sky_path)
    assert order[0] == "sky"          # sky-build ran before either run_grid call
    assert order.count("grid") == 2   # indoor + exterior

def test_daylight_factor_emits_when_not_run(tmp_path):
    out = run_daylight_factor([["m.rad", "g.rad"]], [[1, 1, 0.8, 0, 0, 1]],
                              work_dir=str(tmp_path), run=False)
    assert out["ran"] is False
    flat = " ".join(out["commands"])        # commands are pre-rendered shell strings
    assert "gensky" in flat                 # overcast sky built
    assert "overcast_sky.rad" in flat
    # the emitted plan must reflect BOTH grids a live run performs: the indoor octree
    # (building + overcast sky) and the exterior sky-only reference octree used for E_outdoor.
    assert flat.count("oconv") == 2
    assert "m.rad g.rad overcast_sky.rad" in flat   # indoor octree includes the building
    oconv_cmds = [c for c in out["commands"] if c.startswith("oconv")]
    assert any(c.strip() == "oconv -f overcast_sky.rad > daylight0.oct" for c in oconv_cmds), oconv_cmds

def test_daylight_factor_computes_df_from_stub(monkeypatch, tmp_path):
    # Stub run_grid: indoor point sees 300 lux, exterior reference sees 1500 lux -> DF=20%
    import hcl_radiance.daylight_factor as df
    calls = {"n": 0}
    def fake_run_grid(scene_sets, points, channel_type, **kw):
        calls["n"] += 1
        if calls["n"] == 1:   # indoor grid
            return {"ran": True, "daylight": {"metrics": [{"photopic_lux": 300.0}]}}
        return {"ran": True, "daylight": {"metrics": [{"photopic_lux": 1500.0}]}}  # exterior
    monkeypatch.setattr(df, "_run_grid", fake_run_grid)
    out = run_daylight_factor([["m.rad", "g.rad"]], [[1, 1, 0.8, 0, 0, 1]],
                              work_dir=str(tmp_path), run=True)
    assert out["ran"] is True
    assert out["e_outdoor"] == 1500.0
    assert out["df_per_point"] == [20.0]
    assert out["df_avg"] == 20.0
    assert out["df_min"] == 20.0
    assert out["uniformity"] == 1.0

def test_daylight_factor_multipoint_and_zero_exterior(monkeypatch, tmp_path):
    # Two indoor points (300 and 150 lux) against a 1500 lux exterior reference ->
    # DF = [20.0, 10.0], df_avg = 15.0, df_min = 10.0, uniformity = df_min/df_avg.
    import hcl_radiance.daylight_factor as df
    calls = {"n": 0}
    def fake_run_grid(scene_sets, points, channel_type, **kw):
        calls["n"] += 1
        if calls["n"] == 1:   # indoor grid, 2 points
            return {"ran": True, "daylight": {"metrics": [
                {"photopic_lux": 300.0}, {"photopic_lux": 150.0}]}}
        return {"ran": True, "daylight": {"metrics": [{"photopic_lux": 1500.0}]}}  # exterior
    monkeypatch.setattr(df, "_run_grid", fake_run_grid)
    out = run_daylight_factor([["m.rad", "g.rad"]],
                              [[1, 1, 0.8, 0, 0, 1], [2, 1, 0.8, 0, 0, 1]],
                              work_dir=str(tmp_path), run=True)
    assert out["ran"] is True
    assert out["df_per_point"] == [20.0, 10.0]
    assert out["df_avg"] == 15.0
    assert out["df_min"] == 10.0
    assert out["uniformity"] == round(10.0 / 15.0, 4)

def test_daylight_factor_zero_exterior_reference_no_zerodivision(monkeypatch, tmp_path):
    # Exterior reference of 0 lux must not raise ZeroDivisionError: DF per point -> 0.0,
    # uniformity -> 0.0.
    import hcl_radiance.daylight_factor as df
    calls = {"n": 0}
    def fake_run_grid(scene_sets, points, channel_type, **kw):
        calls["n"] += 1
        if calls["n"] == 1:   # indoor grid, 2 points
            return {"ran": True, "daylight": {"metrics": [
                {"photopic_lux": 300.0}, {"photopic_lux": 150.0}]}}
        return {"ran": True, "daylight": {"metrics": [{"photopic_lux": 0.0}]}}  # exterior
    monkeypatch.setattr(df, "_run_grid", fake_run_grid)
    out = run_daylight_factor([["m.rad", "g.rad"]],
                              [[1, 1, 0.8, 0, 0, 1], [2, 1, 0.8, 0, 0, 1]],
                              work_dir=str(tmp_path), run=True)
    assert out["ran"] is True
    assert out["e_outdoor"] == 0.0
    assert out["df_per_point"] == [0.0, 0.0]
    assert out["uniformity"] == 0.0


def test_exterior_grid_failure_returns_an_error_not_a_keyerror(monkeypatch, tmp_path):
    """A failed EXTERIOR reference run must surface as an error envelope, not KeyError.

    Found by audit 2026-08-06. The indoor result is guarded for exactly this ("daylight" absent
    on a failed run), then the exterior result one line later was used unguarded, so an exterior
    failure died on `KeyError: 'daylight'` instead of reporting which run failed and why. DF is
    E_indoor/E_outdoor, so the exterior reference is not optional - it is the denominator.
    """
    import hcl_radiance.daylight_factor as df

    calls = {"n": 0}

    def fake_run_grid(scene, points, ct, **kw):
        calls["n"] += 1
        if calls["n"] == 1:                      # indoor: succeeds
            return {"ran": True, "daylight": {"channels": [[1, 1, 1]],
                                              "metrics": [{"photopic_lux": 100.0}]}}
        return {"ran": True, "error": "rtrace: fatal - command line error",
                "failed_step": "rtrace -I -ab 2"}      # exterior: fails

    monkeypatch.setattr(df, "_run_grid", fake_run_grid)
    out = df.run_daylight_factor(scene_sets=["m.rad"], indoor_points=[[0, 0, 0.8, 0, 0, 1]],
                                 work_dir=str(tmp_path), run=True)
    assert out["ran"] is True
    assert "df_avg" not in out, "a failed exterior run must not report a DF"
    assert "error" in out and out["error"], f"the failure must be surfaced: {out}"
