"""SEDES1 CCM coefficients CCM(λ,Kt) = A(λ) + B(λ)·Kt + C(λ)·Kt².

PRIMARY (default) = the FAITHFUL Fig.11 digitization (human-in-the-loop WebPlotDigitizer,
A/B/C + σ on a 10nm grid 330–1100nm), bundled here as `_sedes1_fig11.csv`. The legacy eyeballed
9-anchor SEED is retained (`seed_coeffs`) for the 'seed' variant. The seed over-blued the cloudy
sky ~2× (verified): seed B(400)=-3.55 vs faithful -2.04. See methodology §8.6.

⚠ A TABULATED alternative to this digitisation exists — see `_sedes2_data.py`. Whitaker &
Newmiller (1998), NREL/SR-520-23942 Table 2-1 publishes 74 rows of the same Nann & Riordan
regression, so the coefficients here need not have been read off a figure. It is NOT a
drop-in replacement: that model has SIX coefficients with a 1/cos(z) zenith term and is driven
by NGH (measured ÷ estimated-clear-sky global horizontal), not by Kt. Swapping the numbers
alone would silently evaluate a different model. `Sedes2Modifier` implements it opt-in; this
module remains the shipped default so published figures stay reproducible.
"""
import csv
import os

# --- legacy eyeballed 9-anchor seed (retained for the 'seed' variant) ---
SEED_WL_NM = [350.0, 400.0, 450.0, 500.0, 600.0, 700.0, 800.0, 950.0, 1050.0]
SEED_A = [2.56389, 2.34167, 1.89444, 1.60278, 1.31111, 1.13222, 1.015, 0.65833, 0.88444]
SEED_B = [-3.78333, -3.55, -2.36667, -1.71667, -1.06667, -0.59333, -0.19, 0.65, 0.15333]
SEED_C = [2.11111, 2.33333, 1.55556, 1.22222, 0.88889, 0.57778, 0.2, -0.33333, -0.04444]

# --- faithful Fig.11 digitization (primary source of truth) ---
_CSV = os.path.join(os.path.dirname(__file__), "_sedes1_fig11.csv")
FIG11_WL, FIG11_A, FIG11_B, FIG11_C, FIG11_SIGMA = [], [], [], [], []
with open(_CSV) as _fh:
    for _r in csv.reader(_fh):
        if not _r or _r[0].lstrip().startswith("#") or _r[0] == "wavelength_nm":
            continue
        if _r[1].strip() == "" or _r[2].strip() == "" or _r[3].strip() == "":   # need A,B,C all present
            continue
        FIG11_WL.append(float(_r[0])); FIG11_A.append(float(_r[1]))
        FIG11_B.append(float(_r[2])); FIG11_C.append(float(_r[3]))
        FIG11_SIGMA.append(float(_r[4]) if len(_r) > 4 and _r[4] != "" else 0.0)


def _interp(grid, ys, wl):
    if wl <= grid[0]:
        return ys[0]
    if wl >= grid[-1]:
        return ys[-1]
    lo = 0
    while grid[lo + 1] < wl:
        lo += 1
    t = (wl - grid[lo]) / (grid[lo + 1] - grid[lo])
    return ys[lo] + t * (ys[lo + 1] - ys[lo])


def ccm_coeffs(wl_nm):
    """Faithful Fig.11 (A,B,C) at wl_nm (verbatim). Pass-through (1,0,0) outside 330–1100nm."""
    if wl_nm < FIG11_WL[0] or wl_nm > FIG11_WL[-1]:
        return (1.0, 0.0, 0.0)
    return (_interp(FIG11_WL, FIG11_A, wl_nm),
            _interp(FIG11_WL, FIG11_B, wl_nm),
            _interp(FIG11_WL, FIG11_C, wl_nm))


def ccm_sigma(wl_nm):
    """Fig.11 regression standard error σ(λ); 0.0 outside the digitized range."""
    if wl_nm < FIG11_WL[0] or wl_nm > FIG11_WL[-1]:
        return 0.0
    return _interp(FIG11_WL, FIG11_SIGMA, wl_nm)


def seed_coeffs(wl_nm):
    """Legacy eyeballed 9-anchor seed (A,B,C) — for the 'seed' variant only."""
    return (_interp(SEED_WL_NM, SEED_A, wl_nm),
            _interp(SEED_WL_NM, SEED_B, wl_nm),
            _interp(SEED_WL_NM, SEED_C, wl_nm))
