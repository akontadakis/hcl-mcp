"""Local recalibration of the SEDES1 cloud CCM from measured diffuse spectra.

Per wavelength, least-squares fit CCM(λ,Kt) = A + B·Kt + C·Kt² to the normalized shape-ratio
r = (s/∫s)/(c/∫c) of measured diffuse s vs a clear-sky reference c. Pure-Python normal equations.
"""
import csv
import math


def _solve3(m, y):
    """Solve 3x3 linear system m·x = y by Gaussian elimination. Returns None if singular."""
    a = [row[:] + [y[i]] for i, row in enumerate(m)]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-15:
            return None
        a[col], a[piv] = a[piv], a[col]
        for r in range(3):
            if r != col:
                f = a[r][col] / a[col][col]
                for k in range(col, 4):
                    a[r][k] -= f * a[col][k]
    return [a[i][3] / a[i][i] for i in range(3)]


def _quad_fit(kt, y):
    """Fit y = a + b·kt + c·kt². Returns (a, b, c, sigma). Pass-through (1,0,0,0) if <3 points."""
    n = len(kt)
    if n < 3:
        return (1.0, 0.0, 0.0, 0.0)
    S = [0.0] * 5   # Σ kt^p, p=0..4
    T = [0.0] * 3   # Σ y·kt^p, p=0..2
    for k, yy in zip(kt, y):
        p = 1.0
        for i in range(5):
            S[i] += p
            p *= k
        T[0] += yy; T[1] += yy * k; T[2] += yy * k * k
    sol = _solve3([[S[0], S[1], S[2]], [S[1], S[2], S[3]], [S[2], S[3], S[4]]], T)
    if sol is None:
        return (1.0, 0.0, 0.0, 0.0)
    a, b, c = sol
    sse = sum((yy - (a + b * k + c * k * k)) ** 2 for k, yy in zip(kt, y))
    sigma = math.sqrt(sse / (n - 3)) if n > 3 else 0.0
    return (a, b, c, sigma)


def fit_ccm(spectra, kt_values, reference_shapes, wavelength_nm):
    """spectra/reference_shapes: lists of per-λ values aligned to wavelength_nm; kt_values parallel."""
    if len(spectra) != len(kt_values):
        raise ValueError(
            f"fit_ccm: len(spectra)={len(spectra)} != len(kt_values)={len(kt_values)}"
        )
    if len(reference_shapes) != len(kt_values):
        raise ValueError(
            f"fit_ccm: len(reference_shapes)={len(reference_shapes)} != len(kt_values)={len(kt_values)}"
        )
    A, B, C, SIG = [], [], [], []
    for j in range(len(wavelength_nm)):
        xs, ys = [], []
        for i, kt in enumerate(kt_values):
            s, c = spectra[i], reference_shapes[i]
            ss, sc = sum(s), sum(c)
            if ss <= 0 or sc <= 0 or c[j] <= 0:
                continue
            ys.append((s[j] / ss) / (c[j] / sc))
            xs.append(kt)
        a, b, cc, sg = _quad_fit(xs, ys)
        A.append(a); B.append(b); C.append(cc); SIG.append(sg)
    return {"wavelength_nm": list(wavelength_nm), "A": A, "B": B, "C": C, "sigma": SIG}


def write_ccm_csv(path, fit):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["# locally-fit SEDES1 CCM(lambda,Kt)=A+B*Kt+C*Kt^2; sigma=regression std error"])
        w.writerow(["wavelength_nm", "A", "B", "C", "sigma"])
        for i, wl in enumerate(fit["wavelength_nm"]):
            w.writerow([wl, fit["A"][i], fit["B"][i], fit["C"][i], fit["sigma"][i]])


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


def load_ccm_csv(path):
    """Return (coeffs_fn: wl->(a,b,c), sigma_fn: wl->float). Pass-through (1,0,0)/0 outside range."""
    wl, A, B, C, SIG = [], [], [], [], []
    with open(path) as fh:
        for r in csv.reader(fh):
            if not r or r[0].lstrip().startswith("#") or r[0] == "wavelength_nm":
                continue
            wl.append(float(r[0])); A.append(float(r[1])); B.append(float(r[2]))
            C.append(float(r[3])); SIG.append(float(r[4]) if len(r) > 4 and r[4] != "" else 0.0)

    if not wl:
        raise ValueError(f"no data rows in CCM CSV: {path}")

    def coeffs(w):
        if w < wl[0] or w > wl[-1]:
            return (1.0, 0.0, 0.0)
        return (_interp(wl, A, w), _interp(wl, B, w), _interp(wl, C, w))

    def sigma(w):
        if w < wl[0] or w > wl[-1]:
            return 0.0
        return _interp(wl, SIG, w)

    return coeffs, sigma
