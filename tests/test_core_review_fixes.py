"""Core-calculation defects found by the 2026-11-26 review, each pinned by the wrong number
it produced. One section per finding (C2, C3, C5, C6, C7 of .scratch/review-2026-11-26)."""
import math

import pytest

from hcl_core import solpos
from hcl_core.compliance import check_compliance
from hcl_core.epw_location import parse_epw_location
from hcl_core.luminaire import color_luminaire
from hcl_core.spd import parse_spd
from hcl_core.spectral_pipeline import annual_records, record_from_epw
from test_spectral_pipeline import _HEADER, _row, _write_epw

MISSING = 9999      # the EPW sentinel for a missing irradiance


# ---- C2: a missing irradiance column is not a zero ----

def _noon(tmp_path, ghi, dni, dhi):
    return _write_epw(tmp_path, _row(6, 12, 28, 12, 40, 101300, ghi, dni, dhi, 2, 1, 15, 0.12, 0.2))


def test_a_missing_ghi_is_closed_from_the_other_two_not_read_as_overcast(tmp_path):
    """GHI drives the clearness index, which picks the cloud colour model. Missing GHI read as
    0 gave Kt = 0: the full overcast correction on a sunny hour (diffuse CCT 11 060 K became
    21 070 K) with nothing in the record to say so."""
    measured = record_from_epw(_noon(tmp_path, 780, 700, 100), month=6, day=21, hour=12)
    cz = math.cos(math.radians(measured.geometry.zenith_deg))
    closed = 700 * cz + 100
    record = record_from_epw(_noon(tmp_path, MISSING, 700, 100), month=6, day=21, hour=12)
    assert record.broadband["ghi"] == pytest.approx(closed)
    assert record.provenance["clearness_kt"] > 0.3
    assert record.provenance["irradiance_derived"] == ["ghi"]
    assert record.provenance["irradiance_missing"] == []


def test_a_missing_dhi_is_closed_from_the_other_two(tmp_path):
    reference = record_from_epw(_noon(tmp_path, 780, 700, 100), month=6, day=21, hour=12)
    cz = math.cos(math.radians(reference.geometry.zenith_deg))
    record = record_from_epw(_noon(tmp_path, 780, 700, MISSING), month=6, day=21, hour=12)
    assert record.broadband["dhi"] == pytest.approx(780 - 700 * cz)
    assert record.provenance["irradiance_derived"] == ["dhi"]


def test_two_missing_columns_cannot_be_closed_and_the_record_says_so(tmp_path):
    record = record_from_epw(_noon(tmp_path, 780, MISSING, MISSING), month=6, day=21, hour=12)
    assert record.provenance["irradiance_missing"] == ["dni", "dhi"]
    assert record.provenance["irradiance_derived"] == []


def test_complete_irradiance_carries_empty_flags(tmp_path):
    record = record_from_epw(_noon(tmp_path, 780, 700, 100), month=6, day=21, hour=12)
    assert record.provenance["irradiance_missing"] == []
    assert record.provenance["irradiance_derived"] == []
    assert record.broadband["ghi"] == 780


def test_the_yearly_loop_applies_the_same_rule(tmp_path):
    (record,) = annual_records(_noon(tmp_path, MISSING, 700, 100))
    assert record.provenance["irradiance_derived"] == ["ghi"]
    assert record.provenance["clearness_kt"] > 0.3


# ---- C3: a half-hour time zone is not truncated for the solar geometry ----

def _epw_at_zone(tmp_path, zone):
    header = _HEADER.replace("37.90,23.73,2.0,28.0", f"28.60,77.20,{zone},216.0")
    path = tmp_path / "zone.epw"
    path.write_text(header + "\n" + _row(6, 12, 30, 20, 50, 98000, 800, 700, 150, 2, 1, 15, 0.3, 0.2) + "\n")
    return str(path)


def test_the_exact_meridian_is_kept_beside_the_truncated_one(tmp_path):
    """India is UTC+5.5: standard meridian 82.5 E. `time_zone` stays truncated (-75) because
    DAYSIM's .wea writer does that; the solar geometry must not use it -- 7.5 degrees of
    meridian is half an hour of solar time."""
    with pytest.warns(UserWarning):
        loc = parse_epw_location(_epw_at_zone(tmp_path, 5.5))
    assert loc["time_zone"] == -75
    assert loc["time_zone_exact"] == pytest.approx(-82.5)


def test_whole_hour_zones_are_unchanged(tmp_path):
    loc = parse_epw_location(_epw_at_zone(tmp_path, 2.0))
    assert loc["time_zone"] == -30 and loc["time_zone_exact"] == pytest.approx(-30.0)


