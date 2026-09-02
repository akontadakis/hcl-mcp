"""Anisotropic-diffuse façade projector (optional consumer of SpectralSkyRecord).

Promotes the Reinhart/Tregenza MF:1 sky dome + cosine-weighted integrator (formerly only in
the engine-comparison analysis scripts — gate G1) into src/, so production and the validation
analysis share ONE integrator. Adds façade geometry and the projector that turns the record's horizontal
diffuse into an oriented façade SPD under the selected anisotropy mode. Engines/record are untouched.

modes:  isotropic      — one colour for all facades (today's behaviour); magnitude = isotropic view factor.
        perez          — Layer A angular magnitude only (colour still single).  [Task 4]
        single_scatter — Layer A magnitude x Layer B per-direction colour ratio. [Task 4]
"""
import math

from hcl_core import perez_distribution as A
from hcl_core import sky_radiance as B

ROW_COUNTS = [30, 30, 24, 24, 18, 12, 6, 1]
N_SKY = sum(ROW_COUNTS)                                   # 145
BAND_CENTRE_ALT = [6, 18, 30, 42, 54, 66, 78, 90]


def _band_edges(b):
    if b < 7:
        return 12.0 * b, 12.0 * b + 12.0
    return 84.0, 90.0


def build_dome():
    """145 SKY patches, horizon->zenith, az ascending. Each: row, band, alt, az, theta, omega, cw.
    Verbatim geometry from patch_geometry.build_dome (gate G1: unit radiance integrates to pi)."""
    patches, row = [], 1
    for b, n in enumerate(ROW_COUNTS):
        alt_lo, alt_hi = _band_edges(b)
        th_top = math.radians(90.0 - alt_hi)
        th_bot = math.radians(90.0 - alt_lo)
        dphi = 2.0 * math.pi / n
        omega = dphi * (math.cos(th_top) - math.cos(th_bot))
        cw = dphi * 0.5 * (math.cos(th_top) ** 2 - math.cos(th_bot) ** 2)
        alt_c = float(BAND_CENTRE_ALT[b])
        for i in range(n):
            az_c = 0.0 if n == 1 else (i * 360.0 / n)
            patches.append({"row": row, "band": b, "alt": alt_c, "az": az_c,
                            "theta": 90.0 - alt_c, "omega": omega, "cw": cw})
            row += 1
    return patches


DOME = build_dome()


def integrate_diffuse(values, dome=DOME):
    """Cosine-weighted dome integral Σ value·cw. Unit radiance -> π (gate G1)."""
    if len(values) != len(dome):
        raise ValueError(f"expected {len(dome)} sky patches, got {len(values)}")
    return sum(v * p["cw"] for v, p in zip(values, dome))


def facade_cos_inc(patch_alt_deg, patch_az_deg, surface_az_deg, tilt_deg=90.0):
    """Signed cosine of incidence of a sky-patch direction on a surface normal.
    tilt=90 -> vertical facade -> cos(alt)·cos(az − surface_az) (matches engine_compare.cos_inc/faz)."""
    alt = math.radians(patch_alt_deg)
    daz = math.radians(patch_az_deg - surface_az_deg)
    t = math.radians(tilt_deg)
    # surface normal at altitude (90−tilt) and azimuth surface_az; dot with patch unit vector:
    return (math.cos(alt) * math.sin(t) * math.cos(daz) + math.sin(alt) * math.cos(t))


def scattering_angle_deg(patch_alt, patch_az, sun_alt, sun_az):
    """Great-circle angle (deg) between a patch direction and the sun."""
    a1, a2 = math.radians(patch_alt), math.radians(sun_alt)
    daz = math.radians(patch_az - sun_az)
    c = math.sin(a1) * math.sin(a2) + math.cos(a1) * math.cos(a2) * math.cos(daz)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _isotropic_facade(record, surface_az, tilt):
    """One colour for all facades: horizontal diffuse shape, scaled by the isotropic view factor
    Σ max(0,cos_inc)·omega (= π/2 for a vertical facade). Colour is unchanged by construction."""
    vf = sum(max(0.0, facade_cos_inc(p["alt"], p["az"], surface_az, tilt)) * p["omega"] for p in DOME)
    # horizontal diffuse integrates over the dome to Σ cw = π for unit radiance; the colour (shape) is the
    # record's sky_diffuse_horizontal. Scale shape by vf/π so an isotropic vertical facade gets DHI·(vf/π).
    scale = vf / math.pi
    return [v * scale for v in record.sky_diffuse_horizontal]


