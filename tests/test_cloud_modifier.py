import pytest
from dataclasses import dataclass
from hcl_core.cloud_modifier import clearness_index, broadband_integral, energy_normalize, Sedes1Modifier, CloudModifier
from hcl_core.spectral_engine.base import ClearSkySpectra
from hcl_core import sedes1_fit
from hcl_core._sedes1_data import ccm_coeffs, ccm_sigma, FIG11_WL


def _flat_spectra():
    # native 2-pt grid 0.3–4.0µm; flat direct 1000, diffuse 100 (W/m²/µm).
    return ClearSkySpectra(wavelength_nm=[300.0, 4000.0], direct_normal=[1000.0, 1000.0],
                           sky_diffuse_horizontal=[100.0, 100.0])


def test_energy_normalize_matches_dni_dhi():
    scaled, info = energy_normalize(_flat_spectra(), dni=800.0, dhi=120.0)
    wl_um = [w / 1000.0 for w in scaled.wavelength_nm]
    from hcl_core.cloud_modifier import broadband_integral
    assert abs(broadband_integral(scaled.direct_normal, wl_um) - 800.0) < 1e-6
    assert abs(broadband_integral(scaled.sky_diffuse_horizontal, wl_um) - 120.0) < 1e-6
    # clear-sky broadband: 1000*3.7=3700 direct, 100*3.7=370 diffuse.
    assert abs(info["clear_dni_bb"] - 3700.0) < 1e-6
    assert abs(info["k_dir"] - 800.0 / 3700.0) < 1e-9


def test_energy_normalize_zero_clear_sky_is_safe():
    night = ClearSkySpectra(wavelength_nm=[300.0, 4000.0], direct_normal=[0.0, 0.0],
                            sky_diffuse_horizontal=[0.0, 0.0])
    scaled, info = energy_normalize(night, dni=0.0, dhi=0.0)
    assert info["k_dir"] == 0.0 and info["k_dif"] == 0.0
    assert all(v == 0.0 for v in scaled.direct_normal)


def test_clearness_index_basic():
    # GHI=600, I0_normal=1361, cos z=0.5 → Kt = 600/680.5 = 0.8818
    kt = clearness_index(600.0, 1361.0, 0.5)
    assert abs(kt - 0.8818) < 1e-3


def test_clearness_index_night_is_zero():
    assert clearness_index(0.0, 1361.0, 0.0) == 0.0
    assert clearness_index(0.0, 1361.0, -0.1) == 0.0


def test_clearness_index_clamped_to_1_2():
    assert clearness_index(2000.0, 1361.0, 0.5) == 1.2


def test_broadband_integral_trapezoid():
    # Flat 1000 W/m²/µm from 0.3 to 4.0 µm → 1000 * 3.7 = 3700 W/m².
    wl = [0.3, 4.0]
    spec = [1000.0, 1000.0]
    assert abs(broadband_integral(spec, wl) - 3700.0) < 1e-6


def test_broadband_integral_triangle():
    # 0 at 0.3µm rising to 1000 at 1.3µm → triangle area = 0.5*1.0*1000 = 500 W/m².
    wl = [0.3, 1.3]
    spec = [0.0, 1000.0]
    assert abs(broadband_integral(spec, wl) - 500.0) < 1e-6


def _grid_spectra():
    # 5-point native grid spanning UV→NIR so CCM and integrals are exercised.
    wl_nm = [300.0, 400.0, 550.0, 700.0, 4000.0]
    return ClearSkySpectra(wavelength_nm=wl_nm,
                           direct_normal=[200.0, 800.0, 1000.0, 900.0, 5.0],
                           sky_diffuse_horizontal=[80.0, 120.0, 100.0, 70.0, 1.0])


def test_sedes1_satisfies_protocol():
    assert isinstance(Sedes1Modifier(), CloudModifier)
    assert Sedes1Modifier().name == "sedes1"


def test_sedes1_preserves_bridge_invariant():
    from hcl_core.cloud_modifier import broadband_integral
    scaled, info = Sedes1Modifier().apply(_grid_spectra(), dni=700.0, dhi=110.0,
                                          ghi=300.0, kt=0.25, geo=None)
    wl_um = [w / 1000.0 for w in scaled.wavelength_nm]
    assert abs(broadband_integral(scaled.direct_normal, wl_um) - 700.0) < 1e-4
    assert abs(broadband_integral(scaled.sky_diffuse_horizontal, wl_um) - 110.0) < 1e-4
    assert info["kt"] == 0.25 and info["ccm_applied"] is True


def test_sedes1_reshapes_diffuse_bluer_under_cloud():
    # Compare diffuse blue/red ratio: overcast (kt 0.25) should be bluer than clear (kt 0.70).
    base = _grid_spectra()
    overcast, _ = Sedes1Modifier().apply(base, dni=700.0, dhi=110.0, ghi=300.0, kt=0.25, geo=None)
    clear, _ = Sedes1Modifier().apply(base, dni=700.0, dhi=110.0, ghi=600.0, kt=0.70, geo=None)
    # index 1 = 400nm (blue), index 3 = 700nm (red)
    r_overcast = overcast.sky_diffuse_horizontal[1] / overcast.sky_diffuse_horizontal[3]
    r_clear = clear.sky_diffuse_horizontal[1] / clear.sky_diffuse_horizontal[3]
    assert r_overcast > r_clear


