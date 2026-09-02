"""Canonical sky-truth record + the engine→1nm resampler.

SpectralSkyRecord stores the two EPW-anchored physical spectra (direct_normal, sky_diffuse_horizontal)
at 1nm 380–780, plus broadband/atmosphere/geometry/provenance. resample_to_1nm() bridges the engine's
native W/m²/µm grid to the project's 1nm W/m²/nm grid — the ONE place the µm→nm (×0.001) conversion lives.
"""
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING
from hcl_core.cloud_modifier import clearness_index, broadband_integral

if TYPE_CHECKING:  # type-only; avoids importing at runtime (no behavior change)
    from hcl_core.atmosphere import AtmosphericState
    from hcl_core.solpos import SolarGeometry

GRID_NM = [380.0 + i for i in range(401)]   # 380..780 @1nm


@dataclass(frozen=True)
class SpectralSkyRecord:
    timestamp: tuple
    grid_nm: list
    direct_normal: list            # W/m²/nm
    sky_diffuse_horizontal: list   # W/m²/nm
    broadband: dict                # {dni, dhi, ghi, clearness_kt}
    atmosphere: "AtmosphericState"
    geometry: "SolarGeometry"
    provenance: dict


def _interp(grid_x, ys, x):
    """Linear interpolation of ys (aligned to grid_x, ascending) at x; clamps to endpoints."""
    if x <= grid_x[0]:
        return ys[0]
    if x >= grid_x[-1]:
        return ys[-1]
    lo, hi = 0, len(grid_x) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if grid_x[mid] <= x:
            lo = mid
        else:
            hi = mid
    t = (x - grid_x[lo]) / (grid_x[hi] - grid_x[lo])
    return ys[lo] + t * (ys[hi] - ys[lo])


def resample_to_1nm(spectra):
    """(ClearSkySpectra native W/m²/µm) -> (direct_1nm, diffuse_1nm) on GRID_NM in W/m²/nm.

    Linear interpolation onto the 1nm grid, then ×0.001 to convert W·m⁻²·µm⁻¹ → W·m⁻²·nm⁻¹.
    """
    gx = spectra.wavelength_nm
    direct = [_interp(gx, spectra.direct_normal, x) * 0.001 for x in GRID_NM]
    diffuse = [_interp(gx, spectra.sky_diffuse_horizontal, x) * 0.001 for x in GRID_NM]
    return direct, diffuse


def ground_for_receiver(rec, *, surface_tilt_deg, spectral_albedo):
    """Spectral ground-reflected term = spectral_GHI(λ) · albedo(λ) · (1−cos tilt)/2.

    spectral_GHI(λ) = direct_normal·cos z + sky_diffuse_horizontal. tilt=0 → zeros; tilt=90 → 0.5·…
    NB (spec §6): this is the spectral GROUND-GLOW input for the Radiance path, not a standalone
    receiver irradiance — Radiance transport does the sky transposition/projection. Isotropic ground
    (azimuth-independent), so no orientation argument.
    """
    view_factor = (1.0 - math.cos(math.radians(surface_tilt_deg))) / 2.0
    cz = math.cos(math.radians(rec.geometry.zenith_deg))
    out = []
    for i in range(len(rec.grid_nm)):
        ghi_lambda = rec.direct_normal[i] * cz + rec.sky_diffuse_horizontal[i]
        out.append(ghi_lambda * spectral_albedo[i] * view_factor)
    return out


