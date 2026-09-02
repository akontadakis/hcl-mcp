"""Gated live Daysim smoke test. SKIPPED in CI.

Runs only when Daysim is already available (HCL_DAYSIM_BIN/PATH) or when explicitly opted in with
HCL_DAYSIM_LIVE=1 (which also permits a one-time build_daysim). The emit-path test runs everywhere.
"""
import os
import asyncio
import pytest

from hcl_daysim.discover import daysim_status
import hcl_daysim.subhourly as sub
import hcl_mcp.server as srv

_LIVE = daysim_status()["available"] or os.environ.get("HCL_DAYSIM_LIVE") == "1"

# A 1-day, 2-record minimal EPW header + data (enough for epw2wea to emit a tiny hourly .wea).
_TINY_EPW = (
    "LOCATION,Test,WA,USA,Custom,000000,47.6,-122.3,-8.0,20.0\n"
    "DESIGN CONDITIONS,0\n"
    "TYPICAL/EXTREME PERIODS,0\n"
    "GROUND TEMPERATURES,0\n"
    "HOLIDAYS/DAYLIGHT SAVINGS,No,0,0,0\n"
    "COMMENTS 1,\n"
    "COMMENTS 2,\n"
    "DATA PERIODS,1,1,Data,Sunday,1/1,1/1\n"
    + "".join(
        f"1990,1,1,{h+1},60,?9?9?9?9?9?9?9?9?9?9?9?9?9?9?9?9?9?9?9?9?9*9*9?9?9,"
        "10.0,5.0,80,101325,0,0,300,200,150,100,100,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0\n"
        for h in range(24)
    )
)

def test_emit_path_offline(tmp_path, monkeypatch):
    # Always-runnable: emit path returns commands regardless of Daysim.
    monkeypatch.setattr(sub, "_available", lambda: False)
    out = asyncio.run(srv.generate_subhourly_wea(
        epw="/w/in.epw", timestep_min=6, latitude=47.6, longitude=-122.3, time_zone=120,
        site_elevation=20, work_dir=str(tmp_path), run=False))
    assert out["ran"] is False and any("ds_shortterm" in c for c in out["commands"])

@pytest.mark.skipif(not _LIVE, reason="Daysim not available and HCL_DAYSIM_LIVE!=1")
def test_live_build_then_generate(tmp_path):
    # Build once if needed (opt-in), then generate a sub-hourly .wea from the fixture EPW.
    if not daysim_status()["available"]:
        res = srv.build_daysim(src_dir=str(tmp_path / "Daysim"), run=True, work_dir=str(tmp_path))
        assert res["ran"], f"build_daysim failed: {res.get('reason')}"
        os.environ["HCL_DAYSIM_BIN"] = res["bin_dir"]
    assert daysim_status()["available"]

    epw = tmp_path / "tiny.epw"; epw.write_text(_TINY_EPW)
    # No explicit coords: exercise EPW-derived location (correct DAYSIM convention from the EPW).
    out = asyncio.run(srv.generate_subhourly_wea(
        epw=str(epw), timestep_min=6, work_dir=str(tmp_path), run=True))
    assert out["ran"] is True, out
    assert os.path.isfile(out["wea"]) and os.path.getsize(out["wea"]) > 0
    # the generated .hea used the EPW's location in DAYSIM convention (longitude negated to +122.3)
    assert "longitude 122.3" in (tmp_path / "daysim_header.hea").read_text()
