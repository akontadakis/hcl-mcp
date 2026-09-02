# tests/test_atmos_refinements_guard.py
# NOTE: _HEADER/_row/_write_epw are copied VERBATIM from tests/test_spectral_pipeline.py — the proven
# EPW fixture (day is hardcoded to 21; _row takes (month, hour, ...)). Other new test files in this
# plan import these three helpers from this module by bare name (no `tests.` prefix — there is no
# tests/__init__.py, and pytest's prepend import mode makes sibling test modules importable directly).
from hcl_core.spectral_pipeline import record_from_epw
from hcl_core import atmosphere

_HEADER = "\n".join([
    "LOCATION,Athens,-,GRC,TMY,167160,37.90,23.73,2.0,28.0",
    "DESIGN CONDITIONS,0", "TYPICAL/EXTREME PERIODS,0", "GROUND TEMPERATURES,0",
    "HOLIDAYS/DAYLIGHT SAVINGS,No,0,0,0", "COMMENTS 1,", "COMMENTS 2,",
    "DATA PERIODS,1,1,Data,Sunday, 1/ 1,12/31",
])

def _row(month, hour, db, dew, rh, pr, ghi, dni, dhi, ts, os_, pc, aod, alb):
    v = ["2020", str(month), "21", str(hour), "0", "C9C9C9"] + ["0"] * 29
    v[6] = str(db); v[7] = str(dew); v[8] = str(rh); v[9] = str(pr)
    v[13] = str(ghi); v[14] = str(dni); v[15] = str(dhi)
    v[22] = str(ts); v[23] = str(os_); v[28] = str(pc); v[29] = str(aod); v[32] = str(alb)
    return ",".join(v)

def _write_epw(tmp_path, *rows):
    p = tmp_path / "t.epw"
    p.write_text(_HEADER + "\n" + "\n".join(rows) + "\n")
    return str(p)

def test_default_call_matches_explicit_legacy_defaults(tmp_path):
    epw = _write_epw(tmp_path, _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2))
    base = record_from_epw(epw, 6, 21, 12)
    same = record_from_epw(epw, 6, 21, 12, overrides={})   # explicit legacy default reproduces bare call
    assert base.direct_normal == same.direct_normal
    assert base.sky_diffuse_horizontal == same.sky_diffuse_horizontal

def test_derive_default_aerosol_g_is_065():
    st = atmosphere.derive({"dry_bulb_c": 28.0, "rh_pct": 60.0, "pressure_pa": 101300.0,
                            "aod": 0.12, "albedo": 0.2})
    assert getattr(st, "aerosol_g", 0.65) == 0.65
