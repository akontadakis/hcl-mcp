import math
from hcl_core.spectral_sky import SpectralSkyRecord, resample_to_1nm, GRID_NM, ground_for_receiver
from hcl_core.spectral_engine.base import ClearSkySpectra
from dataclasses import dataclass
from hcl_core.spectral_sky import build_record, resample_to_1nm
from hcl_core.spectral_engine.spectrl2 import Spectrl2Engine
from hcl_core.cloud_modifier import Sedes1Modifier, broadband_integral
from dataclasses import dataclass as _dc


@_dc
class _G:
    zenith_deg: float; air_mass: float; earth_radius_vector: float; day_of_year: int = 172
@_dc
class _A:
    aod500: float; angstrom_alpha: float; pw_cm: float; ozone_atm_cm: float
    pressure_mbar: float; albedo: float; aerosol_g: float = 0.65


def test_build_record_end_to_end_clear_hour():
    geo = _G(zenith_deg=30.0, air_mass=1.15, earth_radius_vector=1.0)
    atm = _A(0.1, 1.14, 1.5, 0.30, 1013.0, 0.2)
    rec = build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo,
                       timestamp=(6, 21, 12), dni=800.0, dhi=120.0, ghi=812.0, i0_normal=1361.0)
    assert len(rec.direct_normal) == 401 and len(rec.sky_diffuse_horizontal) == 401
    assert rec.provenance["engine"] == "spectrl2"
    assert rec.provenance["cloud_model"] == "sedes1"
    assert 0.0 <= rec.provenance["clearness_kt"] <= 1.2
    # Bridge invariant carried in provenance (full-range integrals matched DNI/DHI before resample).
    assert rec.provenance["k_dir"] > 0 and rec.provenance["k_dif"] > 0
    assert rec.broadband["dni"] == 800.0


def test_build_record_night_is_zeroed():
    geo = _G(zenith_deg=100.0, air_mass=float("inf"), earth_radius_vector=1.0)
    atm = _A(0.1, 1.14, 1.5, 0.30, 1013.0, 0.2)
    rec = build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo,
                       timestamp=(12, 21, 2), dni=0.0, dhi=0.0, ghi=0.0, i0_normal=1361.0)
    assert all(v == 0.0 for v in rec.direct_normal)
    assert rec.provenance["night"] is True


@dataclass
class _Geo:
    zenith_deg: float


def _rec(zenith):
    return SpectralSkyRecord(timestamp=(6, 21, 12), grid_nm=list(GRID_NM),
                             direct_normal=[1.0] * 401, sky_diffuse_horizontal=[0.5] * 401,
                             broadband={}, atmosphere=None, geometry=_Geo(zenith), provenance={})


def test_grid_is_401_points_380_to_780():
    assert len(GRID_NM) == 401
    assert GRID_NM[0] == 380.0 and GRID_NM[-1] == 780.0
    assert GRID_NM[1] - GRID_NM[0] == 1.0


def test_resample_converts_um_to_nm_and_interpolates():
    # Native grid: two points at 380nm and 780nm, flat 1000 W/m²/µm direct.
    cs = ClearSkySpectra(wavelength_nm=[380.0, 780.0], direct_normal=[1000.0, 1000.0],
                         sky_diffuse_horizontal=[200.0, 200.0])
    direct, diffuse = resample_to_1nm(cs)
    assert len(direct) == 401 and len(diffuse) == 401
    # 1000 W/m²/µm == 1.0 W/m²/nm (×0.001). Flat input → flat output.
    assert abs(direct[0] - 1.0) < 1e-9
    assert abs(direct[200] - 1.0) < 1e-9      # 580nm, interpolated
    assert abs(diffuse[-1] - 0.2) < 1e-9


def test_resample_linear_interpolation_midpoint():
    # Native 380nm=0, 780nm=400 (W/m²/µm) → at 580nm expect 200 µm-units = 0.2 nm-units.
    cs = ClearSkySpectra(wavelength_nm=[380.0, 780.0], direct_normal=[0.0, 400.0],
                         sky_diffuse_horizontal=[0.0, 0.0])
    direct, _ = resample_to_1nm(cs)
    assert abs(direct[200] - 0.2) < 1e-9


