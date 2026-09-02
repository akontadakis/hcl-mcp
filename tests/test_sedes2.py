"""SEDES2 (Whitaker 1998 Table 2-1) — the opt-in tabulated cloud modifier.

These tests pin the two things that make SEDES2 a different MODEL rather than a coefficient
swap (the zenith term and the NGH variable), and the one thing that must not change: the
shipped SEDES1 default stays bit-identical, because every published overcast figure was
computed with it.
"""
import math

import pytest

from hcl_core._sedes2_data import SEDES2_COEFFS, sedes2_coeffs
from hcl_core.cloud_modifier import (Sedes1Modifier, Sedes2Modifier,
                                     normalized_global_horizontal)
from hcl_core.spectral_engine.base import ClearSkySpectra


def _spectra(n=41):
    wl = [380.0 + 10.0 * i for i in range(n)]
    return ClearSkySpectra(wavelength_nm=wl,
                           direct_normal=[1.0] * n,
                           sky_diffuse_horizontal=[1.0] * n)


class _Geo:
    def __init__(self, zenith_deg):
        self.zenith_deg = zenith_deg
        self.cos_zenith = math.cos(math.radians(zenith_deg))


# --- the artifact itself ---------------------------------------------------------------

def test_table_is_the_full_74_row_grid():
    assert len(SEDES2_COEFFS) == 74
    assert sorted(SEDES2_COEFFS) == list(range(320, 1051, 10))
    assert all(len(v) == 6 for v in SEDES2_COEFFS.values())


@pytest.mark.parametrize("wl,expected", [
    # Spot-checked against a visual read of the rendered NREL PDF page, not only pdftotext:
    # 640 and 760 were the two rows OCR damaged, and 320/1050 are the endpoints.
    (320, (1.285724, 0.306791, -0.29613, -0.58516, 0.020632, 0.209150)),
    (640, (1.040910, -0.002430, -0.35577, 0.051709, 0.225536, -0.026530)),
    (760, (1.364134, -0.108860, -0.84101, 0.233641, 0.440063, -0.119070)),
    (1050, (1.242954, -0.130070, -0.32480, 0.179514, 0.068458, -0.060710)),
])
def test_coefficients_match_the_primary_source(wl, expected):
    assert SEDES2_COEFFS[wl] == pytest.approx(expected, abs=1e-9)


def test_1040_and_1050_are_the_duplicated_terminal_row():
    # Present in the source table itself. Pinned so nobody "fixes" it into an interpolation.
    assert SEDES2_COEFFS[1040] == SEDES2_COEFFS[1050]


def test_interpolation_is_linear_between_table_rows():
    lo, hi = SEDES2_COEFFS[540], SEDES2_COEFFS[550]
    mid = sedes2_coeffs(545)
    assert mid == pytest.approx([(a + b) / 2 for a, b in zip(lo, hi)], abs=1e-12)


def test_out_of_range_clamps_rather_than_extrapolating():
    assert sedes2_coeffs(200) == SEDES2_COEFFS[320]
    assert sedes2_coeffs(2000) == SEDES2_COEFFS[1050]


# --- NGH is not Kt ----------------------------------------------------------------------

def test_ngh_is_measured_over_clear_sky_not_extraterrestrial():
    assert normalized_global_horizontal(400.0, 800.0) == pytest.approx(0.5)
    # Clear sky drives NGH to 1, where a clearness index would sit near 0.7. This is the
    # whole reason the two variables cannot be substituted.
    assert normalized_global_horizontal(800.0, 800.0) == pytest.approx(1.0)


def test_ngh_is_none_when_the_reference_is_unusable():
    assert normalized_global_horizontal(100.0, 0.0) is None
    assert normalized_global_horizontal(None, 800.0) is None


# --- the model ---------------------------------------------------------------------------

def test_reanchored_ccm_is_exactly_unity_at_clear_sky():
    m = Sedes2Modifier(reanchor=True)
    cz = math.cos(math.radians(35))
    for wl in (400, 500, 600, 700):
        assert m._ccm(wl, 1.0, cz) == pytest.approx(1.0, abs=1e-12)


def test_cloud_boosts_blue_more_than_red():
    m = Sedes2Modifier()
    cz = math.cos(math.radians(40))
    blue, red = m._ccm(450, 0.3, cz), m._ccm(650, 0.3, cz)
    assert blue > red > 0.0


