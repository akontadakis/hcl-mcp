"""Regression tests for the 2026-06-27 end-to-end validation defects (room.obj run).

Each test pins one papercut found while validating the MCP surface against a user OBJ:
  DEF-1  run_grid silently accepts dict-style scene_sets -> misleading oconv error
  DEF-2  run_annual rejects inline point lists (run_grid accepts them)
  DEF-6  save_brief rejects natural key typos with no "did you mean" hint
  DEF-7  build_report mel-EDI row ignores the melanopic_lux key the sim tools actually emit
  DEF-8  daysim_status version probe surfaces ds_shortterm's "fatal error" line as the version
  WEATHER  weather(wea_path=...) dumps the whole year's arrays inline (238 KB) -> token blowup
"""
import os
import asyncio

import pytest


# ---- DEF-1: run_grid must reject dict scene_sets elements with a clear message ----
def test_run_grid_rejects_dict_scene_sets(tmp_path):
    import hcl_radiance.grid as grid
    with pytest.raises(ValueError, match=r"list of \.rad"):
        grid.run_grid(scene_sets=[{"materials": ["m.rad"], "geometry": "g.rad", "sky_color": "s"}],
                      points=[[0, 0, 1.2, 0, 0, 1]], channel_type=0,
                      work_dir=str(tmp_path), run=False)


# ---- DEF-2: run_annual must accept inline [x,y,z,dx,dy,dz] points like run_grid ----
def test_run_annual_accepts_inline_points(tmp_path):
    import hcl_mcp.server as srv
    cs = [{"materials": ["m.rad"], "geometry": "g.rad", "sky_color": [1, 1, 1]} for _ in range(3)]
    out = asyncio.run(srv.run_annual(channel_scenes=cs, wea="x.wea",
                                     points=[[1.0, 1.0, 1.2, 0, -1, 0]], channel_type=1,
                                     run=False, work_dir=str(tmp_path)))
    assert out["ran"] is False and "commands" in out   # emit path, no crash on a list
    # the inline rows were materialized to a .pts on disk that the commands can reference
    assert os.path.exists(os.path.join(str(tmp_path), "annual_points.pts"))


# ---- DEF-6: save_brief should suggest the right key for a known typo ----
def test_save_brief_suggests_alias_for_known_typo(tmp_path):
    from hcl_mcp.studio import save_brief_to_dir
    with pytest.raises(ValueError, match="did you mean"):
        save_brief_to_dir(str(tmp_path), "s1", {"fixtures": {"fixture_count": 8}})


# ---- DEF-7: build_report mel-EDI row reads melanopic_lux (the sim tools' key) ----
def test_report_mel_edi_row_converts_a_legacy_melanopic_lux_brief(tmp_path):
    # DEF-7: a brief carrying only `melanopic_lux` must still populate the row (not "not
    # evaluated"). But melanopic_lux is NOT mel-EDI, so the row must show the CONVERTED value and
    # flag the approximation -- printing 265 against a 250 mel-EDI target was a false PASS.
    from hcl_mcp.studio import build_report_to_dir, empty_brief
    b = empty_brief("r7")
    b["goal"] = {"mel_edi_target": 250}
    b["sim_results"] = {"photopic_lux": 300, "melanopic_lux": 265}   # natural key, NOT 'mel_edi'
    res = build_report_to_dir(str(tmp_path), "r7", b)
    md = open(res["md_path"]).read()
    row = [ln for ln in md.splitlines() if "mel-EDI (lx)" in ln][0]
    assert "not evaluated" not in row                       # the row is still populated
    assert "265" not in row                                 # but NOT as raw melanopic_lux
    assert "240.9" in row and "❌" in row                    # 265 / 1.0997 -> fails the 250 target
    assert "derived from a legacy" in md                     # approximation is disclosed


def test_report_mel_edi_row_prefers_exact_mel_der_when_present(tmp_path):
    # With mel_der in the brief the exact S 026 relation (E_v x mel-DER) is used, no approximation.
    from hcl_mcp.studio import build_report_to_dir, empty_brief
    b = empty_brief("r8")
    b["goal"] = {"mel_edi_target": 250}
    b["sim_results"] = {"photopic_lux": 300, "melanopic_lux": 265, "mel_der": 0.9}
    res = build_report_to_dir(str(tmp_path), "r8", b)
    md = open(res["md_path"]).read()
    row = [ln for ln in md.splitlines() if "mel-EDI (lx)" in ln][0]
    assert "270" in row and "✅" in row                       # 300 x 0.9 = 270 >= 250
    assert "derived from a legacy" not in md


def test_report_mel_edi_row_uses_mel_edi_verbatim_when_given(tmp_path):
    from hcl_mcp.studio import build_report_to_dir, empty_brief
    b = empty_brief("r9")
    b["goal"] = {"mel_edi_target": 250}
    b["sim_results"] = {"photopic_lux": 300, "mel_edi": 262, "melanopic_lux": 288}
    res = build_report_to_dir(str(tmp_path), "r9", b)
    md = open(res["md_path"]).read()
    row = [ln for ln in md.splitlines() if "mel-EDI (lx)" in ln][0]
    assert "262" in row and "288" not in row and "✅" in row
    assert "derived from a legacy" not in md


# ---- DEF-8: version probe must not surface the "fatal error" line as a version ----
def test_daysim_version_ignores_fatal_error_line(monkeypatch):
    import hcl_daysim.discover as disc

    class _Proc:
        stdout = (b"/usr/local/daysim/bin/ds_shortterm: fatal error - "
                  b"header file missing\n")

    monkeypatch.setattr(disc.subprocess, "run", lambda *a, **k: _Proc())
    assert disc._version("/usr/local/daysim/bin/ds_shortterm") is None


# ---- WEATHER: weather(wea_path=...) returns a compact summary, not the raw year ----
def test_weather_returns_compact_summary_not_raw_arrays(tmp_path):
    import hcl_mcp.server as srv
    wea = tmp_path / "t.wea"
    wea.write_text("place\n0 0\n0\n0\n0\n0\n"
                   "6 21 8.5 800 90\n6 21 9.5 850 95\n6 21 10.5 900 100\n")
    out = srv.weather(wea_path=str(wea))
    assert "wea_summary" in out
    assert out["wea_summary"]["n_records"] == 3
    # the giant per-hour arrays must NOT be dumped inline
    assert "DNI" not in out.get("wea", {})
