# tests/test_fixtures.py
import math
import pytest
from hcl_core.fixtures import room_cavity_ratio, utilization_factor, _CU_TABLE

def test_rcr_matches_zonal_cavity_formula():
    # RCR = 5 * h_cav * (L+W) / (L*W)
    rcr = room_cavity_ratio(length_m=6.0, width_m=4.0, h_cavity_m=2.0)
    assert rcr == pytest.approx(5 * 2.0 * (6 + 4) / (6 * 4))  # = 4.1667

def test_uf_interpolates_table_at_integer_rcr():
    # At an exact tabulated RCR, UF equals the table value times the unit reflectance factor (1.0 at 0.7/0.5/0.2)
    uf = utilization_factor(rcr=5.0, distribution="direct",
                            rho_ceiling=0.7, rho_wall=0.5, rho_floor=0.2)
    assert uf == pytest.approx(_CU_TABLE["direct"][5], abs=1e-9)

def test_uf_decreases_with_rcr():
    hi = utilization_factor(rcr=2.0, distribution="direct", rho_ceiling=0.7, rho_wall=0.5, rho_floor=0.2)
    lo = utilization_factor(rcr=8.0, distribution="direct", rho_ceiling=0.7, rho_wall=0.5, rho_floor=0.2)
    assert hi > lo

def test_uf_lower_for_indirect_than_direct():
    d = utilization_factor(rcr=4.0, distribution="direct", rho_ceiling=0.7, rho_wall=0.5, rho_floor=0.2)
    i = utilization_factor(rcr=4.0, distribution="indirect", rho_ceiling=0.7, rho_wall=0.5, rho_floor=0.2)
    assert i < d

def test_uf_rises_with_reflectance():
    base = utilization_factor(rcr=4.0, distribution="direct", rho_ceiling=0.7, rho_wall=0.5, rho_floor=0.2)
    bright = utilization_factor(rcr=4.0, distribution="direct", rho_ceiling=0.8, rho_wall=0.7, rho_floor=0.3)
    assert bright > base

from hcl_core.fixtures import visual_flux_lm

def test_visual_flux_lumen_method():
    # Phi = Em * A / (UF * MF)
    A = 6.0 * 4.0
    uf = utilization_factor(rcr=room_cavity_ratio(6, 4, 2.0), distribution="direct",
                            rho_ceiling=0.7, rho_wall=0.5, rho_floor=0.2)
    expected = 500.0 * A / (uf * 0.8)
    phi = visual_flux_lm(length_m=6, width_m=4, h_cavity_m=2.0, target_em_lux=500.0,
                         maintenance_factor=0.8, distribution="direct",
                         rho_ceiling=0.7, rho_wall=0.5, rho_floor=0.2)
    assert phi == pytest.approx(expected, rel=1e-9)

def test_visual_flux_ignores_daylight():
    # C1: daylight must NOT reduce the installed visual flux. Enforce machine-checkably that the
    # signature has no daylight input at all, not just that the result is positive.
    import inspect
    params = inspect.signature(visual_flux_lm).parameters
    assert not any("daylight" in name for name in params), \
        "visual_flux_lm must not accept any daylight parameter (C1)"
    phi = visual_flux_lm(length_m=6, width_m=4, h_cavity_m=2.0, target_em_lux=500.0,
                         maintenance_factor=0.8, distribution="direct",
                         rho_ceiling=0.7, rho_wall=0.5, rho_floor=0.2)
    assert phi > 0

from hcl_core.fixtures import led_palette, solve_circadian_spectrum, MEL_DER_PHYSICAL_MAX

def test_led_palette_sorted_by_cct_with_der():
    pal = led_palette()
    assert pal == sorted(pal, key=lambda e: e["cct_K"])
    assert all("mel_der" in e and "name" in e for e in pal)
    assert all(0.2 < e["mel_der"] < 1.6 for e in pal)  # sane melanopic ratio band
    # the illustrative palette caps well below the physical ceiling (verified ~0.82 vs 1.2)
    assert max(e["mel_der"] for e in pal) < MEL_DER_PHYSICAL_MAX