def build_record(engine, modifier, atm, geo, *, timestamp, dni, dhi, ghi, i0_normal, clearsky_correction=None):
    """Run engine → cloud modifier (full-range energy + CCM) → resample → SpectralSkyRecord.

    The energy/CCM step is on the engine's native W/m²/µm full range; resample_to_1nm then converts
    to the 1nm 380–780 W/m²/nm record. Bridge invariant scale factors land in provenance.
    """
    cz = math.cos(math.radians(geo.zenith_deg))
    night = geo.zenith_deg >= 90.0 or cz <= 0.0
    clear = engine.compute(atm, geo)  # tilt 0 → horizontal sky-truth

    if night:
        zeros = [0.0] * 401
        # Twilight edge (spec §13): mid-interval geometry can read "below horizon" while the hour-ending
        # EPW row still carries radiation. Zero the record (sun is down at the sampled instant) but flag it
        # so the dropped energy is auditable rather than silent.
        prov = {"engine": engine.name, "cloud_model": modifier.name, "night": True,
                "night_but_epw_nonzero": (dni > 0.0 or dhi > 0.0 or ghi > 0.0),
                "k_dir": 0.0, "k_dif": 0.0, "clearness_kt": 0.0,
                "native_resolution": getattr(engine, "native_resolution", engine.name),
                # GHI closure check vs the EPW column (spec §6/§13); spectra are zeroed at night so
                # the bridge residual is identically zero (no rescale happened).
                "ghi_epw_residual": (dni * cz + dhi) - ghi,
                "bridge_residuals": {"direct_bb": 0.0, "diffuse_bb": 0.0},
                "ccm_applied": False}
        return SpectralSkyRecord(timestamp=timestamp, grid_nm=list(GRID_NM),
                                 direct_normal=list(zeros), sky_diffuse_horizontal=list(zeros),
                                 broadband={"dni": dni, "dhi": dhi, "ghi": ghi, "clearness_kt": 0.0},
                                 atmosphere=atm, geometry=geo, provenance=prov)

    cs_info = {"clearsky_corrected": False}
    if clearsky_correction is not None:
        clear, cs_info = clearsky_correction.apply(clear)

    kt = clearness_index(ghi, i0_normal, cz)
    scaled, info = modifier.apply(clear, dni=dni, dhi=dhi, ghi=ghi, kt=kt, geo=geo)
    direct_1nm, diffuse_1nm = resample_to_1nm(scaled)
    # Bridge closure (spec §4/§6/§13, methodology §10): the post-rescale broadband integral of each
    # component should equal the EPW DNI/DHI exactly (residual ~0 confirms the invariant held), and the
    # DNI/DHI-derived GHI is cross-checked against the EPW GHI column.
    wl_um = [w / 1000.0 for w in scaled.wavelength_nm]
    bridge_residuals = {"direct_bb": broadband_integral(scaled.direct_normal, wl_um) - dni,
                        "diffuse_bb": broadband_integral(scaled.sky_diffuse_horizontal, wl_um) - dhi}
    prov = {"engine": engine.name, "cloud_model": modifier.name, "night": False,
            "native_resolution": getattr(engine, "native_resolution", engine.name),
            "clearness_kt": kt,
            "k_dir": info["k_dir"], "k_dif": info["k_dif"],
            "clear_dni_bb": info["clear_dni_bb"], "clear_dhi_bb": info["clear_dhi_bb"],
            "ghi_epw_residual": (dni * cz + dhi) - ghi,
            "bridge_residuals": bridge_residuals,
            "ccm_variant": info.get("ccm_variant"),
            "ccm_basis": info.get("ccm_basis"),
            "coeff_method": info.get("coeff_method"),
            "ccm_source": info.get("ccm_source"),
            "ccm_applied": info.get("ccm_applied"),
            "ccm_sigma": info.get("ccm_sigma"),
            "ccm_sigma_mean": info.get("ccm_sigma_mean")}
    prov.update(cs_info)
    return SpectralSkyRecord(timestamp=timestamp, grid_nm=list(GRID_NM),
                             direct_normal=direct_1nm, sky_diffuse_horizontal=diffuse_1nm,
                             broadband={"dni": dni, "dhi": dhi, "ghi": ghi, "clearness_kt": kt},
                             atmosphere=atm, geometry=geo, provenance=prov)
