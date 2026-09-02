"""SEDES2 cloud-cover modifier coefficients — TABULATED, not figure-digitised.

The SEDES1 coefficients this package has shipped until now were recovered by
WebPlotDigitizer from Nann & Riordan (1991) Fig. 11, because that paper plots the curves
without tabulating them. A tabulation of the same regression DOES exist and was simply not
found earlier:

    Whitaker, C.M. & Newmiller, J.D. (1998), "Photovoltaic Module Energy Rating Procedure
    — Final Subcontract Report", NREL/SR-520-23942, Table 2-1, pp. 19-20.
    https://docs.nrel.gov/docs/legosti/old/23942.pdf

whose own text states the coefficients "were derived from measured data using statistical
analyses as described by Nann and Riordan, 1991". A US Government contractor report,
distributed without copyright restriction.

TWO STRUCTURAL DIFFERENCES from the SEDES1 form in `_sedes1_data.py`, both verified against
the primary PDF rather than a secondary description. They are why this is a SEPARATE model
and not a coefficient swap:

1. SIX coefficients, not three — the model carries a 1/cos(z) zenith term (report Eq. 2-39):

       CCM(λ, NGH, z) = (A1 + A2/cos z) + (B1 + B2/cos z)·NGH + (C1 + C2/cos z)·NGH²

   A three-term A+B·Kt+C·Kt² fit has no way to represent this; the zenith dependence is
   absorbed into the other terms.

2. The independent variable is NGH, NOT the Liu-Jordan clearness index Kt (report Eq. 2-43):

       NGH = H_H,meas / (H_s,H,est + H_d,est · cos z)

   i.e. measured broadband global horizontal over the ESTIMATED CLEAR-SKY global
   horizontal. Kt divides by the EXTRATERRESTRIAL horizontal instead. Feeding Kt where the
   model expects NGH silently evaluates the polynomial off its fitted domain — near clear
   sky NGH → 1 while Kt → ~0.7, so the two are not even approximately interchangeable.

⚠ The 1040 nm and 1050 nm rows are BYTE-IDENTICAL in Table 2-1. Verified present in the
source PDF itself, not a transcription artefact — the terminal row is duplicated, so the
last 10 nm carries no independent information.

The table spans 320-1050 nm at 10 nm. The 380-780 nm visible window this package cares
about sits inside it, so no extrapolation is needed there; `_interp` clamps at both ends
for callers who ask outside.

Transcribed from the primary PDF 2026-08-06. The committed CSV that this table is checked
against is `tests/fixtures/sedes2_ccm_coefficients.csv` (test_sedes2.py); the full provenance
record lives with the open-data sources outside this repository.
"""

