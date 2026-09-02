"""All-sky cloud bridge: energy-rescale (always) + SEDES1 spectral modifier (shape, diffuse).

Energy half forces the clear-sky spectra to match EPW broadband DNI/DHI on the full native range.
Shape half reshapes the diffuse spectrum by CCM(λ,Kt)=A+B·Kt+C·Kt² (Nann & Riordan 1991, SEDES1),
then renormalizes diffuse back to DHI so the bridge invariant is preserved.
"""
from typing import Protocol, runtime_checkable
from hcl_core.spectral_engine.base import ClearSkySpectra
from hcl_core._sedes1_data import ccm_coeffs, seed_coeffs, ccm_sigma
from hcl_core._sedes2_data import sedes2_coeffs


def normalized_global_horizontal(ghi, clear_ghi):
    """NGH = measured GHI / ESTIMATED CLEAR-SKY GHI (Whitaker 1998 Eq. 2-43).

    This is the SEDES2 independent variable and it is NOT the clearness index Kt:
    `clearness_index` above divides by the EXTRATERRESTRIAL horizontal, this divides by the
    engine's own clear-sky horizontal. Under clear sky NGH -> 1 while Kt -> ~0.7, so the two
    cannot be substituted for one another.

    Returns None when the clear-sky reference is unusable (night, or no clear-sky GHI), so a
    caller falls back to a grey CCM rather than dividing by ~0 and reshaping on noise.
    """
    if clear_ghi is None or clear_ghi <= 1e-9 or ghi is None:
        return None
    return max(0.0, min(1.5, ghi / clear_ghi))


def clearness_index(ghi, i0_normal, cos_zenith):
    """Kt = GHI / (I0_normal · cos z). 0 at/below horizon; clamped to [0, 1.2]. (SEDES1 Eq. 6)"""
    if cos_zenith <= 0.0 or i0_normal <= 0.0:
        return 0.0
    kt = ghi / (i0_normal * cos_zenith)
    return max(0.0, min(1.2, kt))


def broadband_integral(spectrum_per_um, wavelength_um):
    """Trapezoidal ∫ spectrum(λ) dλ over the native grid. Inputs W/m²/µm and µm → W/m²."""
    total = 0.0
    for i in range(len(wavelength_um) - 1):
        dw = wavelength_um[i + 1] - wavelength_um[i]
        total += 0.5 * (spectrum_per_um[i] + spectrum_per_um[i + 1]) * dw
    return total


def energy_normalize(spectra, dni, dhi):
    """Grey-scale clear-sky direct/diffuse so their FULL-range broadband integrals equal EPW DNI/DHI.

    Per-component (SEDES1 Eq. 9 neutral baseline). Returns (scaled ClearSkySpectra, info dict with
    k_dir/k_dif scale factors + clear-sky broadband integrals for provenance). Done on the native
    W/m²/µm grid BEFORE any narrowing to 380–780. (spec §5, §11 #1)
    """
    wl_um = [w / 1000.0 for w in spectra.wavelength_nm]
    clear_dni = broadband_integral(spectra.direct_normal, wl_um)
    clear_dhi = broadband_integral(spectra.sky_diffuse_horizontal, wl_um)
    k_dir = dni / clear_dni if clear_dni > 1e-9 else 0.0
    k_dif = dhi / clear_dhi if clear_dhi > 1e-9 else 0.0
    scaled = ClearSkySpectra(
        wavelength_nm=list(spectra.wavelength_nm),
        direct_normal=[v * k_dir for v in spectra.direct_normal],
        sky_diffuse_horizontal=[v * k_dif for v in spectra.sky_diffuse_horizontal],
    )
    return scaled, {"k_dir": k_dir, "k_dif": k_dif,
                    "clear_dni_bb": clear_dni, "clear_dhi_bb": clear_dhi}


@runtime_checkable
class CloudModifier(Protocol):
    name: str
    def apply(self, clear, *, dni, dhi, ghi, kt, geo): ...


