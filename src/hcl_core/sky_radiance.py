"""Layer B — single-scattering per-direction spectral COLOUR (rides on Layer A's magnitude).

The colour anisotropy arises ONLY from the Rayleigh-vs-aerosol ratio varying with scattering angle Θ:
Rayleigh is λ⁻⁴ blue-rich and peaks 90° from the sun; the aerosol Henyey–Greenstein lobe is warm and forward
(near the sun). Mixing the two by angle tilts the colour; a wavelength-independent angular phase would not.
The field is normalized to a unit cosine-weighted dome mean (colour-only — it does not change the engine's
baseline diffuse colour) and damped toward isotropy by the single fitted knob η (see Task 5).
"""
import math
from hcl_core import receiver as R

DEFAULT_G = 0.65          # aerosol HG asymmetry (forward); typical continental
DEFAULT_ETA = 0.5         # the one tunable knob, and it is EMPIRICAL: fitted against an internal dataset
                          # that is not published with this toolkit. The fit constrains it to an INTERVAL,
                          # eta in [0.19, 0.69] - matching the median exactly gives 0.458, which the data
                          # cannot distinguish from 0.5. 0.5 is kept because moving it would assert a
                          # precision the fit does not carry. Any claim that eta is "fitted" must carry the
                          # interval, never a point estimate.
                          # Single-scatter is first-order and omits multiple-scattering graying, so the raw
                          # swing is damped toward isotropy.


def rayleigh_phase(theta_deg):
    c = math.cos(math.radians(theta_deg))
    return 0.75 * (1.0 + c * c)


def hg_phase(theta_deg, g):
    c = math.cos(math.radians(theta_deg))
    return (1.0 - g * g) / math.pow(1.0 + g * g - 2.0 * g * c, 1.5)


def _patch_spectrum(theta_deg, wavelengths_nm, aod_ratio, g):
    """Un-normalized single-scatter spectrum at a patch: Rayleigh(λ⁻⁴)·phase + aerosol(λ⁻¹)·HG."""
    ray_ph = rayleigh_phase(theta_deg)
    hg_ph = hg_phase(theta_deg, g)
    out = []
    for wl in wavelengths_nm:
        x = 550.0 / wl
        rayleigh = (x ** 4) * ray_ph
        aerosol = aod_ratio * (x ** 1) * hg_ph
        out.append(rayleigh + aerosol)
    return out


def color_ratio_field(wavelengths_nm, sun_alt, sun_az, *, aod_ratio, g=DEFAULT_G, eta=None):
    """Per-patch colour-only spectral ratio (145 x len(wl)), dome-mean-normalized to 1, η-damped.
    eta=None resolves to the live module-level DEFAULT_ETA (the single fitted knob), so callers that
    leave it unset always track the fitted constant rather than a value frozen at import time."""
    if eta is None:
        eta = DEFAULT_ETA
    raw = []
    for p in R.DOME:
        th = R.scattering_angle_deg(p["alt"], p["az"], sun_alt, sun_az)
        raw.append(_patch_spectrum(th, wavelengths_nm, aod_ratio, g))
    # cosine-weighted dome mean spectrum (the grey baseline that carries the magnitude)
    mean = [R.integrate_diffuse([raw[i][k] for i in range(R.N_SKY)]) / math.pi
            for k in range(len(wavelengths_nm))]
    field = []
    for i in range(R.N_SKY):
        ratio = [(raw[i][k] / mean[k]) if mean[k] > 1e-30 else 1.0 for k in range(len(wavelengths_nm))]
        field.append([1.0 + eta * (r - 1.0) for r in ratio])
    return field
