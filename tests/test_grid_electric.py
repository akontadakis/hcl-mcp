import os
import hcl_radiance.grid as grid
from hcl_core.data import W_PHOTOPIC_3, W_PHOTOPIC_9

_IES_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "synthetic_typeC.ies")  # input_watts=10


def _dot(w, c):
    return sum(wi * ci for wi, ci in zip(w, c))


# DEF-2: a luminaire SPD imposes spectrum but must PRESERVE the ies2rad luminous output.

def test_normalize_luminance_preserves_photopic_output_9ch():
    # A tiny relative-SPD-shaped 9-vector (peak ~0.01) must be rescaled so its photopic-weighted
    # sum equals a flat white's — otherwise the electric contribution collapses ~100x.
    raw = [0.0, 0.009, 0.006, 0.011, 0.013, 0.016, 0.017, 0.015, 0.004]
    norm = grid._normalize_luminance(raw, 1)
    assert abs(_dot(W_PHOTOPIC_9, norm) - _dot(W_PHOTOPIC_9, [1.0] * 9)) < 1e-6
    # the spectral SHAPE is retained (ratios between nonzero bins unchanged, modulo 6-dp rounding)
    assert abs(norm[1] / norm[2] - raw[1] / raw[2]) < 1e-4


def test_normalize_luminance_flat_white_is_identity():
    assert grid._normalize_luminance([1.0] * 9, 1) == [1.0] * 9
    assert grid._normalize_luminance([1.0] * 3, 0) == [1.0] * 3


def test_normalize_luminance_3ch_preserves_output():
    raw = [0.02, 0.03, 0.01]
    norm = grid._normalize_luminance(raw, 0)
    assert abs(_dot(W_PHOTOPIC_3, norm) - _dot(W_PHOTOPIC_3, [1.0] * 3)) < 1e-6


# DEF-3: total_wattage derives from the IES when the electric_lights spec carries no `wattage`.

def test_luminaire_wattage_explicit_wins():
    assert grid._luminaire_wattage({"ies": _IES_FIX, "wattage": 40}) == 40


def test_luminaire_wattage_falls_back_to_ies_input_watts():
    assert grid._luminaire_wattage({"ies": _IES_FIX}) == 10.0


def test_run_grid_total_wattage_from_ies_when_unset(monkeypatch, tmp_path):
    # Drop-in payload (ies + placement, NO wattage) must still tally energy: 2 fixtures x 10 W = 20 W.
    monkeypatch.setattr(grid, "_available", lambda: False)
    out = grid.run_grid(
        scene_sets=[["m.rad", "sky.rad", "g.rad"]],
        points=[[0, 0, 1.2, 0, 0, 1]], channel_type=0, work_dir=str(tmp_path),
        electric_lights=[{"ies": _IES_FIX,
                          "placement": {"positions": [{"xyz": [0, 0, 3]}, {"xyz": [1, 0, 3]}]}}],
        run=True)
    assert out["total_wattage"] == 20.0

def _fake_run_factory(res_by_suffix):
    def fake_run(steps, work_dir, available):
        for s in steps:
            out = s.get("stdout", "")
            for suffix, text in res_by_suffix.items():
                if out.endswith(suffix):
                    open(os.path.join(work_dir, out), "w").write(text)
        return {"ran": True, "returncode": 0, "commands": [], "outputs": []}
    return fake_run

def test_run_grid_electric_assembles_combined_and_electric_octrees(monkeypatch, tmp_path):
    monkeypatch.setattr(grid, "_available", lambda: False)
    out = grid.run_grid(
        scene_sets=[["m.rad", "sky.rad", "g.rad"]],
        points=[[0, 0, 1.2, 0, 0, 1]], channel_type=0, work_dir=str(tmp_path),
        electric_lights=[{"ies": "lamp.ies", "placement": {"positions": [{"xyz": [0, 0, 3]}]},
                          "wattage": 40}],
        run=True)
    assert out["ran"] is False
    blob = " ".join(out["commands"])
    assert "ies2rad" in blob
    assert any("combined" in c for c in out["commands"])
    assert any("electric" in c for c in out["commands"])
    assert out["total_wattage"] == 40

def test_run_grid_electric_returns_three_metric_sets(monkeypatch, tmp_path):
    monkeypatch.setattr(grid, "_available", lambda: True)
    monkeypatch.setattr(grid, "run_sequence", _fake_run_factory({
        "daylight0.res": "1 1 1\n", "electric0.res": "0.5 0.5 0.5\n",
        "combined0.res": "1.5 1.5 1.5\n"}))
    out = grid.run_grid(
        scene_sets=[["m.rad", "sky.rad", "g.rad"]],
        points=[[0, 0, 1.2, 0, 0, 1]], channel_type=0, work_dir=str(tmp_path),
        electric_lights=[{"ies": "lamp.ies", "placement": {"positions": [{"xyz": [0, 0, 3]}]},
                          "wattage": 40}],
        run=True)
    assert out["ran"] is True
    assert round(out["daylight"]["metrics"][0]["melanopic_lux"], 6) == 179.0
    assert round(out["electric"]["metrics"][0]["melanopic_lux"], 6) == 89.5
    assert round(out["combined"]["metrics"][0]["melanopic_lux"], 6) == 268.5


