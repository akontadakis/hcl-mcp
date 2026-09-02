"""Parse and recombine annual .ill outputs."""
from hcl_core.metrics import circadian_metrics


def _parse_ill_header(lines):
    """Scan a Radiance matrix header. Returns (nrows, ncols, ncomp, fmt, data_start_index).

    Real dctimestep ASCII output is a Radiance matrix: an info header
    (`#?RADIANCE`, optional command/comment lines, then `NROWS=`/`NCOLS=`/`NCOMP=`/
    `FORMAT=` lines) terminated by a blank line, followed by the data block. We scan
    for the KEY=VALUE lines wherever they appear (rather than Lark's brittle fixed
    `lines[4/5/6]` offsets, which also only read the first digit of each count) and
    take the data as starting after the first blank line once a header is seen.
    Returns nrows/ncols/ncomp as ints (or None if absent), the raw `FORMAT` value
    (or None if absent) so the caller can reject non-ASCII matrices, and the 0-based
    index of the first data line (0 when there is no header at all).
    """
    nrows = ncols = ncomp = fmt = None
    header_seen = False
    data_start = None
    for idx, raw in enumerate(lines):
        s = raw.strip()
        if s.upper().startswith("#?RADIANCE"):
            header_seen = True
            continue
        if "=" in s:
            key, _, val = s.partition("=")
            key = key.strip().upper()
            val = val.strip()
            if key in ("NROWS", "NCOLS", "NCOMP", "FORMAT"):
                header_seen = True
                if key == "NROWS" and val.isdigit():
                    nrows = int(val)
                elif key == "NCOLS" and val.isdigit():
                    ncols = int(val)
                elif key == "NCOMP" and val.isdigit():
                    ncomp = int(val)
                elif key == "FORMAT":
                    fmt = val
                continue
        if header_seen and s == "":
            data_start = idx + 1
            break
    return nrows, ncols, ncomp, fmt, (data_start if data_start is not None else 0)


def parse_ill(text, sensor=0):
    """dctimestep .ill matrix -> one sensor's per-timestep [R,G,B] series.

    A real dctimestep matrix has NROWS=points, NCOLS=timesteps, NCOMP=3: each DATA
    ROW is a single sensor point, holding NCOLS RGB triplets interleaved across the
    row. (This matches Lark's own 'Read Colored Annual Results': NROWS->points, data
    after the header, each row a sensor.) So the per-timestep series for a sensor is
    that sensor's row chunked into NCOMP-sized groups -- NOT one triplet per line.

    `sensor` selects which point's series to return (default 0 -- the eye point for
    HCL studies). With no Radiance header (e.g. a hand-written single-row stream),
    the entire numeric stream is treated as one sensor's series chunked into triples.
    """
    lines = text.splitlines()
    nrows, ncols, ncomp, fmt, data_start = _parse_ill_header(lines)
    if fmt is not None and fmt.strip().lower() != "ascii":
        raise ValueError(
            f"parse_ill needs an ASCII matrix but the header declares FORMAT={fmt!r}; "
            "re-run dctimestep without binary output (ASCII) before parsing.")
    comp = ncomp or 3
    data_rows = [ln for ln in lines[data_start:] if ln.strip()]
    if not data_rows:
        return []
    if sensor >= len(data_rows):
        raise IndexError(f"sensor {sensor} out of range ({len(data_rows)} sensor row(s) in .ill)")
    vals = []
    for tok in data_rows[sensor].split():
        try:
            vals.append(float(tok))
        except ValueError:
            continue
    series = [vals[i:i + comp][:3] for i in range(0, len(vals) - comp + 1, comp)]
    return [t for t in series if len(t) == 3]

def parse_ill_matrix(text):
    """All sensor rows of a dctimestep ASCII matrix -> [n_points][n_timesteps][R,G,B].

    Same layout as parse_ill (NROWS=points, NCOLS=timesteps, NCOMP=3, interleaved RGB per
    row) but returns every sensor instead of just one. parse_ill is left untouched for the
    melanopic single-eye path.
    """
    lines = text.splitlines()
    _nrows, _ncols, ncomp, fmt, data_start = _parse_ill_header(lines)
    if fmt is not None and fmt.strip().lower() != "ascii":
        raise ValueError(
            f"parse_ill_matrix needs an ASCII matrix but the header declares FORMAT={fmt!r}; "
            "re-run dctimestep without binary output (ASCII) before parsing.")
    comp = ncomp or 3
    matrix = []
    for ln in lines[data_start:]:
        if not ln.strip():
            continue
        vals = []
        for tok in ln.split():
            try:
                vals.append(float(tok))
            except ValueError:
                continue
        series = [vals[i:i + comp][:3] for i in range(0, len(vals) - comp + 1, comp)]
        matrix.append([t for t in series if len(t) == 3])
    return matrix

def combine_sky_sun(sky_rows, sun_rows):
    """ADDITION (NOT a Lark port): total = sky-diffuse + sun-direct, element-wise per timestep.

    The Lark 'Colored Sky For Annual Irradiance' source has NO sky+sun summation component — it
    outputs resultSky and resultSun as SEPARATE .ill files by design. This is our physically-correct
    addition to produce a total irradiance time series (consistent with how spec §9.6 labels other
    additions). It is correct, not verbatim — keep it, but do not present it as a Lark port.

    Both inputs come from the same sensor row of the sky and sun .ill files, so they have equal
    length; `zip` truncates to the shorter if they ever differ (defensive, no crash).
    """
    return [[s + u for s, u in zip(sr, ur)] for sr, ur in zip(sky_rows, sun_rows)]

def recombine_annual(combined_sets, channel_type) -> list:
    """combined_sets: 1 set (3ch) or 3 sets (9ch), each a list of per-timestep [R,G,B].
    Returns per-timestep circadian metrics.

    CALLER CONTRACT (9-channel): the 3 channel-sets are concatenated per timestep in the order
    given -> [s0_R,s0_G,s0_B, s1_R,s1_G,s1_B, s2_R,s2_G,s2_B]. circadian_metrics(channel_type=1)
    expects those 9 values in W_*_9 weight order, so the caller MUST pass channel_scenes in the
    matching band order. The 3-channel path (one set) is order-trivial and pinned by test.
    """
    n_steps = len(combined_sets[0])
    out_channels = []
    for t in range(n_steps):
        row = []
        for s in combined_sets:
            row.extend(s[t])
        out_channels.append(row)
    # out_channels is always a list of per-timestep rows, so circadian_metrics returns a
    # list of metric dicts; normalize the single-row case defensively for the type checker.
    metrics = circadian_metrics(out_channels, channel_type)
    return metrics if isinstance(metrics, list) else [metrics]