def test_circadian_reachable_within_palette_names_lowest_cct_preset():
    # required below the palette max -> reachable by palette, choose the lowest-CCT preset that meets it
    pal = led_palette()
    palette_max = max(e["mel_der"] for e in pal)
    required = palette_max - 0.05
    res = solve_circadian_spectrum(required_mel_der=required)
    assert res["reachable"] is True and res["by_palette"] is True
    chosen = next(e for e in pal if e["name"] == res["chosen_preset"])
    assert chosen["mel_der"] >= required
    assert [e for e in pal if e["cct_K"] < chosen["cct_K"] and e["mel_der"] >= required] == []

def test_circadian_reachable_beyond_palette_has_no_preset():
    # between palette max and the physical ceiling -> reachable but beyond the illustrative palette
    pal = led_palette()
    required = max(e["mel_der"] for e in pal) + 0.1  # still < MEL_DER_PHYSICAL_MAX (1.2)
    assert required < MEL_DER_PHYSICAL_MAX
    res = solve_circadian_spectrum(required_mel_der=required)
    assert res["reachable"] is True and res["by_palette"] is False
    assert res["chosen_preset"] is None

def test_circadian_unreachable_above_physical_ceiling():
    # above the physical ceiling -> not reachable by any spectrum (C2)
    res = solve_circadian_spectrum(required_mel_der=MEL_DER_PHYSICAL_MAX + 0.3)
    assert res["reachable"] is False
    assert res["chosen_preset"] is None
    assert res["physical_max"] == pytest.approx(MEL_DER_PHYSICAL_MAX)

from hcl_core.fixtures import recommend_fixtures

def _base_kwargs(**over):
    kw = dict(length_m=6.0, width_m=4.0, height_m=3.0, mount_height_m=2.8,
              workplane_height_m=0.8, eye_height_m=1.2,
              rho_ceiling=0.7, rho_wall=0.5, rho_floor=0.2, maintenance_factor=0.8,
              target_em_lux=500.0, target_mel_edi=250.0, mel_edi_daylight=0.0,
              vertical_horizontal_ratio=0.4, distribution="direct",
              target_efficacy_lm_w=120.0, per_fixture_lumen_options=(2000, 3000, 4000))
    kw.update(over)
    return kw

def test_output_has_all_contract_keys():
    out = recommend_fixtures(**_base_kwargs())
    for k in ("required_flux_lm", "fixture_count", "layout", "target_cct_band", "min_mel_der",
              "mel_der_achievable_max", "palette_mel_der_max", "beyond_illustrative_palette",
              "circadian_reachable_by_cct", "binding_constraint",
              "vertical_horizontal_ratio", "flux_count", "uniformity_count", "est_total_watts",
              "power_density_w_m2", "per_fixture_options", "supplementary_fixtures_advised",
              "glare_warning", "assumptions", "caveats"):
        assert k in out, f"missing {k}"
    assert out["layout"].keys() >= {"nx", "ny", "spacing_m", "positions"}
    assert len(out["positions"] if "positions" in out else out["layout"]["positions"]) == out["fixture_count"]

def test_fixture_count_is_realized_grid_and_covers_drivers():
    out = recommend_fixtures(**_base_kwargs())
    assert out["fixture_count"] == out["layout"]["nx"] * out["layout"]["ny"]
    assert out["fixture_count"] >= max(out["flux_count"], out["uniformity_count"])
    assert len(out["layout"]["positions"]) == out["fixture_count"]