def test_variant_defaults_and_validation():
    assert Sedes1Modifier().variant == "reanchored"
    assert Sedes1Modifier("verbatim").variant == "verbatim"
    assert Sedes1Modifier("seed").variant == "seed"
    with pytest.raises(ValueError):
        Sedes1Modifier("bogus")


def test_reanchored_is_neutral_at_clear_kt():
    m = Sedes1Modifier()                       # reanchored default
    for wl in (400.0, 500.0, 600.0, 700.0):
        assert abs(m._ccm(wl, 0.70) - 1.0) < 1e-9    # pass-through at clear Kt by construction


def test_reanchored_blue_enhanced_at_overcast():
    m = Sedes1Modifier()
    assert m._ccm(400.0, 0.25) > m._ccm(700.0, 0.25)
    assert m._ccm(400.0, 0.25) > 1.3


def test_seed_variant_over_blues_vs_faithful():
    # the verified finding: the seed amplifies blue more than the faithful re-anchored CCM
    assert Sedes1Modifier("seed")._ccm(400.0, 0.25) > Sedes1Modifier()._ccm(400.0, 0.25)


def test_info_records_variant():
    out, info = Sedes1Modifier().apply(_grid_spectra(), dni=700.0, dhi=110.0, ghi=300.0, kt=0.25, geo=None)
    assert info["ccm_variant"] == "reanchored"


def test_kt_sweep_cct_regression():
    """Verified evidence (spec): seed over-blues; faithful halves it. Athens clear noon, real pipeline."""
    from hcl_core import solpos
    from hcl_core.atmosphere import AtmosphericState
    from hcl_core.spectral_engine.spectrl2 import Spectrl2Engine
    from hcl_core.spectral_metrics import cct_duv

    atm = AtmosphericState(aod500=0.15, angstrom_alpha=1.3, pw_cm=1.5, ozone_atm_cm=0.34,
                           pressure_mbar=1008.0, albedo=0.2, provenance={})
    # Arbitrary fixture coordinates, NOT any measured site. The expectations below are
    # pinned at THIS geometry, so the values stay as they are.
    geo = solpos.compute(month=5, day=13, hour=13, latitude=37.98, longitude=-23.73, time_zone=-45)
    clear = Spectrl2Engine().compute(atm, geo)

    def cct(variant, kt):
        out, _ = Sedes1Modifier(variant).apply(clear, dni=800.0, dhi=120.0, ghi=900.0, kt=kt, geo=geo)
        pairs = [(w, v) for w, v in zip(out.wavelength_nm, out.sky_diffuse_horizontal) if 380 <= w <= 780]
        return cct_duv(pairs)["cct_K"]

    assert abs(cct("seed", 0.25) - 16763) < 300        # the over-blueing (deep-dive's 11000-17000K)
    assert abs(cct("verbatim", 0.25) - 11982) < 300    # faithful ~halves it
    assert abs(cct("reanchored", 0.25) - 14601) < 300  # pure-cloud default
    assert cct("verbatim", 0.25) < cct("seed", 0.25) - 3000   # faithful is materially less blue
    # Clear anchor row (Kt=0.70): reanchored is unity at clear by construction, so it matches seed.
    assert abs(cct("seed", 0.70) - 10564) < 300
    assert abs(cct("verbatim", 0.70) - 9258) < 300
    assert abs(cct("reanchored", 0.70) - 10565) < 300


# --- D-15: spec §13 explicit grey fallback — kt is None → CCM=1.0 (energy-rescale only, no reshape) ---

def test_sedes1_grey_fallback_when_kt_is_none():
    from hcl_core.cloud_modifier import broadband_integral, energy_normalize
    base = _grid_spectra()
    out, info = Sedes1Modifier().apply(base, dni=700.0, dhi=110.0, ghi=300.0, kt=None, geo=None)
    # Energy bridge still holds (diffuse integrates to DHI)...
    wl_um = [w / 1000.0 for w in out.wavelength_nm]
    assert abs(broadband_integral(out.sky_diffuse_horizontal, wl_um) - 110.0) < 1e-4
    # ...but no spectral reshape was applied: diffuse == the pure energy-normalized clear shape.
    enorm, _ = energy_normalize(base, 700.0, 110.0)
    assert out.sky_diffuse_horizontal == enorm.sky_diffuse_horizontal
    assert info["ccm_applied"] is False


# --- Task 1: "local" variant + coeffs/sigma injection ---

def _flat_coeffs(wl_nm):      # CCM = 1 + 0.001*(wl-550)*kt ... simple, non-trivial
    return (1.0, 0.0002 * (wl_nm - 550.0), 0.0)


