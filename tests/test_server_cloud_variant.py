import pytest
from hcl_mcp import server

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

def _write_epw(tmp_path):
    p = tmp_path / "t.epw"
    p.write_text(_HEADER + "\n" + _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2) + "\n")
    return str(p)

def test_default_and_seed_differ(tmp_path):
    epw = _write_epw(tmp_path)
    base = server.spectral_sky_from_epw(epw, 6, 21, 12)
    seed = server.spectral_sky_from_epw(epw, 6, 21, 12, cloud_variant="seed")
    assert base["sky_diffuse_horizontal"] != seed["sky_diffuse_horizontal"]

def test_local_requires_coeffs(tmp_path):
    epw = _write_epw(tmp_path)
    with pytest.raises(ValueError):
        server.spectral_sky_from_epw(epw, 6, 21, 12, cloud_variant="local")

def test_local_bad_ccm_coeffs_path_raises_clean_valueerror(tmp_path):
    epw = _write_epw(tmp_path)
    missing = str(tmp_path / "does_not_exist_ccm.csv")
    with pytest.raises(ValueError, match="cloud_variant='local' could not load ccm_coeffs"):
        server.spectral_sky_from_epw(epw, 6, 21, 12, cloud_variant="local", ccm_coeffs=missing)
