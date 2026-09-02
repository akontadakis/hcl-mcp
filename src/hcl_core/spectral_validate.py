"""Validation harness: drift-vs-templates (reuses reconstruction_divergence) + cross-engine compare."""
from hcl_core.spectral_reconstruct import reconstruction_divergence


def drift_vs_templates(sky_channels, sun_channels, channel_type, *, sky_spd=None, solar_zenith=None):
    """How far do the enhanced (physical-shaped) reconstructions move the circadian metrics vs flat/neutral."""
    return reconstruction_divergence(sky_channels, sun_channels, channel_type,
                                     sky_spd=sky_spd, solar_zenith=solar_zenith)


def _interp(gx, ys, x):
    if x <= gx[0]:
        return ys[0]
    if x >= gx[-1]:
        return ys[-1]
    lo = 0
    while gx[lo + 1] < x:
        lo += 1
    t = (x - gx[lo]) / (gx[lo + 1] - gx[lo])
    return ys[lo] + t * (ys[lo + 1] - ys[lo])


def _stats(a_gx, a_y, b_gx, b_y, lo_nm, hi_nm):
    diffs = []
    for x in range(int(lo_nm), int(hi_nm) + 1):
        av = _interp(a_gx, a_y, x); bv = _interp(b_gx, b_y, x)
        if abs(av) > 1e-12:
            diffs.append(100.0 * (bv - av) / av)
    if not diffs:
        return 0.0, 0.0
    return sum(diffs) / len(diffs), max(diffs, key=abs)


def compare_engines(a, b, *, lo_nm=380, hi_nm=780):
    """Mean/max relative % difference (b vs a) of direct + diffuse over the visible band.

    Raises ValueError if either spectrum's wavelength grid does not span [lo_nm, hi_nm];
    the comparator refuses to silently clamp/extrapolate outside an engine's measured range.
    """
    for label, cs in (("a", a), ("b", b)):
        gx = cs.wavelength_nm
        if not gx or min(gx) > lo_nm or max(gx) < hi_nm:
            span = f"[{min(gx)}, {max(gx)}]" if gx else "[]"
            raise ValueError(
                f"compare_engines: spectrum '{label}' grid {span} nm does not span the "
                f"comparison band [{lo_nm}, {hi_nm}] nm; refusing to clamp/extrapolate silently")
    dmean, dmax = _stats(a.wavelength_nm, a.direct_normal, b.wavelength_nm, b.direct_normal, lo_nm, hi_nm)
    fmean, fmax = _stats(a.wavelength_nm, a.sky_diffuse_horizontal,
                         b.wavelength_nm, b.sky_diffuse_horizontal, lo_nm, hi_nm)
    return {"direct_mean_pct": dmean, "direct_max_pct": dmax,
            "diffuse_mean_pct": fmean, "diffuse_max_pct": fmax}
