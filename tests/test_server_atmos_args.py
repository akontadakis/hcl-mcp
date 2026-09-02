from hcl_mcp import server
from test_atmos_refinements_guard import _write_epw, _row   # bare sibling import (no tests/__init__.py)


def test_atmosphere_from_epw_ozone_climatology(tmp_path):
    epw = _write_epw(tmp_path, _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2))
    base = server.atmosphere_from_epw(epw, 6, 21, 12)
    clim = server.atmosphere_from_epw(epw, 6, 21, 12, ozone_mode="climatology")
    assert base["ozone_atm_cm"] == 0.30
    assert clim["ozone_atm_cm"] != 0.30
