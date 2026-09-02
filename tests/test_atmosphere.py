import pytest

from hcl_core import atmosphere


def test_gueymard94_pw_reasonable_magnitude():
    # Warm humid: ~mid-latitude summer → order 2-4 cm precipitable water.
    pw = atmosphere.gueymard94_pw(temp_air_c=28.0, relative_humidity_pct=60.0)
    assert 1.5 < pw < 5.0


def test_gueymard94_pw_monotonic_in_humidity():
    dry = atmosphere.gueymard94_pw(temp_air_c=20.0, relative_humidity_pct=20.0)
    wet = atmosphere.gueymard94_pw(temp_air_c=20.0, relative_humidity_pct=90.0)
    assert wet > dry


def test_reitan63_pw_positive_and_monotonic():
    cold = atmosphere.reitan63_pw(dew_point_c=-5.0)
    warm = atmosphere.reitan63_pw(dew_point_c=20.0)
    assert 0.0 < cold < warm < 8.0


def _full_row():
    return {
        "month": 6, "day": 21, "hour": 12,
        "dry_bulb_c": 28.0, "dew_point_c": 12.0, "rh_pct": 60.0, "pressure_pa": 101300.0,
        "ghi": 800.0, "dni": 850.0, "dhi": 120.0,
        "total_sky_cover": 2.0, "opaque_sky_cover": 1.0,
        "precip_water_mm": 15.0, "aod": 0.12, "albedo": 0.18,
    }


def test_derive_uses_epw_pressure_and_albedo_and_aod():
    st = atmosphere.derive(_full_row())
    assert abs(st.pressure_mbar - 1013.0) < 0.5          # 101300 Pa / 100
    assert st.albedo == 0.18
    assert st.aod500 == 0.12
    assert st.ozone_atm_cm == 0.30
    assert st.angstrom_alpha == 1.14
    assert st.provenance["pressure_mbar"]["source"] == "epw"
    assert st.provenance["ozone_atm_cm"]["source"] == "default"


def test_derive_pw_prefers_gueymard_when_rh_present():
    st = atmosphere.derive(_full_row())
    assert abs(st.pw_cm - atmosphere.gueymard94_pw(28.0, 60.0)) < 1e-9
    assert st.provenance["pw_cm"]["method"] == "gueymard94"


def test_derive_pw_falls_back_to_reitan_without_rh():
    row = _full_row()
    row["rh_pct"] = None
    st = atmosphere.derive(row)
    assert abs(st.pw_cm - atmosphere.reitan63_pw(12.0)) < 1e-9
    assert st.provenance["pw_cm"]["method"] == "reitan63"


def test_derive_applies_defaults_when_fields_missing():
    row = _full_row()
    row["pressure_pa"] = None
    row["albedo"] = None
    row["aod"] = None
    st = atmosphere.derive(row)
    assert st.pressure_mbar == 1013.25
    assert st.albedo == 0.20
    assert st.aod500 == 0.10
    assert st.provenance["albedo"]["source"] == "default"
    assert st.provenance["aod500"]["source"] == "default"


def test_overrides_win_and_are_marked():
    st = atmosphere.derive(_full_row(), overrides={"aod500": 0.25, "ozone_atm_cm": 0.32})
    assert st.aod500 == 0.25
    assert st.ozone_atm_cm == 0.32
    assert st.provenance["aod500"]["source"] == "override"
    assert st.provenance["ozone_atm_cm"]["source"] == "override"


def test_pw_cm_override_path():
    st = atmosphere.derive(_full_row(), overrides={"pw_cm": 2.5})
    assert st.pw_cm == 2.5
    assert st.provenance["pw_cm"]["source"] == "override"


def test_pw_formulas_pinned_values():
    # Regression lock: guards against silent drift in coefficient transcription.
    # Pinned via: python -c "from hcl_core import atmosphere; print(repr(...))"
    assert abs(atmosphere.gueymard94_pw(28.0, 60.0) - 3.5744180977243283) < 1e-6
    assert abs(atmosphere.reitan63_pw(20.0) - 3.753917645034515) < 1e-6


