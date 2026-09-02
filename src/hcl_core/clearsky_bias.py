# src/hcl_core/clearsky_bias.py
"""Optional clear-sky engine-bias correction K(λ) — DEFAULT OFF / opt-in.

The clear-sky engines (SPECTRL2) run too blue. This layer multiplies the engine's clear diffuse by a
per-engine spectral warming K(λ) and renormalizes so the broadband diffuse is unchanged (shape-only).

⚠️ K(λ) is EMPIRICAL. The shipped curve was derived from an internal measured dataset that is not
published with this toolkit, against the engine's own clear prediction, both unit-area normalised. Its
derivation is not reproducible from this repo. It is applied SHAPE-ONLY, so that dataset's absolute scale
never enters the correction.

Never silently on: `enabled=False` by default, and the pipeline only applies it when explicitly
constructed enabled and passed to build_record. Inserted BEFORE the cloud modifier (architecture
invariant).
"""
import csv
import os
from hcl_core.spectral_engine.base import ClearSkySpectra
from hcl_core.cloud_modifier import broadband_integral

_ART = {"spectrl2": os.path.join(os.path.dirname(__file__), "_clearsky_K_spectrl2.csv")}


def _load(path):
    wl, k = [], []
    with open(path) as fh:
        for row in csv.reader(fh):
            if not row or row[0].lstrip().startswith("#") or row[0] == "wavelength_nm":
                continue
            wl.append(float(row[0])); k.append(float(row[1]))
    return wl, k


class ClearSkyBiasCorrection:
    name = "clearsky_bias"

    def __init__(self, engine_name="spectrl2", enabled=False):
        self.engine_name = engine_name
        self.enabled = enabled
        self._wl, self._k = _load(_ART[engine_name]) if engine_name in _ART else ([], [])

    def K(self, wl_nm):
        """Interpolated warming factor; 1.0 when disabled or outside the artifact range."""
        if not self.enabled or not self._wl or wl_nm < self._wl[0] or wl_nm > self._wl[-1]:
            return 1.0
        lo = 0
        while self._wl[lo + 1] < wl_nm:
            lo += 1
        t = (wl_nm - self._wl[lo]) / (self._wl[lo + 1] - self._wl[lo])
        return self._k[lo] + t * (self._k[lo + 1] - self._k[lo])

    def apply(self, clear):
        # No-op (and honestly reported) when disabled OR when no K(λ) artifact exists for this engine.
        if not self.enabled or not self._wl:
            return clear, {"clearsky_corrected": False, "engine": self.engine_name}
        # K(λ) is unity outside 380–780 nm, so only the visible shape is reshaped; the renorm below preserves
        # the broadband integral over the engine's FULL native range (it rescales the untouched NIR/UV too by a
        # scalar). That is fine for the colour metrics (CCT/mel-DER over 380–780): a scalar leaves visible shape
        # unchanged, and the cloud modifier re-anchors the diffuse to DHI downstream regardless.
        wl_um = [w / 1000.0 for w in clear.wavelength_nm]
        before = broadband_integral(clear.sky_diffuse_horizontal, wl_um)
        reshaped = [d * self.K(w) for w, d in zip(clear.wavelength_nm, clear.sky_diffuse_horizontal)]
        after = broadband_integral(reshaped, wl_um)
        renorm = before / after if after > 1e-12 else 1.0
        reshaped = [v * renorm for v in reshaped]
        out = ClearSkySpectra(wavelength_nm=list(clear.wavelength_nm),
                              direct_normal=list(clear.direct_normal),
                              sky_diffuse_horizontal=reshaped)
        return out, {"clearsky_corrected": True, "engine": self.engine_name,
                     "k_source": "clear_exterior_measured"}