def test_spectra_use_the_exact_meridian_for_the_sun(tmp_path):
    with pytest.warns(UserWarning):
        record = record_from_epw(_epw_at_zone(tmp_path, 5.5), month=6, day=21, hour=12)
    exact = solpos.compute(month=6, day=21, hour=11.5, latitude=28.60, longitude=-77.20,
                           time_zone=-82.5)
    truncated = solpos.compute(month=6, day=21, hour=11.5, latitude=28.60, longitude=-77.20,
                               time_zone=-75.0)
    assert abs(exact.zenith_deg - truncated.zenith_deg) > 1.0, "fixture no longer separates them"
    assert record.geometry.zenith_deg == pytest.approx(exact.zenith_deg, abs=1e-6)


# ---- C5: colouring a luminaire either happens or is refused ----

_LIGHT = "void light lum\n0\n0\n3 1 1 1\n\nlum sphere bulb\n0\n0\n4 0 0 2.5 0.05\n"
_NINE = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]


def test_a_luminaire_with_windows_line_endings_is_coloured_too():
    out = color_luminaire(_LIGHT.replace("\n", "\r\n"), _NINE, 0, in_place=False)
    assert "3 0.1 0.2 0.3" in out and "3 1 1 1" not in out


def test_a_luminaire_without_the_default_light_line_is_refused_not_passed_through():
    """Returning the text unchanged reads as success, and the caller goes on to simulate an
    uncoloured lamp in what it believes is the blue channel."""
    with pytest.raises(ValueError, match="3 1 1 1"):
        color_luminaire("void light lum\n0\n0\n3 5 5 5\n", _NINE, 0, in_place=False)


def test_a_decimal_radiance_is_not_mistaken_for_the_default_line():
    """`3 1 1 1.0` used to match up to the dot and become `3 0.1 0.2 0.3.0`."""
    with pytest.raises(ValueError, match="3 1 1 1"):
        color_luminaire("void light lum\n0\n0\n3 1 1 1.0\n", _NINE, 0, in_place=False)


# ---- C6: two samples at one wavelength are reported, not divided by ----

@pytest.mark.parametrize("spd", [
    [(400, 1), (400, 2), (500, 1), (780, 1)],          # at the short end
    [(380, 1), (500, 1), (700, 1), (700, 2)],          # at the long end
])
def test_a_repeated_wavelength_at_an_end_is_a_clear_error(spd):
    with pytest.raises(ValueError, match="wavelength"):
        parse_spd([list(pair) for pair in spd])


# ---- C7: the note says what was actually scored ----

def test_a_non_melanopic_check_does_not_claim_to_be_scored_as_mel_edi():
    out = check_compliance(standard="en_12464_1", task="office_writing_reading", em=520, ugr=18,
                           uo=0.65, ra=85)
    assert out["quantity"] == "non_melanopic"
    assert out["quantity_note"].startswith("Not a melanopic check")
    assert "Scored as CIE S 026 mel-EDI" not in out["quantity_note"]


def test_a_melanopic_check_still_says_so():
    out = check_compliance(mel_edi=300, standard="brown_2022")
    assert out["quantity"] == "mel_edi"
    assert out["quantity_note"].startswith("Scored as CIE S 026 mel-EDI")


# ---- A3: a half-hour UTC offset reaches gendaylit as a half meridian ----

@pytest.mark.parametrize("utc, meridian", [(2, "-30"), (5.5, "-82.5"), (-3.5, "52.5"), (5.75, "-86.25")])
def test_the_gendaylit_meridian_keeps_fractional_zones(utc, meridian):
    """`int(utc * -15)` sent India's sun to meridian -82 and Nepal's to -86."""
    from hcl_radiance.sky import build_gendaylit
    cmd = build_gendaylit(6, 21, 12, irrad_mode="W", lat=28.6, lon=77.2, utc=utc, direct=700,
                          diffuse=100)
    assert cmd[cmd.index("-m") + 1] == meridian


# ---- C9: a zero illuminance setpoint is an input mistake, not a division ----

@pytest.mark.parametrize("setpoint", [0, 0.0, -300])
def test_a_setpoint_of_zero_or_less_is_refused_by_name(setpoint):
    from hcl_core.lighting_controls import light_fraction
    with pytest.raises(ValueError, match="setpoint"):
        light_fraction(100.0, setpoint)


def test_a_real_setpoint_still_gives_the_energyplus_fraction():
    from hcl_core.lighting_controls import light_fraction
    assert light_fraction(125.0, 500.0) == pytest.approx(0.75)
    assert light_fraction(900.0, 500.0) == 0.0


# ---- second review 2026-11-26 ----

def test_the_greenwich_meridian_is_written_as_zero_not_minus_zero():
    """`0 * -15` is -0.0 in floating point and printed as "-0": harmless to gendaylit, but a
    changed command line for every site on UTC+0."""
    from hcl_radiance.sky import _meridian
    assert _meridian(0) == "0" and _meridian(0.0) == "0"
    assert _meridian(2) == "-30" and _meridian(5.5) == "-82.5" and _meridian(-3.5) == "52.5"