def test_local_requires_coeffs():
    with pytest.raises(ValueError):
        Sedes1Modifier(variant="local")


def test_unknown_variant_raises():
    with pytest.raises(ValueError):
        Sedes1Modifier(variant="bogus")


def test_local_variant_reanchors_to_unity_at_clear():
    m = Sedes1Modifier(variant="local", coeffs=_flat_coeffs)
    # reanchored: CCM(λ, 0.70) == 1.0 exactly for every wavelength
    assert abs(m._ccm(500.0, 0.70) - 1.0) < 1e-12
    assert abs(m._ccm(400.0, 0.70) - 1.0) < 1e-12


# --- Task 2: sigma surfaced into apply() info ---

def _clear():
    wl = [300.0 + 10.0 * i for i in range(120)]
    return ClearSkySpectra(wavelength_nm=wl, direct_normal=[1.0] * 120,
                           sky_diffuse_horizontal=[0.5] * 120)


def test_apply_surfaces_ccm_sigma():
    _, info = Sedes1Modifier().apply(_clear(), dni=800.0, dhi=120.0, ghi=700.0, kt=0.6, geo=None)
    assert "ccm_sigma" in info and "500" in info["ccm_sigma"]
    assert "ccm_sigma_mean" in info


# --- Task 4: local variant round-trip test ---

def test_local_from_fig11_matches_reanchored(tmp_path):
    # Dump the shipped Fig.11 coeffs to a CSV, load as 'local' → identical reshape to 'reanchored'.
    fit = {"wavelength_nm": FIG11_WL,
           "A": [ccm_coeffs(w)[0] for w in FIG11_WL],
           "B": [ccm_coeffs(w)[1] for w in FIG11_WL],
           "C": [ccm_coeffs(w)[2] for w in FIG11_WL],
           "sigma": [ccm_sigma(w) for w in FIG11_WL]}
    p = tmp_path / "fig11_dump.csv"
    sedes1_fit.write_ccm_csv(str(p), fit)
    coeffs, sigma = sedes1_fit.load_ccm_csv(str(p))
    local = Sedes1Modifier(variant="local", coeffs=coeffs, sigma=sigma)
    ref = Sedes1Modifier(variant="reanchored")
    c = _clear()
    out_l, info_l = local.apply(c, dni=800.0, dhi=120.0, ghi=700.0, kt=0.5, geo=None)
    out_r, info_r = ref.apply(c, dni=800.0, dhi=120.0, ghi=700.0, kt=0.5, geo=None)
    for a, b in zip(out_l.sky_diffuse_horizontal, out_r.sky_diffuse_horizontal):
        assert abs(a - b) < 1e-9

    # (a) direct off-anchor equivalence: wavelengths NOT aligned to the 10 nm Fig.11/_clear() grid,
    # so _interp must actually do fractional interpolation on both sides identically.
    for w in (405.0, 517.0, 655.0):
        for kt in (0.3, 0.5, 0.9):
            assert abs(local._ccm(w, kt) - ref._ccm(w, kt)) < 1e-9

    # (b) sigma-equivalence: the surfaced ccm_sigma_mean must match too (not just the reshaped shape).
    assert abs(info_l["ccm_sigma_mean"] - info_r["ccm_sigma_mean"]) < 1e-9


def test_provenance_labels_are_variant_aware():
    """ccm_basis/coeff_method must tell the truth per variant; ccm_source carries the local source."""
    c = _clear()
    # default (reanchored) — byte-identical labels, no source
    _, ir = Sedes1Modifier().apply(c, dni=800.0, dhi=120.0, ghi=700.0, kt=0.6, geo=None)
    assert ir["ccm_variant"] == "reanchored"
    assert ir["ccm_basis"] == "fig11-faithful"
    assert ir["coeff_method"] == "webplotdigitizer_fig11"
    assert ir["ccm_source"] is None
    # seed — labeled as the 9-anchor seed, not fig11
    _, isd = Sedes1Modifier(variant="seed").apply(c, dni=800.0, dhi=120.0, ghi=700.0, kt=0.6, geo=None)
    assert isd["ccm_basis"] == "seed-9anchor" and isd["coeff_method"] == "eyeballed_seed"
    # local — labeled as a local fit, with the source string surfaced
    _, il = Sedes1Modifier(variant="local", coeffs=_flat_coeffs, source="my_ccm.csv").apply(
        c, dni=800.0, dhi=120.0, ghi=700.0, kt=0.6, geo=None)
    assert il["ccm_variant"] == "local"
    assert il["ccm_basis"] == "local-fit" and il["coeff_method"] == "local_recalibration"
    assert il["ccm_source"] == "my_ccm.csv"
    # grey-fallback branch still carries the source (no CCM applied)
    _, ig = Sedes1Modifier(variant="local", coeffs=_flat_coeffs, source="my_ccm.csv").apply(
        c, dni=800.0, dhi=120.0, ghi=700.0, kt=None, geo=None)
    assert ig["ccm_source"] == "my_ccm.csv" and ig["ccm_basis"] == "grey-fallback"
