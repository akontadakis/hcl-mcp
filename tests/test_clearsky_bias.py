# tests/test_clearsky_bias.py
import math
import pytest
from hcl_core.clearsky_bias import ClearSkyBiasCorrection
from hcl_core.spectral_engine.base import ClearSkySpectra


def _spectra():
    wl = list(range(380, 781))
    return ClearSkySpectra(wavelength_nm=wl, direct_normal=[1.0] * len(wl),
                           sky_diffuse_horizontal=[1.0] * len(wl))


def test_default_disabled_is_identity():
    c = ClearSkyBiasCorrection()
    assert c.enabled is False
    out, info = c.apply(_spectra())
    assert info["clearsky_corrected"] is False
    assert out.sky_diffuse_horizontal == [1.0] * 401          # bit-identical when off


def test_enabled_warms_blue_down_red_up():
    c = ClearSkyBiasCorrection(enabled=True)
    assert c.K(780.0) > 1.0 > c.K(380.0)                       # warming shape (red up, blue down)


def test_enabled_preserves_broadband_integral():
    from hcl_core.cloud_modifier import broadband_integral
    sp = _spectra()
    wl_um = [w / 1000.0 for w in sp.wavelength_nm]
    before = broadband_integral(sp.sky_diffuse_horizontal, wl_um)
    out, info = ClearSkyBiasCorrection(enabled=True).apply(sp)
    after = broadband_integral(out.sky_diffuse_horizontal, wl_um)
    assert abs(after - before) / before < 1e-6                 # energy preserved; only shape changed
    assert info["clearsky_corrected"] is True and info["engine"] == "spectrl2"


def test_passthrough_outside_artifact_range():
    assert ClearSkyBiasCorrection(enabled=True).K(200.0) == 1.0
    assert ClearSkyBiasCorrection(enabled=True).K(2000.0) == 1.0


def test_unknown_engine_reports_no_correction():
    # enabled but no artifact for this engine -> honest no-op (not a false 'corrected' claim)
    out, info = ClearSkyBiasCorrection(engine_name="smarts", enabled=True).apply(_spectra())
    assert info["clearsky_corrected"] is False
    assert out.sky_diffuse_horizontal == [1.0] * 401