# --- D-1: spec §4 declares per-field provenance {source, method, uncertainty} ---

def test_provenance_entries_carry_uncertainty_key():
    from hcl_core import atmosphere
    row = {"month": 6, "day": 21, "hour": 12, "dry_bulb_c": 28.0, "rh_pct": 40.0,
           "dew_point_c": 12.0, "pressure_pa": 101300.0, "aod": 0.12, "albedo": 0.2}
    atm = atmosphere.derive(row)
    for field, entry in atm.provenance.items():
        assert set(entry.keys()) == {"source", "method", "uncertainty"}, field


def test_van_heuklon_athens_summer_reasonable():
    # Athens (37.9N, 23.73E), ~Jun 21 (doy 172): mid-latitude summer ~0.33-0.37 atm-cm.
    o3 = atmosphere.van_heuklon_ozone(37.90, 23.73, 172)
    assert 0.30 < o3 < 0.40


def test_van_heuklon_equator_lower_than_high_lat():
    # Ozone climatology: high latitude carries more column ozone than the equator.
    eq = atmosphere.van_heuklon_ozone(0.0, 23.73, 172)
    hi = atmosphere.van_heuklon_ozone(60.0, 23.73, 172)
    assert hi > eq
    assert abs(eq - 0.235) < 0.02   # equator collapses to the 235 DU base


def test_van_heuklon_hemisphere_season_flips():
    # Same |lat|, same day: the N and S hemispheres use distinct van Heuklon coefficient sets
    # (A/B/C/F/H/I differ), so the two column-ozone values must not coincide.
    n = atmosphere.van_heuklon_ozone(45.0, 0.0, 172)
    s = atmosphere.van_heuklon_ozone(-45.0, 0.0, 172)
    assert n != s


def test_van_heuklon_published_reference_values():
    # Pinned against van Heuklon (1979) Table 1 hemisphere-specific coefficients
    # (canonical reference implementation: R.T. Wilson vanHOzone).
    assert atmosphere.van_heuklon_ozone(37.9, 23.73, 172) == pytest.approx(0.34202, abs=1e-4)
    assert atmosphere.van_heuklon_ozone(37.9, 23.73, 74) == pytest.approx(0.34304, abs=1e-4)
    assert atmosphere.van_heuklon_ozone(50.0, 0.0, 1) == pytest.approx(0.34070, abs=1e-4)  # Wilson canonical example
    assert atmosphere.van_heuklon_ozone(0.0, 23.73, 172) == pytest.approx(0.23500, abs=1e-5)  # equator -> 235 base
    assert atmosphere.van_heuklon_ozone(60.0, 23.73, 172) == pytest.approx(0.41577, abs=1e-4)
    assert atmosphere.van_heuklon_ozone(-37.9, 23.73, 172) == pytest.approx(0.27796, abs=1e-4)


def test_van_heuklon_peaks_in_local_spring_not_summer():
    # Physical-phase guard: real total column ozone peaks in local SPRING, not mid-summer.
    # NH: spring (May, doy 135) column ozone EXCEEDS mid-summer (Jul, doy 196).
    assert atmosphere.van_heuklon_ozone(37.9, 23.73, 135) > atmosphere.van_heuklon_ozone(37.9, 23.73, 196)
    # SH mirror: SH spring is ~Sep-Nov, so SH ozone at doy 196 (austral winter->spring approach)
    # exceeds SH doy 135 (austral autumn trough).
    assert atmosphere.van_heuklon_ozone(-37.9, 23.73, 196) > atmosphere.van_heuklon_ozone(-37.9, 23.73, 135)


def test_aerosol_g_default_and_override():
    row = {"dry_bulb_c": 20.0, "rh_pct": 50.0, "pressure_pa": 101300.0, "aod": 0.1, "albedo": 0.2}
    assert atmosphere.derive(row).aerosol_g == 0.65
    st = atmosphere.derive(row, overrides={"aerosol_g": 0.60})
    assert st.aerosol_g == 0.60
    assert st.provenance["aerosol_g"]["source"] == "override"


