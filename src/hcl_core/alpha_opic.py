"""CIE S 026 alpha-opic suite. Port of Lark 'CIE Toolbox' with the two §9.3 fixes.

Two correctness notes for the *channel* path (alpha_opic_from_channels):
  - §9.3b reorders 3-channel input to ascending wavelength. This makes the
    3-channel result INTENTIONALLY DIFFER from Lark v3.0, whose 3-channel
    binning is mis-aligned (red integrated against the blue action-spectrum
    end). The port is correct; do not "restore" Lark's ordering.
  - The per-channel intensity uses the source's (179/683)*(1/107) scaling
    (§9.3a). The 1/107 factor is unexplained in the source; it cancels in
    ELR (the ratio E_alpha/E_v) and in ratios of two same-path EDIs, but it
    does NOT cancel in absolute EDI (which is proportional to E_alpha via a
    source-independent K_alpha^D65) -- so it scales the raw E_alpha AND the
    absolute EDI/mel-EDI. Treat absolute E_alpha / EDI from this path as
    unvalidated -- use alpha_opic_from_spd for physically meaningful
    absolute irradiance. (See hcl-methodology.md §6.4.)
"""
from hcl_core.data import ALPHA_ARRAYS, ALPHA_NAMES, V_LAMBDA, D65_ELR, BINS_9, BINS_3_ASC
from hcl_core.spd import parse_spd, to_grid_list

DL = 1  # wavelength step (nm); source line 79

# Optional numpy fast-path (CORE-10). colour-science depends on numpy, so it's
# normally present; the pure-Python reference (_from_irradiance_pure) stays the
# source of truth and is used when numpy is absent.
try:
    import numpy as _np
    _V_NP = _np.asarray(V_LAMBDA, dtype=float)
    _D65_NP = _np.asarray(D65_ELR, dtype=float)
    _ALPHA_NP = {a: _np.asarray(ALPHA_ARRAYS[a], dtype=float) for a in ALPHA_ARRAYS}
except Exception:  # pragma: no cover - numpy is a hard transitive dep
    _np = None

# 9-channel bins are ascending. 3-channel: reorder [r,g,b] -> ascending [b,g,r] (§9.3b fix).
# Single source lives in hcl_core.data; alias kept for backward-compat references.
_BINS_3_ASC = BINS_3_ASC

def _reconstruct_irradiance(channels, channel_type):
    """Spread each channel flat across its bin -> 401 per-nm values (380..780).

    §9.3a: float division (the source's (179/683)*(1/107) integer-divides to 0).
    """
    if channel_type not in (0, 1):
        raise ValueError("channel_type must be 0 (3-channel) or 1 (9-channel)")
    if channel_type == 1:
        if len(channels) != 9:
            raise ValueError("9-channel alpha-opic needs 9 values")
        vals, bins = list(channels), BINS_9
    else:
        if len(channels) != 3:
            raise ValueError("3-channel alpha-opic needs 3 values [r,g,b]")
        r, g, b = channels
        vals, bins = [b, g, r], _BINS_3_ASC  # ascending order
    intensity = [(179.0 / 683.0) * (1.0 / 107.0) * v for v in vals]
    irrad = []
    for i, (lo, hi) in enumerate(bins):
        irrad += [intensity[i]] * (hi - lo)
    irrad.append(intensity[-1])  # the 780 nm point
    assert len(irrad) == 401
    return irrad

def irradiance_per_nm(channels, channel_type):
    """Public 401-value (380..780 nm @1 nm) flat reconstruction of per-channel irradiance.

    This is the §9.3a-corrected flat step-expansion (I=(179/683)*(1/107)*channel held constant
    across each bin) — the exact Lark 2.0 CIE-Toolbox method (base spec §5.4). Exposed for the
    annual->nvRD bridge's `faithful` reconstruction (spec §5.2). Delegates to the existing
    private reconstruction so the two never diverge.
    """
    return _reconstruct_irradiance(channels, channel_type)

def _from_irradiance_pure(irrad, alpha):
    """Core CIE S 026 integrals for one alpha selector (1..5). Pure-Python reference."""
    action = ALPHA_ARRAYS[alpha]
    e_alpha = sum(irrad[i] * action[i] * DL for i in range(401))
    e_v = 683 * sum(irrad[i] * V_LAMBDA[i] * DL for i in range(401))
    elr = (e_alpha / e_v) * 1000 if e_v else 0.0
    d65_a = sum(D65_ELR[i] * action[i] * DL for i in range(401))
    d65_v = 683 * sum(D65_ELR[i] * V_LAMBDA[i] * DL for i in range(401))
    k_d65 = (d65_a / d65_v) * 1000  # D65 alpha-opic ELR (mW/lm)
    edi = (e_alpha * 1000) / k_d65 if e_alpha else 0.0
    return {"E_alpha": round(e_alpha, 6), "ELR": round(elr, 4), "EDI": round(edi, 4)}


def _from_irradiance(irrad, alpha):
    """Core CIE S 026 integrals for one alpha selector (1..5).

    numpy fast-path when available (CORE-10), else the pure-Python reference.
    Both apply the SAME rounding, which absorbs sub-ULP np.dot-vs-sum differences,
    so results are identical to _from_irradiance_pure (parity-tested).
    """
    if _np is None:
        return _from_irradiance_pure(irrad, alpha)
    action = _ALPHA_NP[alpha]
    irr = _np.asarray(irrad, dtype=float)
    e_alpha = float(_np.dot(irr, action)) * DL
    e_v = 683 * float(_np.dot(irr, _V_NP)) * DL
    elr = (e_alpha / e_v) * 1000 if e_v else 0.0
    d65_a = float(_np.dot(_D65_NP, action)) * DL
    d65_v = 683 * float(_np.dot(_D65_NP, _V_NP)) * DL
    k_d65 = (d65_a / d65_v) * 1000  # D65 alpha-opic ELR (mW/lm)
    edi = (e_alpha * 1000) / k_d65 if e_alpha else 0.0
    return {"E_alpha": round(e_alpha, 6), "ELR": round(elr, 4), "EDI": round(edi, 4)}

def alpha_opic_from_channels(channels, channel_type, alpha=None) -> dict:
    """alpha: 1=S,2=M,3=L,4=rhod,5=mel; None -> all five (keyed by name).

    9-channel recommended. ELR/EDI are robust; raw E_alpha is scaled by the
    source's unvalidated 1/107 factor (see module docstring) -- prefer
    alpha_opic_from_spd when you need absolute E_alpha.
    """
    irrad = _reconstruct_irradiance(channels, channel_type)
    if alpha is None:
        return {ALPHA_NAMES[a]: _from_irradiance(irrad, a) for a in range(1, 6)}
    return _from_irradiance(irrad, alpha)

def alpha_opic_from_spd(spd, alpha=None) -> dict:
    """Exact CIE S 026 from a full spectral irradiance distribution (no bin reconstruction).

    spd: text or iterable of (wavelength, value). The gold-standard path (§5.4):
    no 1/107 scaling, so absolute E_alpha is physically meaningful.
    """
    irrad = to_grid_list(parse_spd(spd))  # 401 values, 380..780 nm
    if alpha is None:
        return {ALPHA_NAMES[a]: _from_irradiance(irrad, a) for a in range(1, 6)}
    return _from_irradiance(irrad, alpha)
