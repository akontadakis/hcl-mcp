"""Streaming reader for the SKYSPECTRA dataset (Zenodo 8147546, CC BY-NC-ND 4.0).

Long-format CSVs (one row per timestamp x wavelength, or x patch x wavelength). The patch file is 1.4 GB, so
everything streams: rows sharing (location, timestamp[, patch]) are contiguous, so we buffer at most one
group at a time. Raw data is git-ignored and not redistributed (download from Zenodo 8147546).
"""
import csv

GRID_NM = tuple(range(380, 781))           # 401


def to_grid(pairs):
    """Sort (wl,value) pairs and linear-interp/clip onto GRID_NM (380-780 @1nm).

    Blank / non-numeric values are dropped (the SKYSPECTRA patch file carries blank-radiance rows at some
    wavelengths); an all-blank spectrum returns zeros rather than raising."""
    pts = sorted((w, v) for w, v in ((_f(a), _f(b)) for a, b in pairs) if w is not None and v is not None)
    if not pts:
        return [0.0] * len(GRID_NM)
    xs = [w for w, _ in pts]
    ys = [v for _, v in pts]

    def interp(x):
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        lo, hi = 0, len(xs) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if xs[mid] <= x:
                lo = mid
            else:
                hi = mid
        t = (x - xs[lo]) / (xs[hi] - xs[lo])
        return ys[lo] + t * (ys[hi] - ys[lo])

    return [interp(float(wl)) for wl in GRID_NM]


def _f(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def iter_horizontal(path, location):
    """Yield (timestamp, spd_on_grid(401), cct_horizontal_or_None) per (location,timestamp), streaming."""
    with open(path, newline="") as fh:
        r = csv.DictReader(fh)
        key, pairs, cct = None, [], None
        for row in r:
            if row["location_code"] != location:
                if key is not None:
                    yield key[0], to_grid(pairs), cct
                    key, pairs, cct = None, [], None
                continue
            k = (row["timestamp"], row["measurement_setup"])
            if k != key:
                if key is not None:
                    yield key[0], to_grid(pairs), cct
                key, pairs, cct = k, [], _f(row.get("cct_horizontal"))
            pairs.append((row["wavelength"], row["spectral_horizontal_irradiance"]))
        if key is not None and pairs:
            yield key[0], to_grid(pairs), cct


def iter_patch_sets(path, location):
    """Yield (timestamp, [patch dicts]) per (location,timestamp), streaming. patch dict:
    {patch, almucantar, azimuth, cct, spd(401)}."""
    with open(path, newline="") as fh:
        r = csv.DictReader(fh)
        ts_key = None
        patches = {}          # patch_id -> {"meta":..., "pairs":[...]}
        order = []

        def flush():
            out = []
            for pid in order:
                p = patches[pid]
                out.append({"patch": int(pid), "almucantar": _f(p["alt"]), "azimuth": _f(p["az"]),
                            "cct": _f(p["cct"]), "spd": to_grid(p["pairs"])})
            return out

        for row in r:
            if row["location_code"] != location:
                continue
            ts = (row["timestamp"], row["measurement_setup"])
            if ts != ts_key:
                if ts_key is not None and patches:
                    yield ts_key[0], flush()
                ts_key, patches, order = ts, {}, []
            pid = row["patch"]
            if pid not in patches:
                patches[pid] = {"alt": row["patch_almucantar"], "az": row["patch_azimuth"],
                                "cct": row["cct_patch"], "pairs": []}
                order.append(pid)
            patches[pid]["pairs"].append((row["wavelength"], row["spectral_patch_radiance"]))
        if ts_key is not None and patches:
            yield ts_key[0], flush()


def load_meta(path):
    """Small metadata CSV -> dict keyed by (location_code, timestamp, measurement_setup)."""
    out = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            out[(row["location_code"], row["timestamp"], row.get("measurement_setup", ""))] = row
    return out
