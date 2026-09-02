from hcl_core.alpha_opic import alpha_opic_from_channels

def test_positive_input_gives_nonzero_edi():  # guards the §9.3a integer-division bug
    r = alpha_opic_from_channels([0.1] * 9, channel_type=1, alpha=5)
    assert r["EDI"] > 0 and r["E_alpha"] > 0 and r["ELR"] > 0

def test_edi_scales_linearly_and_elr_is_scale_invariant():
    a = alpha_opic_from_channels([0.1] * 9, channel_type=1, alpha=5)
    b = alpha_opic_from_channels([0.2] * 9, channel_type=1, alpha=5)
    assert round(b["EDI"] / a["EDI"], 6) == 2.0
    assert round(b["ELR"], 6) == round(a["ELR"], 6)

def test_zero_input_is_zero():
    r = alpha_opic_from_channels([0.0] * 9, channel_type=1, alpha=5)
    assert r["E_alpha"] == 0 and r["EDI"] == 0 and r["ELR"] == 0

def test_alpha_none_returns_all_five():
    r = alpha_opic_from_channels([0.1] * 9, channel_type=1, alpha=None)
    assert set(r.keys()) == {"s_cone", "m_cone", "l_cone", "rhodopic", "melanopic"}

def test_three_channel_supported():
    r = alpha_opic_from_channels([0.2, 0.3, 0.4], channel_type=0, alpha=5)  # r,g,b
    assert r["EDI"] > 0

from hcl_core.alpha_opic import alpha_opic_from_spd

def test_from_spd_flat_positive():
    r = alpha_opic_from_spd([(380, 1.0), (780, 1.0)], alpha=5)
    assert r["E_alpha"] > 0 and r["EDI"] > 0 and r["ELR"] > 0

def test_from_spd_all_alphas():
    r = alpha_opic_from_spd([(380, 1.0), (780, 1.0)], alpha=None)
    assert set(r.keys()) == {"s_cone", "m_cone", "l_cone", "rhodopic", "melanopic"}

def test_from_spd_scales_linearly():
    a = alpha_opic_from_spd([(380, 1.0), (780, 1.0)], alpha=5)
    b = alpha_opic_from_spd([(380, 2.0), (780, 2.0)], alpha=5)
    assert round(b["E_alpha"] / a["E_alpha"], 6) == 2.0
    assert round(a["ELR"], 6) == round(b["ELR"], 6)

import pytest

def test_invalid_channel_type_rejected():
    with pytest.raises(ValueError):
        alpha_opic_from_channels([0.2, 0.3, 0.4], channel_type=2, alpha=5)

from hcl_core.alpha_opic import irradiance_per_nm
from hcl_core.alpha_opic import _reconstruct_irradiance  # internal parity check

def test_irradiance_per_nm_is_401_and_flat_within_bins():
    v = irradiance_per_nm([0.1] * 9, channel_type=1)
    assert len(v) == 401
    # flat within the first 9-channel bin [380,419): all equal
    assert len(set(v[0:39])) == 1

def test_irradiance_per_nm_matches_private_reconstruction_bit_for_bit():
    ch = [0.10, 0.12, 0.20, 0.30, 0.35, 0.33, 0.25, 0.18, 0.12]
    assert irradiance_per_nm(ch, channel_type=1) == _reconstruct_irradiance(ch, 1)

def test_irradiance_per_nm_uses_9p3a_float_division_nonzero():
    # guards the §9.3a fix: positive channels -> positive per-nm irradiance (never integer-divided to 0)
    assert sum(irradiance_per_nm([0.5] * 9, channel_type=1)) > 0


def test_numpy_and_pure_inner_products_agree():
    import hcl_core.alpha_opic as ao
    ch = [0.10, 0.12, 0.20, 0.30, 0.35, 0.33, 0.25, 0.18, 0.12]
    irrad = ao._reconstruct_irradiance(ch, 1)
    np_path = ao._from_irradiance(irrad, 5)
    pure = ao._from_irradiance_pure(irrad, 5)
    assert pure["E_alpha"] == np_path["E_alpha"]
    assert pure["ELR"] == np_path["ELR"]
    assert pure["EDI"] == np_path["EDI"]


def test_numpy_and_pure_agree_all_alphas():
    import hcl_core.alpha_opic as ao
    ch = [0.10, 0.12, 0.20, 0.30, 0.35, 0.33, 0.25, 0.18, 0.12]
    irrad = ao._reconstruct_irradiance(ch, 1)
    for alpha in range(1, 6):
        assert ao._from_irradiance(irrad, alpha) == ao._from_irradiance_pure(irrad, alpha)


def test_from_irradiance_zero_is_zero_both_paths():
    import hcl_core.alpha_opic as ao
    r = ao._from_irradiance([0.0] * 401, 5)
    assert r["E_alpha"] == 0 and r["ELR"] == 0 and r["EDI"] == 0
    rp = ao._from_irradiance_pure([0.0] * 401, 5)
    assert rp["E_alpha"] == 0 and rp["ELR"] == 0 and rp["EDI"] == 0
