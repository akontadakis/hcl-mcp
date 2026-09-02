"""SPD parsing & binning — faithful port of Lark 'Convert SPD' (lines 111-211)."""
import os

from hcl_core.data import BINS_9, BINS_3

MIN_A, MAX_A = 380, 780

def _read_if_path(spd):
    """If *spd* is a bare path to a readable file, return its text; else return it unchanged.

    Lets every spd-consuming MCP tool accept a `.spd` file path as well as inline text, matching
    the IES reader (ies._read_text) and the geometry importer's luminaire-SPD read. Inline SPDs are
    multi-row (contain newlines), so the no-newline guard keeps real content off the filesystem;
    a non-existent string falls through to the normal text parse (a clear "no rows" error, not
    FileNotFoundError)."""
    if isinstance(spd, str) and "\n" not in spd and os.path.isfile(spd):
        with open(spd) as fh:
            return fh.read()
    return spd

def _rows_from_text(text):
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "," in line:
            parts = line.split(",")
        elif "\t" in line:
            parts = line.split("\t")
        else:
            parts = line.split()
        if len(parts) < 2:
            continue
        try:
            rows.append((float(parts[0]), float(parts[1])))
        except ValueError:
            continue  # tolerate stray text rows
    return rows

def parse_spd(spd):
    """spd: text, a `.spd` file path, or iterable of (wavelength, value). Returns {int_nm: value} on a 1-nm grid 380..780."""
    spd = _read_if_path(spd)
    rows = _rows_from_text(spd) if isinstance(spd, str) else [(float(a), float(b)) for a, b in spd]
    lines = [[a, b] for a, b in rows if MIN_A <= a <= MAX_A]
    if not lines:
        raise ValueError("no wavelength rows in 380-780 nm range")
    lines.sort(key=lambda r: r[0])

    if len(lines) == 1:
        # A single in-range sample can't define a slope (lines[1]/lines[-2] would IndexError);
        # extend it flat to the 380/780 anchors instead of crashing.
        only_v = lines[0][1]
        if lines[0][0] > MIN_A:
            lines.insert(0, [MIN_A, only_v])
        if lines[-1][0] < MAX_A:
            lines.append([MAX_A, only_v])
    else:
        if lines[0][0] > MIN_A:
            (oa, ob), (na, nb) = lines[0], lines[1]
            grad = (nb - ob) / (na - oa)
            # clamp: linear extrapolation can dip below zero; negative irradiance is unphysical
            # and would bias alpha-opic / melanopic integrals (positive action-spectrum weights).
            lines.insert(0, [MIN_A, max(0.0, ob - grad * (oa - MIN_A))])
        if lines[-1][0] < MAX_A:
            (oa, ob), (na, nb) = lines[-2], lines[-1]
            grad = (nb - ob) / (na - oa)
            lines.append([MAX_A, max(0.0, nb + grad * (MAX_A - na))])

    new = [list(lines[0])]
    for i in range(len(lines) - 1):
        oa, ob = lines[i]
        na, nb = lines[i + 1]
        n = int(round(na - oa))
        if n <= 0:
            # Sub-integer gap collapses onto the same 1-nm node: skip the /n
            # interpolation (which would divide by zero) but still emit the
            # segment endpoint so fractional-resolution energy reaches the grid.
            new.append([na, nb])
            continue
        for k in range(n):
            new.append([oa + (na - oa) / n * (k + 1), ob + (nb - ob) / n * (k + 1)])

    # Collapse onto the integer grid (last write wins for colliding sub-integer
    # wavelengths). This snaps each sub-integer sample's energy onto its nearest
    # 1-nm node so fractional-resolution detail still reaches the grid.
    snapped = {int(round(a)): b for a, b in new}
    # Re-pin the two grid anchors to their original endpoint values: 380/780 are
    # boundary conditions and must not be displaced by a neighbouring fractional
    # row that rounds onto them.
    snapped[MIN_A] = lines[0][1]
    snapped[MAX_A] = lines[-1][1]

    # int(round()) is round-half-to-even, so for half-integer-aligned, even-spaced
    # SPDs (554.5/555.5/556.5... -> 554/556/556/558...) consecutive .5 nodes
    # collide and ODD integer keys are never emitted, leaving < 401 keys and a
    # KeyError downstream. Backfill any missing integer key in 380..780 by linear
    # interpolation between its nearest present neighbours, guaranteeing exactly
    # 401 keys. For integer-spaced inputs the collapse already fills every key, so
    # nothing is backfilled and the output is bit-identical to the old behaviour.
    present = sorted(snapped)
    grid = {}
    j = 0
    last = len(present) - 1
    for w in range(MIN_A, MAX_A + 1):
        if w in snapped:
            grid[w] = snapped[w]
            continue
        while j < last and present[j + 1] < w:
            j += 1
        wa = present[j]
        wb = present[j + 1] if j < last else wa
        va, vb = snapped[wa], snapped[wb]
        grid[w] = va if wb == wa else va + (vb - va) * (w - wa) / (wb - wa)
    return grid

def to_grid_list(spd_dict):
    """Ordered list of the 401 values for 380..780 nm."""
    return [spd_dict[w] for w in range(MIN_A, MAX_A + 1)]

def bin_average(spd_dict, channel_type):
    """channel_type: 0 -> 3 bins [r,g,b]; 1 -> 9 bins [b1..r3]. Inclusive [lo,hi] both ends
    (closed-band MEAN, not a partition). Exact: no rounding.

    The result is returned at full precision. The original Lark port rounded each band mean to 3
    decimals, which is an ABSOLUTE quantum of 5e-4 and therefore scale-dependent: harmless on the
    preset SPDs it was written for (native scale ~75-113, error 5e-4 %) but corrupting on absolute
    spectral irradiance, which is what `spectral_emit.to_channels` feeds in -- real sky/sun records
    run 0.02-1.3 W/m2/nm, and a relative luminaire SPD normalised later can sit near 0.01, where the
    worst band error reaches ~13 %. Removing the rounding is inert for every existing consumer: the
    `validation.binning_fidelity` and `tests/test_spd.py` goldens come from a linear ramp whose true
    band means are exactly representable, so they are unchanged to the digit.
    """
    if channel_type not in (0, 1):
        raise ValueError("channel_type must be 0 (3-channel) or 1 (9-channel)")
    bins = BINS_3 if channel_type == 0 else BINS_9
    out = []
    for lo, hi in bins:
        # Inclusive [lo, hi] on BOTH ends is intentional: this returns the MEAN spectral value over
        # the closed band, not a partitioned/summed total, so a sample on a shared bin edge
        # legitimately belongs to both adjacent band-means (no energy double-count). THIS is the
        # convention the §9.3a channel reconstruction is calibrated to -- that reconstruction is a
        # flat linear scalar (alpha_opic._reconstruct_irradiance), so it cannot be, and never was,
        # calibrated to the rounding precision.
        vals = [spd_dict[k] for k in spd_dict if lo <= k <= hi]
        out.append(sum(vals) / len(vals))
    return out
