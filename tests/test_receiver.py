import math
import pytest
from hcl_core import receiver as R
from hcl_core.spectral_metrics import cct_duv


def test_dome_g1_unit_radiance_integrates_to_pi():
    assert R.N_SKY == 145
    assert abs(R.integrate_diffuse([1.0] * R.N_SKY) - math.pi) < 1e-9


def test_facade_cos_inc_vertical_matches_engine_compare():
    # vertical facade facing east (az 90); a patch at alt 30, az 90 faces it directly
    ci = R.facade_cos_inc(patch_alt_deg=30.0, patch_az_deg=90.0, surface_az_deg=90.0, tilt_deg=90.0)
    assert abs(ci - math.cos(math.radians(30.0))) < 1e-9
    # a patch directly behind (az 270) is shaded (negative)
    assert R.facade_cos_inc(30.0, 270.0, 90.0, 90.0) < 0.0


def test_scattering_angle_zero_at_sun_and_symmetric():
    assert R.scattering_angle_deg(40.0, 180.0, 40.0, 180.0) < 1e-6
    a = R.scattering_angle_deg(40.0, 150.0, 40.0, 180.0)
    b = R.scattering_angle_deg(40.0, 210.0, 40.0, 180.0)
    assert abs(a - b) < 1e-9                       # symmetric about the solar azimuth


def _record(hour=13):
    from hcl_core import solpos
    from hcl_core.atmosphere import AtmosphericState
    from hcl_core.spectral_engine.spectrl2 import Spectrl2Engine
    from hcl_core.cloud_modifier import Sedes1Modifier
    from hcl_core.spectral_sky import build_record
    atm = AtmosphericState(aod500=0.15, angstrom_alpha=1.3, pw_cm=1.5, ozone_atm_cm=0.34,
                           pressure_mbar=1008.0, albedo=0.2, provenance={})
    # Arbitrary fixture coordinates, NOT any measured site. The expectations below are
    # pinned at THIS geometry, so the values stay as they are.
    geo = solpos.compute(month=5, day=13, hour=hour, latitude=37.98, longitude=-23.73, time_zone=-45)
    return build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo, timestamp=(5, 13, hour),
                        dni=800.0, dhi=120.0, ghi=900.0, i0_normal=1361.0)


def test_isotropic_mode_preserves_horizontal_colour():
    rec = _record()
    horiz = list(zip(rec.grid_nm, rec.sky_diffuse_horizontal))
    for o, az in (("E", 90.0), ("W", 270.0), ("N", 0.0), ("S", 180.0)):
        spd = R.oriented_diffuse_for_receiver(rec, surface_az=az, tilt=90.0, mode="isotropic")
        pairs = list(zip(rec.grid_nm, spd))
        assert abs(cct_duv(pairs)["cct_K"] - cct_duv(horiz)["cct_K"]) < 1.0   # one colour for all facades
        assert all(v >= 0.0 for v in spd)


def test_perez_and_single_scatter_implemented_in_task4():
    # Task 4 replaced the NotImplementedError placeholders; both modes now return a 401-value SPD.
    rec = _record()
    for mode in ("perez", "single_scatter"):
        spd = R.oriented_diffuse_for_receiver(rec, surface_az=90.0, tilt=90.0, mode=mode)
        assert len(spd) == len(rec.grid_nm)
        assert all(v >= 0.0 for v in spd)


def test_unknown_mode_raises():
    rec = _record()
    with pytest.raises(ValueError):
        R.oriented_diffuse_for_receiver(rec, surface_az=90.0, mode="bogus")


def test_eps_delta_overcast_dni_zero_uses_overcast_bin():
    # Regression: `if dni and dhi` treated overcast (dni==0.0) as missing data and returned the
    # clear-sky default (eps=6.5, the clearest bin) -- backwards. dni=0 must yield the overcast eps.
    from hcl_core import solpos
    from hcl_core.atmosphere import AtmosphericState
    from hcl_core.spectral_engine.spectrl2 import Spectrl2Engine
    from hcl_core.cloud_modifier import Sedes1Modifier
    from hcl_core.spectral_sky import build_record
    atm = AtmosphericState(aod500=0.15, angstrom_alpha=1.3, pw_cm=1.5, ozone_atm_cm=0.34,
                           pressure_mbar=1008.0, albedo=0.2, provenance={})
    geo = solpos.compute(month=5, day=13, hour=13, latitude=37.98, longitude=-23.73, time_zone=-45)
    rec = build_record(Spectrl2Engine(), Sedes1Modifier(), atm, geo, timestamp=(5, 13, 13),
                       dni=0.0, dhi=120.0, ghi=120.0, i0_normal=1361.0)
    eps, _ = R._eps_delta(rec)
    assert eps < 1.5            # overcast bin (~1.0), NOT the clear-sky default 6.5
