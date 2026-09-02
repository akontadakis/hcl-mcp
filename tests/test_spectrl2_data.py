from hcl_core.spectral_engine import _spectrl2_data as D


def test_all_columns_have_122_values():
    for col in (D.WL_UM, D.ET_H0, D.ABS_H2O, D.ABS_O3, D.ABS_UMG):
        assert len(col) == 122


def test_first_and_last_row_anchors():
    # First row: 0.300  535.9  0.0  10.0  0.0   (λ, H0, aw, ao, au)
    assert D.WL_UM[0] == 0.300
    assert D.ET_H0[0] == 535.9
    assert D.ABS_H2O[0] == 0.0
    assert D.ABS_O3[0] == 10.0
    assert D.ABS_UMG[0] == 0.0
    # Last row: 4.000  8.6  0.0045  0.0  0.025
    assert D.WL_UM[-1] == 4.000
    assert D.ET_H0[-1] == 8.6
    assert D.ABS_H2O[-1] == 0.0045
    assert D.ABS_O3[-1] == 0.0
    assert D.ABS_UMG[-1] == 0.025


def test_wavelengths_ascending_and_34_in_visible():
    assert all(D.WL_UM[i] < D.WL_UM[i + 1] for i in range(121))
    vis = [w for w in D.WL_UM if 0.380 <= w <= 0.780]
    assert len(vis) == 34
