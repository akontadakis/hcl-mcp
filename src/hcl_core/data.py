"""Verified small constants + re-exported 1-nm arrays.

Most constants are digit-for-digit from the Lark v3.0 source. A few derive
from published literature rather than Lark code; those are marked inline
(e.g. EML_PER_MEDI).
"""
from hcl_core._spectra import (  # noqa: F401  (re-exported)
    ACTION_S, ACTION_M, ACTION_L, ACTION_RHOD, ACTION_MEL,
    V_LAMBDA, D65_ELR, IPRGC_SENS_WEIGHTING,
)

# Wavelength bins (nm). Source: Convert SPD / CIE Toolbox.
BINS_9 = [[380, 419], [419, 459], [459, 499], [499, 529], [529, 558],
          [558, 587], [587, 608], [608, 630], [630, 780]]  # b1,b2,b3,g1,g2,g3,r1,r2,r3
BINS_3 = [[587, 780], [499, 587], [380, 499]]              # r,g,b (source ordering)
# 3-channel bins reordered ascending (§9.3b fix): consumed as ascending [b,g,r] bins.
# Single source for alpha_opic + spectral_reconstruct.
BINS_3_ASC = [[380, 499], [499, 587], [587, 780]]

# Grid-engine coefficient vectors. Source: 9-/3-channel circadian luminance.py.
W_PHOTOPIC_9 = [0.0003, 0.009098397, 0.055590209, 0.164071102, 0.250355905,
                0.259754249, 0.130177072, 0.081085718, 0.049591265]
W_MELANOPIC_9 = [0.0119, 0.1784, 0.4165, 0.268843, 0.1033, 0.019, 0.0017, 0.000296, 0.000061]
W_NEUROPIC_9 = [0.905130569, 0.0948, 0.000069431, 0, 0, 0, 0, 0, 0]  # grid value (see §9.2)
W_PHOTOPIC_3 = [0.265, 0.670, 0.065]
W_MELANOPIC_3 = [0.0021, 0.3911, 0.6068]

LUMINOUS_EFFICACY = 179.0  # Radiance lm/W

# Action-spectrum index per CIE S 026 alpha selector (1..5).
ALPHA_ARRAYS = {1: ACTION_S, 2: ACTION_M, 3: ACTION_L, 4: ACTION_RHOD, 5: ACTION_MEL}
ALPHA_NAMES = {1: "s_cone", 2: "m_cone", 3: "l_cone", 4: "rhodopic", 5: "melanopic"}

FOV_WEIGHTS = {"upper_inner": 2.06, "upper_outer": 1.37, "lower_inner": 0.34, "lower_outer": 0.23}

NVRD = {"EI50": 106.0, "slope": 3.55, "filters_h": (0.3, 1.7, 2.3),
        "zeff": 310.0 / 683.0 / 118.5 / 1.42 * 0.91, "timestep_h": 0.1}

# Not in Lark source -- from the "Five-Step" method (Eq. 3): EML ~= mel-EDI * 1.103.
# Staged for later plans; unused in Plan 1.
EML_PER_MEDI = 1.103
