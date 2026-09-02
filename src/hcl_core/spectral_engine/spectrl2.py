"""Pure-Python port of the Bird SPECTRL2 clear-sky spectral model (spectrl2_2.c, units=1).

Faithful transcription of the per-wavelength Beer–Lambert transmittances + single-pass diffuse
decomposition. C constants verbatim (e.g. Rayleigh 1.3366, uniform-gas 118.3). Solar geometry is
PASSED IN (SolarGeometry) — no native solpos. Output is W/m²/µm on the native 122-pt grid.
Reference: Bird & Riordan 1986; SERI/TR-215-2436.
"""
import math

from hcl_core.spectral_engine.base import ClearSkySpectra
from hcl_core.spectral_engine import _spectrl2_data as D

_OMEG = 0.945    # single-scattering albedo at 0.4µm
_OMEGP = 0.095


class Spectrl2Engine:
    name = "spectrl2"
    native_resolution = "spectrl2_122pt"

    def compute(self, atm, geo, *, tilt_deg: float = 0.0, cos_incidence=None) -> ClearSkySpectra:
        wl_nm = [w * 1000.0 for w in D.WL_UM]
        cz = math.cos(math.radians(geo.zenith_deg))

        # Night / sun below horizon → no direct or diffuse.
        if geo.zenith_deg >= 90.0 or cz <= 0.0 or not math.isfinite(geo.air_mass):
            zeros = [0.0] * 122
            return ClearSkySpectra(wavelength_nm=wl_nm, direct_normal=list(zeros),
                                   sky_diffuse_horizontal=list(zeros))

        Am = geo.air_mass
        Amp = Am * atm.pressure_mbar / 1013.0
        Amo = 1.003454 / math.sqrt(cz * cz + 0.006908)
        erv = geo.earth_radius_vector
        tau500, alpha, W, O3 = atm.aod500, atm.angstrom_alpha, atm.pw_cm, atm.ozone_atm_cm
        rho = atm.albedo                      # gray ground albedo (all 6 SPECTRL2 bands)
        assym = atm.aerosol_g                 # rural aerosol asymmetry (was 0.65 literal, now parameterized)

        # Forward-scatter terms (Eq 3-11..3-15).
        alg = math.log(1.0 - assym)
        afs = alg * (1.459 + alg * (0.1595 + alg * 0.4129))
        bfs = alg * (0.0783 + alg * (-0.3824 - alg * 0.5874))
        fsp = 1.0 - 0.5 * math.exp((afs + bfs / 1.8) / 1.8)
        fs = 1.0 - 0.5 * math.exp((afs + bfs * cz) * cz)

        tilted = tilt_deg > 1.0e-4
        ct = math.cos(math.radians(tilt_deg))
        ci = cos_incidence if cos_incidence is not None else cz

        direct = [0.0] * 122
        diffuse = [0.0] * 122
        for i in range(122):
            wvl = D.WL_UM[i]
            H0 = D.ET_H0[i] * erv
            Aw, Ao, Au = D.ABS_H2O[i], D.ABS_O3[i], D.ABS_UMG[i]

            omegl = _OMEG * math.exp(-_OMEGP * (math.log(wvl / 0.4)) ** 2)
            ca = tau500 * (wvl * 2.0) ** (-alpha)        # aerosol optical depth at λ (Eq 2-7)

            Tr = math.exp(-Amp / (wvl ** 4 * (115.6406 - 1.3366 / wvl ** 2)))   # Rayleigh (Eq 2-4)
            To = math.exp(-Ao * O3 * Amo)                                       # ozone (Eq 2-9)
            Tw = math.exp(-0.2385 * Aw * W * Am / (1.0 + 20.07 * Aw * W * Am) ** 0.45)   # water (Eq 2-8)
            Tu = math.exp(-1.41 * Au * Amp / (1.0 + 118.3 * Au * Amp) ** 0.45)  # uniform gas (Eq 2-11)
            Tas = math.exp(-omegl * ca * Am)             # aerosol scattering (Eq 3-9)
            Taa = math.exp((omegl - 1.0) * ca * Am)      # aerosol absorption (Eq 3-10)
            Ta = math.exp(-ca * Am)                      # aerosol total (Eq 2-6)

            # Primed (diffuse-path, fixed air mass 1.8).
            Trp = math.exp(-1.8 / (wvl ** 4 * (115.6406 - 1.3366 / wvl ** 2)))
            Twp = math.exp(-0.4293 * Aw * W / (1.0 + 36.126 * Aw * W) ** 0.45)
            Tup = math.exp(-2.538 * Au / (1.0 + 212.94 * Au) ** 0.45)
            Tasp = math.exp(-omegl * ca * 1.8)
            Taap = math.exp((omegl - 1.0) * ca * 1.8)

            # Direct normal (Eq 2-1).
            c2 = H0 * To * Tw * Tu
            dir_n = c2 * Tr * Ta

            # Diffuse on horizontal (Eq 3-1..3-8).
            c2 *= cz * Taa
            c4 = (wvl + 0.55) ** 1.8 if wvl <= 0.45 else 1.0      # Cs forward-scatter (Eq 3-17)
            rhoa = Tup * Twp * Taap * (0.5 * (1.0 - Trp) + (1.0 - fsp) * Trp * (1.0 - Tasp))  # Eq 3-8
            dray = c2 * (1.0 - Tr ** 0.95) / 2.0                  # Rayleigh diffuse (Eq 3-5)
            daer = c2 * Tr ** 1.5 * (1.0 - Tas) * fs              # aerosol diffuse (Eq 3-6)
            drgd = (dir_n * cz + dray + daer) * rho * rhoa / (1.0 - rho * rhoa)  # ground multi-refl (Eq 3-7)
            dif = (dray + daer + drgd) * c4

            if tilted:
                dtot = dir_n * cz + dif
                t_grd = dtot * rho * (1.0 - ct) / 2.0            # ground-reflected onto tilt (Eq 3-18)
                beam_frac = dir_n / H0
                t_beamdif = dif * beam_frac * ci / cz            # beam-correlated diffuse on tilt
                t_iso = dif * (1.0 - beam_frac) * (1.0 + ct) / 2.0   # isotropic sky on tilt
                dif = t_grd + t_beamdif + t_iso

            direct[i] = dir_n
            diffuse[i] = dif

        return ClearSkySpectra(wavelength_nm=wl_nm, direct_normal=direct,
                               sky_diffuse_horizontal=diffuse)