def _eps_delta(record):
    """Derive Perez epsilon/delta for the record. Uses broadband DNI/DHI when present; else a clear-sky
    default from geometry. Documented approximation — colour ordering is robust to the exact bin."""
    z = record.geometry.zenith_deg
    bb = record.broadband                              # always present; a dict {dni,dhi,ghi,clearness_kt}
    dni, dhi = bb.get("dni"), bb.get("dhi")
    # dni==0.0 with dhi>0 is a valid OVERCAST reading, not missing data. Test `is not None`
    # rather than truthiness, else overcast hours fall through to the clear-sky default below
    # (the highest/clearest Perez bin) -- exactly backwards. sky_clearness(0, dhi, z) -> eps~1.0.
    if dni is not None and dhi is not None and dhi > 0:
        return A.sky_clearness(dni, dhi, z), A.sky_brightness(dhi, z)
    return 6.5, 0.12                                   # clear default (highest bin) — documented fallback


def _anchored_facade(record, surface_az, tilt, color_field):
    """Build the per-patch field (Layer A magnitude x colour), anchor its dome integral to the record's
    horizontal diffuse, then project onto the facade normal. color_field=None -> single (Layer A) colour."""
    eps, dl = _eps_delta(record)
    Z = math.radians(record.geometry.zenith_deg)
    sun_alt = 90.0 - record.geometry.zenith_deg
    sun_az = record.geometry.azimuth_deg
    base = record.sky_diffuse_horizontal
    nwl = len(base)
    # Layer A relative luminance per patch
    lum = []
    for p in DOME:
        zeta = math.radians(p["theta"])
        gamma = math.radians(scattering_angle_deg(p["alt"], p["az"], sun_alt, sun_az))
        lum.append(max(0.0, A.relative_luminance(zeta, gamma, Z, eps, dl)))
    # per-patch spectrum = base colour x (Layer A magnitude) x (Layer B colour ratio if present)
    patch_spd = []
    for i, p in enumerate(DOME):
        cr = color_field[i] if color_field is not None else None
        patch_spd.append([base[k] * lum[i] * (cr[k] if cr is not None else 1.0) for k in range(nwl)])
    # anchor: cosine-weighted dome integral must reproduce the horizontal diffuse at each wavelength
    out = []
    for k in range(nwl):
        dome_k = integrate_diffuse([patch_spd[i][k] for i in range(N_SKY)])
        anchor = (base[k] * math.pi / dome_k) if dome_k > 1e-30 else 0.0
        fac = sum(max(0.0, facade_cos_inc(p["alt"], p["az"], surface_az, tilt)) * p["omega"] * patch_spd[i][k]
                  for i, p in enumerate(DOME))
        out.append(fac * anchor)
    return out


def oriented_diffuse_for_receiver(record, *, surface_az, tilt=90.0, mode="isotropic"):
    """Oriented façade diffuse SPD (401 values) for the receiver, under the selected anisotropy mode."""
    if mode == "isotropic":
        return _isotropic_facade(record, surface_az, tilt)
    if mode == "perez":
        return _anchored_facade(record, surface_az, tilt, color_field=None)
    if mode == "single_scatter":
        field = B.color_ratio_field(record.grid_nm, sun_alt=90.0 - record.geometry.zenith_deg,
                                     sun_az=record.geometry.azimuth_deg,
                                     aod_ratio=max(0.05, record.atmosphere.aod500 * 2.0),
                                     g=record.atmosphere.aerosol_g)
        return _anchored_facade(record, surface_az, tilt, color_field=field)
    raise ValueError(f"unknown mode {mode!r}; choose isotropic, perez, single_scatter")
