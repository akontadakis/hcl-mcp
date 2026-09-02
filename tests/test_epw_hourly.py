from hcl_core import epw_hourly

# A minimal EPW: 8 header lines, then two data rows. Field layout per the EPW data dictionary.
# Comma indices: 0 yr,1 mo,2 day,3 hr,4 min,5 flags(string),6 drybulb,7 dewpoint,8 rh,9 pressure(Pa),
# 10 etrh,11 etrdn,12 horizIR,13 GHI,14 DNI,15 DHI,...,22 totalsky,23 opaquesky,...,28 precipwater,
# 29 AOD,...,32 albedo.
_HEADER = "\n".join([
    "LOCATION,Athens,-,GRC,TMY,167160,37.90,23.73,2.0,28.0",
    "DESIGN CONDITIONS,0",
    "TYPICAL/EXTREME PERIODS,0",
    "GROUND TEMPERATURES,0",
    "HOLIDAYS/DAYLIGHT SAVINGS,No,0,0,0",
    "COMMENTS 1,",
    "COMMENTS 2,",
    "DATA PERIODS,1,1,Data,Sunday, 1/ 1,12/31",
])


def _row(month, hour, drybulb, dew, rh, pressure, ghi, dni, dhi,
         totsky, opqsky, precip, aod, albedo):
    f = ["2020", str(month), "21", str(hour), "0", "C9C9C9"]
    # pad to 35 fields, then place values at their indices
    vals = f + ["0"] * (35 - len(f))
    vals[6] = str(drybulb); vals[7] = str(dew); vals[8] = str(rh); vals[9] = str(pressure)
    vals[13] = str(ghi); vals[14] = str(dni); vals[15] = str(dhi)
    vals[22] = str(totsky); vals[23] = str(opqsky)
    vals[28] = str(precip); vals[29] = str(aod); vals[32] = str(albedo)
    return ",".join(vals)


def _write_epw(tmp_path, *rows):
    p = tmp_path / "test.epw"
    p.write_text(_HEADER + "\n" + "\n".join(rows) + "\n")
    return str(p)


def test_parses_row_values(tmp_path):
    path = _write_epw(tmp_path, _row(6, 12, 28.5, 12.0, 40, 101300, 800, 850, 120,
                                     2, 1, 15, 0.12, 0.2))
    rows = epw_hourly.parse_epw_hourly(path)
    assert len(rows) == 1
    r = rows[0]
    assert r["month"] == 6 and r["day"] == 21 and r["hour"] == 12
    assert r["dry_bulb_c"] == 28.5
    assert r["dew_point_c"] == 12.0
    assert r["rh_pct"] == 40.0
    assert r["pressure_pa"] == 101300.0
    assert r["ghi"] == 800.0 and r["dni"] == 850.0 and r["dhi"] == 120.0
    assert r["total_sky_cover"] == 2.0 and r["opaque_sky_cover"] == 1.0
    assert r["precip_water_mm"] == 15.0
    assert r["aod"] == 0.12
    assert r["albedo"] == 0.2


def test_sentinels_become_none(tmp_path):
    # dew point 99.9, RH 999, pressure 999999, precip 999, AOD .999, albedo 999 are EPW "missing".
    # Also test dry_bulb 99.9, ghi/dni/dhi 9999, opaque_sky_cover 99.
    path = _write_epw(tmp_path, _row(1, 3, 99.9, 99.9, 999, 999999, 9999, 9999, 9999,
                                     99, 99, 999, 0.999, 999))
    r = epw_hourly.parse_epw_hourly(path)[0]
    assert r["dry_bulb_c"] is None
    assert r["dew_point_c"] is None
    assert r["rh_pct"] is None
    assert r["pressure_pa"] is None
    assert r["ghi"] is None
    assert r["dni"] is None
    assert r["dhi"] is None
    assert r["total_sky_cover"] is None
    assert r["opaque_sky_cover"] is None
    assert r["precip_water_mm"] is None
    assert r["aod"] is None
    assert r["albedo"] is None


def test_skips_eight_header_lines_and_blank_lines(tmp_path):
    path = _write_epw(tmp_path,
                      _row(6, 11, 25, 10, 45, 101000, 700, 800, 110, 1, 0, 14, 0.1, 0.2),
                      _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2))
    rows = epw_hourly.parse_epw_hourly(path)
    assert len(rows) == 2
    assert rows[0]["hour"] == 11 and rows[1]["hour"] == 12


def test_row_for_finds_match(tmp_path):
    path = _write_epw(tmp_path,
                      _row(6, 11, 25, 10, 45, 101000, 700, 800, 110, 1, 0, 14, 0.1, 0.2),
                      _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2))
    rows = epw_hourly.parse_epw_hourly(path)
    assert epw_hourly.row_for(rows, 6, 21, 12)["dni"] == 850.0
    assert epw_hourly.row_for(rows, 6, 21, 99) is None


# --- D-27: spec §13 + methodology §14 — malformed rows skipped with a reason + reported drop count ---

def test_diagnostics_reports_dropped_counts_by_reason(tmp_path):
    """parse_epw_hourly_diagnostics returns (rows, diag) with kept/dropped + per-reason counts."""
    good = _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2)
    short = "2020,6,21,13,0,C9C9C9,28,12,40"          # < 16 fields
    bad_date = ",".join(["2020", "X", "21", "14", "0", "C9C9C9"] + ["0"] * 29)  # non-int month
    path = _write_epw(tmp_path, good, short, bad_date)
    rows, diag = epw_hourly.parse_epw_hourly_diagnostics(path)
    assert len(rows) == 1
    assert diag["kept"] == 1
    assert diag["dropped"] == 2
    assert diag["reasons"]["short_row"] == 1
    assert diag["reasons"]["bad_date"] == 1


def test_parse_epw_hourly_returns_only_rows_for_backward_compat(tmp_path):
    """The original list-returning API is preserved (callers/tests unchanged)."""
    good = _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2)
    path = _write_epw(tmp_path, good, "2020,6,21,13,0,C9C9C9,28")
    rows = epw_hourly.parse_epw_hourly(path)
    assert isinstance(rows, list) and len(rows) == 1


def test_dropped_rows_are_logged_with_a_reason(tmp_path, caplog):
    """A dropped row emits a logged reason (spec §13: 'skipped with a logged reason')."""
    import logging
    good = _row(6, 12, 28, 12, 40, 101300, 800, 850, 120, 2, 1, 15, 0.12, 0.2)
    path = _write_epw(tmp_path, good, "2020,6,21,13,0,C9C9C9,28")
    with caplog.at_level(logging.WARNING, logger="hcl_core.epw_hourly"):
        epw_hourly.parse_epw_hourly(path)
    assert any("dropped" in r.message.lower() for r in caplog.records)