def test_resample_single_point_grid_clamps_flat():
    # A degenerate 1-point native grid must not divide by zero: the endpoint
    # clamps cover every target wavelength, yielding a flat resampled spectrum.
    cs = ClearSkySpectra(wavelength_nm=[500.0], direct_normal=[1000.0],
                         sky_diffuse_horizontal=[200.0])
    direct, diffuse = resample_to_1nm(cs)
    assert len(direct) == 401 and len(diffuse) == 401
    assert all(abs(v - 1.0) < 1e-9 for v in direct)    # 1000 µm-units → 1.0 nm-units, flat
    assert all(abs(v - 0.2) < 1e-9 for v in diffuse)


def test_record_is_frozen_and_self_describing():
    rec = SpectralSkyRecord(timestamp=(6, 21, 12), grid_nm=list(GRID_NM),
                            direct_normal=[0.0] * 401, sky_diffuse_horizontal=[0.0] * 401,
                            broadband={"dni": 850.0, "dhi": 120.0, "ghi": 0.0, "clearness_kt": 0.0},
                            atmosphere=None, geometry=None,
                            provenance={"engine": "spectrl2"})
    assert rec.timestamp == (6, 21, 12)
    assert rec.provenance["engine"] == "spectrl2"
    try:
        rec.timestamp = (1, 1, 1)
        assert False, "record should be frozen"
    except Exception:
        pass


def test_ground_zero_for_horizontal_receiver():
    g = ground_for_receiver(_rec(60.0), surface_tilt_deg=0.0, spectral_albedo=[0.2] * 401)
    assert all(v == 0.0 for v in g)


def test_ground_vertical_receiver_half_hemisphere():
    # tilt=90 → view factor (1-cos90)/2 = 0.5. GHI(λ)=1.0*cos60 + 0.5 = 1.0. ground=1.0*0.2*0.5=0.1.
    g = ground_for_receiver(_rec(60.0), surface_tilt_deg=90.0, spectral_albedo=[0.2] * 401)
    assert abs(g[0] - 0.1) < 1e-9
    assert len(g) == 401


def test_build_record_twilight_edge_flags_dropped_epw():
    """Night (zenith below horizon) with nonzero EPW radiation flags the audit anomaly."""
    geo = _G(zenith_deg=92.0, air_mass=float("inf"), earth_radius_vector=1.0)
    atm = _A(0.1, 1.14, 1.5, 0.30, 1013.0, 0.2)
    rec = build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo,
                       timestamp=(12, 21, 2), dni=50.0, dhi=20.0, ghi=10.0, i0_normal=1361.0)
    # Night condition → spectra zeroed.
    assert all(v == 0.0 for v in rec.direct_normal)
    assert all(v == 0.0 for v in rec.sky_diffuse_horizontal)
    assert rec.provenance["night"] is True
    # Twilight audit flag: sun below horizon but EPW still carrying radiation (§13).
    assert rec.provenance["night_but_epw_nonzero"] is True


def test_build_record_day_provenance_keys_complete():
    """Day branch populates all required provenance keys: energy scalars + meta.

    Tests that build_record captures the bridge-invariant scale factors and metadata
    for day hours. CCM caveat keys (ccm_basis, coeff_method, ccm_applied) are covered
    by test_build_record_day_ccm_caveats_propagated.
    """
    geo = _G(zenith_deg=30.0, air_mass=1.15, earth_radius_vector=1.0)
    atm = _A(0.1, 1.14, 1.5, 0.30, 1013.0, 0.2)
    rec = build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo,
                       timestamp=(6, 21, 12), dni=800.0, dhi=120.0, ghi=812.0, i0_normal=1361.0)
    # Day branch: energy scalars (bridge invariant).
    assert rec.provenance["k_dir"] > 0.0
    assert rec.provenance["k_dif"] > 0.0
    assert rec.provenance["clear_dni_bb"] > 0.0
    assert rec.provenance["clear_dhi_bb"] > 0.0
    # Day branch: clearness + metadata.
    assert rec.provenance["clearness_kt"] >= 0.0
    assert isinstance(rec.provenance["native_resolution"], str) and len(rec.provenance["native_resolution"]) > 0
    assert rec.provenance["engine"] == "spectrl2"
    assert rec.provenance["cloud_model"] == "sedes1"
    assert rec.provenance["night"] is False


