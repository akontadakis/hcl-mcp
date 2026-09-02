from hcl_core import _spectra

def test_action_spectra_are_401_points():
    for name in ["ACTION_S", "ACTION_M", "ACTION_L", "ACTION_RHOD", "ACTION_MEL", "V_LAMBDA", "D65_ELR"]:
        arr = getattr(_spectra, name)
        assert len(arr) == 401, f"{name} should be 401 points (380-780nm @1nm)"

def test_vlambda_peaks_near_555nm():
    # V(lambda) peaks at 555nm -> index 175 (380 + 175 = 555)
    v = _spectra.V_LAMBDA
    assert v.index(max(v)) == 175

def test_iprgc_curve_nonempty():
    assert len(_spectra.IPRGC_SENS_WEIGHTING) > 300


from hcl_core import data

def test_weight_columns_sum_to_one_within_tol():
    # Each metric column is a normalized action-spectrum integral. photopic-9 is 1.000024 by design.
    for name in ["W_PHOTOPIC_9", "W_MELANOPIC_9", "W_NEUROPIC_9", "W_PHOTOPIC_3", "W_MELANOPIC_3"]:
        s = sum(getattr(data, name))
        assert abs(s - 1.0) < 5e-5, f"{name} sums to {s}"

def test_photopic9_known_nonunity_sum():
    assert round(sum(data.W_PHOTOPIC_9), 6) == 1.000024

def test_bins_match_source():
    assert data.BINS_9[0] == [380, 419] and data.BINS_9[-1] == [630, 780]
    assert data.BINS_3 == [[587, 780], [499, 587], [380, 499]]

def test_bins_3_asc_single_source():
    # §9.3b ascending bins; single source consumed by alpha_opic + spectral_reconstruct.
    assert data.BINS_3_ASC == [[380, 499], [499, 587], [587, 780]]
    from hcl_core import alpha_opic, spectral_reconstruct
    assert alpha_opic._BINS_3_ASC is data.BINS_3_ASC
    assert spectral_reconstruct._BINS_3_ASC is data.BINS_3_ASC

def test_fov_and_nvrd_constants():
    assert data.FOV_WEIGHTS == {"upper_inner": 2.06, "upper_outer": 1.37, "lower_inner": 0.34, "lower_outer": 0.23}
    assert data.NVRD["EI50"] == 106.0 and data.NVRD["slope"] == 3.55
