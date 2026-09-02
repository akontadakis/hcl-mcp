import math
from hcl_core import perez_distribution as P


def test_air_mass_kasten():
    assert abs(P.air_mass(0.0) - 1.0) < 0.02          # overhead sun ~1
    assert P.air_mass(60.0) > P.air_mass(20.0)        # grows toward horizon
    assert P.air_mass(85.0) > 9.0                      # large near horizon


def test_clearness_bins_clear_vs_overcast():
    # clear noon: high DNI, low DHI, small zenith -> high epsilon (clearest bin 8 -> idx 7)
    eps_clear = P.sky_clearness(dni=850.0, dhi=90.0, zenith_deg=20.0)
    assert eps_clear > 6.2
    # overcast: ~no beam -> epsilon ~ 1 (bin 0)
    eps_oc = P.sky_clearness(dni=2.0, dhi=120.0, zenith_deg=50.0)
    assert eps_oc < 1.23


def test_brightness_positive_and_scales_with_dhi():
    d1 = P.sky_brightness(dhi=100.0, zenith_deg=40.0)
    d2 = P.sky_brightness(dhi=200.0, zenith_deg=40.0)
    assert 0.0 < d1 < d2


def test_coeff_table_shape():
    assert len(P.PEREZ_COEFF) == 8
    assert all(len(b) == 5 and all(len(t) == 4 for t in b) for b in P.PEREZ_COEFF)


def test_relative_luminance_clear_brightens_toward_sun():
    # clear sky (epsilon>6): a patch near the sun is brighter than one far from it
    eps, dl = 6.5, 0.12
    Z = math.radians(30.0)
    near = P.relative_luminance(zeta_rad=Z, gamma_rad=math.radians(10.0), zenith_rad=Z, epsilon=eps, delta=dl)
    far = P.relative_luminance(zeta_rad=Z, gamma_rad=math.radians(120.0), zenith_rad=Z, epsilon=eps, delta=dl)
    assert near > far > 0.0


def test_relative_luminance_overcast_is_finite_and_positive():
    # bin 0 (overcast) uses the exp/pow branch; must not blow up
    lv = P.relative_luminance(zeta_rad=0.3, gamma_rad=1.0, zenith_rad=0.6, epsilon=1.02, delta=0.3)
    assert lv > 0.0 and math.isfinite(lv)
