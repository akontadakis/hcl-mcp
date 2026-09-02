"""mel-DER reported at a point must describe the spectrum AT THAT POINT, not at the lamp.

The electric block hands `circadian_metrics` the luminaire's own SPD, so every point in the
block receives the SOURCE mel-DER — identical everywhere by construction — and `mel_edi` is
built from it as photopic_lux(at the point) x mel-DER(at the lamp). That is right only while
the transport is spectrally neutral. A room with any spectrally selective surface shifts the
spectrum at the eye, and the error grows with the shift while the provenance label still reads
"spd", which everywhere else in this codebase means MORE trustworthy.

These tests are written against the DEFECT, not against one particular repair: they assert only
that the reported mel-DER responds to the spectrum the simulation actually produced.
"""
import os

import pytest

import hcl_radiance.grid as grid
from hcl_core.presets import get_preset
from hcl_core.spd import parse_spd, bin_average
from hcl_core.spectral_metrics import mel_der

# FL4 is the worst binning case in the preset library, so the two routes are far apart and a
# test cannot pass by accident on a spectrum where they happen to agree.
SPIKY = "FL4"

_IES_FIX = os.path.join(os.path.dirname(__file__), "fixtures", "synthetic_typeC.ies")


def _source_channels():
    return bin_average(parse_spd(get_preset(SPIKY)), 1)


def _warm_transport():
    """Per-bin reflectance rising toward red: a beech/ochre room, not a pathological case."""
    return [0.45 + 0.30 * i / 8.0 for i in range(9)]


def _res_text(rows):
    """rtrace -I output: one 'R G B' line per point."""
    return "".join(" ".join(f"{v:.9g}" for v in r) + "\n" for r in rows)


def _fake_run_with(electric_channels_per_point):
    """Fake run_sequence that plants chosen 9-channel electric results.

    electric_channels_per_point: [[9 values], ...] — one row per point. Set i of the 9-channel
    run carries channels 3i..3i+2 (a=blue, b=green, c=red, per §9.2).
    """
    def fake_run(steps, work_dir, available):
        for s in steps:
            out = s.get("stdout", "")
            for i in range(3):
                if out.endswith(f"electric{i}.res"):
                    rows = [pt[3 * i:3 * i + 3] for pt in electric_channels_per_point]
                    open(os.path.join(work_dir, out), "w").write(_res_text(rows))
                elif out.endswith(f"daylight{i}.res") or out.endswith(f"combined{i}.res"):
                    rows = [[0.0, 0.0, 0.0] for _ in electric_channels_per_point]
                    open(os.path.join(work_dir, out), "w").write(_res_text(rows))
        return {"ran": True, "returncode": 0, "commands": [], "outputs": []}
    return fake_run


def _run(monkeypatch, tmp_path, electric_channels_per_point):
    monkeypatch.setattr(grid, "_available", lambda: True)
    monkeypatch.setattr(grid, "run_sequence", _fake_run_with(electric_channels_per_point))
    n = len(electric_channels_per_point)
    return grid.run_grid(
        scene_sets=[["m_a.rad", "sky_a.rad", "g_a.rad"],
                    ["m_b.rad", "sky_b.rad", "g_b.rad"],
                    ["m_c.rad", "sky_c.rad", "g_c.rad"]],
        points=[[0, 0, 1.2, 0, 0, 1]] * n, channel_type=1, work_dir=str(tmp_path),
        electric_lights=[{"ies": _IES_FIX, "preset": SPIKY,
                          "placement": {"positions": [{"xyz": [0, 0, 3]}]}}],
        run=True)