def test_aod_anchor_identity_at_500():
    row = {"pressure_pa": 101300.0, "aod": 0.20, "albedo": 0.2, "dry_bulb_c": 20.0, "rh_pct": 50.0}
    assert atmosphere.derive(row).aod500 == atmosphere.derive(row, aod_anchor_nm=500.0).aod500


def test_aod_anchor_550_converts_up():
    # AOD given at 550 nm converts to a LARGER tau500 (shorter wavelength = more AOD).
    row = {"pressure_pa": 101300.0, "aod": 0.20, "albedo": 0.2, "dry_bulb_c": 20.0, "rh_pct": 50.0}
    st = atmosphere.derive(row, aod_anchor_nm=550.0)
    assert st.aod500 > 0.20
    assert st.provenance["aod500"]["method"] == "angstrom_from_550.0nm"


def test_ozone_mode_climatology_differs_from_constant():
    row = {"pressure_pa": 101300.0, "aod": 0.1, "albedo": 0.2, "dry_bulb_c": 20.0, "rh_pct": 50.0}
    const = atmosphere.derive(row)                                            # 0.30
    clim = atmosphere.derive(row, ozone_mode="climatology",
                             lat_deg=37.9, lon_deg=23.73, day_of_year=172)
    assert const.ozone_atm_cm == 0.30
    assert clim.ozone_atm_cm != 0.30
    assert clim.provenance["ozone_atm_cm"]["method"] == "van_heuklon79"


# ---- EPW albedo 0.000 is a de-facto "no data" marker, not a measurement ----

def test_albedo_zero_is_treated_as_missing_with_honest_provenance():
    # REGRESSION: IWEC/TMY2 write a literal 0.000 for every hour instead of the 999.0 sentinel.
    # Accepting it zeroed the whole ground-reflected term AND claimed source="epw".
    #
    # Arbitrary fixture coordinates, NOT any measured site. The expectations below are
    # pinned at THIS geometry, so the values stay as they are.
    row = dict(_full_row(), albedo=0.0)
    st = atmosphere.derive(row, lat_deg=37.98, lon_deg=23.73, day_of_year=172)
    assert st.albedo == 0.20                                  # the documented default
    assert st.provenance["albedo"]["source"] == "default"      # never "epw" for a defaulted value


def test_low_but_physical_albedo_still_comes_from_the_epw():
    # a real dark surface (Chania ships 0.06-0.09) must NOT be swallowed by the floor
    row = dict(_full_row(), albedo=0.06)
    st = atmosphere.derive(row, lat_deg=37.98, lon_deg=23.73, day_of_year=172)
    assert st.albedo == 0.06
    assert st.provenance["albedo"]["source"] == "epw"


def test_epw_hourly_reports_a_zero_albedo_column_as_missing():
    from hcl_core.epw_hourly import _num, _VALID
    assert _num(["0.000"], 0, 999.0, _VALID["albedo"]) is None      # de-facto no-data
    assert _num(["0.200"], 0, 999.0, _VALID["albedo"]) == 0.20      # real value survives
    assert _num(["999.0"], 0, 999.0, _VALID["albedo"]) is None      # documented sentinel


def test_bundled_iwec_epw_yields_a_nonzero_ground_term():
    # The end-to-end guard: with albedo defaulted, a vertical surface must see ground glow.
    import os
    epw = os.path.join(os.path.dirname(__file__), os.pardir,
                       "hcl_validation", "inputs", "weather", "GRC_Athens.167160_IWEC.epw")
    if not os.path.exists(epw):
        pytest.skip("Athens IWEC EPW not present")
    from hcl_core.epw_hourly import parse_epw_hourly, row_for
    row = row_for(parse_epw_hourly(epw), 6, 21, 13)
    assert row["albedo"] is None, "0.000 albedo column must parse as missing"
    st = atmosphere.derive(row, lat_deg=37.98, lon_deg=23.73, day_of_year=172)
    assert st.albedo > 0.0 and st.provenance["albedo"]["source"] == "default"
