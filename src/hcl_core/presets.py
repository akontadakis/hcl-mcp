"""Built-in light-source SPDs.

Two families:
  * CIE standard illuminants (D65/D50/A/FL1-12) via colour-science (authoritative standard data).
  * Illustrative LED model SPDs (spec 5.7) - phosphor-converted white-LED models built from a
    pump Gaussian + a broad phosphor hump. These are CLEARLY ILLUSTRATIVE, NOT MEASURED data:
    they exist so callers have plausible LED shapes to exercise the pipeline, and every one is
    flagged illustrative=True. Do not treat them as a product datasheet.
"""
import math
import colour
from colour import SpectralShape

_SHAPE = SpectralShape(380, 780, 1)
_STD_NAMES = ["D65", "D50", "A"] + [f"FL{i}" for i in range(1, 13)]
_ALIASES = {f"F{i}": f"FL{i}" for i in range(1, 13)}

# --- Illustrative LED model -------------------------------------------------

def _gauss(w, mu, sigma):
    return math.exp(-0.5 * ((w - mu) / sigma) ** 2)

def _led_curve(pump_mu, pump_sigma, phosphor_weight, phosphor_mu=580.0, phosphor_sigma=95.0):
    """Build an illustrative phosphor-converted white-LED SPD over 380-780 nm @1 nm, peak-normalized.

    pump_mu/pump_sigma     : the (blue or violet) pump emission Gaussian.
    phosphor_weight        : blue:phosphor ratio knob; higher -> warmer (more phosphor relative to pump).
    phosphor_mu/sigma      : the broad yellow/green phosphor hump (wide Gaussian-ish).

    NOT a measurement - a smooth physically-plausible model. Returns a list of 401 floats (380..780).
    """
    raw = [_gauss(w, pump_mu, pump_sigma) + phosphor_weight * _gauss(w, phosphor_mu, phosphor_sigma)
           for w in range(380, 781)]
    peak = max(raw)
    return [v / peak for v in raw]  # peak-normalize to 1.0

# Each entry: (pump_mu, pump_sigma, phosphor_weight, phosphor_mu, phosphor_sigma). The phosphor
# weight AND placement are tuned so the named models land near their CCT (verified via
# colour-science, loose tolerance): higher weight / redder phosphor -> warmer -> lower CCT. A
# single neutral phosphor hump can't span 3000-5000 K on weight alone, so warmer models also push
# the phosphor hump redder/wider. Still an illustrative fit, not a calibration.
_LED_MODELS = {
    "LED_3000K":     (450.0, 14.0, 8.0,  625.0, 110.0),  # warm: heavy, red-shifted phosphor
    "LED_4000K":     (450.0, 14.0, 2.2,  595.0, 98.0),   # neutral
    "LED_5000K":     (450.0, 14.0, 1.15, 580.0, 95.0),   # cool: stronger blue pump
    "LED_BLUEPUMP":  (450.0, 14.0, 1.4,  580.0, 95.0),   # generic blue-pump white (~4500 K-ish)
    "LED_VIOLETPUMP":(415.0, 11.0, 1.8,  580.0, 95.0),   # violet-pump white (narrower, shorter pump)
}
ILLUSTRATIVE_LEDS = tuple(_LED_MODELS)

_LED_NOTE = ("Illustrative LED model (pump Gaussian + broad phosphor hump) - NOT measured data; "
             "do not treat as a product datasheet. See spec 5.7.")

_NAMES = _STD_NAMES + list(_LED_MODELS)

def list_presets():
    """Names of the built-in light-source SPDs (CIE standards + illustrative LED models)."""
    return list(_NAMES)

def preset_meta(name):
    """Metadata for a preset: {family, illustrative, notes, source}. Raises KeyError on unknown names."""
    if name in _LED_MODELS:
        return {"family": "illustrative_led", "illustrative": True, "notes": _LED_NOTE,
                "source": "synthetic physical model (this package)"}
    key = _ALIASES.get(name.upper(), name.upper())
    if key in _STD_NAMES:
        return {"family": "cie_illuminant", "illustrative": False,
                "notes": "CIE standard illuminant via colour-science (authoritative standard data).",
                "source": "colour-science"}
    raise KeyError(f"unknown preset {name!r}; choose from {_NAMES}")

def get_preset(name):
    """Return the SPD as a list of (wavelength_nm, value) pairs on a 1-nm 380-780 grid.

    Standard illuminants come from colour-science. The LED_* presets are ILLUSTRATIVE models
    (flagged via preset_meta(name)['illustrative'] == True), NOT measured data - see spec 5.7.
    Accepts 'F1'..'F12' as aliases for 'FL1'..'FL12'. Raises KeyError on unknown names.
    """
    if name in _LED_MODELS:
        curve = _led_curve(*_LED_MODELS[name])
        return [(w, round(float(curve[i]), 6)) for i, w in enumerate(range(380, 781))]
    key = _ALIASES.get(name.upper(), name.upper())
    if key not in colour.SDS_ILLUMINANTS:
        raise KeyError(f"unknown preset {name!r}; choose from {_NAMES}")
    sd = colour.SDS_ILLUMINANTS[key].copy().align(_SHAPE)
    return [(w, round(float(sd[w]), 6)) for w in range(380, 781)]
