from hcl_core.spectral_engine import smarts
from hcl_core import atmosphere, solpos


def _atm_geo():
    geo = solpos.compute(month=6, day=21, hour=12.0, latitude=37.9, longitude=23.73, time_zone=2.0)
    atm = atmosphere.derive({"pressure_pa": 101300.0, "aod": 0.2, "albedo": 0.2,
                             "dry_bulb_c": 25.0, "rh_pct": 50.0}, overrides={"aerosol_g": 0.62})
    return atm, geo


def test_deck_default_is_rural():
    atm, geo = _atm_geo()
    assert "'S&F_RURAL'" in smarts.build_deck(atm, geo)


def test_deck_user_sets_alpha_and_g():
    atm, geo = _atm_geo()
    deck = smarts.build_deck(atm, geo, aerosol="user")
    assert "'USER'" in deck
    assert "1.14 1.14" in deck        # ALPHA1 ALPHA2 = angstrom_alpha
    assert "0.62" in deck             # GG = aerosol_g