def test_is_sky_file_basename_fallback():
    # For a file that cannot be read (the emit path), the BASENAME decides. Plain substring, not a
    # word boundary: the boundary rule this replaced silently missed skydome.rad and clearsky.rad
    # (ADR-0007), and any boundary rule just moves that edge somewhere else.
    assert grid._is_sky_file("sky.rad")
    assert grid._is_sky_file("sky_clear.rad")
    assert grid._is_sky_file("clear_sky.rad")
    assert grid._is_sky_file("Sky.rad")                 # case-insensitive
    assert grid._is_sky_file("skydome.rad")             # the case the word boundary lost
    assert not grid._is_sky_file("whiskey.rad")         # no 'sky' substring at all
    assert not grid._is_sky_file("/home/sky_user/room.rad")  # dir name ignored, basename is room.rad


def test_run_grid_electric_threads_per_luminaire_units(monkeypatch, tmp_path):
    # A feet-declared luminaire (units=1) must emit ies2rad -df, not the default -dm.
    monkeypatch.setattr(grid, "_available", lambda: False)
    out = grid.run_grid(
        scene_sets=[["m.rad", "sky.rad", "g.rad"]],
        points=[[0, 0, 1.2, 0, 0, 1]], channel_type=0, work_dir=str(tmp_path),
        electric_lights=[{"ies": "lamp.ies", "units": 1,
                          "placement": {"positions": [{"xyz": [0, 0, 3]}]}, "wattage": 40}],
        run=True)
    blob = " ".join(out["commands"])
    assert "-df" in blob and "-dm" not in blob


def test_run_grid_electric_explicit_sky_files_override_heuristic(monkeypatch, tmp_path):
    # Oddly-named sky (ambient.rad, not matching the _is_sky_file heuristic) is dropped from the
    # electric octree because it's listed explicitly in sky_files; real geometry stays.
    monkeypatch.setattr(grid, "_available", lambda: False)
    out = grid.run_grid(scene_sets=[["m.rad", "ambient.rad", "g.rad"]],
                        points=[[0, 0, 1.2, 0, 0, 1]], channel_type=0, work_dir=str(tmp_path),
                        electric_lights=[{"ies": "lamp.ies",
                                          "placement": {"positions": [{"xyz": [0, 0, 3]}]},
                                          "wattage": 40}],
                        sky_files=["ambient.rad"], run=True)
    e = [c for c in out["commands"] if "electric0.oct" in c and "oconv" in c]
    assert e and "ambient.rad" not in e[0]
    assert "m.rad" in e[0] and "g.rad" in e[0]


def test_run_grid_electric_heuristic_still_used_when_sky_files_none(monkeypatch, tmp_path):
    # Without sky_files, the _is_sky_file basename heuristic still drops sky.rad from the
    # electric octree (backward-compatible default).
    monkeypatch.setattr(grid, "_available", lambda: False)
    out = grid.run_grid(scene_sets=[["m.rad", "sky.rad", "g.rad"]],
                        points=[[0, 0, 1.2, 0, 0, 1]], channel_type=0, work_dir=str(tmp_path),
                        electric_lights=[{"ies": "lamp.ies",
                                          "placement": {"positions": [{"xyz": [0, 0, 3]}]},
                                          "wattage": 40}], run=True)
    e = [c for c in out["commands"] if "electric0.oct" in c and "oconv" in c]
    assert e and "sky.rad" not in e[0]


def test_run_grid_electric_empty_sky_files_falls_back_to_heuristic(monkeypatch, tmp_path):
    # An empty sky_files list must behave like None (fall back to the _is_sky_file heuristic),
    # not "drop nothing" — otherwise sky geometry leaks into the electric-only octree.
    monkeypatch.setattr(grid, "_available", lambda: False)
    out = grid.run_grid(scene_sets=[["m.rad", "sky.rad", "g.rad"]],
                        points=[[0, 0, 1.2, 0, 0, 1]], channel_type=0, work_dir=str(tmp_path),
                        electric_lights=[{"ies": "lamp.ies",
                                          "placement": {"positions": [{"xyz": [0, 0, 3]}]},
                                          "wattage": 40}],
                        sky_files=[], run=True)
    e = [c for c in out["commands"] if "electric0.oct" in c and "oconv" in c]
    assert e and "sky.rad" not in e[0]   # heuristic still drops sky.rad despite empty sky_files
    assert "m.rad" in e[0] and "g.rad" in e[0]
