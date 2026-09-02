"""Dual per-nm spectral reconstruction from Radiance channel totals (spec §5.2). Pure-Python.

Two first-class methods, both re-integrating to the per-channel bin totals:
  - faithful : flat §9.3a step-expansion + neutral sun (reuses alpha_opic.irradiance_per_nm) -> Lark 2.0.
  - reference: within each bin, scale a per-nm reference SPD R(lambda) so its bin-integral matches the
               channel total (E(lambda)=E_bin*R/∫_bin R). Sky shaped by sky_spd or a CIE D-series sky;
               sun re-colored by an air-mass direct-normal solar SPD keyed to solar_zenith.

The bin energy is ALWAYS preserved (reference only redistributes WITHIN a bin), so the reconstruction
never contradicts the Radiance transport. This is the central invariant tested in
test_spectral_reconstruct.py.
"""
from hcl_core.alpha_opic import irradiance_per_nm, alpha_opic_from_channels
from hcl_core.data import ACTION_MEL, IPRGC_SENS_WEIGHTING, BINS_9, BINS_3_ASC
from hcl_core._recon_data import solar_spd_for_zenith, dseries_spd

# 3-channel bins reordered ascending (matches alpha_opic's _BINS_3_ASC; §9.3b).
# Single source lives in hcl_core.data; alias kept for backward-compat references.
_BINS_3_ASC = BINS_3_ASC

def _bin_spans(channel_type):
    """Return [(lo_idx, hi_idx), ...] index spans into the 401-vector, matching the flat reconstruction.

    The flat reconstruction fills (hi-lo) values per bin and appends ONE final 780-nm point. So bin i
    occupies indices [lo-380, hi-380); the last bin's final index (780 -> 400) is the appended point.
    We fold that appended point into the last bin's span so re-summation covers all 401 indices.
    """
    bins = BINS_9 if channel_type == 1 else _BINS_3_ASC
    spans = []
    for k, (lo, hi) in enumerate(bins):
        lo_i, hi_i = lo - 380, hi - 380
        if k == len(bins) - 1:
            hi_i = 401  # include the appended 780-nm point
        spans.append((lo_i, hi_i))
    return spans

def _shape_within_bins(flat_vector, ref_spd, channel_type):
    """Redistribute each bin's flat energy across ref_spd's shape, preserving the bin total.

    For each bin: E(lambda) = E_bin * ref_spd(lambda) / sum_bin(ref_spd). The shape is clamped to
    non-negative first (an irradiance spectrum is physically non-negative; a mixed-sign reference with
    a positive bin-sum would otherwise leak negative per-nm values — D-18). If the clamped shape sums
    to <= 0, fall back to the flat (uniform) distribution for that bin.
    """
    out = [0.0] * 401
    for lo_i, hi_i in _bin_spans(channel_type):
        e_bin = sum(flat_vector[lo_i:hi_i])
        shape = [v if v > 0.0 else 0.0 for v in ref_spd[lo_i:hi_i]]
        s = sum(shape)
        if s <= 0:
            # uniform fallback = flat values as-is
            for i in range(lo_i, hi_i):
                out[i] = flat_vector[i]
        else:
            for j, i in enumerate(range(lo_i, hi_i)):
                out[i] = e_bin * shape[j] / s
    return out

def _sky_reference_spd(sky_spd, dseries_sky, sky_cct):
    """Pick the per-nm reference shape for the sky. An explicit (measured/physical) sky_spd wins;
    else a D-series sky from sky_cct; else a generic D65 daylight shape.

    Precedence matters: annual_nvrd(physical_sky=True, sky_reconstruction='dseries') passes BOTH a
    per-timestep physical sky_spd AND dseries_sky=True. Checking sky_spd first means physics-covered
    timesteps use the real EPW-derived sky and only uncovered timesteps (sky_spd=None) fall back to
    the D-series shape -- which is also what keeps the physical-coverage note truthful.
    """
    if sky_spd is not None:
        # sky_spd is a 401-list (already on the 380..780 grid). Accept a list directly.
        if len(sky_spd) != 401:
            raise ValueError("sky_spd must be a 401-value 380..780 nm @1 nm list")
        return list(sky_spd)
    if dseries_sky:
        if sky_cct is None:
            raise ValueError("dseries_sky=True requires sky_cct")
        return dseries_spd(sky_cct)
    # default generic clear-ish daylight sky shape (D65 CCT) when nothing supplied
    return dseries_spd(6504.0)

