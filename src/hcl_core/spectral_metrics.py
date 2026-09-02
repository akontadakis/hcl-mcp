"""Derived HCL quantities (extra). CCT/Duv via colour-science; mel-DER from the bundled action-spectrum curves."""
import colour

from hcl_core.data import ACTION_MEL, V_LAMBDA, EML_PER_MEDI
from hcl_core.spd import parse_spd, to_grid_list
from hcl_core.presets import get_preset

_D65_GRID = None

def _grid(spd):
    return to_grid_list(parse_spd(spd))

def cct_duv(spd):
    """Correlated colour temperature (K) and Duv from an SPD, via colour-science (Ohno 2013)."""
    d = parse_spd(spd)
    sd = colour.SpectralDistribution({float(w): v for w, v in d.items()})
    xyz = colour.sd_to_XYZ(sd)
    uv = colour.UCS_to_uv(colour.XYZ_to_UCS(xyz))
    cct, duv = colour.uv_to_CCT(uv, method="Ohno 2013")
    return {"cct_K": round(float(cct), 1), "duv": round(float(duv), 5)}

def _mel_elr(grid):
    e_mel = sum(grid[i] * ACTION_MEL[i] for i in range(401))
    e_v = 683 * sum(grid[i] * V_LAMBDA[i] for i in range(401))
    return (e_mel / e_v) * 1000 if e_v else 0.0

def mel_der(spd):
    """Melanopic Daylight (D65) Efficacy Ratio = mel-ELR(source)/mel-ELR(D65). 1.0 for D65 by definition."""
    global _D65_GRID
    if _D65_GRID is None:
        _D65_GRID = _grid(get_preset("D65"))
    ref = _mel_elr(_D65_GRID)
    return round(_mel_elr(_grid(spd)) / ref, 4) if ref else 0.0

# Wavelength -> bin index, for each channel_type. A closed [lo, hi] band shares its edge with
# the next band (see spd.bin_average), but weighting a spectrum needs a PARTITION, so an edge
# sample is assigned to the first band containing it. That moves one 1-nm sample out of ~40 per
# band and is far below the accuracy of the transport it is weighting.
_BIN_OF = {}


def _bin_of(channel_type):
    if channel_type not in _BIN_OF:
        from hcl_core.data import BINS_3, BINS_9
        bins = BINS_3 if channel_type == 0 else BINS_9
        table = []
        for lam in range(380, 781):
            idx = next((i for i, (lo, hi) in enumerate(bins) if lo <= lam <= hi), len(bins) - 1)
            table.append(idx)
        _BIN_OF[channel_type] = table
    return _BIN_OF[channel_type]


def mel_der_transported(spd, channels, channel_type):
    """mel-DER of the spectrum implied AT A POINT by a known source SPD and the channels measured
    there. Returns None when the transport cannot be recovered.

    WHY THIS EXISTS. mel-DER is a property of the spectrum where the observer is, not where the
    lamp is. Handing `mel_der(spd)` to a transported result reports the LUMINAIRE and is only
    right while the room is spectrally neutral; handing over the binned channels loses the source's
    within-bin structure and reads up to ~8% high on a narrow-band fluorescent. Neither is the
    quantity a sensor at that point would read.

    WHAT IT COMPUTES. The engine models transport at the resolution of its bins: it bins the source
    (spd.bin_average), bins each material, and multiplies per channel. So the per-bin transport it
    applied is recoverable exactly as T_i = channels_i / source_i, and the spectrum it implies at the
    point is S(lambda) * T_i for lambda in band i. Weighting THAT against the S 026 action spectra
    keeps the source's full 1-nm structure and applies the transport the simulation actually ran.

    Scale-invariant in both arguments: T_i carries the arbitrary ratio between the channels' units
    (irradiance) and the SPD's (often relative), and that factor cancels in the mel/photopic ratio.
    Reduces EXACTLY to mel_der(spd) when every T_i is equal, i.e. when nothing shifted the spectrum
    — which is why supplying a source SPD for source characterisation is unaffected by this route.

    Returns None when no band carries usable light (all source bands zero, or a zero denominator),
    leaving the caller to fall back rather than publish a fabricated number.
    """
    from hcl_core.spd import bin_average
    src = parse_spd(spd)
    s_bins = bin_average(src, channel_type)
    if len(channels) != len(s_bins):
        raise ValueError(f"channel_type {channel_type} needs {len(s_bins)} channels, "
                         f"got {len(channels)}")
    # A band the source does not emit in contributes nothing regardless of what is measured
    # there; T_i = 0 keeps it out of both integrals instead of dividing by zero.
    transport = [(float(c) / s) if s > 0 else 0.0 for c, s in zip(channels, s_bins)]
    grid = _grid(spd)
    bin_of = _bin_of(channel_type)
    num = sum(grid[i] * transport[bin_of[i]] * ACTION_MEL[i] for i in range(401))
    den = 683 * sum(grid[i] * transport[bin_of[i]] * V_LAMBDA[i] for i in range(401))
    # The single gate on "no transport to recover". A dark point drives every T_i to zero and with
    # it the denominator; so does an all-negative channel row (rtrace can return small negatives
    # from interpolation). Both mean there is nothing here to weight a spectrum by, and returning
    # None hands the caller a labelled fallback instead of a fabricated ratio.
    if den <= 0:
        return None
    global _D65_GRID
    if _D65_GRID is None:
        _D65_GRID = _grid(get_preset("D65"))
    ref = _mel_elr(_D65_GRID)
    return round(((num / den) * 1000) / ref, 4) if ref else None


