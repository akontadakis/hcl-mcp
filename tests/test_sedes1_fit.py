import os

import pytest

from hcl_core import sedes1_fit

def test_fit_recovers_known_coeffs():
    # Grid with B(λ) summing to zero → shape normalization is identity → exact recovery.
    wl = [400.0, 500.0, 600.0]
    B_true = [-0.20, 0.0, 0.20]                 # sums to 0
    kts = [0.2, 0.4, 0.6, 0.8, 1.0]
    ref = [[1.0, 1.0, 1.0] for _ in kts]        # flat clear reference
    spectra = [[1.0 + B_true[j] * kt for j in range(3)] for kt in kts]  # CCM = 1 + B·Kt
    fit = sedes1_fit.fit_ccm(spectra, kts, ref, wl)
    assert all(abs(a - 1.0) < 1e-6 for a in fit["A"])
    for j in range(3):
        assert abs(fit["B"][j] - B_true[j]) < 1e-6
        assert abs(fit["C"][j]) < 1e-6

def test_fit_ccm_mismatched_lengths_raises():
    wl = [400.0, 500.0, 600.0]
    kts = [0.2, 0.4, 0.6]
    ref = [[1.0, 1.0, 1.0] for _ in kts]
    spectra = [[1.0, 1.0, 1.0] for _ in kts]
    with pytest.raises(ValueError):
        sedes1_fit.fit_ccm(spectra, kts + [0.8], ref, wl)          # len(spectra) != len(kt_values)
    with pytest.raises(ValueError):
        sedes1_fit.fit_ccm(spectra, kts, ref + [[1.0, 1.0, 1.0]], wl)  # len(reference_shapes) != len(kt_values)


def test_load_ccm_csv_no_data_rows_raises(tmp_path):
    p = tmp_path / "empty_ccm.csv"
    p.write_text("# locally-fit SEDES1 CCM(lambda,Kt)=A+B*Kt+C*Kt^2; sigma=regression std error\n"
                 "wavelength_nm,A,B,C,sigma\n")
    with pytest.raises(ValueError):
        sedes1_fit.load_ccm_csv(str(p))


def test_fit_csv_roundtrip(tmp_path):
    wl = [400.0, 500.0, 600.0]
    fit = {"wavelength_nm": wl, "A": [1.0, 1.0, 1.0], "B": [-0.2, 0.0, 0.2],
           "C": [0.0, 0.0, 0.0], "sigma": [0.01, 0.0, 0.01]}
    p = tmp_path / "athens_ccm.csv"
    sedes1_fit.write_ccm_csv(str(p), fit)
    coeffs, sigma = sedes1_fit.load_ccm_csv(str(p))
    assert abs(coeffs(500.0)[1] - 0.0) < 1e-9
    assert abs(coeffs(400.0)[1] - (-0.2)) < 1e-9
    assert sigma(400.0) >= 0.0


# Development-only: a local measured-SPD directory, never distributed. Set
# HCL_MEASURED_SPD_DIR to point at one; otherwise this skips.
_MEASURED = os.environ.get(
    "HCL_MEASURED_SPD_DIR",
    os.path.join(os.path.dirname(__file__), "fixtures", "measured-spd-local"))
_MEASURED_SPD = os.path.join(_MEASURED, "measured-spd")


@pytest.mark.skipif(not os.path.isdir(_MEASURED_SPD),
                    reason="local measured-SPD fixture not present")
def test_local_measured_spds_are_readable():
    import glob
    assert glob.glob(os.path.join(_MEASURED_SPD, "*.txt")), "expected measured SPDs"
