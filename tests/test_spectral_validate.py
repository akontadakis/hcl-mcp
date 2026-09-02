import pytest
from dataclasses import dataclass
from hcl_core.spectral_validate import drift_vs_templates, compare_engines


@dataclass
class _CS:
    wavelength_nm: list; direct_normal: list; sky_diffuse_horizontal: list; units: str = "W/m^2/um"


def test_drift_vs_templates_returns_divergence_keys():
    out = drift_vs_templates([10.0] * 9, [5.0] * 9, 1)
    assert "flat_vs_reference" in out and "neutral_vs_colored_sun" in out
    assert "mel_edi_pct" in out["flat_vs_reference"]


def test_compare_engines_identical_is_zero():
    a = _CS([380.0, 780.0], [1.0, 1.0], [0.5, 0.5])
    out = compare_engines(a, a)
    assert abs(out["direct_max_pct"]) < 1e-9 and abs(out["diffuse_mean_pct"]) < 1e-9


def test_compare_engines_reports_difference():
    a = _CS([380.0, 780.0], [1.0, 1.0], [0.5, 0.5])
    b = _CS([380.0, 780.0], [1.1, 1.1], [0.5, 0.5])   # +10% direct
    out = compare_engines(a, b)
    assert abs(out["direct_mean_pct"] - 10.0) < 1e-6


def test_compare_engines_raises_on_grid_not_spanning_band():
    full = _CS([380.0, 780.0], [1.0, 1.0], [0.5, 0.5])
    narrow = _CS([400.0, 700.0], [1.0, 1.0], [0.5, 0.5])   # does not span 380..780
    with pytest.raises(ValueError):
        compare_engines(full, narrow)
    with pytest.raises(ValueError):
        compare_engines(narrow, full)
