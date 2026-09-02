"""Annual circadian dosimetry over a melanopic-EDI time series (pure-Python)."""

def _nominal_step_hours(hoy, step_hours=None):
    """Each sample's own interval length, in hours.

    Explicit `step_hours` (from the run's timestep) wins. Otherwise infer it as the MODAL
    positive gap, which is robust to the gaps that bound each occupied block: a daylit-hours-only
    series is mostly nominal steps plus one large gap per day, so the most frequent gap is the
    nominal step while the mean or the max would be skewed by the gaps.

    The mode, not the median. On the block-gap case above the two agree, so the difference only
    shows on an EVEN-length gap list, where the median averages the two middle values and can
    return a duration no sample actually had: gaps [1, 1, 2, 2] give median 1.5 h, an interval
    that never occurred, where the mode gives 1 h. Every value this returns is an interval the
    series really contained.
    """
    if step_hours is not None:
        return float(step_hours)
    gaps = [hoy[i + 1] - hoy[i] for i in range(len(hoy) - 1) if hoy[i + 1] > hoy[i]]
    if not gaps:
        return 1.0                                   # single sample / no usable spacing
    # The MODAL gap: a real timestep recurs once per sample, while block/overnight/inter-month
    # gaps appear at most once per block, so the most frequent gap is the nominal step. Ties break
    # to the smaller gap (a block gap never outnumbers the steps it separates).
    from collections import Counter
    counts = Counter(gaps)
    return float(min(counts, key=lambda g: (-counts[g], g)))


def hours_above_threshold(medi_series, hoy, threshold=250.0, *, step_hours=None):
    """Total hours where mel-EDI >= threshold.

    Each qualifying sample contributes its own timestep, NOT the gap to the next sample. A
    forward difference `hoy[i+1]-hoy[i]` is only correct on a contiguous series: on the
    daylit-hours-only / multi-month windows `hcl_core.weather.decompose` produces, the last
    sample of every block would absorb the whole non-occupied gap (an 08:00-18:00 three-day
    window read 59 h instead of 33 h; a Jun-Aug window read 1475 h instead of 33 h, because
    `decompose` repeats a fixed day/hour window across months).

    So the duration is the nominal step (`step_hours`, else the modal positive gap), clamped
    by the actual forward gap so a genuinely shorter final interval is never over-counted. This
    matches `hcl_core.daylight_metrics.annual_sunlight_exposure`, which takes an explicit
    `step_hours` and is gap-immune by construction.
    """
    if len(medi_series) != len(hoy):
        raise ValueError("medi_series and hoy must be the same length")
    nominal = _nominal_step_hours(hoy, step_hours)
    total = 0.0
    for i, m in enumerate(medi_series):
        if m >= threshold:
            d = nominal
            if i + 1 < len(hoy):
                fwd = hoy[i + 1] - hoy[i]
                if 0.0 < fwd < d:
                    d = fwd                          # a short tail interval, not a block gap
            total += d
    return round(total, 4)

def daily_profile(medi_series, days):
    """Group mel-EDI values by day number -> {day: [values...]}."""
    prof = {}
    for m, d in zip(medi_series, days):
        prof.setdefault(d, []).append(m)
    return prof

def dose_summary(medi_series, hoy, threshold=250.0, *, step_hours=None):
    """Compact summary: hours_above (>= threshold), mean, max, n.

    `medi_series` must be CIE S 026 mel-EDI (lx). Do NOT pass `melanopic_lux` — it is larger by
    D65's own melanopic/photopic ratio (1.0997x on the 9-bin route), so it would silently relax
    the threshold. See `hcl_core.metrics._with_mel_edi`.
    """
    n = len(medi_series)
    return {"n": n, "threshold": threshold,
            "hours_above": hours_above_threshold(medi_series, hoy, threshold,
                                                 step_hours=step_hours),
            "mean": (sum(medi_series) / n) if n else 0.0,
            "max": max(medi_series) if n else 0.0}
