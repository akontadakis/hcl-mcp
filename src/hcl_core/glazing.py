"""Representative glazing spectral transmittances, for deconfounding a measured SPD
that genuinely passed through glass.

⚠️ Apply this ONLY to an SPD that genuinely passed through glass. Applied to an
exterior reading it would divide out a filter that was never in the light path.

The curves are REPRESENTATIVE / parametric, used as a sensitivity BAND (clear ->
single -> double Low-E, increasing warm tilt), never as a single ground truth. Each is
renormalized so its photopic visible transmittance equals `target_vt`.

`KINDS` keeps its lowE_* members: those remain valid kinds of glazing a caller may
model.
"""
from hcl_core.data import V_LAMBDA, D65_ELR

GRID_NM = tuple(range(380, 781))            # 401 ints, aligned to V_LAMBDA / D65_ELR

# ASSUMED, NOT MEASURED. This is a stated assumption a caller may override, not a
# derived value: no transmittance measurement or product datasheet backs it. Plain
# uncoated double glazing runs nearer 0.78-0.82 photopic VT.
ASSUMED_UNCOATED_DOUBLE_VT = 0.80
KINDS = ("clear", "lowE_single", "lowE_double")


def _raw_shape(kind, wl):
    """Pre-normalization shape s(λ)∈[0,1]; red/blue tilt (warmth) rises clear<single<double."""
    t = (wl - 380) / 400.0                   # 0 at 380nm → 1 at 780nm
    if kind == "clear":        return 1.0                  # neutral float (flat)
    if kind == "lowE_single":  return 0.85 + 0.15 * t      # mild warm tilt
    if kind == "lowE_double":  return 0.70 + 0.30 * t      # strong warm tilt (spectrally selective)
    raise ValueError(f"unknown glazing kind {kind!r}; choose from {KINDS}")


def _visible_transmittance(trans):
    """Photopic VT = Σ T·D65·V / Σ D65·V (CIE visible transmittance)."""
    num = sum(t * d * v for t, d, v in zip(trans, D65_ELR, V_LAMBDA))
    den = sum(d * v for d, v in zip(D65_ELR, V_LAMBDA))
    return num / den


def transmittance(kind, target_vt=ASSUMED_UNCOATED_DOUBLE_VT):
    """401-value spectral transmittance for `kind`, scaled so VT == target_vt.

    `target_vt` defaults to an ASSUMED value (see the module docstring); it is NOT measured.
    Any result sensitive to it must state the value used.
    """
    raw = [_raw_shape(kind, wl) for wl in GRID_NM]
    k = target_vt / _visible_transmittance(raw)
    scaled = [r * k for r in raw]
    # Physical transmittance must stay <= 1. For the shipped representative curves this holds
    # with margin (peak ~0.90), so the clamp below is inert. Assert it, so any future warming of
    # `_raw_shape` that pushes a value past 1 — which would make the clamp silently distort the VT
    # normalization — fails loudly here instead of shipping a wrong VT.
    assert max(scaled) <= 1.0 + 1e-9, f"{kind}: scaled transmittance exceeds 1 — clamp would distort VT"
    return [min(1.0, v) for v in scaled]


def deconfound(spd_pairs, kind, target_vt=ASSUMED_UNCOATED_DOUBLE_VT):
    """Divide a measured (wl, value) SPD by the glazing transmittance -> the sky-side
    relative SPD (sky x instrument-response; the detector response is NOT removed).

    ⚠️ Valid only for an SPD that genuinely passed through glass. Applied to an
    outside (exterior) reading it divides out a filter that was never in the light
    path.
    """
    t = transmittance(kind, target_vt)
    out = []
    for wl, v in spd_pairs:
        i = int(round(wl)) - 380
        ti = t[i] if 0 <= i < len(t) else 1.0
        out.append((wl, v / ti if ti > 1e-6 else v))
    return out