def test_build_record_day_ccm_caveats_propagated():
    """D-14 Decision A: SEDES1 CCM modeling-caveat strings must appear on day records.

    Uses the real Sedes1Modifier (not a mock) so the exact string values are exercised
    end-to-end. These keys allow consumers to audit that the diffuse shape rests on a
    fig11-faithful digitization (spec §5/§12).
    """
    geo = _G(zenith_deg=30.0, air_mass=1.15, earth_radius_vector=1.0)
    atm = _A(0.1, 1.14, 1.5, 0.30, 1013.0, 0.2)
    rec = build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo,
                       timestamp=(6, 21, 12), dni=800.0, dhi=120.0, ghi=812.0, i0_normal=1361.0)
    assert rec.provenance["ccm_basis"] == "fig11-faithful"
    assert rec.provenance["coeff_method"] == "webplotdigitizer_fig11"
    assert rec.provenance["ccm_applied"] is True


def test_build_record_day_provenance_carries_ccm_variant():
    """The persisted record must disclose WHICH variant ran — reanchored and verbatim share
    ccm_basis/coeff_method strings, so without ccm_variant they are indistinguishable."""
    geo = _G(zenith_deg=30.0, air_mass=1.15, earth_radius_vector=1.0)
    atm = _A(0.1, 1.14, 1.5, 0.30, 1013.0, 0.2)
    for variant in ("reanchored", "verbatim", "seed"):
        rec = build_record(Spectrl2Engine(), Sedes1Modifier(variant), atm, geo,
                           timestamp=(6, 21, 12), dni=800.0, dhi=120.0, ghi=812.0, i0_normal=1361.0)
        assert rec.provenance["ccm_variant"] == variant


def test_build_record_native_resolution_follows_engine():
    """native_resolution is the engine's own label, not a hardcoded spectrl2 string."""
    geo = _G(zenith_deg=30.0, air_mass=1.15, earth_radius_vector=1.0)
    atm = _A(0.1, 1.14, 1.5, 0.30, 1013.0, 0.2)
    rec = build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo,
                       timestamp=(6, 21, 12), dni=800.0, dhi=120.0, ghi=812.0, i0_normal=1361.0)
    assert rec.provenance["native_resolution"] == "spectrl2_122pt"

    class _OtherEngine(Spectrl2Engine):
        name = "other"
        native_resolution = "other_native"

    rec2 = build_record(_OtherEngine(), Sedes1Modifier(), atm, geo,
                        timestamp=(6, 21, 12), dni=800.0, dhi=120.0, ghi=812.0, i0_normal=1361.0)
    assert rec2.provenance["native_resolution"] == "other_native"
    assert rec2.provenance["engine"] == "other"


def test_build_record_night_ccm_applied_false_no_strings():
    """D-14 Decision A: night records carry ccm_applied=False for schema symmetry.

    Night records have no CCM run, so ccm_basis and coeff_method must NOT appear
    (no CCM ran — adding them would be misleading). Only ccm_applied=False is added.
    """
    geo = _G(zenith_deg=100.0, air_mass=float("inf"), earth_radius_vector=1.0)
    atm = _A(0.1, 1.14, 1.5, 0.30, 1013.0, 0.2)
    rec = build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo,
                       timestamp=(12, 21, 2), dni=0.0, dhi=0.0, ghi=0.0, i0_normal=1361.0)
    assert rec.provenance["ccm_applied"] is False
    assert "ccm_basis" not in rec.provenance
    assert "coeff_method" not in rec.provenance