class Sedes1Modifier:
    """SEDES1 (Nann & Riordan 1991): grey energy-normalize + spectral CCM reshape of the diffuse.

    variant: 'reanchored' (default) — CCM'(λ,Kt)=CCM(λ,Kt)/CCM(λ,0.70), a PURE cloud modifier (unity at
    clear Kt; the clear-sky engine bias is handled separately, see clear-sky bias layer / spec P5).
    'verbatim' — the faithful Fig.11 CCM as published (also carries a clear-sky-bias correction).
    'seed' — the legacy eyeballed 9-anchor seed (over-blues ~2×; kept for comparison).
    'local' — caller-injected coeffs/sigma (e.g. from sedes1_fit.load_ccm_csv, a locally-fitted CCM),
    reanchored the same way as 'reanchored' (unity at clear Kt); pass source=<csv path/fit metadata>
    to record the coeffs provenance.

    Provenance (in apply() info + record): ccm_variant names the variant, ccm_basis/coeff_method label
    the coefficient source honestly per variant (fig11-faithful/webplotdigitizer_fig11 for
    reanchored+verbatim, seed-9anchor/eyeballed_seed for seed, local-fit/local_recalibration for local),
    and ccm_source carries the local source string (None otherwise).
    """
    name = "sedes1"
    KT_CLEAR = 0.70

    # Per-variant provenance labels for the applied CCM: (ccm_basis, coeff_method). Keeps the
    # shipped default byte-identical while telling the truth about non-Fig.11 variants.
    _BASIS = {
        "reanchored": ("fig11-faithful", "webplotdigitizer_fig11"),
        "verbatim": ("fig11-faithful", "webplotdigitizer_fig11"),
        "seed": ("seed-9anchor", "eyeballed_seed"),
        "local": ("local-fit", "local_recalibration"),
    }

    def __init__(self, variant="reanchored", *, coeffs=None, sigma=None, source=None):
        if variant not in ("reanchored", "verbatim", "seed", "local"):
            raise ValueError(f"unknown variant {variant!r}; choose reanchored, verbatim, seed, local")
        if variant == "local" and coeffs is None:
            raise ValueError("variant='local' requires coeffs=<callable wl_nm -> (a,b,c)>")
        self.variant = variant
        self._coeffs_fn = coeffs
        self._sigma_fn = sigma or ccm_sigma
        self._source = source   # coeffs provenance: for 'local', the fitted-CSV path / fit metadata

    def _sigma_summary(self):
        s = {str(int(w)): self._sigma_fn(w) for w in (400.0, 500.0, 600.0, 700.0)}
        return s, (sum(s.values()) / len(s))

    def _ccm(self, wl_nm, kt):
        if self.variant == "seed":
            coeffs = seed_coeffs
        elif self.variant == "local":
            coeffs = self._coeffs_fn
        else:
            coeffs = ccm_coeffs
        a, b, c = coeffs(wl_nm)
        val = a + b * kt + c * kt * kt
        if self.variant in ("reanchored", "local"):
            base = a + b * self.KT_CLEAR + c * self.KT_CLEAR * self.KT_CLEAR
            val = val / base if base > 1e-6 else val
        return val

    def apply(self, clear, *, dni, dhi, ghi, kt, geo):
        scaled, info = energy_normalize(clear, dni, dhi)
        if kt is None:
            # Grey fallback (spec §13): no clearness index → CCM ≡ 1.0. The always-on energy-rescale
            # still guarantees broadband correctness; the diffuse keeps its clear-sky shape (no reshape).
            _sig, _sigm = self._sigma_summary()
            info.update({"kt": None, "ccm_applied": False, "cloud_model": "sedes1",
                         "ccm_variant": self.variant, "ccm_basis": "grey-fallback",
                         "coeff_method": "none", "ccm_source": self._source,
                         "ccm_sigma": _sig, "ccm_sigma_mean": _sigm})
            return scaled, info
        wl_um = [w / 1000.0 for w in scaled.wavelength_nm]
        reshaped = [d * max(0.0, self._ccm(w_nm, kt))
                    for w_nm, d in zip(scaled.wavelength_nm, scaled.sky_diffuse_horizontal)]
        dhi_after = broadband_integral(reshaped, wl_um)
        renorm = dhi / dhi_after if dhi_after > 1e-9 else 0.0
        reshaped = [v * renorm for v in reshaped]
        out = ClearSkySpectra(wavelength_nm=list(scaled.wavelength_nm),
                              direct_normal=scaled.direct_normal,
                              sky_diffuse_horizontal=reshaped)
        _sig, _sigm = self._sigma_summary()
        _basis, _method = self._BASIS[self.variant]
        info.update({"kt": kt, "ccm_applied": True, "cloud_model": "sedes1",
                     "ccm_variant": self.variant, "ccm_basis": _basis,
                     "coeff_method": _method, "ccm_source": self._source,
                     "ccm_sigma": _sig, "ccm_sigma_mean": _sigm})
        return out, info


