import math
import pytest
from hcl_core import receiver as R
from hcl_core.spectral_metrics import cct_duv


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


def _cct(rec, az, mode):
    spd = R.oriented_diffuse_for_receiver(rec, surface_az=az, tilt=90.0, mode=mode)
    return cct_duv(list(zip(rec.grid_nm, spd)))["cct_K"]


def test_perez_mode_colour_is_orientation_independent():
    rec = _record()
    ccts = [_cct(rec, az, "perez") for az in (0.0, 90.0, 180.0, 270.0)]
    assert max(ccts) - min(ccts) < 5.0          # Layer A changes magnitude, not colour


def test_single_scatter_produces_facade_colour_spread():
    rec = _record()
    ccts = {o: _cct(rec, az, "single_scatter") for o, az in (("N", 0.0), ("E", 90.0), ("S", 180.0), ("W", 270.0))}
    spread = max(ccts.values()) - min(ccts.values())
    assert spread > 50.0                         # single_scatter DOES vary colour by orientation (η=1 raw is large)


def test_isotropic_still_flat():
    rec = _record()
    ccts = [_cct(rec, az, "isotropic") for az in (0.0, 90.0, 180.0, 270.0)]
    assert max(ccts) - min(ccts) < 1.0
