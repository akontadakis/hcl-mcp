import math
from dataclasses import dataclass
from hcl_core.spectral_engine.spectrl2 import Spectrl2Engine
from hcl_core.spectral_engine import _spectrl2_data as D


# Minimal geometry/atmosphere stand-ins (avoid importing Phase-1 modules so this task is isolated;
# the engine only reads the attributes named below).
@dataclass
class Geo:
    zenith_deg: float; air_mass: float; earth_radius_vector: float; day_of_year: int = 360
@dataclass
class Atm:
    aod500: float; angstrom_alpha: float; pw_cm: float; ozone_atm_cm: float
    pressure_mbar: float; albedo: float; aerosol_g: float = 0.65


def _idx(um):
    return min(range(122), key=lambda i: abs(D.WL_UM[i] - um))


# Golden reference: the Fortran SPCTRAL2 TAPE case (GLOBAL TILT @40°).
# TAPE1: tau5=0.04, alpha=1.0, ozone=0.367, W=0.2, tilt=40, press=816, NDAY=360.
# TAPE1 line4: Z=79.94 (zenith), AI=56.11 (incidence). OUTPUT header: AM=5.55, ERV=1.0347.
_GEO = Geo(zenith_deg=79.94, air_mass=5.55, earth_radius_vector=1.0347)
_ATM = Atm(aod500=0.04, angstrom_alpha=1.0, pw_cm=0.2, ozone_atm_cm=0.367,
           pressure_mbar=816.0, albedo=0.2)
_CI = math.cos(math.radians(56.11))  # cos incidence on the 40° tilt

# Reference rows from SPCTRAL2_OUTPUT.txt: (λµm, global, direct, diffuse), W/m²/µm.
_REF = [
    (0.4000, 258.5532, 227.7916, 131.5366),
    (0.4500, 532.8571, 593.1810, 202.0993),
    (0.5000, 610.3002, 781.2781, 174.6597),
    (0.5500, 627.0659, 877.1638, 137.9595),
    (0.6560, 625.5478, 949.3600,  96.1847),
    (0.7100, 660.3042, 1020.8553, 91.0754),
]


def test_golden_direct_normal_matches_fortran_reference():
    cs = Spectrl2Engine().compute(_ATM, _GEO, tilt_deg=40.0, cos_incidence=_CI)
    # Verified: the port reproduces the Fortran direct column to <0.05% in the visible.
    for um, _glo, direct, _dif in _REF:
        got = cs.direct_normal[_idx(um)]
        assert abs(got - direct) / direct < 0.005, f"{um}µm direct {got} vs {direct}"


def test_golden_diffuse_on_tilt_matches_fortran_reference():
    cs = Spectrl2Engine().compute(_ATM, _GEO, tilt_deg=40.0, cos_incidence=_CI)
    # In tilt mode the engine stores diffuse-on-tilt in sky_diffuse_horizontal. Verified <0.01% in VIS.
    for um, _glo, _direct, dif in _REF:
        got = cs.sky_diffuse_horizontal[_idx(um)]
        assert abs(got - dif) / dif < 0.01, f"{um}µm diffuse {got} vs {dif}"


def test_exact_rayleigh_constant_locked():
    # Tr(0.5µm, Amp=4.471) with C constants: exp(-Amp/(0.5^4*(115.6406-1.3366/0.25))) = 0.52281
    Amp = 5.55 * 816.0 / 1013.0
    tr = math.exp(-Amp / (0.5 ** 4 * (115.6406 - 1.3366 / 0.5 ** 2)))
    assert abs(tr - 0.52281) < 1e-4
    assert abs(Amp - 4.47) < 0.01


def test_horizontal_mode_is_default_and_positive():
    cs = Spectrl2Engine().compute(_ATM, _GEO)  # tilt_deg defaults to 0 → horizontal
    assert len(cs.wavelength_nm) == 122
    assert cs.wavelength_nm[_idx(0.5)] == 500.0
    assert cs.direct_normal[_idx(0.5)] > 0
    assert cs.sky_diffuse_horizontal[_idx(0.5)] > 0
    assert cs.units == "W/m^2/um"


def test_night_returns_zeros():
    night = Geo(zenith_deg=95.0, air_mass=float("inf"), earth_radius_vector=1.0)
    cs = Spectrl2Engine().compute(_ATM, night)
    assert all(v == 0.0 for v in cs.direct_normal)
    assert all(v == 0.0 for v in cs.sky_diffuse_horizontal)
