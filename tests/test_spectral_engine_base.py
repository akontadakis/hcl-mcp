from dataclasses import FrozenInstanceError

import pytest

from hcl_core.spectral_engine.base import ClearSkySpectra, SpectralEngine


def test_clearsky_spectra_holds_three_arrays_and_default_units():
    cs = ClearSkySpectra(wavelength_nm=[380.0, 381.0], direct_normal=[1.0, 2.0],
                         sky_diffuse_horizontal=[0.1, 0.2])
    assert cs.units == "W/m^2/um"
    assert cs.wavelength_nm == [380.0, 381.0]
    assert cs.direct_normal == [1.0, 2.0]
    assert cs.sky_diffuse_horizontal == [0.1, 0.2]


def test_clearsky_spectra_is_frozen():
    # The record is sky-truth — callers must not mutate it in place. Mirrors the
    # frozen guard already covered for SpectralSkyRecord.
    cs = ClearSkySpectra(wavelength_nm=[380.0], direct_normal=[1.0],
                         sky_diffuse_horizontal=[0.1])
    with pytest.raises(FrozenInstanceError):
        cs.units = "W/m^2/nm"


def test_spectral_engine_is_a_runtime_checkable_protocol():
    class Dummy:
        name = "dummy"
        def compute(self, atm, geo, *, tilt_deg=0.0, cos_incidence=None):
            return ClearSkySpectra([380.0], [0.0], [0.0])
    assert isinstance(Dummy(), SpectralEngine)