def test_inline_list_spd_does_not_crash_the_electric_block(monkeypatch, tmp_path):
    """An SPD supplied inline as [[nm, value], ...] is a documented input shape.

    `_sole_electric_spd` puts it in a set to test whether the luminaires share one spectrum,
    and a list is unhashable — so the whole run dies with TypeError. This is the shape an MCP
    caller sends, because JSON has no other way to carry an inline spectrum.
    """
    s = _source_channels()
    monkeypatch.setattr(grid, "_available", lambda: True)
    monkeypatch.setattr(grid, "run_sequence", _fake_run_with([s]))
    out = grid.run_grid(
        scene_sets=[["m_a.rad"], ["m_b.rad"], ["m_c.rad"]],
        points=[[0, 0, 1.2, 0, 0, 1]], channel_type=1, work_dir=str(tmp_path),
        electric_lights=[{"ies": _IES_FIX, "spd": [list(p) for p in get_preset(SPIKY)],
                          "placement": {"positions": [{"xyz": [0, 0, 3]}]}}],
        run=True)
    assert out["ran"] is True
    assert out["electric"]["metrics"][0]["mel_der"] > 0


def test_mel_der_differs_between_two_points_with_different_spectra(monkeypatch, tmp_path):
    """Two points, two different transported spectra, one mel-DER value: that cannot be right.

    Point 0 sees the source spectrum unchanged; point 1 sees it through a warm surface. A
    mel-DER that is identical at both is reporting the lamp, not the room.
    """
    s = _source_channels()
    warm = [c * t for c, t in zip(s, _warm_transport())]
    out = _run(monkeypatch, tmp_path, [s, warm])
    m = out["electric"]["metrics"]
    assert m[0]["mel_der"] != pytest.approx(m[1]["mel_der"], rel=1e-6), (
        "mel_der is constant across points with different spectra — it is the SOURCE value")


def test_mel_der_falls_when_the_room_shifts_the_spectrum_red(monkeypatch, tmp_path):
    """A warm room lowers melanopic content. The reported mel-DER must move with it."""
    s = _source_channels()
    warm = [c * t for c, t in zip(s, _warm_transport())]
    out = _run(monkeypatch, tmp_path, [warm])
    at_point = out["electric"]["metrics"][0]["mel_der"]
    source = mel_der(get_preset(SPIKY))
    assert at_point < source * 0.99, (
        f"warm-surface transport must lower mel-DER below the source {source:.4f}, got {at_point:.4f}")


def test_mel_edi_is_built_from_the_at_point_der(monkeypatch, tmp_path):
    """mel_edi = photopic_lux(at the point) x mel-DER(at the point) — both at the same place."""
    s = _source_channels()
    warm = [c * t for c, t in zip(s, _warm_transport())]
    out = _run(monkeypatch, tmp_path, [warm])
    m = out["electric"]["metrics"][0]
    assert m["mel_edi"] == pytest.approx(m["photopic_lux"] * m["mel_der"], rel=1e-9)
    naive = m["photopic_lux"] * mel_der(get_preset(SPIKY))
    assert m["mel_edi"] < naive * 0.99, "mel_edi still carries the source mel-DER"


def test_transport_shift_advisory_fires_and_names_the_size(monkeypatch, tmp_path):
    """A materially shifted spectrum must be announced, or the at-point value looks like a bug
    to anyone holding the luminaire's datasheet."""
    from hcl_mcp.advisories import advise
    s = _source_channels()
    warm = [c * t for c, t in zip(s, _warm_transport())]
    out = _run(monkeypatch, tmp_path, [warm])
    items = advise("run_grid", {}, out["electric"]["metrics"][0])
    codes = [a["code"] for a in items]
    assert "SPECTRAL_TRANSPORT_SHIFT" in codes


def test_transport_shift_advisory_fires_on_the_WHOLE_run_grid_result(monkeypatch, tmp_path):
    """The advisory must reach the tool result, not just a metrics dict picked out by hand.

    run_grid nests per-point metrics under `electric.metrics[i]`, so a rule that reads
    `transport_ratio` off the top level alone fires in a unit test and never in production —
    on the very tool the defect lived in. Asserting against the FULL result is the difference.
    """
    from hcl_mcp.advisories import advise
    s = _source_channels()
    warm = [c * t for c, t in zip(s, _warm_transport())]
    out = _run(monkeypatch, tmp_path, [s, warm])          # point 0 neutral, point 1 shifted
    codes = [a["code"] for a in advise("run_grid", {}, out)]
    assert "SPECTRAL_TRANSPORT_SHIFT" in codes, "advisory never reaches the run_grid result"