def _sun_reference_spd(sun_spd, solar_zenith):
    """Pick the per-nm sun reference: an explicit 401-value sun_spd, else the air-mass template."""
    if sun_spd is not None:
        if len(sun_spd) != 401:
            raise ValueError("sun_spd must be a 401-value 380..780 nm @1 nm list")
        return list(sun_spd)
    zen = 30.0 if solar_zenith is None else solar_zenith
    return solar_spd_for_zenith(zen)

def reconstruct_spectrum(sky_channels, sun_channels, channel_type, *, method="reference",
                         sky_spd=None, sun_spd=None, sun_spectral="colored", solar_zenith=None,
                         dseries_sky=False, sky_cct=None):
    """Assemble a 401-value (380..780 nm @1 nm) per-nm spectral irradiance from sky+sun channel sets.

    method='faithful': flat §9.3a reconstruction of (sky+sun); sun stays in its neutral split.
    method='reference': sky shaped by sky_spd (or D-series sky if dseries_sky), sun re-colored by an
      air-mass direct-normal solar SPD keyed to solar_zenith (sun_spectral='colored'), else flat
      (sun_spectral='neutral'). Sky+sun per-nm spectra are summed. Each bin's total is preserved.
    """
    if method == "faithful":
        summed = [s + u for s, u in zip(sky_channels, sun_channels)]
        return irradiance_per_nm(summed, channel_type)
    if method != "reference":
        raise ValueError("method must be 'faithful' or 'reference'")

    flat_sky = irradiance_per_nm(sky_channels, channel_type)
    flat_sun = irradiance_per_nm(sun_channels, channel_type)

    # Sky: shaped by the reference SPD.
    sky_ref = _sky_reference_spd(sky_spd, dseries_sky, sky_cct)
    sky_nm = _shape_within_bins(flat_sky, sky_ref, channel_type)

    # Sun: colored by air-mass solar SPD, or flat (neutral) fallback.
    if sun_spectral == "colored":
        sun_ref = _sun_reference_spd(sun_spd, solar_zenith)
        sun_nm = _shape_within_bins(flat_sun, sun_ref, channel_type)
    elif sun_spectral == "neutral":
        sun_nm = flat_sun  # flat/neutral split, sim-faithful
    else:
        raise ValueError("sun_spectral must be 'colored' or 'neutral'")

    return [sky_nm[i] + sun_nm[i] for i in range(401)]

# ---------- divergence ----------
def _mel_edi_proxy(spectrum):
    """Melanopic-EDI proxy: ∫ spectrum * melanopic action. (Relative metric for divergence %.)"""
    return sum(spectrum[i] * ACTION_MEL[i] for i in range(401))

def _i_eff_proxy(spectrum):
    """ipRGC-weighted effective irradiance proxy over 390-700 nm (indices 10..-80 = 311 pts)."""
    win = spectrum[10:-80]
    return sum(win[i] * IPRGC_SENS_WEIGHTING[i] for i in range(len(win)))

def _pct(a, b):
    """Signed percent difference of a vs b, relative to b. 0 when both ~0."""
    if abs(b) < 1e-15:
        return 0.0 if abs(a) < 1e-15 else 100.0
    return 100.0 * (a - b) / b

