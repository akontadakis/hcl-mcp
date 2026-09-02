from hcl_core.spectral_metrics import (
    cct_duv, mel_der, mel_photopic_ratio, eml_medi_convert, alpha_opic_from_spd,
    scale_warning_for, spd_looks_relative)
from hcl_core.presets import get_preset

def test_cct_of_standard_illuminants():
    assert abs(cct_duv(get_preset("D65"))["cct_K"] - 6504) < 15
    assert abs(cct_duv(get_preset("A"))["cct_K"] - 2856) < 15
    assert abs(cct_duv(get_preset("D50"))["cct_K"] - 5003) < 15

def test_mel_der_d65_is_one():
    assert mel_der(get_preset("D65")) == 1.0

def test_mel_der_incandescent_is_low():
    assert abs(mel_der(get_preset("A")) - 0.4958) < 0.005

def test_mel_photopic_ratio_d65():
    assert abs(mel_photopic_ratio(get_preset("D65")) - 0.9058) < 0.001

def test_eml_medi_conversion():
    assert eml_medi_convert(250, "medi_to_eml") == 275.75
    assert eml_medi_convert(250, "eml_to_medi") == 226.65

def test_alpha_opic_from_spd_keys_and_positivity():
    out = alpha_opic_from_spd(get_preset("D65"))
    for k in ("s_edi", "m_edi", "l_edi", "rhod_edi", "mel_edi"):
        assert k in out and out[k] >= 0.0

def test_alpha_opic_from_spd_flags_relative_input():
    out = alpha_opic_from_spd([(380, 1.0), (780, 1.0)])
    assert out.get("scale_warning") is not None
    assert "relative" in out["scale_warning"].lower()
    assert "mel_edi" in out

def test_alpha_opic_from_spd_no_warning_for_absolute_input():
    out = alpha_opic_from_spd([(380, 100.0), (780, 100.0)])
    assert out.get("scale_warning") is None


def test_scale_warning_does_not_assert_a_real_absolute_spd_is_relative():
    """A genuinely ABSOLUTE daylight SPD must not be told its EDIs are meaningless.

    Absolute exterior daylight readings (W/m2/nm) peak around 0.004-0.41, so the peak<=1.5
    heuristic flags all of them as "relative". Real daylight at 1 nm spreads its energy over
    ~400 bands, so a per-nm peak simply cannot separate absolute from normalised: absolute
    readings integrate to 1-139 W/m2 and a normalised peak-1 spectrum lands in the same range.

    The heuristic is therefore kept as a HINT, but it must no longer assert the input IS relative
    or that the EDIs are unusable -- on correct absolute data that tells the user to discard a
    correct answer.
    """
    spd = [[w, 0.13] for w in range(380, 781)]   # a realistic absolute daylight reading
    w = scale_warning_for(spd)
    assert w, "an ambiguous scale should still be surfaced"
    low = w.lower()
    assert "appears relative" not in low, f"must not assert the input IS relative: {w}"
    assert "not absolute" not in low, f"must not assert the input is NOT absolute: {w}"
    assert "indeterminate" in low or "cannot" in low, f"must say the scale is undecidable: {w}"


def test_spd_looks_relative_still_flags_a_normalised_spectrum():
    """The hint must still fire on an obviously normalised (peak-1) spectrum."""
    assert spd_looks_relative([[w, 1.0] for w in range(380, 781)]) is True


def test_spd_looks_relative_does_not_fire_on_a_large_absolute_spd():
    """And must not fire on a clearly absolute one."""
    assert spd_looks_relative([[w, 100.0] for w in range(380, 781)]) is False
