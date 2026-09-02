"""Always-on regression guard for the α-opic / spectral-metric path.

Pins `alpha_opic_from_spd`, `mel_der` and `mel_photopic_ratio` against **public CIE
illuminants and LED presets** shipped in `hcl_core.presets`, so the guard runs in every
checkout — including a published one that carries no measured fixture.

The values below were computed from this code and are frozen. If the metric code drifts,
these fail. If a change here is intended, update the numbers and say why in the commit.

`D65 mel_der == 1.0` exactly is the anchor: mel-DER is defined against D65, so any
deviation there is a defect in the definition itself, not a tolerance question.

The development-only counterpart is `test_measured_spd_fixture.py`, which runs the same
checks over a local measured fixture when one is present.
"""
import pytest

from hcl_core import presets
from hcl_core.alpha_opic import alpha_opic_from_spd as ao_exact
from hcl_core.spectral_metrics import mel_der, mel_photopic_ratio

# name -> frozen expectations. ELR = efficacy of luminous radiation, per CIE S 026.
GOLDEN = {
    'D65': {'mel_der': 1.0, 'mel_photopic_ratio': 0.9058, 'melanopic': 1.3262,
            's_cone': 0.8173, 'm_cone': 1.4558, 'l_cone': 1.6289, 'rhodopic': 1.4497},
    'D50': {'mel_der': 0.8474, 'mel_photopic_ratio': 0.7675, 'melanopic': 1.1238,
            's_cone': 0.6104, 'm_cone': 1.383, 'l_cone': 1.6294, 'rhodopic': 1.2704},
    'A': {'mel_der': 0.4958, 'mel_photopic_ratio': 0.4491, 'melanopic': 0.6575,
          's_cone': 0.2542, 'm_cone': 1.1742, 'l_cone': 1.6567, 'rhodopic': 0.8308},
    'FL2': {'mel_der': 0.5699, 'mel_photopic_ratio': 0.5162, 'melanopic': 0.7558,
            's_cone': 0.5083, 'm_cone': 1.2814, 'l_cone': 1.616, 'rhodopic': 0.925},
    'FL7': {'mel_der': 0.9234, 'mel_photopic_ratio': 0.8364, 'melanopic': 1.2246,
            's_cone': 0.8162, 'm_cone': 1.4366, 'l_cone': 1.6184, 'rhodopic': 1.3636},
    'FL11': {'mel_der': 0.5636, 'mel_photopic_ratio': 0.5105, 'melanopic': 0.7475,
             's_cone': 0.4833, 'm_cone': 1.2664, 'l_cone': 1.6143, 'rhodopic': 0.9393},
    'LED_3000K': {'mel_der': 0.5699, 'mel_photopic_ratio': 0.5162, 'melanopic': 0.7559,
                  's_cone': 0.3359, 'm_cone': 1.2378, 'l_cone': 1.6393, 'rhodopic': 0.9305},
    'LED_4000K': {'mel_der': 0.6855, 'mel_photopic_ratio': 0.6209, 'melanopic': 0.9091,
                  's_cone': 0.5054, 'm_cone': 1.3007, 'l_cone': 1.6324, 'rhodopic': 1.0694},
    'LED_5000K': {'mel_der': 0.8181, 'mel_photopic_ratio': 0.741, 'melanopic': 1.085,
                  's_cone': 0.7177, 'm_cone': 1.3594, 'l_cone': 1.6327, 'rhodopic': 1.2221},
    'LED_BLUEPUMP': {'mel_der': 0.7859, 'mel_photopic_ratio': 0.7119, 'melanopic': 1.0423,
                     's_cone': 0.6505, 'm_cone': 1.3504, 'l_cone': 1.6296, 'rhodopic': 1.1883},
    'LED_VIOLETPUMP': {'mel_der': 0.6543, 'mel_photopic_ratio': 0.5927, 'melanopic': 0.8678,
                       's_cone': 0.4189, 'm_cone': 1.3134, 'l_cone': 1.6187, 'rhodopic': 1.0498},
}
_ALPHA = ("melanopic", "s_cone", "m_cone", "l_cone", "rhodopic")


def test_every_pinned_preset_still_ships():
    """A renamed or dropped preset must fail loudly, not silently shrink the guard."""
    available = set(presets.list_presets())
    missing = sorted(set(GOLDEN) - available)
    assert not missing, f"pinned presets no longer shipped: {missing}"


def test_d65_mel_der_is_exactly_one():
    """mel-DER is defined against D65. Anything but 1.0 is a definition defect."""
    assert mel_der(presets.get_preset("D65")) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_grid_is_cie_s026_aligned(name):
    spd = presets.get_preset(name)
    assert len(spd) == 401
    assert spd[0][0] == 380 and spd[-1][0] == 780


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_alpha_opic_matches_golden(name):
    spd = presets.get_preset(name)
    want = GOLDEN[name]
    assert mel_der(spd) == pytest.approx(want["mel_der"], abs=1e-4)
    assert mel_photopic_ratio(spd) == pytest.approx(want["mel_photopic_ratio"], abs=1e-4)
    ao = ao_exact(spd)
    for alpha in _ALPHA:
        assert ao[alpha]["ELR"] == pytest.approx(want[alpha], abs=1e-3)


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_alpha_opic_values_are_physical(name):
    """Every ELR is finite and positive — a guard that survives a golden refresh."""
    ao = ao_exact(presets.get_preset(name))
    for alpha in _ALPHA:
        v = ao[alpha]["ELR"]
        assert v == v and 0.0 < v < 100.0, f"{name}/{alpha} = {v}"