def reconstruction_divergence(sky_channels, sun_channels, channel_type, *, sky_spd=None,
                              solar_zenith=None, dseries_sky=False, sky_cct=None):
    """Quantify how much the reconstruction CHOICE moves the circadian metrics (spec §5.2, §5.3).

    Returns {flat_vs_reference:{mel_edi_pct,i_eff_pct}, neutral_vs_colored_sun:{mel_edi_pct,i_eff_pct}}.
    Each percentage is the ENHANCED choice relative to the simpler baseline:
    flat_vs_reference = 100*(reference - flat)/flat; neutral_vs_colored_sun = 100*(colored - neutral)/neutral.
    A positive value means the enhanced reconstruction yields the larger metric.
    """
    flat = reconstruct_spectrum(sky_channels, sun_channels, channel_type, method="faithful")
    ref = reconstruct_spectrum(sky_channels, sun_channels, channel_type, method="reference",
                               sky_spd=sky_spd, sun_spectral="colored", solar_zenith=solar_zenith,
                               dseries_sky=dseries_sky, sky_cct=sky_cct)
    sun_neu = reconstruct_spectrum(sky_channels, sun_channels, channel_type, method="reference",
                                   sky_spd=sky_spd, sun_spectral="neutral",
                                   dseries_sky=dseries_sky, sky_cct=sky_cct)
    sun_col = ref  # reference already uses colored sun
    return {
        "flat_vs_reference": {
            "mel_edi_pct": float(_pct(_mel_edi_proxy(ref), _mel_edi_proxy(flat))),
            "i_eff_pct": float(_pct(_i_eff_proxy(ref), _i_eff_proxy(flat))),
        },
        "neutral_vs_colored_sun": {
            "mel_edi_pct": float(_pct(_mel_edi_proxy(sun_col), _mel_edi_proxy(sun_neu))),
            "i_eff_pct": float(_pct(_i_eff_proxy(sun_col), _i_eff_proxy(sun_neu))),
        },
    }


def assemble_nvrd_rows(point_xyz, view_vec, timestamps, per_timestep_channels, *, method,
                       channel_type=1, sky_spd=None, sun_spd=None, sky_spd_series=None,
                       sun_spd_series=None, sun_spectral="colored",
                       solar_zenith=None, dseries_sky=False, sky_cct=None):
    """Build nvRD CSV-layout rows (one per timestep), EXACTLY matching Lark's nvRD model row layout.

    Row = [x,y,z, vx,vy,vz, month,day,hour, aopic_irrad, ELR, EDI, <401 per-nm W/m^2/nm>]  (len 413).
    Cols 9-11 are the MELANOPIC alpha-opic E/ELR/EDI (alpha=5) of the SUMMED sky+sun channels
    (alpha_opic_from_channels). Cols 12+ are the chosen 401-value reconstruction (spec §5.2).

    point_xyz, view_vec: 3-lists. timestamps: list of (month, day, hour). per_timestep_channels:
    list of (sky_channels, sun_channels) aligned with timestamps. solar_zenith may be a scalar or a
    per-timestep list (for the enhanced colored sun). sky_spd_series and sun_spd_series may each be
    a per-timestep list (entries a 401-SPD or None), overriding the scalar sky_spd/sun_spd for that row.
    """
    px, py, pz = point_xyz
    vx, vy, vz = view_vec
    rows = []
    for t, ((m, d, h), (sky_ch, sun_ch)) in enumerate(zip(timestamps, per_timestep_channels)):
        summed = [s + u for s, u in zip(sky_ch, sun_ch)]
        ao = alpha_opic_from_channels(summed, channel_type, alpha=5)  # melanopic E/ELR/EDI
        zen = solar_zenith[t] if isinstance(solar_zenith, (list, tuple)) else solar_zenith
        eff_sky = sky_spd_series[t] if sky_spd_series is not None else sky_spd
        eff_sun = sun_spd_series[t] if sun_spd_series is not None else sun_spd
        spectrum = reconstruct_spectrum(sky_ch, sun_ch, channel_type, method=method, sky_spd=eff_sky,
                                        sun_spd=eff_sun, sun_spectral=sun_spectral, solar_zenith=zen,
                                        dseries_sky=dseries_sky, sky_cct=sky_cct)
        row = [px, py, pz, vx, vy, vz, m, d, h, ao["E_alpha"], ao["ELR"], ao["EDI"], *spectrum]
        rows.append(row)
    return rows
