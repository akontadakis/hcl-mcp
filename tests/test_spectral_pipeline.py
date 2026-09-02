import pytest
from hcl_core.spectral_pipeline import record_from_epw
from hcl_core.spectral_pipeline import annual_records

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


def test_record_from_epw_clear_noon(tmp_path):
    epw = _write_epw(tmp_path, _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2))
    rec = record_from_epw(epw, 6, 21, 12)
    assert rec.timestamp == (6, 21, 12)
    assert len(rec.direct_normal) == 401 and len(rec.sky_diffuse_horizontal) == 401
    assert rec.broadband["dni"] == 850.0 and rec.broadband["dhi"] == 120.0
    assert rec.provenance["engine"] == "spectrl2" and rec.provenance["cloud_model"] == "sedes1"
    assert 0.0 <= rec.provenance["clearness_kt"] <= 1.2
    assert rec.atmosphere.pressure_mbar == pytest.approx(1013.0, abs=0.5)


def test_record_from_epw_missing_row_raises(tmp_path):
    epw = _write_epw(tmp_path, _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2))
    with pytest.raises(ValueError):
        record_from_epw(epw, 6, 21, 3)   # hour 3 not in the file


def test_record_from_epw_overrides_applied(tmp_path):
    epw = _write_epw(tmp_path, _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2))
    rec = record_from_epw(epw, 6, 21, 12, overrides={"aod500": 0.30})
    assert rec.atmosphere.aod500 == 0.30
    assert rec.atmosphere.provenance["aod500"]["source"] == "override"


def test_annual_records_one_per_row(tmp_path):
    epw = _write_epw(tmp_path,
                     _row(6, 11, 25, 10, 45, 101000, 700, 800, 110, 1, 0, 14, 0.1, 0.2),
                     _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2))
    recs = annual_records(epw)
    assert len(recs) == 2
    assert recs[0].timestamp == (6, 21, 11) and recs[1].timestamp == (6, 21, 12)


def test_annual_records_hours_subset(tmp_path):
    epw = _write_epw(tmp_path,
                     _row(6, 11, 25, 10, 45, 101000, 700, 800, 110, 1, 0, 14, 0.1, 0.2),
                     _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2))
    recs = annual_records(epw, hours=[(6, 21, 12)])
    assert len(recs) == 1 and recs[0].timestamp == (6, 21, 12)


# --- (a) D-27 follow-through: a RUN surfaces the EPW drop count programmatically ---

def test_annual_records_default_returns_list(tmp_path):
    epw = _write_epw(tmp_path, _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2))
    recs = annual_records(epw)
    assert isinstance(recs, list)


def test_annual_records_return_diagnostics_reports_drops(tmp_path):
    good = _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2)
    short = "2020,6,21,13,0,C9C9C9,28,12,40"          # < 16 fields → dropped
    epw = _write_epw(tmp_path, good, short)
    recs, diag = annual_records(epw, return_diagnostics=True)
    assert len(recs) == 1
    assert diag["kept"] == 1
    assert diag["dropped"] == 1
    assert diag["reasons"]["short_row"] == 1


def test_record_from_epw_return_diagnostics(tmp_path):
    good = _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2)
    short = "2020,6,21,13,0,C9C9C9,28,12,40"
    epw = _write_epw(tmp_path, good, short)
    rec, diag = record_from_epw(epw, 6, 21, 12, return_diagnostics=True)
    assert rec.timestamp == (6, 21, 12)
    assert diag["dropped"] == 1


def test_record_from_epw_ozone_climatology(tmp_path):
    epw = _write_epw(tmp_path, _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2))
    base = record_from_epw(epw, 6, 21, 12)
    clim = record_from_epw(epw, 6, 21, 12, ozone_mode="climatology")
    assert base.atmosphere.ozone_atm_cm == 0.30
    assert clim.atmosphere.ozone_atm_cm != 0.30


def test_annual_records_ozone_climatology_varies_by_season(tmp_path):
    epw = _write_epw(tmp_path,
                     _row(1, 12, 8, 2, 60, 101300, 400, 500, 90, 4, 3, 8, 0.1, 0.2),      # Jan
                     _row(7, 12, 30, 15, 45, 101300, 900, 900, 110, 1, 0, 20, 0.1, 0.2))  # Jul
    recs = annual_records(epw, ozone_mode="climatology")
    o3 = {r.timestamp[0]: r.atmosphere.ozone_atm_cm for r in recs}
    assert o3[1] != o3[7]           # seasonal ozone differs
    assert all(v != 0.30 for v in o3.values())


def test_ozone_climatology_uses_east_positive_longitude(tmp_path):
    """van Heuklon expects the paper's EAST-positive longitude; parse_epw_location returns the
    DAYSIM/.wea WEST-positive value, so the pipeline must sign-flip before deriving ozone."""
    from hcl_core.atmosphere import van_heuklon_ozone
    epw = _write_epw(tmp_path, _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2))
    rec = record_from_epw(epw, 6, 21, 12, ozone_mode="climatology")
    expected = van_heuklon_ozone(37.90, 23.73, 172)     # LOCATION lat/lon as written (east-positive)
    assert rec.atmosphere.ozone_atm_cm == pytest.approx(expected, abs=1e-12)
    wrong_sign = van_heuklon_ozone(37.90, -23.73, 172)  # the pre-fix west-positive feed
    assert abs(expected - wrong_sign) > 1e-3            # the conventions genuinely differ here


def test_record_provenance_carries_ccm_sigma(tmp_path):
    epw = _write_epw(tmp_path, _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2))
    rec = record_from_epw(epw, 6, 21, 12)
    assert "ccm_sigma_mean" in rec.provenance
    assert rec.provenance["ccm_sigma_mean"] is not None