def test_visual_binding_when_circadian_reachable():
    from hcl_core.fixtures import led_palette
    amax = max(e["mel_der"] for e in led_palette())
    mel = 0.6 * amax * 500.0 * 0.4   # required_der = mel/(em*vhr) = 0.6*amax
    out = recommend_fixtures(**_base_kwargs(target_mel_edi=mel))
    assert out["circadian_reachable_by_cct"] is True
    assert out["binding_constraint"] == "visual"
    assert out["glare_warning"] is False
    assert out["supplementary_fixtures_advised"] is False

def test_circadian_binds_and_warns_when_unreachable_by_cct():
    from hcl_core.fixtures import led_palette
    amax = max(e["mel_der"] for e in led_palette())
    mel = 2.0 * amax * 300.0 * 0.3   # required_der = 2*amax > achievable_max
    out = recommend_fixtures(**_base_kwargs(target_em_lux=300.0, target_mel_edi=mel,
                                            vertical_horizontal_ratio=0.3))
    assert out["circadian_reachable_by_cct"] is False
    assert out["binding_constraint"] == "circadian"
    assert out["supplementary_fixtures_advised"] is True
    assert out["glare_warning"] is True
    assert out["required_flux_lm"] >= visual_flux_lm(
        length_m=6, width_m=4, h_cavity_m=2.0, target_em_lux=300.0, maintenance_factor=0.8,
        distribution="direct", rho_ceiling=0.7, rho_wall=0.5, rho_floor=0.2)

def test_beyond_palette_band_is_reachable_without_supplementary():
    out = recommend_fixtures(**_base_kwargs(target_em_lux=500.0, target_mel_edi=200.0,
                                            vertical_horizontal_ratio=0.4))  # required_der = 1.0
    assert out["circadian_reachable_by_cct"] is True
    assert out["beyond_illustrative_palette"] is True
    assert out["binding_constraint"] == "visual"
    assert out["supplementary_fixtures_advised"] is False
    assert out["glare_warning"] is False
    assert out["target_cct_band"][0] >= 5000

def test_daylight_credited_only_in_circadian():
    no_dl = recommend_fixtures(**_base_kwargs(target_mel_edi=300.0, mel_edi_daylight=0.0))
    with_dl = recommend_fixtures(**_base_kwargs(target_mel_edi=300.0, mel_edi_daylight=120.0))
    assert with_dl["required_flux_lm"] <= no_dl["required_flux_lm"]
    assert with_dl["flux_count"] >= 1 and no_dl["flux_count"] >= 1

def test_assumptions_and_caveats_present():
    out = recommend_fixtures(**_base_kwargs())
    assert out["assumptions"] and out["caveats"]
    assert any("V/H" in a or "ratio" in a for a in out["assumptions"])

def test_recommend_fixtures_rejects_zero_em_with_circadian_target():
    with pytest.raises(ValueError):
        recommend_fixtures(**_base_kwargs(target_em_lux=0.0, target_mel_edi=250.0))

def test_recommend_fixtures_emits_no_colour_runtime_warning(recwarn):
    import hcl_core.fixtures as fx
    fx._PALETTE_CACHE = None   # force the colour-backed palette solve to actually run
    fx.recommend_fixtures(length_m=6, width_m=4, height_m=3, mount_height_m=2.8,
                          target_em_lux=500, target_mel_edi=250)
    # colour emits ColourRuntimeWarning ("Aligning ... spectral data shape ...") from cct_duv/mel_der;
    # it subclasses Warning (NOT RuntimeWarning). The palette solve must suppress it.
    offenders = [w for w in recwarn.list
                 if type(w.category).__name__ == "ColourRuntimeWarning"
                 or "ColourRuntimeWarning" in w.category.__name__
                 or "Aligning" in str(w.message)
                 or "Colour" in str(w.message) or "CCT" in str(w.message)]
    assert not offenders, [(w.category.__name__, str(w.message)) for w in offenders]

def test_recommend_fixtures_docstring_not_pure():
    from hcl_mcp.server import recommend_fixtures
    assert "Pure" not in recommend_fixtures.__doc__
    assert "deterministic" in recommend_fixtures.__doc__.lower()
