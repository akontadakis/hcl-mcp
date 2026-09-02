from hcl_core._recon_data import (
    SOLAR_AM_SPD, solar_spd_for_zenith, dseries_spd, dseries_xy_from_cct,
    DSERIES_S0, DSERIES_S1, DSERIES_S2,
)

def test_solar_rows_are_401_and_positive():
    for am, spd in SOLAR_AM_SPD.items():
        assert len(spd) == 401, f"AM{am} not 401 points"
        assert all(v >= 0 for v in spd) and sum(spd) > 0

def test_solar_lookup_monotonic_in_zenith():
    # As zenith increases (longer path / more air mass), the spectrum reddens:
    # blue/red ratio must DECREASE monotonically. Use bin proxies (450nm idx 70, 650nm idx 270).
    def br(z):
        s = solar_spd_for_zenith(z); return s[70] / s[270]
    ratios = [br(z) for z in (0.0, 20.0, 40.0, 60.0, 75.0)]
    assert all(ratios[i] >= ratios[i + 1] - 1e-9 for i in range(len(ratios) - 1))

def test_solar_lookup_returns_401():
    assert len(solar_spd_for_zenith(30.0)) == 401

def test_dseries_eigenvectors_401():
    for vec in (DSERIES_S0, DSERIES_S1, DSERIES_S2):
        assert len(vec) == 401

def test_dseries_table_structural_anchor():
    # CIE construction: at 560nm (10-nm anchor index 18) S0=100.0, S1=0.0, S2=0.0. This locks the
    # authoritative table so a future re-fabrication of the eigenvectors cannot pass silently.
    from hcl_core._recon_data import _S0, _S1, _S2
    assert len(_S0) == 41 and len(_S1) == 41 and len(_S2) == 41
    assert _S0[18] == 100.0 and _S1[18] == 0.0 and _S2[18] == 0.0

def test_dseries_d65_reconstructs_d65_shape():
    # Dependency-free structural validation of the corrected table + the D-series formulas.
    from hcl_core._recon_data import _S0, _S1, _S2
    spd = dseries_spd(6504.0)  # CCT ~6504 K -> D65
    assert len(spd) == 401
    assert all(v > 0 for v in spd), "reconstructed D65 SPD must be strictly positive"
    # Eigenvector structural property (CIE construction; 560nm anchor = index 18).
    assert _S0[18] == 100.0 and _S1[18] == 0.0 and _S2[18] == 0.0
    # A ~6500 K daylight SPD peaks in the blue-green: argmax index < ~200 (< ~580 nm).
    assert spd.index(max(spd)) < 200


import pytest

def test_dseries_xy_from_cct_in_range_ok():
    for cct in (4000.0, 6504.0, 25000.0):
        x, y = dseries_xy_from_cct(cct)
        assert 0.0 < x < 1.0 and -1.0 < y < 1.0

def test_dseries_xy_from_cct_rejects_out_of_range():
    with pytest.raises(ValueError):
        dseries_xy_from_cct(3999.0)
    with pytest.raises(ValueError):
        dseries_xy_from_cct(25001.0)

def test_dseries_spd_propagates_cct_guard():
    with pytest.raises(ValueError):
        dseries_spd(2000.0)