def test_transport_shift_advisory_reports_the_worst_point(monkeypatch, tmp_path):
    """With one advisory standing for many points, it must describe the worst of them."""
    from hcl_mcp.advisories import advise
    s = _source_channels()
    mild = [c * t for c, t in zip(s, [0.60 + 0.02 * i / 8.0 for i in range(9)])]
    warm = [c * t for c, t in zip(s, _warm_transport())]
    out = _run(monkeypatch, tmp_path, [mild, warm])
    ratios = [m["transport_ratio"] for m in out["electric"]["metrics"]]
    worst_pct = max(abs(1.0 - r) for r in ratios) * 100.0
    msg = [a for a in advise("run_grid", {}, out)
           if a["code"] == "SPECTRAL_TRANSPORT_SHIFT"][0]["message"]
    assert f"{worst_pct:.1f}%" in msg, f"message must quote the worst shift {worst_pct:.1f}%: {msg}"


def test_no_transport_advisory_on_a_run_grid_result_with_a_neutral_room(monkeypatch, tmp_path):
    """The nested walk must not turn the rule into an always-on alarm."""
    from hcl_mcp.advisories import advise
    s = _source_channels()
    out = _run(monkeypatch, tmp_path, [[c * 0.55 for c in s]])
    codes = [a["code"] for a in advise("run_grid", {}, out)]
    assert "SPECTRAL_TRANSPORT_SHIFT" not in codes


def test_no_transport_advisory_when_the_room_is_spectrally_neutral(monkeypatch, tmp_path):
    """The rule must stay quiet on a grey room, or it is noise on every electric run."""
    from hcl_mcp.advisories import advise
    s = _source_channels()
    out = _run(monkeypatch, tmp_path, [[c * 0.55 for c in s]])
    codes = [a["code"] for a in advise("run_grid", {}, out["electric"]["metrics"][0])]
    assert "SPECTRAL_TRANSPORT_SHIFT" not in codes


def test_a_source_with_a_dark_band_does_not_divide_by_zero():
    """A narrow-band source can emit nothing across a whole 40 nm bin.

    Its transport there is undefined, not infinite: no light left the lamp in that band, so
    nothing measured there can be attributed to it. The band must drop out of both integrals
    rather than take the whole call down with a ZeroDivisionError.
    """
    from hcl_core.metrics import circadian_metrics
    # Emission only above 500 nm: the three blue bins ([380,419], [419,459], [459,499]) average
    # to exactly zero.
    spd = [[nm, 0.0 if nm < 500 else 1.0] for nm in range(380, 781)]
    ch = bin_average(parse_spd(spd), 1)
    assert ch[0] == 0.0 and ch[1] == 0.0
    m = circadian_metrics([c * 0.5 for c in ch], 1, spd=spd)
    assert m["mel_der_source"] == "spd_transported"
    assert m["mel_der"] > 0


def test_unrecoverable_transport_falls_back_and_says_so():
    """All-dark channels carry no transport to recover. Report the source value, labelled."""
    from hcl_core.metrics import circadian_metrics
    m = circadian_metrics([0.0] * 9, 1, spd=get_preset(SPIKY))
    assert m["mel_der_source"] == "spd_source_untransported"
    assert m["mel_der"] == pytest.approx(mel_der(get_preset(SPIKY)), rel=1e-9)
    assert "mel_der_note" in m


def test_neutral_transport_still_reproduces_the_exact_source_der(monkeypatch, tmp_path):
    """The case the SPD route was added for must not regress.

    With a spectrally neutral room the spectrum at the point IS the source spectrum, so the
    exact CIE S 026 value must survive — including its advantage over the binned route, which
    reads ~8% high on this fluorescent.
    """
    s = _source_channels()
    grey = [c * 0.55 for c in s]           # flat reflectance: no spectral shift
    out = _run(monkeypatch, tmp_path, [grey])
    m = out["electric"]["metrics"][0]
    assert m["mel_der"] == pytest.approx(mel_der(get_preset(SPIKY)), rel=2e-3)
