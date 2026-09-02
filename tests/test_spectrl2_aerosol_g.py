from hcl_core.spectral_engine.spectrl2 import Spectrl2Engine
from hcl_core import atmosphere, solpos


def test_spectrl2_uses_aerosol_g():
    geo = solpos.compute(month=6, day=21, hour=12.0, latitude=37.9, longitude=23.73, time_zone=2.0)
    row = {"dry_bulb_c": 25.0, "rh_pct": 50.0, "pressure_pa": 101300.0, "aod": 0.2, "albedo": 0.2}
    a1 = atmosphere.derive(row)                                   # g=0.65
    a2 = atmosphere.derive(row, overrides={"aerosol_g": 0.50})    # g=0.50
    d1 = Spectrl2Engine().compute(a1, geo).sky_diffuse_horizontal
    d2 = Spectrl2Engine().compute(a2, geo).sky_diffuse_horizontal
    assert d1 != d2                                              # asymmetry changes diffuse