class Sedes2Modifier:
    """SEDES2 (Whitaker & Newmiller 1998, NREL/SR-520-23942 Table 2-1) — OPT-IN, not default.

    The six-coefficient tabulated form of the same Nann & Riordan regression that
    `Sedes1Modifier` approximates from a digitised figure. Two structural differences, both
    of which are the REASON this is a separate class rather than a variant of SEDES1:

      CCM(λ, NGH, z) = (A1 + A2/cos z) + (B1 + B2/cos z)·NGH + (C1 + C2/cos z)·NGH²

    1. It carries a 1/cos(z) ZENITH term. SEDES1's three-term fit has no way to express
       this, so in that model the zenith dependence is absorbed into A/B/C.
    2. Its independent variable is NGH, not Kt (see `normalized_global_horizontal`).

    Because of (2) this modifier REFUSES to run on a clearness index: `apply` needs a
    clear-sky GHI reference to form NGH, and falls back to a grey (unity) CCM if it cannot,
    rather than silently evaluating the polynomial on the wrong variable.

    Nothing in `src/` constructs this. It is opt-in so every published figure computed with
    the SEDES1 default remains bit-identical; adopting it changes overcast colour and
    requires a re-run before any overcast number is re-quoted.
    """
    name = "sedes2"

    def __init__(self, *, reanchor=True):
        # `reanchor` divides by the modifier's own clear-sky value (NGH=1 at this zenith),
        # matching how the SEDES1 default is made a PURE cloud term carrying no clear-sky
        # bias of its own. Off = the coefficients exactly as tabulated.
        self.reanchor = reanchor

    def _ccm(self, wl_nm, ngh, cos_z):
        a1, a2, b1, b2, c1, c2 = sedes2_coeffs(wl_nm)
        inv = 1.0 / cos_z
        a, b, c = a1 + a2 * inv, b1 + b2 * inv, c1 + c2 * inv
        val = a + b * ngh + c * ngh * ngh
        if self.reanchor:
            base = a + b + c                      # NGH = 1 is clear sky by construction
            val = val / base if abs(base) > 1e-6 else val
        return val

    def apply(self, clear, *, dni, dhi, ghi, kt, geo, clear_ghi=None):
        scaled, info = energy_normalize(clear, dni, dhi)
        cos_z = getattr(geo, "cos_zenith", None)
        if cos_z is None:
            z = getattr(geo, "zenith_deg", None)
            if z is not None:
                import math
                cos_z = math.cos(math.radians(z))
        ngh = normalized_global_horizontal(ghi, clear_ghi)
        # Two independent ways to be unable to evaluate: no NGH reference, or the sun at/below
        # the horizon where 1/cos(z) diverges. Both take the grey path; neither guesses.
        if ngh is None or cos_z is None or cos_z <= 0.05:
            info.update({"kt": kt, "ngh": ngh, "ccm_applied": False, "cloud_model": "sedes2",
                         "ccm_variant": "reanchored" if self.reanchor else "verbatim",
                         "ccm_basis": "whitaker1998-table2-1", "coeff_method": "tabulated",
                         "ccm_source": "NREL/SR-520-23942 Table 2-1",
                         "ccm_sigma": None, "ccm_sigma_mean": None})
            return scaled, info
        wl_um = [w / 1000.0 for w in scaled.wavelength_nm]
        reshaped = [d * max(0.0, self._ccm(w_nm, ngh, cos_z))
                    for w_nm, d in zip(scaled.wavelength_nm, scaled.sky_diffuse_horizontal)]
        dhi_after = broadband_integral(reshaped, wl_um)
        renorm = dhi / dhi_after if dhi_after > 1e-9 else 0.0
        reshaped = [v * renorm for v in reshaped]
        out = ClearSkySpectra(wavelength_nm=list(scaled.wavelength_nm),
                              direct_normal=scaled.direct_normal,
                              sky_diffuse_horizontal=reshaped)
        info.update({"kt": kt, "ngh": ngh, "ccm_applied": True, "cloud_model": "sedes2",
                     "ccm_variant": "reanchored" if self.reanchor else "verbatim",
                     "ccm_basis": "whitaker1998-table2-1", "coeff_method": "tabulated",
                     "ccm_source": "NREL/SR-520-23942 Table 2-1",
                     "ccm_sigma": None, "ccm_sigma_mean": None})
        return out, info