# wavelength_nm: (A1, A2, B1, B2, C1, C2)
SEDES2_COEFFS = {
    320: (1.285724, 0.306791, -0.29613, -0.58516, 0.020632, 0.209150),
    330: (1.235103, 0.262007, -0.28377, -0.53864, 0.010728, 0.206493),
    340: (1.206166, 0.250204, -0.25258, -0.51989, 0.004315, 0.204614),
    350: (1.139737, 0.242676, -0.19222, -0.49821, -0.011840, 0.201329),
    360: (1.091643, 0.244214, -0.13386, -0.48722, -0.027200, 0.200767),
    370: (1.033731, 0.251496, -0.07915, -0.48133, -0.042850, 0.202966),
    380: (0.997179, 0.243862, -0.06550, -0.45039, -0.036070, 0.191915),
    390: (0.997948, 0.227502, -0.08976, -0.40715, -0.010390, 0.173710),
    400: (0.990572, 0.205403, -0.12091, -0.35735, 0.018082, 0.152083),
    410: (0.984024, 0.193105, -0.13671, -0.32748, 0.034395, 0.140702),
    420: (0.971385, 0.177868, -0.15584, -0.29288, 0.051752, 0.127548),
    430: (0.976450, 0.159398, -0.18434, -0.25421, 0.072127, 0.112706),
    440: (0.973204, 0.142079, -0.20773, -0.21836, 0.088689, 0.098569),
    450: (0.979785, 0.129315, -0.22806, -0.19197, 0.103365, 0.087170),
    460: (0.985780, 0.119208, -0.24438, -0.17140, 0.117445, 0.076708),
    470: (0.998610, 0.109176, -0.26163, -0.15113, 0.132599, 0.066066),
    480: (1.005317, 0.099677, -0.27866, -0.13004, 0.147219, 0.055762),
    490: (1.019677, 0.089575, -0.30482, -0.10709, 0.166260, 0.045127),
    500: (1.024404, 0.080517, -0.32229, -0.08750, 0.179513, 0.036474),
    510: (1.031585, 0.069067, -0.34795, -0.06441, 0.196865, 0.025472),
    520: (1.049367, 0.056443, -0.38233, -0.04055, 0.218811, 0.013729),
    530: (1.063939, 0.046316, -0.40907, -0.02121, 0.236117, 0.004201),
    540: (1.071553, 0.038300, -0.42769, -0.00587, 0.248413, -0.002990),
    550: (1.070387, 0.031852, -0.43045, 0.004491, 0.251829, -0.007680),
    560: (1.062834, 0.026342, -0.41879, 0.011999, 0.246651, -0.010460),
    570: (1.045843, 0.024689, -0.37226, 0.009432, 0.223078, -0.008010),
    580: (1.037469, 0.023472, -0.33927, 0.008971, 0.207507, -0.006900),
    590: (1.026083, 0.023298, -0.31410, 0.008151, 0.195734, -0.005180),
    600: (1.040383, 0.015681, -0.34917, 0.024337, 0.218887, -0.014260),
    610: (1.050820, 0.006659, -0.38518, 0.041762, 0.241564, -0.024110),
    620: (1.051636, 0.000294, -0.39171, 0.051032, 0.246386, -0.029020),
    630: (1.040294, -0.002640, -0.36449, 0.050866, 0.230633, -0.027690),
    640: (1.040910, -0.002430, -0.35577, 0.051709, 0.225536, -0.026530),
    650: (1.040678, -0.003160, -0.34746, 0.053757, 0.221069, -0.026110),
    660: (1.065054, -0.007750, -0.38644, 0.068596, 0.246247, -0.034700),
    670: (1.081709, -0.010200, -0.40061, 0.077291, 0.257483, -0.040340),
    680: (1.077241, -0.006970, -0.36968, 0.071587, 0.240555, -0.037160),
    690: (1.040409, -0.004130, -0.28523, 0.052308, 0.187536, -0.024550),
    700: (1.016405, -0.000670, -0.23359, 0.036039, 0.150176, -0.012270),
    710: (1.006519, -0.004160, -0.21335, 0.030742, 0.130581, -0.007250),
    720: (1.015005, -0.009860, -0.20643, 0.033451, 0.120013, -0.007090),
    730: (1.112120, -0.039850, -0.37030, 0.086799, 0.198931, -0.035060),
    740: (1.259638, -0.079380, -0.63633, 0.167885, 0.336038, -0.080230),
    750: (1.359701, -0.106810, -0.82757, 0.227298, 0.435026, -0.114110),
    760: (1.364134, -0.108860, -0.84101, 0.233641, 0.440063, -0.119070),
    770: (1.413504, -0.124910, -0.91952, 0.262684, 0.480399, -0.134970),
    780: (1.472111, -0.143780, -1.00406, 0.291321, 0.524579, -0.149180),
    790: (1.460142, -0.142480, -0.96339, 0.280995, 0.499939, -0.141490),
    800: (1.397082, -0.126130, -0.83251, 0.242547, 0.428312, -0.118920),
    810: (1.303223, -0.098120, -0.64065, 0.184689, 0.325405, -0.086460),
    820: (1.231193, -0.083470, -0.50422, 0.149742, 0.253542, -0.066610),
    830: (1.278968, -0.098010, -0.59564, 0.179143, 0.301940, -0.082880),
    840: (1.394604, -0.129990, -0.82226, 0.248595, 0.424660, -0.122620),
    850: (1.486840, -0.157670, -1.02211, 0.309727, 0.533828, -0.158110),
    860: (1.533058, -0.173320, -1.12535, 0.343352, 0.589583, -0.177380),
    870: (1.548420, -0.176910, -1.14042, 0.350555, 0.597075, -0.181380),
    880: (1.509161, -0.162710, -1.02979, 0.319605, 0.536668, -0.163600),
    890: (1.398192, -0.124700, -0.77108, 0.242984, 0.400871, -0.121500),
    900: (1.176119, -0.068240, -0.34215, 0.120864, 0.176265, -0.053490),
    910: (0.986845, -0.013150, 0.01589, 0.015608, -0.007840, 0.003255),
    920: (0.830406, 0.031590, 0.284686, -0.06127, -0.140190, 0.042905),
    930: (0.611229, 0.097008, 0.607703, -0.15086, -0.281580, 0.082580),
    940: (0.369127, 0.137444, 0.920399, -0.22796, -0.428360, 0.122108),
    950: (0.306382, 0.132255, 1.017929, -0.25108, -0.506190, 0.144856),
    960: (0.427639, 0.084802, 0.857880, -0.20327, -0.469870, 0.132757),
    970: (0.650115, 0.034501, 0.600522, -0.12507, -0.371260, 0.097659),
    980: (0.843689, -0.014110, 0.352464, -0.04375, -0.265760, 0.058199),
    990: (1.018712, -0.055840, 0.115209, 0.032978, -0.160690, 0.019510),
    1000: (1.110714, -0.082420, -0.02662, 0.081820, -0.097320, -0.005070),
    1010: (1.158305, -0.098450, -0.10842, 0.111704, -0.059800, -0.020130),
    1020: (1.187785, -0.109710, -0.17215, 0.134360, -0.026170, -0.032360),
    1030: (1.216623, -0.120390, -0.24681, 0.157773, 0.018206, -0.046350),
    1040: (1.242954, -0.130070, -0.32480, 0.179514, 0.068458, -0.060710),
    # ⚠ identical to 1040 in the source table - a duplicated terminal row, not a typo here.
    1050: (1.242954, -0.130070, -0.32480, 0.179514, 0.068458, -0.060710),
}

_GRID = tuple(sorted(SEDES2_COEFFS))
FIRST_NM, LAST_NM = _GRID[0], _GRID[-1]


def sedes2_coeffs(wl_nm):
    """(A1, A2, B1, B2, C1, C2) at `wl_nm`, linearly interpolated on the 10 nm table.

    Clamped outside 320-1050 nm rather than extrapolated: a 6-coefficient polynomial
    extrapolated past its fitted range produces confident nonsense, and every wavelength
    this package integrates over (380-780 nm) is inside the table anyway.
    """
    if wl_nm <= FIRST_NM:
        return SEDES2_COEFFS[FIRST_NM]
    if wl_nm >= LAST_NM:
        return SEDES2_COEFFS[LAST_NM]
    lo = int(wl_nm // 10 * 10)
    hi = lo + 10
    if lo == wl_nm:
        return SEDES2_COEFFS[lo]
    a, b = SEDES2_COEFFS[lo], SEDES2_COEFFS[hi]
    t = (wl_nm - lo) / 10.0
    return tuple(x + t * (y - x) for x, y in zip(a, b))
