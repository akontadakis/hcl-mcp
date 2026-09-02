"""Perez 1993 all-weather sky relative-luminance distribution (Layer A — achromatic magnitude).

Pure-Python port of the published model (Perez, Seals & Michalsky 1993, Sol. Energy 50:235), grounded in
and cross-checked against the upstream Radiance source `gen/gendaylit.c` (coefficient array, epsilon bins,
and the l(zeta,gamma) form). This layer supplies the angular *brightness* envelope only; the spectral colour
rides on top in `sky_radiance.py`. No engine internals are touched.
"""
import math

# Perez luminance coefficients: 8 epsilon-bins x 5 params (a..e) x 4 terms (x[i][0..3]).
# Verbatim from Radiance gen/gendaylit.c:27 (coeff_perez[]), reshaped [bin][param][term].
_FLAT = (
    1.3525, -0.2576, -0.2690, -1.4366, -0.7670, 0.0007, 1.2734, -0.1233, 2.8000, 0.6004,
    1.2375, 1.000, 1.8734, 0.6297, 0.9738, 0.2809, 0.0356, -0.1246, -0.5718, 0.9938,
    -1.2219, -0.7730, 1.4148, 1.1016, -0.2054, 0.0367, -3.9128, 0.9156, 6.9750, 0.1774,
    6.4477, -0.1239, -1.5798, -0.5081, -1.7812, 0.1080, 0.2624, 0.0672, -0.2190, -0.4285,
    -1.1000, -0.2515, 0.8952, 0.0156, 0.2782, -0.1812, -4.5000, 1.1766, 24.7219, -13.0812,
    -37.7000, 34.8438, -5.0000, 1.5218, 3.9229, -2.6204, -0.0156, 0.1597, 0.4199, -0.5562,
    -0.5484, -0.6654, -0.2672, 0.7117, 0.7234, -0.6219, -5.6812, 2.6297, 33.3389, -18.3000,
    -62.2500, 52.0781, -3.5000, 0.0016, 1.1477, 0.1062, 0.4659, -0.3296, -0.0876, -0.0329,
    -0.6000, -0.3566, -2.5000, 2.3250, 0.2937, 0.0496, -5.6812, 1.8415, 21.0000, -4.7656,
    -21.5906, 7.2492, -3.5000, -0.1554, 1.4062, 0.3988, 0.0032, 0.0766, -0.0656, -0.1294,
    -1.0156, -0.3670, 1.0078, 1.4051, 0.2875, -0.5328, -3.8500, 3.3750, 14.0000, -0.9999,
    -7.1406, 7.5469, -3.4000, -0.1078, -1.0750, 1.5702, -0.0672, 0.4016, 0.3017, -0.4844,
    -1.0000, 0.0211, 0.5025, -0.5119, -0.3000, 0.1922, 0.7023, -1.6317, 19.0000, -5.0000,
    1.2438, -1.9094, -4.0000, 0.0250, 0.3844, 0.2656, 1.0468, -0.3788, -2.4517, 1.4656,
    -1.0500, 0.0289, 0.4260, 0.3590, -0.3250, 0.1156, 0.7781, 0.0025, 31.0625, -14.5000,
    -46.1148, 55.3750, -7.2312, 0.4050, 13.3500, 0.6234, 1.5000, -0.6426, 1.8564, 0.5636,
)
PEREZ_COEFF = tuple(
    tuple(tuple(_FLAT[20 * b + 4 * i + j] for j in range(4)) for i in range(5))
    for b in range(8)
)

SOLAR_CONSTANT_E = 1367.0   # W/m^2 (Radiance gendaylit value, used for Delta)


def air_mass(zenith_deg):
    """Kasten 1965 relative optical air mass (gendaylit.c:1506)."""
    z = min(zenith_deg, 90.0)
    return 1.0 / (math.cos(math.radians(z)) + 0.15 * math.exp(math.log(93.885 - z) * (-1.253)))


def sky_clearness(dni, dhi, zenith_deg):
    """Perez sky clearness epsilon (gendaylit.c:1236). dni = direct *normal*, dhi = diffuse horizontal."""
    if dhi <= 0.0:
        return 1.0
    z = math.radians(zenith_deg)
    k = 1.041 * z * z * z
    return ((dhi + dni) / dhi + k) / (1.0 + k)


def sky_brightness(dhi, zenith_deg, eccentricity=1.0):
    """Perez sky brightness Delta (gendaylit.c:1225)."""
    return dhi * air_mass(zenith_deg) / (SOLAR_CONSTANT_E * eccentricity)


def _numlin(epsilon):
    """Epsilon -> bin index 0..7 (gendaylit.c get_numlin)."""
    for thr, idx in ((1.065, 0), (1.230, 1), (1.500, 2), (1.950, 3),
                     (2.800, 4), (4.500, 5), (6.200, 6)):
        if epsilon < thr:
            return idx
    return 7


def perez_params(zenith_rad, epsilon, delta):
    """The 5 Perez luminance coefficients (a,b,c,d,e) for the given sky (gendaylit.c:1359-1371)."""
    if 1.065 < epsilon < 2.8 and delta < 0.2:
        delta = 0.2
    n = _numlin(epsilon)
    x = PEREZ_COEFF[n]
    Z = zenith_rad
    if n != 0:
        return tuple(x[i][0] + x[i][1] * Z + delta * (x[i][2] + x[i][3] * Z) for i in range(5))
    a = x[0][0] + x[0][1] * Z + delta * (x[0][2] + x[0][3] * Z)
    b = x[1][0] + x[1][1] * Z + delta * (x[1][2] + x[1][3] * Z)
    e = x[4][0] + x[4][1] * Z + delta * (x[4][2] + x[4][3] * Z)
    c = math.exp(math.pow(delta * (x[2][0] + x[2][1] * Z), x[2][2])) - x[2][3]
    d = -math.exp(delta * (x[3][0] + x[3][1] * Z)) + x[3][2] + delta * x[3][3]
    return (a, b, c, d, e)


def relative_luminance(zeta_rad, gamma_rad, zenith_rad, epsilon, delta):
    """Perez relative luminance l(zeta,gamma) (gendaylit.c:1374). zeta = patch zenith angle,
    gamma = angle between patch and sun. Clamp cos(zeta) away from 0 at the horizon."""
    a, b, c, d, e = perez_params(zenith_rad, epsilon, delta)
    cz = math.cos(zeta_rad)
    if cz < 0.01:
        cz = 0.01
    g = gamma_rad
    return (1.0 + a * math.exp(b / cz)) * (1.0 + c * math.exp(d * g) + e * math.cos(g) * math.cos(g))
