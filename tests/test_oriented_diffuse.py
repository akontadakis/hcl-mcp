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


# ---- review 2026-11-26, C4: the anchored modes carry the right AMOUNT of light ----

@pytest.mark.parametrize("mode", ["isotropic", "perez", "single_scatter"])
def test_a_horizontal_receiver_gets_back_the_horizontal_diffuse(mode):
    """Tilt 0 is the plane the record's diffuse spectrum was measured on. Every mode must hand
    that spectrum back. The two anchored modes returned pi times it: the anchor was
    `base * pi / dome`, and the dome integral already carries the pi."""
    rec = _record()
    got = sum(R.oriented_diffuse_for_receiver(rec, surface_az=180.0, tilt=0.0, mode=mode))
    assert got == pytest.approx(sum(rec.sky_diffuse_horizontal), rel=0.02)


@pytest.mark.parametrize("mode", ["perez", "single_scatter"])
def test_a_vertical_facade_cannot_receive_several_times_the_whole_sky(mode):
    """A wall sees half the sky. Facing the sun on a clear day it can beat the horizontal value
    by the bright ring round the sun, not by a factor of pi."""
    rec = _record()
    horizontal = sum(rec.sky_diffuse_horizontal)
    for az in (0.0, 90.0, 180.0, 270.0):
        facade = sum(R.oriented_diffuse_for_receiver(rec, surface_az=az, tilt=90.0, mode=mode))
        assert 0.1 * horizontal < facade < 1.6 * horizontal, (az, facade / horizontal)