def mel_photopic_ratio(spd):
    """Action-weighted melanopic/photopic integral ratio = Sum(SPD*mel) / Sum(SPD*V), using the
    peak-normalized action spectra. NOTE: this is NOT the mel-EDI/photopic-lux ratio (which is 1.0
    for D65) and NOT mel-DER; it is a raw spectral-shape indicator (D65 ~= 0.9058). Use mel_der for
    the D65-referenced melanopic measure."""
    g = _grid(spd)
    denom = sum(g[i] * V_LAMBDA[i] for i in range(401))
    return round(sum(g[i] * ACTION_MEL[i] for i in range(401)) / denom, 4) if denom else 0.0

def eml_medi_convert(value, direction):
    """Convert between Equivalent Melanopic Lux and melanopic-EDI (EML = mel-EDI * 1.103)."""
    if direction == "medi_to_eml":
        return round(value * EML_PER_MEDI, 2)
    if direction == "eml_to_medi":
        return round(value / EML_PER_MEDI, 2)
    raise ValueError("direction must be 'medi_to_eml' or 'eml_to_medi'")

# --- Exact-from-SPD alpha-opic path (no channel reconstruction) -------------
# This is the "ground truth" path that the validation §5.10 #4 check compares the channel-
# reconstruction path (alpha_opic_from_channels, which leans on the §9.3a reconstruction
# constant) against. We REUSE the verified hcl_core.alpha_opic.alpha_opic_from_spd and reshape
# its name-keyed output {s_cone:{EDI..},..} to a flat {s_edi..mel_edi} dict, so the EDIs are
# identical to the codebase's verified exact path and use the same K^D65 normalization as the
# channel path (any divergence the validation surfaces is due to channel reconstruction, not
# differing constants).
from hcl_core.alpha_opic import alpha_opic_from_spd as _ao_exact

EDI_NAME = {"s": "s_cone", "m": "m_cone", "l": "l_cone", "rhod": "rhodopic", "mel": "melanopic"}

# CORE-3 / GAP 1: a single relative-input detector reused everywhere SPD-scale matters
# (the spectral_metrics wrapper below + the alpha_opic / spectral_metrics MCP tools), so the
# peak<=1.5 heuristic lives in one place.
_RELATIVE_PEAK_MAX = 1.5
# ⚠️ This is a HINT, not a determination, and the wording must stay that way. A per-nm peak cannot
# separate absolute from normalised: real daylight at 1 nm spreads its energy over ~400 bands, so
# ABSOLUTE readings sit near 0.1-0.4 W/m2/nm — below this threshold, i.e. a real absolute spectrum
# is flagged. Integrated irradiance does not separate them either (absolute daylight readings can
# integrate to 1-139 W/m2, overlapping a normalised spectrum). So the warning reports that the
# scale is UNDECIDABLE from the numbers alone; it must never assert the input IS relative or that
# the EDIs are unusable, because on correct absolute data that tells the user to discard a correct
# answer.
_SCALE_WARNING = (
    "SPD scale is INDETERMINATE from the values alone (peak <= 1.5). This is consistent with BOTH "
    "a normalised/relative spectrum AND a genuinely absolute one — real daylight at 1 nm peaks near "
    "0.1-0.4 W/m2/nm, so a low peak is not evidence of normalisation. If the input is absolute "
    "(W/m2/nm) the *_edi values are correct lux-scale EDIs; if it is relative they are shape "
    "indicators only. The scale-invariant metrics (mel-DER, CCT, alpha-opic ratios) are unaffected "
    "either way. Confirm the units at the source.")


def spd_looks_relative(spd) -> bool:
    """True when the SPD's peak value is <= 1.5 (i.e. looks relative/normalized, not absolute
    spectral irradiance in W/m2/nm). Shared heuristic behind the scale_warning surfaced by the
    spectral_metrics wrapper and the alpha_opic / spectral_metrics MCP tools."""
    vals = parse_spd(spd).values()
    return bool(vals) and max(vals) <= _RELATIVE_PEAK_MAX


def scale_warning_for(spd):
    """Return the relative-SPD scale_warning message when `spd` looks relative, else None."""
    return _SCALE_WARNING if spd_looks_relative(spd) else None

def alpha_opic_from_spd(spd):
    """Exact alpha-opic EDIs computed directly from a full SPD (no 9-channel reconstruction).

    Returns {s_edi, m_edi, l_edi, rhod_edi, mel_edi}. Thin reshaping wrapper over the verified
    hcl_core.alpha_opic.alpha_opic_from_spd exact path (same CIE S 026 K^D65 normalization used
    by the channel path), so the validation §5.10 #4 divergence check compares like-with-like.
    """
    full = _ao_exact(spd)  # {"s_cone": {"E_alpha","ELR","EDI"}, ...}
    out = {f"{k}_edi": full[name]["EDI"] for k, name in EDI_NAME.items()}
    out["scale_warning"] = scale_warning_for(spd)
    return out