def test_zenith_term_actually_moves_the_result():
    """The A2/B2/C2 columns are the whole structural difference from SEDES1 — if the model
    gave the same answer at every zenith they would be dead weight."""
    m = Sedes2Modifier()
    high = m._ccm(450, 0.4, math.cos(math.radians(20)))
    low = m._ccm(450, 0.4, math.cos(math.radians(70)))
    assert abs(high - low) > 1e-3


def test_apply_preserves_the_dhi_energy_invariant():
    m = Sedes2Modifier()
    out, info = m.apply(_spectra(), dni=700.0, dhi=120.0, ghi=500.0, kt=0.55,
                        geo=_Geo(40.0), clear_ghi=800.0)
    from hcl_core.cloud_modifier import broadband_integral
    wl_um = [w / 1000.0 for w in out.wavelength_nm]
    assert broadband_integral(out.sky_diffuse_horizontal, wl_um) == pytest.approx(120.0, rel=1e-9)
    assert info["ccm_applied"] is True
    assert info["cloud_model"] == "sedes2"
    assert info["coeff_method"] == "tabulated"


def test_apply_falls_back_to_grey_without_a_clear_sky_reference():
    """Refusing to run is the point: with no NGH there is no honest way to evaluate, and
    substituting kt would evaluate the polynomial on the wrong variable."""
    m = Sedes2Modifier()
    out, info = m.apply(_spectra(), dni=700.0, dhi=120.0, ghi=500.0, kt=0.55,
                        geo=_Geo(40.0), clear_ghi=None)
    assert info["ccm_applied"] is False
    assert info["ngh"] is None
    assert out.sky_diffuse_horizontal == pytest.approx(
        [120.0 / 0.4] * len(out.sky_diffuse_horizontal), rel=1e-6)


def test_apply_falls_back_at_low_sun_where_the_zenith_term_diverges():
    m = Sedes2Modifier()
    _out, info = m.apply(_spectra(), dni=10.0, dhi=30.0, ghi=20.0, kt=0.2,
                         geo=_Geo(89.0), clear_ghi=100.0)
    assert info["ccm_applied"] is False


# --- the guarantee that made this opt-in --------------------------------------------------

def test_sedes1_default_is_untouched_by_the_sedes2_addition():
    """Option (a) as accepted: SEDES2 ships alongside, so every published figure computed
    with the SEDES1 default must still reproduce exactly."""
    m = Sedes1Modifier()
    assert m.name == "sedes1"
    assert m.variant == "reanchored"
    out, info = m.apply(_spectra(), dni=700.0, dhi=120.0, ghi=500.0, kt=0.55, geo=_Geo(40.0))
    assert info["cloud_model"] == "sedes1"
    assert info["ccm_basis"] == "fig11-faithful"
    from hcl_core.cloud_modifier import broadband_integral
    wl_um = [w / 1000.0 for w in out.wavelength_nm]
    assert broadband_integral(out.sky_diffuse_horizontal, wl_um) == pytest.approx(120.0, rel=1e-9)


def test_the_two_models_disagree_under_cloud():
    """If they agreed, adopting SEDES2 would be cosmetic. They do not: this is the finding
    that a re-run is needed before any overcast number is re-quoted."""
    s1, s2 = Sedes1Modifier(), Sedes2Modifier()
    cz = math.cos(math.radians(40))
    assert abs(s1._ccm(450, 0.25) - s2._ccm(450, 0.25, cz)) > 0.01


def test_module_matches_the_committed_data_artifact():
    """The shipped coefficients and the committed CSV in tests/fixtures/ are
    two copies of the same table. Either could be edited alone; this is what makes that a
    build failure rather than a silent divergence between the code and its own provenance
    record."""
    import csv
    from pathlib import Path
    # Relocated into tests/fixtures/ when docs/validation/ moved out of the published
    # tree (2026-08-10), following the same pattern as de2de1a. The provenance record
    # travels WITH the test that checks it, so this can never silently skip again.
    p = Path(__file__).resolve().parent / "fixtures" / "sedes2_ccm_coefficients.csv"
    if not p.exists():                       # the folder is data, not a package dependency
        pytest.skip(f"coefficient artifact not present: {p}")
    rows = list(csv.DictReader(l for l in p.open() if not l.startswith("#")))
    assert len(rows) == len(SEDES2_COEFFS)
    for r in rows:
        wl = int(r["wavelength_nm"])
        got = tuple(float(r[k]) for k in ("A1", "A2", "B1", "B2", "C1", "C2"))
        assert got == pytest.approx(SEDES2_COEFFS[wl], abs=1e-9), f"{wl} nm differs"
