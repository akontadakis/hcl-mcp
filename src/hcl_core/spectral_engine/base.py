"""The spectral-engine swap point: ClearSkySpectra output + the SpectralEngine Protocol.

Backends (spectrl2, smarts, …) implement SpectralEngine.compute() and return ClearSkySpectra on
their NATIVE wavelength grid in W/m²/µm. Conversion to the project's 1nm/380–780/W·m⁻²·nm⁻¹ record
is the resampler's job (hcl_core.spectral_sky), never the engine's.
"""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ClearSkySpectra:
    wavelength_nm: list           # engine-native grid in nm (SPECTRL2: 122 pts spanning 300–4000nm)
    direct_normal: list           # W/m²/µm
    sky_diffuse_horizontal: list  # W/m²/µm — diffuse on a horizontal plane (incl. sky-ground multi-reflection)
    units: str = "W/m^2/um"


@runtime_checkable
class SpectralEngine(Protocol):
    name: str
    def compute(self, atm, geo, *, tilt_deg: float = 0.0, cos_incidence=None) -> ClearSkySpectra: ...