def test_clearsky_correction_default_off_is_bit_identical():
    geo = _G(zenith_deg=30.0, air_mass=1.15, earth_radius_vector=1.0)
    atm = _A(0.1, 1.14, 1.5, 0.30, 1013.0, 0.2)
    base = build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo,
                        timestamp=(6, 21, 12), dni=800.0, dhi=120.0, ghi=812.0, i0_normal=1361.0)
    same = build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo,
                        timestamp=(6, 21, 12), dni=800.0, dhi=120.0, ghi=812.0, i0_normal=1361.0,
                        clearsky_correction=None)
    assert same.sky_diffuse_horizontal == base.sky_diffuse_horizontal     # default off = unchanged


def test_clearsky_correction_on_warms_diffuse():
    from hcl_core.clearsky_bias import ClearSkyBiasCorrection
    from hcl_core.spectral_metrics import cct_duv
    geo = _G(zenith_deg=20.0, air_mass=1.06, earth_radius_vector=1.0)
    atm = _A(0.15, 1.3, 1.5, 0.34, 1008.0, 0.2)
    off = build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo,
                       timestamp=(5, 13, 13), dni=800.0, dhi=120.0, ghi=900.0, i0_normal=1361.0)
    on = build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo,
                      timestamp=(5, 13, 13), dni=800.0, dhi=120.0, ghi=900.0, i0_normal=1361.0,
                      clearsky_correction=ClearSkyBiasCorrection(enabled=True))
    pairs_off = [(w, v) for w, v in zip(off.grid_nm, off.sky_diffuse_horizontal) if 380 <= w <= 780]
    pairs_on = [(w, v) for w, v in zip(on.grid_nm, on.sky_diffuse_horizontal) if 380 <= w <= 780]
    assert cct_duv(pairs_on)["cct_K"] < cct_duv(pairs_off)["cct_K"]        # warmer (lower CCT) with K on
    assert on.provenance.get("clearsky_corrected") is True


# --- D-28: spec §4/§6/§13 + methodology §10 — bridge_residuals + ghi_epw_residual provenance ---

def test_day_provenance_carries_ghi_epw_residual():
    """ghi_epw_residual = (DNI·cos z + DHI) − GHI_epw is computed and stored (spec §6/§13)."""
    geo = _G(zenith_deg=30.0, air_mass=1.15, earth_radius_vector=1.0)
    atm = _A(0.1, 1.14, 1.5, 0.30, 1013.0, 0.2)
    rec = build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo,
                       timestamp=(6, 21, 12), dni=800.0, dhi=120.0, ghi=812.0, i0_normal=1361.0)
    cz = math.cos(math.radians(30.0))
    assert rec.provenance["ghi_epw_residual"] == (800.0 * cz + 120.0) - 812.0


def test_day_provenance_carries_bridge_residuals_near_zero():
    """bridge_residuals reports the post-bridge broadband closure (exact by construction → ~0)."""
    geo = _G(zenith_deg=30.0, air_mass=1.15, earth_radius_vector=1.0)
    atm = _A(0.1, 1.14, 1.5, 0.30, 1013.0, 0.2)
    rec = build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo,
                       timestamp=(6, 21, 12), dni=800.0, dhi=120.0, ghi=812.0, i0_normal=1361.0)
    br = rec.provenance["bridge_residuals"]
    assert abs(br["direct_bb"]) < 1e-6
    assert abs(br["diffuse_bb"]) < 1e-6


def test_night_provenance_carries_residual_keys_for_symmetry():
    """Night branch carries the same residual keys (schema symmetry) even though spectra are zeroed."""
    geo = _G(zenith_deg=100.0, air_mass=float("inf"), earth_radius_vector=1.0)
    atm = _A(0.1, 1.14, 1.5, 0.30, 1013.0, 0.2)
    rec = build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo,
                       timestamp=(12, 21, 2), dni=0.0, dhi=0.0, ghi=0.0, i0_normal=1361.0)
    assert "ghi_epw_residual" in rec.provenance
    assert "bridge_residuals" in rec.provenance
